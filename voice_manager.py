#!/usr/bin/env python3
"""
Dashscope TTS 音色管理工具

用法:python voice_manager.py enroll [--api-key KEY] [--model MODEL]
  python voice_manager.py list[--api-key KEY] [--model MODEL]
  python voice_manager.py delete --voice-id ID [--api-key KEY] [--model MODEL]

说明:
  - 将干声音频文件 (5~10秒, mp3/wav/flac 等) 放入同目录下的 voice_samples/ 文件夹
  - 运行 enroll 命令自动注册所有音频文件并输出 voice_id
  - 注册结果同时保存到 voice_registry.jsonAPI Key 获取优先级: --api-key 参数 > 脚本顶部 API_KEY 常量 > 环境变量DASHSCOPE_API_KEY
"""

import argparse
import base64
import json
import os
import pathlib
import sys

import requests

# ═══════════════════════════════════════════════
# ↓ 可直接在这里填入 API Key，省得每次传参
API_KEY = ""
# ═══════════════════════════════════════════════

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE_SAMPLES_DIR = os.path.join(SCRIPT_DIR, "voice_samples")
VOICE_REGISTRY_FILE = os.path.join(SCRIPT_DIR, "voice_registry.json")

DEFAULT_MODEL = "qwen3-tts-vc-2026-01-22" #这里的可以看百炼平台官方的模型名
ENROLLMENT_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
MIME_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
}


# ──────────────────────── 工具函数 ────────────────────────


def get_api_key(args_key=None) -> str:
    if args_key:
        return args_key
    if API_KEY:
        return API_KEY
    return os.getenv("DASHSCOPE_API_KEY", "")


