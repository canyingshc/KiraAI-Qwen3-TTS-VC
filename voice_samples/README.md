# Voice Samples / 音色样本文件夹

将干声音频文件放入此文件夹，然后运行上级目录的 `voice_manager.py` 进行音色注册。

## 要求

- 时长: 5~10 秒
- 内容: 纯干声，尽量无背景噪音、混响、BGM
- 格式: mp3 / wav / flac / ogg / m4a / aac / wma

## 使用

```bash
# 进入插件目录
cd core/provider/src/dashscope_tts/

# 注册全部音频
python voice_manager.py enroll --api-key sk-你的密钥

# 查看已注册的音色
python voice_manager.py list --api-key sk-你的密钥

# 删除指定音色
python voice_manager.py delete --voice-id 音色ID --api-key sk-你的密钥

```
