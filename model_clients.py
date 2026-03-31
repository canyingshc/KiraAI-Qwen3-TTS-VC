import time
import asyncio
import base64
import threading
import io
import wave
import os
import uuid as _uuid
from typing import Optional

from core.provider import ModelInfo, TTSModelClient
from core.chat.message_elements import Record
from core.logging_manager import get_logger

logger = get_logger("provider", "purple")


class DashscopeTTSClient(TTSModelClient):
    """
    Dashscope Qwen TTS Realtime — 声音复刻语音合成

    provider_config:
        api_key    : str  — Dashscope API Key

    model_config:
        voice_id   : str  — 已注册的复刻音色 ID（必填）
        ws_url     : str  — WebSocket 地址（可选，默认北京）
        timeout    : int  — 超时秒数（可选，默认 120）

    model_id 示例: qwen3-tts-vc-realtime-2026-01-15

    返回: Record 对象（内含临时 WAV 文件路径）
    """

    def __init__(self, model: ModelInfo):
        super().__init__(model)

    async def text_to_speech(self, text: str, **kwargs) -> Record:
        """
        合成语音，保存为临时 WAV 文件，返回 Record 对象。
        """
        # ---- 延迟导入 dashscope ----
        try:
            import dashscope
            from dashscope.audio.qwen_tts_realtime import (
                QwenTtsRealtime,
                QwenTtsRealtimeCallback,
                AudioFormat,
            )
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install: pip install dashscope"
            )

        # ---- 读取配置 ----
        api_key = self.model.provider_config.get("api_key", "")
        voice_id = (
            self.model.model_config.get("voice_id", "")
            if self.model.model_config else ""
        )
        ws_url = (
            self.model.model_config.get(
                "ws_url",
                "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
            )
            if self.model.model_config
            else "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )
        timeout_sec = (
            self.model.model_config.get("timeout", 120)
            if self.model.model_config else 120
        )

        if not voice_id:
            raise ValueError("[TTS] voice_id is required in model_config")
        if not api_key:
            raise ValueError("[TTS] api_key is required in provider_config")

        dashscope.api_key = api_key

        # ---- 共享容器 ----
        audio_chunks: list[bytes] = []
        error_holder: list[Optional[str]] = [None]
        done_event = threading.Event()

        # ---- 回调：收集音频帧 ----
        class _Collector(QwenTtsRealtimeCallback):
            def on_open(self_cb) -> None:
                logger.info("[TTS] WebSocket connected")

            def on_close(self_cb, code, msg) -> None:
                logger.info(f"[TTS] WebSocket closed: code={code} msg={msg}")
                done_event.set()

            def on_event(self_cb, response: dict) -> None:
                try:
                    evt = response.get("type", "")
                    if evt == "response.audio.delta":
                        audio_chunks.append(
                            base64.b64decode(response["delta"])
                        )
                    elif evt == "session.finished":
                        logger.info("[TTS] Session finished")
                        done_event.set()
                    elif evt == "error":
                        err_msg = (
                            response.get("error", {})
                            .get("message", str(response))
                        )
                        logger.error(f"[TTS] Server error: {err_msg}")
                        error_holder[0] = err_msg
                        done_event.set()
                except Exception as exc:
                    logger.error(f"[TTS] Callback exception: {exc}")
                    error_holder[0] = str(exc)
                    done_event.set()

        # ---- 同步合成（在线程中跑） ----
        def _run_sync():
            try:
                logger.info(
                    f"[TTS] Connecting to {ws_url}, "
                    f"model={self.model.model_id}"
                )
                tts = QwenTtsRealtime(
                    model=self.model.model_id,
                    callback=_Collector(),
                    url=ws_url,
                )
                tts.connect()

                logger.info(
                    f"[TTS] Session update: voice_id={voice_id}"
                )
                tts.update_session(
                    voice=voice_id,
                    response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                    mode="server_commit",
                )

                # 按行分块发送
                lines = [l for l in text.split("\n") if l.strip()]
                if not lines:
                    lines = [text]
                for chunk in lines:
                    logger.debug(f"[TTS] Sending: {chunk[:50]}...")
                    tts.append_text(chunk)
                    time.sleep(0.05)

                tts.finish()
                logger.info("[TTS] finish() called, waiting...")

                if not done_event.wait(timeout=timeout_sec):
                    error_holder[0] = (
                        f"TTS timed out after {timeout_sec}s"
                    )
                    logger.error(error_holder[0])

            except Exception as exc:
                error_holder[0] = str(exc)
                logger.error(f"[TTS] Thread exception: {exc}")
                done_event.set()

        # ---- 在线程池执行，不阻塞事件循环 ----
        logger.info(f"[TTS] Starting synthesis for {len(text)} chars")
        await asyncio.to_thread(_run_sync)

        if error_holder[0]:
            raise RuntimeError(f"TTS failed: {error_holder[0]}")

        pcm_data = b"".join(audio_chunks)
        if not pcm_data:
            raise RuntimeError("TTS returned empty audio")

        # ---- PCM → WAV → 临时文件 ----
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_data)
        wav_bytes = wav_buf.getvalue()

        # 使用项目的 data/temp 目录
        try:
            from core.utils.path_utils import get_data_path
            temp_dir = os.path.join(str(get_data_path()), "temp")
        except ImportError:
            temp_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "data", "temp"
            )
        os.makedirs(temp_dir, exist_ok=True)

        filename = f"tts_{_uuid.uuid4().hex[:12]}.wav"
        file_path = os.path.join(temp_dir, filename)

        with open(file_path, "wb") as f:
            f.write(wav_bytes)

        duration = len(pcm_data) / 48000
        logger.info(
            f"[TTS] Done: {len(pcm_data)} PCM → {len(wav_bytes)} WAV "
            f"(~{duration:.1f}s), saved: {file_path}"
        )

        # ---- 返回 Record 对象 ----
        record = Record(
            record=file_path,
            mime="audio/wav",
            name=filename,
        )
        return record