def load_registry() -> dict:
    if os.path.exists(VOICE_REGISTRY_FILE):
        with open(VOICE_REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_registry(registry: dict):
    with open(VOICE_REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def _make_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# ──────────────────────── 核心操作 ────────────────────────


def enroll_voice(
    api_key: str,
    audio_path: str,
    target_model: str,
    preferred_name: str | None = None,
) -> str:
    """注册单个音频文件，返回 voice_id"""
    path = pathlib.Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {audio_path}")

    ext = path.suffix.lower()
    mime = MIME_MAP.get(ext, "audio/mpeg")
    if preferred_name is None:
        preferred_name = path.stem

    b64 = base64.b64encode(path.read_bytes()).decode()
    data_uri = f"data:{mime};base64,{b64}"

    payload = {
        "model": "qwen-voice-enrollment",
        "input": {
            "action": "create",
            "target_model": target_model,
            "preferred_name": preferred_name,
            "audio": {"data": data_uri},
        },
    }

    resp = requests.post(
        ENROLLMENT_URL, json=payload, headers=_make_headers(api_key)
    )
    if resp.status_code != 200:
        raise RuntimeError(f"注册失败 ({resp.status_code}): {resp.text}")

    result = resp.json()
    voice_id = result.get("output", {}).get("voice")
    if not voice_id:
        raise RuntimeError(f"响应中无 voice_id: {result}")

    return voice_id


def enroll_all(api_key: str, target_model: str):
    """批量注册 voice_samples/ 文件夹中的所有音频"""
    if not os.path.exists(VOICE_SAMPLES_DIR):
        os.makedirs(VOICE_SAMPLES_DIR)
        print(f"已创建 voice_samples 文件夹: {VOICE_SAMPLES_DIR}")
        print("请将干声音频文件 (5~10秒) 放入此文件夹后重新运行")
        return

    audio_files = sorted(
        f
        for f in os.listdir(VOICE_SAMPLES_DIR)
        if os.path.isfile(os.path.join(VOICE_SAMPLES_DIR, f))
        and pathlib.Path(f).suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not audio_files:
        print(f"voice_samples/ 中未找到音频文件")
        print(f"支持格式: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return

    print(f"找到 {len(audio_files)} 个音频文件")
    print(f"目标模型: {target_model}")
    print("─" * 55)

    registry = load_registry()

    for filename in audio_files:
        filepath = os.path.join(VOICE_SAMPLES_DIR, filename)
        name = pathlib.Path(filename).stem

        try:
            print(f"  注册: {filename} (name={name}) ...", end=" ", flush=True)
            voice_id = enroll_voice(api_key, filepath, target_model, name)
            print(f"✓ voice_id: {voice_id}")
            registry[name] = {
                "voice_id": voice_id,
                "source_file": filename,
                "target_model": target_model,
            }
        except Exception as e:
            print(f"✗ 失败: {e}")

    save_registry(registry)
    print("─" * 55)
    print(f"完成！注册结果已保存至 {VOICE_REGISTRY_FILE}")


def list_voices(api_key: str, target_model: str):
    """查看已注册音色"""
    # 本地注册表
    registry = load_registry()
    if registry:
        print("═══ 本地注册表 (voice_registry.json) ═══")
        for name, info in registry.items():
            vid = info.get("voice_id", "N/A")
            mdl = info.get("target_model", "N/A")
            src = info.get("source_file", "")
            print(f"  {name}")
            print(f"    voice_id : {vid}")
            print(f"    model    : {mdl}")
            if src:
                print(f"    source   : {src}")
        print()

    # API 查询
    payload = {
        "model": "qwen-voice-enrollment",
        "input": {
            "action": "list",
            "target_model": target_model,
        },
    }

    try:
        resp = requests.post(
            ENROLLMENT_URL, json=payload, headers=_make_headers(api_key)
        )
        if resp.status_code == 200:
            result = resp.json()
            voices = result.get("output", {}).get("voices", [])
            print(f"═══ API 远程音色 (model={target_model}) ═══")
            if voices:
                for v in voices:
                    if isinstance(v, dict):
                        print(f"  {v.get('voice_id', v)}")
                    else:
                        print(f"  {v}")
            else:
                print("  (无)")
        else:
            print(f"API 查询失败 ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"API 查询出错: {e}")


def delete_voice(api_key: str, voice_id: str, target_model: str):
    """删除已注册音色"""
    payload = {
        "model": "qwen-voice-enrollment",
        "input": {
            "action": "delete",
            "target_model": target_model,
            "voice": voice_id,
        },
    }

    resp = requests.post(
        ENROLLMENT_URL, json=payload, headers=_make_headers(api_key)
    )
    if resp.status_code == 200:
        print(f"✓ 已删除音色: {voice_id}")
        # 同步清理本地注册表
        registry = load_registry()
        to_remove = [
            k for k, v in registry.items() if v.get("voice_id") == voice_id
        ]
        for k in to_remove:
            del registry[k]
            print(f"  已从本地注册表移除: {k}")
        save_registry(registry)
    else:
        print(f"✗ 删除失败 ({resp.status_code}): {resp.text}")


# ──────────────────────── CLI 入口 ────────────────────────


def main():
    #公共参数模板（不单独使用，所以 add_help=False）
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-key", type=str, default=None, help="Dashscope API Key")

    parser = argparse.ArgumentParser(
        description="Dashscope TTS 音色管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="...",
    )
    # 主 parser 上不再定义 --api-key

    sub = parser.add_subparsers(dest="command")

    p_enroll = sub.add_parser("enroll", parents=[common], help="注册音频")
    p_enroll.add_argument("--model", type=str, default=DEFAULT_MODEL)

    p_list = sub.add_parser("list", parents=[common], help="查看音色")
    p_list.add_argument("--model", type=str, default=DEFAULT_MODEL)

    p_del = sub.add_parser("delete", parents=[common], help="删除音色")
    p_del.add_argument("--voice-id", type=str, required=True)
    p_del.add_argument("--model", type=str, default=DEFAULT_MODEL)

    args = parser.parse_args()
    # args.api_key 现在无论写在哪个位置都能正确解析

    api_key = get_api_key(getattr(args, "api_key", None))
    if not api_key:
        print("错误: 需要 API Key")
        print("  方式1: --api-key sk-xxx")
        print("  方式2: 编辑脚本顶部 API_KEY 变量")
        print("  方式3: 设置环境变量 DASHSCOPE_API_KEY")
        sys.exit(1)

    if args.command == "enroll":
        enroll_all(api_key, args.model)
    elif args.command == "list":
        list_voices(api_key, args.model)
    elif args.command == "delete":
        delete_voice(api_key, args.voice_id, args.model)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
