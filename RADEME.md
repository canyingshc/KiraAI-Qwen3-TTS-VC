# Qwen TTS Provider for KiraAI

一个为 KiraAI-2.1.0 编写的 **Dashscope Qwen TTS 声音复刻**语音合成 Provider 插件。

支持通过阿里云 Dashscope 的 Realtime WebSocket 接口，将文本合成为语音并以 `Record` 消息元素返回，可无缝接入 KiraAI 的 TTS 流程。

---

## ✨ 特性

- **声音复刻**：基于 `qwen3-tts-vc-realtime` 模型，使用自定义音色进行语音合成
- **延迟加载**：`dashscope` 仅在实际调用 TTS 时才会被 `import`，**即使未安装也不会影响 LLM / Image / Embedding 等其他 Provider 的正常使用**
- **异步友好**：合成过程通过 `asyncio.to_thread` 运行在线程池中，不阻塞事件循环
- **即装即用**：将文件丢入指定目录，配置好参数即可工作

---

## 📦 安装

### 1. 安装依赖

```bash
pip install dashscope httpx
```

### 2. 放置文件

将 `dashscope_tts.py` 复制到以下路径：

```
KiraAI-2.1.0/core/provider/src/
```

即可被 KiraAI 的 Provider 系统自动识别加载。

---

## 🔧 配置

在 KiraAI 的模型配置中添加如下内容：

| 配置项 | 层级 | 必填 | 说明 |
|---|---|---|---|
| `api_key` | `provider_config` | ✅ | 阿里云 Dashscope API Key |
| `voice_id` | `model_config` | ✅ | 已注册的复刻音色 ID（通过 `mp3.py` 获取） |
| `ws_url` | `model_config` | ❌ | WebSocket 地址，默认 `wss://dashscope.aliyuncs.com/api-ws/v1/realtime` |
| `timeout` | `model_config` | ❌ | 超时秒数，默认 `120` |

**model_id 示例：**

```
qwen3-tts-vc-realtime-2026-01-15
```

---

## 🎙️ 获取 Voice ID

在使用 TTS 前，你需要先注册一个自定义音色并获取 `voice_id`。

### 步骤

1. **准备音频素材**
   - 准备一段清晰的 MP3 音频文件作为音色参考

2. **Base64 编码**
   - 前往 [base64encode.org](https://www.base64encode.org/zh/) 将音频文件转换为 Base64 字符串

3. **运行 `mp3.py`**

   编辑 `mp3.py`，填入你的配置：

   ```python
   API_KEY = "sk-your-api-key-here"        # Dashscope API Key
   BASE64_STR = "你的Base64编码音频字符串"    # 第 2 步获取的 Base64
   ```

   你也可以根据需要修改以下字段：

   ```python
   input_dict["target_model"] = "qwen3-tts-vc-realtime-2026-01-15"  # 带 vc 的模型才支持声音复刻
   input_dict["preferred_name"] = "自定义名称"                        # 音色备注名
   ```

   然后运行：

   ```bash
   python mp3.py
   ```

4. **获取结果**

   成功后终端会输出：

   ```
   uploading...
   success!
   voice key: your-voice-id-xxxx
   ```

   将输出的 `voice key` 填入 KiraAI 模型配置的 `voice_id` 字段即可。

> ⚠️ **注意**：仅带 `vc`（Voice Clone）标识的模型支持声音复刻功能。

---

## 📂 项目结构

```
.
├── dashscope_tts.py   # TTS Provider 主文件，放入 core/provider/src/
├── mp3.py             # 声音注册小工具，用于获取 voice_id
└── README.md
```

---

## 🔄 工作流程

```
输入文本
  │
  ▼
DashscopeTTSClient.text_to_speech()
  │
  ├─ 连接 Dashscope WebSocket
  ├─ 发送 session update（音色、格式）
  ├─ 按行分块发送文本
  ├─ 收集返回的 PCM 音频帧
  │
  ▼
PCM → WAV 封装
  │
  ▼
保存至 data/temp/tts_xxxx.wav
  │
  ▼
返回 Record 对象
```

---

## 📝 补充说明

- 合成的音频格式为 **PCM 24000Hz Mono 16bit**，自动封装为 WAV 文件
- 临时音频文件保存在项目的 `data/temp/` 目录下
- 如需调整超时时间，可在 `model_config` 中设置 `timeout`（单位：秒）

---
