# ElevenLabs 语音与异步音乐

使用者显式指定或个人模型列表含 `eleven-v4`、`eleven-v4-turbo`、`elevenlabs-music-v2.5` 时，提交前读取本页，并按[模型选择与恢复](model-selection.md)执行 `describe` → `plan` → `run`。

当前版本完成接口适配准备，生产可用性尚待确认；随包目录与离线 `plan` 通过不代表线上已经开放。无配置时 TTS 仍用 `speech-2.8-hd`，异步音乐仍用 `lyria-3-pro`。只有 API 验收且生产正式可用后才发布默认值切换；不能仅因模型在通用列表出现而自行改变默认值。用户显式型号、个人有序列表和已保存任务按原规则优先。

## 语音

`audio-tts` 的 `prompt` 保存原朗读文本，CLI 将其原样映射为 API 的 `text`（1–5000 字符），包括音频标签、IPA、Unicode 字符。`original_request` 继续保存用户需求。独立 `generate` 使用契约字段 `text`。

`requirements` 可传 `voice`、`stability`、`similarity_boost`、`seed`、`language_code`、`apply_text_normalization`、`timestamps`、`enable_safety_checker`、`output_format`。完整范围和 19 种输出编码见 `describe` 的 `params` 与 `request_schema`。

`voice` 接受名称或 ID；省略时服务默认 Rachel。MiniMax 的默认音色配置和 `voice_setting` 不适用于 ElevenLabs，也不自动转换；不能把同名音色视为同一个声音。其他旧 Speech 参数如 `audio_setting`、`voice_modify`、`pronunciation_dict`、`language_boost` 无已验证映射时拒绝候选，不删除后继续。

```json
{
  "operation": "audio-tts",
  "original_request": "用 eleven-v4 的 Rachel 朗读这句话，并保留时间戳。",
  "model": "eleven-v4",
  "prompt": "[whispering] Welcome to the evening show.",
  "requirements": {"voice": "Rachel", "timestamps": true}
}
```

## 音乐

`music-async` 使用 `elevenlabs-music-v2.5` 时，提示词与 `requirements.composition_plan` 必须且只能有一个。提示词模式使用顶层 `prompt`（1–4100 字符），可选 `requirements.duration`（3–600 **秒**，最多三位小数）和 `force_instrumental`。省略 duration 由服务决定，CLI 不补入时长。两种模式均可设置 `output_format`、`enable_safety_checker`；25 种编码见 `describe`。

计划模式省略顶层 prompt；将完整计划放入 `requirements.composition_plan.chunks`，按播放顺序提供 1–30 段。每段 `duration` 为 3–120 秒，合计不超过 600 秒；必须有 `text` 和 `positive_styles`，纯音乐 text 可以为空。歌词最多 30 行、每行 200 字符，开头可使用 1–100 字符的 `[段落名]`，支持 `{演奏指示}`。可选 `negative_styles`、`context_adherence`、`audio_reference`；`seed` 仅用于计划模式。计划模式下显式提供 duration 或 force_instrumental、提示词模式下显式提供 seed 都会拒绝，避免参数未生效却继续生成。

```json
{
  "operation": "music-async",
  "original_request": "用 elevenlabs-music-v2.5 按两段计划创作纯音乐。",
  "model": "elevenlabs-music-v2.5",
  "requirements": {
    "composition_plan": {
      "chunks": [
        {"text": "[Intro]", "duration": 10, "positive_styles": ["ambient", "soft piano"]},
        {"text": "", "duration": 15, "positive_styles": ["ambient"], "context_adherence": "high"}
      ]
    },
    "seed": 42
  }
}
```

参考音频只能放在具体段落的 `audio_reference`，其中 `audio_url` 必须是公开可读 HTTP(S) URL。本地文件先上传；Agent 核对公开可访问性。`start_ms` / `end_ms` 为**毫秒**，end 必须大于 start，窗口不超过 30000 毫秒。省略 end 使用 start 后 30 秒或音频结尾；可选 strength 为 low / medium / high / xhigh。CLI 校验 URL 结构和时间窗口，不证明远端可读。

旧 Lyria 的 `inputs.images` / `image_urls`、`negative_prompt` 无法直接映射。未知字段、未定位到段落的 `inputs.audios` 和嵌套未知字段都会拒绝，不静默丢弃。用户确需这些要求时保留原请求，报告当前候选不兼容。Gemini 原生 `music-native` 继续使用独立协议，不能改成异步请求。

## 下载、时间戳与费用

任务提交到 `POST /e/v1/audios/generations`，用 `GET /e/v1/tasks/{task_id}` 查询。生成完成但核账未结束时仍可能 processing；继续查询原 ID，不能另提生成。已有 run 用 `continue`，task 记录用 `resume`。查询或下载失败只恢复原任务，输出链接没有固定 24 小时保留保证，应及时下载。

最终 URL 来自 `results[0].url`。下载以实际内容和 ffprobe 解析结果确定 MIME/扩展名，不以请求编码或 URL 后缀命名；`pcm_44100` 实测得到 WAV。Opus 可封装在 Ogg 中。无法解析的原始编码保持 download_failed，保留任务与 URL 供恢复，不猜测格式或再次生成。

TTS 的 `results[0].timestamps` 保存在任务记录中，同时通过 `result_metadata.timestamps` 暴露；run 返回位于 `result.result_metadata.timestamps`。原样保留分段顺序、所有字符与时间数组及空段，不拼接、不补齐。实测 Turbo 样本有 7 段，其中 2 段为空。音乐未返回 lyrics / duration / seed 时不自行补造；实测文件时长与请求时长分别记录。

2026-11-12 合同参考价格：v4 为 $0.08/1000 输入字符，Turbo 为 $0.04/1000 输入字符，音乐为 $0.60/实际输出整分钟并向上取整；账户分组倍率另计。实际扣费以服务账单为准，不用本地字符长度、请求时长或 MP3 padding 推算权威账单。59.9 秒请求本轮计 1 分钟，**60 秒与 60.001 秒请求本轮均计 2 分钟**，不能承诺请求 60 秒只收 1 分钟。省略 duration 的预扣可能为 0，完成后仍按实际数量结算。
