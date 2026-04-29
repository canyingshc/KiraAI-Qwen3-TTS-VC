"""
Dashscope Qwen TTS — 四模式语音合成

支持模式:vc          Voice Clone, HTTP (MultiModalConversation)
  vc-realtime Voice Clone, WebSocket 实时
  vd          Voice Design, WebSocket
  vd-realtime Voice Design, WebSocket 实时

model_id 示例:
  vc:qwen3-tts-vc-2026-01-22
  vc-realtime: qwen3-tts-vc-realtime-2026-01-15
  vd:          qwen3-tts-vd-2026-01-26
  vd-realtime: qwen3-tts-vd-realtime-2026-01-15
"""

from __future__ import annotations

import asyncio
import base64
import glob
import io
import os
import threading
import time
import uuid as _uuid
import wave
from typing import Optional

from core.provider import ModelInfo, TTSModelClient
from core.chat.message_elements import Record
from core.logging_manager import get_logger

logger = get_logger("dashscope_tts", "purple")

# ──────────────────────────── 工具函数 ────────────────────────────

def _get_temp_dir() -> str:
    """获取临时文件目录"""
    try:
        from core.utils.path_utils import get_data_path
        temp_dir = os.path.join(str(get_data_path()), "temp")
    except ImportError:
        temp_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "data", "temp"
        )
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def _cleanup_temp_files(max_age_seconds: int = 3600):
    """清理超过 max_age 的临时音频文件"""
    try:
        temp_dir = _get_temp_dir()
        now = time.time()
        for f in glob.glob(os.path.join(temp_dir, "tts_*.wav")):
            try:
                if now - os.path.getmtime(f) > max_age_seconds:
                    os.remove(f)
            except OSError:
                pass
    except Exception:
        pass


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """PCM 原始数据 → WAV 封装"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)# 16bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _detect_audio_format(data: bytes) -> str:
    """从文件头探测音频格式"""
    if data[:4] == b"RIFF":
        return "wav"
    if data[:3] == b"ID3" or (len(data) > 1and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"OggS":
        return "ogg"
    return "wav"  # 默认


def _save_audio_to_temp(audio_bytes: bytes, fmt: str = "wav") -> Record:
    """保存音频到临时文件，返回 Record"""
    temp_dir = _get_temp_dir()
    filename = f"tts_{_uuid.uuid4().hex[:12]}.{fmt}"
    filepath = os.path.join(temp_dir, filename)

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"[TTS] Saved {len(audio_bytes)} bytes → {filepath}")
    return Record(record=filepath, mime=f"audio/{fmt}", name=filename)


# ──────────────────────────── 模式推断 ────────────────────────────

def _resolve_mode(model_id: str, config_mode: str = "") -> str:
    """
    优先使用配置中显式指定的 mode，否则从model_id 自动推断。
    返回值: 'vc' | 'vc-realtime' | 'vd' | 'vd-realtime'
    """
    if config_mode and config_mode in ("vc", "vc-realtime", "vd", "vd-realtime"):
        return config_mode

    mid = model_id.lower()
    if "vc-realtime" in mid or "vc_realtime" in mid:
        return "vc-realtime"
    if "vd-realtime" in mid or "vd_realtime" in mid:
        return "vd-realtime"
    if "-vc-" in mid or "_vc_" in mid or mid.endswith("-vc") or mid.endswith("_vc"):
        return "vc"
    if "-vd-" in mid or "_vd_" in mid or mid.endswith("-vd") or mid.endswith("_vd"):
        return "vd"
    return "vc-realtime"  # 默认


# ──────────────────────────── TTS Client ────────────────────────────

class DashscopeTTSClient(TTSModelClient):
    """Dashscope Qwen TTS 四模式客户端"""

    def __init__(self, model: ModelInfo):
        super().__init__(model)
        cfg = self.model.model_config or {}
        self._api_key: str = self.model.provider_config.get("api_key", "")
        self._voice_id: str = cfg.get("voice_id", "")
        self._ws_url: str = cfg.get(
            "ws_url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )
        self._timeout: int = cfg.get("timeout", 120)
        self._mode: str = _resolve_mode(
            self.model.model_id, cfg.get("mode", "")
        )

    # ──────────── 入口 ────────────

    async def text_to_speech(self, text: str, **kwargs) -> Record:
        if not self._api_key:
            raise ValueError("[TTS] api_key is required in provider_config")
        if not self._voice_id:
            if self._mode.startswith("vc"):
                raise ValueError(
                    "[TTS] voice_id is required —请用 voice_manager.py enroll 注册音色后填入"
                )
            else:
                raise ValueError(
                    "[TTS] voice_id is required — VD 模式请填入设计音色名称"
                )
        # 清理过期临时文件
        _cleanup_temp_files()

        logger.info(
            f"[TTS] mode={self._mode}, model={self.model.model_id}, "
            f"voice={self._voice_id}, text_len={len(text)}"
        )

        if self._mode == "vc":
            return await self._synth_vc_http(text)
        else:
            #vc-realtime / vd / vd-realtime 都走 WebSocket
            return await self._synth_websocket(text)

    # ────────────VC HTTP (MultiModalConversation) ────────────

    async def _synth_vc_http(self, text: str) -> Record:
        """VC 非实时模式: 通过 HTTP API 合成"""
        try:
            import dashscope
            from dashscope import MultiModalConversation
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install: pip install dashscope"
            )

        dashscope.api_key = self._api_key

        def _call():
            return MultiModalConversation.call(
                model=self.model.model_id,
                api_key=self._api_key,
                text=text,
                voice=self._voice_id,
                stream=False,
            )
        
        logger.info("[TTS] VC HTTP: calling MultiModalConversation...")
        response = await asyncio.to_thread(_call)
        logger.debug(f"[TTS] VC HTTP raw response type: {type(response)}, "
                 f"dir: {[a for a in dir(response) if not a.startswith('_')]}")

        # 检查状态
        status = getattr(response, "status_code", None)
        if status is not None and status != 200:
            msg = getattr(response, "message", str(response))
            raise RuntimeError(f"TTS VC HTTP failed ({status}): {msg}")

        # 提取音频
        audio_bytes = self._extract_audio_from_response(response)
        if not audio_bytes:
            raise RuntimeError("TTS VC HTTP returned empty audio")

        # 探测格式并保存
        fmt = _detect_audio_format(audio_bytes)
        logger.info(f"[TTS] VC HTTP done: {len(audio_bytes)} bytes, format={fmt}")
        return _save_audio_to_temp(audio_bytes, fmt)

    def _extract_audio_from_response(self, response) -> bytes:
        """
        从 MultiModalConversation 响应中提取音频字节。兼容多种可能的响应结构。
        """
        output = getattr(response, "output", response)

        #── 模式1: output.choices[].message.content[]含audio 字段 ──
        choices = (
            output.get("choices", [])
            if isinstance(output, dict)
            else getattr(output, "choices", [])
        )
        if choices:
            choice = choices[0]
            message = (
                choice.get("message", {})
                if isinstance(choice, dict)
                else getattr(choice, "message", {})
            )
            content = (
                message.get("content", [])
                if isinstance(message, dict)
                else getattr(message, "content", [])
            )
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "audio" in item:
                        return self._decode_audio_value(item["audio"])

        # ── 模式2: output.audio 直接存在 ──
        audio_val = (
            output.get("audio")
            if isinstance(output, dict)
            else getattr(output, "audio", None)
        )
        if audio_val is not None:
            return self._decode_audio_value(audio_val)

        # ── 模式3: response本身有 get_audio_data 方法 ──
        if hasattr(response, "get_audio_data"):
            data = response.get_audio_data()
            if data:
                return data if isinstance(data, bytes) else self._decode_audio_value(data)

        raise RuntimeError(
            f"Cannot extract audio from response. "
            f"Output keys: {list(output.keys()) if isinstance(output, dict) else dir(output)}. "
            f"Please check dashscope SDK version (>=1.23.1)."
        )

    def _decode_audio_value(self, value) -> bytes:
        """解码音频值: 可能是 bytes / base64 / data URI / URL / dict / Audio对象"""
        if isinstance(value, bytes):
            return value

        if isinstance(value, dict):
            for key in ("url", "data", "audio"):
                if key in value and value[key]:
                    return self._decode_audio_value(value[key])

        if isinstance(value, str):
            # data URI
            if value.startswith("data:"):
                b64_part = value.split(",", 1)[1] if "," in value else value
                return base64.b64decode(b64_part)
            # URL
            if value.startswith(("http://", "https://")):
                import requests
                resp = requests.get(value, timeout=60)
                resp.raise_for_status()
                return resp.content
            # 裸 base64
            try:
                decoded = base64.b64decode(value)
                if len(decoded) > 100:
                    return decoded
            except Exception:
                pass

        # 兜底：Audio 等非 dict 对象可能支持 [] 访问
        if hasattr(value, '__getitem__') and not isinstance(value, (str, bytes)):
            for key in ("url", "data", "audio"):
                try:
                    v = value[key]
                    if v:
                        return self._decode_audio_value(v)
                except (KeyError, TypeError, IndexError):
                    continue

        raise ValueError(f"Cannot decode audio value (type={type(value).__name__})")

    # ──────────── WebSocket (vc-realtime / vd / vd-realtime) ────────────

    async def _synth_websocket(self, text: str) -> Record:
        """
        WebSocket 模式: 适用于 vc-realtime / vd / vd-realtime。
        三者走完全相同的代码，只有 model_id 不同。
        """
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

        dashscope.api_key = self._api_key

        #── 共享状态 ──
        audio_chunks: list[bytes] = []
        error_holder: list[Optional[str]] = [None]
        done_event = threading.Event()

        # ── 回调 ──
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
                            .get("message", str(response)))
                        logger.error(f"[TTS] Server error: {err_msg}")
                        error_holder[0] = err_msg
                        done_event.set()
                except Exception as exc:
                    logger.error(f"[TTS] Callback exception: {exc}")
                    error_holder[0] = str(exc)
                    done_event.set()

        # ── 同步合成线程 ──
        ws_url = self._ws_url
        model_id = self.model.model_id
        voice_id = self._voice_id
        timeout_sec = self._timeout

        def _run_sync():
            tts = None
            try:
                logger.info(f"[TTS] WS connecting: {ws_url}, model={model_id}")
                tts = QwenTtsRealtime(
                    model=model_id,
                    callback=_Collector(),
                    url=ws_url,
                )
                tts.connect()

                logger.info(f"[TTS] Session update: voice={voice_id}")
                tts.update_session(
                    voice=voice_id,
                    response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                    mode="server_commit",
                )

                #按行分块发送
                lines = [l for l in text.split("\n") if l.strip()]
                if not lines:
                    lines = [text]
                for chunk in lines:
                    logger.debug(f"[TTS] Sending: {chunk[:60]}...")
                    tts.append_text(chunk)
                    time.sleep(0.05)

                tts.finish()
                logger.info("[TTS] finish() called, waiting...")

                if not done_event.wait(timeout=timeout_sec):
                    error_holder[0] = f"TTS timed out after {timeout_sec}s"
                    logger.error(error_holder[0])
            except Exception as exc:
                error_holder[0] = str(exc)
                logger.error(f"[TTS] Thread exception: {exc}")
                done_event.set()
            finally:                # ← 增加 finally
                if tts is not None:
                    try:
                        # QwenTtsRealtime 没有暴露 close()，
                        # 但底层 websocket 连接可以尝试关闭
                        if hasattr(tts, 'close'):
                            tts.close()
                        elif hasattr(tts, '_ws') and tts._ws:
                            tts._ws.close()
                    except Exception:
                        pass
                
        # ── 线程池执行 ──
        await asyncio.to_thread(_run_sync)

        if error_holder[0]:
            raise RuntimeError(f"TTS failed: {error_holder[0]}")

        pcm_data = b"".join(audio_chunks)
        if not pcm_data:
            raise RuntimeError("TTS returned empty audio")

        # PCM → WAV
        wav_bytes = _pcm_to_wav(pcm_data)
        duration = len(pcm_data) / (24000 * 2)
        logger.info(
            f"[TTS] Done: {len(pcm_data)} PCM bytes → "
            f"{len(wav_bytes)} WAV bytes (~{duration:.1f}s)"
        )

        return _save_audio_to_temp(wav_bytes, "wav")
