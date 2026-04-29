# Dashscope Qwen TTS Provider for KiraAI

[![Plugin Version](https://img.shields.io/badge/version-2.0.0-blue)]()
[![KiraAI](https://img.shields.io/badge/platform-KiraAI_2.x-purple)](https://github.com/AkagawaTsuworworshi/KiraAI)
[![License](https://img.shields.io/badge/license-MIT-green)]()

为 [KiraAI](https://github.com/AkagawaTsuworworshi/KiraAI) 编写的 **Dashscope Qwen TTS** 语音合成 Provider 插件，支持**声音复刻 (VC)** 和**声音设计 (VD)** 

---

## ✨ 特性

- **四模式合成** — VC / VC-Realtime / VD / VD-Realtime，通过配置一键切换
- **声音复刻** — 5~10 秒干声即可复刻专属音色
- **音色管理工具** — 内置 CLI 工具，注册 / 查询 / 删除音色一条命令搞定
- **延迟加载** — `dashscope`仅在实际调用 TTS 时 import，不影响其他 Provider正常使用
- **异步友好** — 合成过程通过 `asyncio.to_thread` 运行，不阻塞事件循环
- **零侵入** — 不修改任何框架文件，放入目录即自动识别

---

## 📦 安装

### 1. 安装依赖

```bash
pip install dashscope httpx requests
```

### 2. 放置插件

将 `dashscope_tts/` 整个文件夹复制到：

```
KiraAI/core/provider/src/dashscope_tts/
```
注:没有的话可以新建一个文件夹把东西丢里面
启动KiraAI 后自动识别加载，无需其他配置。

---

##📂 目录结构

```
dashscope_tts/
├── manifest.json          # 插件元数据
├── schema.json            # WebUI 配置字段定义
├── provider.py            # Provider 注册入口
├── model_clients.py       # 核心：四模式 TTS 合成
├── voice_manager.py       # CLI 工具：音色注册 / 查询 / 删除
├── voice_samples/         # 专用文件夹：放入干声音频
│   └── README.md
└── voice_registry.json    # 自动生成：已注册音色记录
```

---

## 🔧 配置

在 KiraAI WebUI 的 Provider 管理页面添加 Dashscope TTS，配置以下字段：

### Provider 配置

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `api_key` | ✅ | 阿里云百炼平台 API Key |

### Model 配置

| 字段 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `mode` | ❌ | 自动推断 | `vc-realtime` \| `vd-realtime` \| `vc` \| `vd`，留空则从 model_id 自动推断 |
| `voice_id` | ✅ | — | VC 模式：注册获得的音色 ID；VD 模式：设计音色名称 |
| `ws_url` | ❌ | 北京节点 | WebSocket 地址（仅 realtime/vd 模式） |
| `timeout` | ❌ | `120` | 合成超时时间（秒） |

---

## 🎛️ 四模式对照

| mode | model_id 示例 | 协议 | voice_id 来源 | 特点 |
|------|---------------|------|---------------|------|
| `vc` | `qwen3-tts-vc-2026-01-22` | HTTP | 注册的复刻音色 | 非实时，质量优先 |
| `vc-realtime` | `qwen3-tts-vc-realtime-2026-01-15` | WebSocket | 注册的复刻音色 | 实时流式，低延迟 |
| `vd` | `qwen3-tts-vd-2026-01-26` | WebSocket | 设计音色名称 | 非实时，质量优先 |
| `vd-realtime` | `qwen3-tts-vd-realtime-2026-01-15` | WebSocket | 设计音色名称 | 实时流式，低延迟 |

> **自动推断规则：** 如果 `mode` 未填写，插件会从 `model_id` 中检测 `vc-realtime` / `vd-realtime` / `vc` / `vd` 关键字自动判断。默认 fallback 为 `vc-realtime`。
>
> **代码实现：** `vc-realtime` / `vd` / `vd-realtime` 复用同一个 WebSocket 方法`_synth_websocket()`，仅 `model_id` 不同。`vc` 独立走 HTTP 的`_synth_vc_http()`。

---

## 🎙️ 音色管理

### 准备音频

将干声音频文件放入插件目录下的 `voice_samples/` 文件夹：

- **时长**：5~10 秒
- **内容**：纯干声，无背景噪音/ 混响 / BGM
- **格式**：mp3 / wav / flac / ogg / m4a / aac / wma

### 注册音色

```bash
cd core/provider/src/dashscope_tts/

# 注册 voice_samples/ 中的所有音频
python voice_manager.py enroll --api-key sk-你的密钥

# 指定目标模型（默认 qwen3-tts-vc-realtime-2026-01-15）
python voice_manager.py enroll --api-key sk-你的密钥 --model qwen3-tts-vc-2026-01-22
```

输出示例：

```
找到 2个音频文件
目标模型: qwen3-tts-vc-realtime-2026-01-15
───────────────────────────────────────────────────────注册: sakura.mp3 (name=sakura) ... ✓ voice_id: qwen-tts-vc-sakura-xxx
  注册: tomori.wav (name=tomori) ... ✓ voice_id: qwen-tts-vc-tomori-xxx
───────────────────────────────────────────────────────
完成！注册结果已保存至 voice_registry.json
```

将输出的 `voice_id` 填入 KiraAI WebUI 中对应模型的 **Voice ID** 配置项。

### 查看已注册音色

```bash
python voice_manager.py list --api-key sk-你的密钥
```

### 删除音色

```bash
python voice_manager.py delete --voice-id qwen-tts-vc-sakura-xxx --api-key sk-你的密钥
```

### API Key 配置

`voice_manager.py` 支持三种方式提供 API Key（优先级从高到低）：

1. 命令行参数：`--api-key sk-xxx`
2. 脚本顶部常量：编辑 `voice_manager.py` 中的 `API_KEY = "sk-xxx"`
3. 环境变量：`DASHSCOPE_API_KEY`

---

## 🔄 工作流程

```
输入文本│▼
DashscopeTTSClient.text_to_speech()
  │
  ├─ 从 model_config 解析 mode / voice_id
  │
  ├── mode =vc ─────────────────────────┐
  │   调用 MultiModalConversation (HTTP) │
  │   提取音频字节→ 探测格式 → 保存        │
  │                                      ▼
  ├── mode = vc-realtime / vd / vd-realtime
  │   连接 WebSocket
  │   发送 session update（音色、格式）
  │   按行分块发送文本
  │   收集PCM 音频帧
  │   PCM → WAV 封装
  │                                      │
  ▼                                      ▼
保存至 data/temp/tts_xxxx.wav
  │
  ▼
返回 Record对象 → KiraAI 发送语音消息
```

---

## ⚠️ 注意事项

- 仅带**vc**（Voice Clone）标识的模型支持声音复刻，VD 模型使用预设的设计音色
- 合成音频格式为 **PCM 24000Hz Mono 16bit**（WebSocket 模式），自动封装为 WAV
- WebSocket 地址默认为北京节点，海外部署请切换至新加坡节点：
  ```
  wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
  ```
- `dashscope` SDK 版本建议 ≥ 1.23.9

---

---

## 📝 Q&A

<details>
<summary><b>voice_id怎么获取？</b></summary>

将干声音频放入 `voice_samples/` 文件夹，运行 `python voice_manager.py enroll --api-key sk-xxx`，控制台会输出 voice_id。详见上方[音色管理](#-音色管理) 章节。
</details>

<details>
<summary><b>mode 填什么？</b></summary>

四选一：`vc` / `vc-realtime` / `vd` / `vd-realtime`。也可以不填，插件会从 model_id 自动判断。推荐 `vc-realtime`（声音复刻 + 低延迟）。
</details>

<details>
<summary><b>不注册音色能用吗？</b></summary>

可以。使用 VD（Voice Design）模式，`voice_id` 填入阿里提供的设计音色名称即可，无需注册。
</details>

<details>
<summary><b>VC HTTP 模式解析报错？</b></summary>

`vc` 模式调用 `MultiModalConversation.call()`，不同SDK 版本的响应结构可能有差异。如果遇到解析失败，建议先切换到 `vc-realtime` 模式使用——WebSocket 路径的响应格式完全确定，稳定性更高。
</details>

---

## 📄 License

MIT
```
