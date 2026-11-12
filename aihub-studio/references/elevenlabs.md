# ElevenLabs 语音、音乐与转写

使用者显式指定或个人模型列表含 `eleven-v4`、`eleven-v4-turbo`、其 `-custom-voice` 变体、`elevenlabs-music-v2.5`、`scribe-v2` / `scribe-v3` 时，提交前读取本页，并按[模型选择与恢复](model-selection.md)执行 `describe` → `plan` → `run`。

当前版本完成接口适配准备，生产可用性尚待确认；随包目录与离线 `plan` 通过不代表线上已经开放。无配置时 TTS 仍用 `speech-2.8-hd`，异步音乐仍用 `lyria-3-pro`。只有 API 验收且生产正式可用后才发布默认值切换；不能仅因模型在通用列表出现而自行改变默认值。用户显式型号、个人有序列表和已保存任务按原规则优先。

## 语音

`audio-tts` 的 `prompt` 保存原朗读文本，CLI 将其原样映射为 API 的 `text`，包括音频标签、IPA、Unicode 字符。统一接口允许 1–5000 字符，官方最多 2000，长文本可由其他兼容渠道承接，不统一缩小共享上限。`original_request` 继续保存用户需求。独立 `generate` 使用契约字段 `text`。

`requirements` 可传 `voice`、`stability`、`similarity_boost`、`seed`、`language_code`、`apply_text_normalization`、`timestamps`、`enable_safety_checker`、`output_format`，以及前后文、词典和专业克隆控制。完整范围和 19 种输出编码见 `describe`。`previous_text` / `future_text` 各最多 100 字符，仅 v4 及其 custom 支持；`pronunciation_dictionary_locators` 最多 3 项，须有词典 ID、版本及权限；`clone_strength` 要求已有音色已为对应模型微调，不等同于 similarity。官方 Turbo 不支持前后文或显式 similarity，seed 必须大于 0。普通型号保留统一范围，交由 Gateway 匹配兼容渠道，不擅自删参强制官方。nullable 控制省略／null 表示不指定；false、0、空数组保留。

`voice` 接受名称或 ID；省略时服务默认 Rachel。MiniMax 的默认音色配置和 `voice_setting` 不适用于 ElevenLabs，也不自动转换；不能把同名音色视为同一个声音。其他旧 Speech 参数如 `audio_setting`、`voice_modify`、`pronunciation_dict`、`language_boost` 无已验证映射时拒绝候选，不删除后继续。

`eleven-v4-custom-voice` / `eleven-v4-turbo-custom-voice` 仅走官方，必须显式提供已有音色 ID，不能用 Rachel 补缺；它们不是创建或克隆声音的接口。本地按官方约束校验 custom，不把这些约束覆盖到普通型号。

查找 ElevenLabs 音色使用共用 CLI `voices --skill aihub-audio`：携带 Gateway Token 读取 `/e/v1/configs/elevenlabs-preset-voice-id` 的完整本地目录，不扣生成 quota、不实时访问上游；保留 name、description、languages、preview_url 等元数据。目录不是完整白名单，命中也不强制官方。选定的 voice_id 原样填入本次 requirements.voice，不写入 MiniMax 默认音色配置。

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

`music-async` 使用 `elevenlabs-music-v2.5` 时，提示词与 `requirements.composition_plan` 必须且只能有一个。提示词模式使用顶层 `prompt`（1–4100 字符），可选整数 `requirements.music_length_ms`（3000–600000 **毫秒**）和 `force_instrumental`。省略或 null 由服务决定，CLI 不补入时长。两种模式均可设置 `output_format`、`enable_safety_checker`、`timestamps`。统一目录保留 25 种编码；**官方 Music 仅 MP3／Opus，PCM／μ-law／A-law 保留 Fal**，不能宣称所有渠道支持全部枚举。默认 mp3_48000_192。

计划模式省略顶层 prompt；将完整计划放入 `requirements.composition_plan.chunks`，按播放顺序提供 1–30 段。每段整数 `duration_ms` 为 3000–120000 毫秒，合计不超过 600000 毫秒；必须有 `text` 和 `positive_styles`，纯音乐 text 可以为空。歌词最多 30 行、每行 200 字符，开头可使用 1–100 字符的 `[段落名]`，支持 `{演奏指示}`。可选 `negative_styles`、`context_adherence`、`audio_reference`；`seed` 仅用于计划模式。计划模式下非 null 的 music_length_ms 或 force_instrumental=true、提示词模式下非 null 的 seed 会拒绝。官方 seed 为 0–2147483647，风格列表最多 50 项；其他渠道由 Gateway 匹配。

**4.0.0 迁移**：歌曲 `requirements.duration: 30` 改为 `requirements.music_length_ms: 30000`；段落 `duration: 15` 改为 `duration_ms: 15000`。独立 generate 同样使用毫秒。旧秒制字段（包括 null）明确拒绝，不自动转换。已受理任务继续原 ID 查询／下载；尚未提交的旧计划需迁移原请求后重新 plan，不能编辑计划指纹，也不能重发受理状态不明的任务。

```json
{
  "operation": "music-async",
  "original_request": "用 elevenlabs-music-v2.5 按两段计划创作纯音乐。",
  "model": "elevenlabs-music-v2.5",
  "requirements": {
    "composition_plan": {
      "chunks": [
        {"text": "[Intro]", "duration_ms": 10000, "positive_styles": ["ambient", "soft piano"]},
        {"text": "", "duration_ms": 15000, "positive_styles": ["ambient"], "context_adherence": "high"}
      ]
    },
    "seed": 42
  }
}
```

参考音频只能放在具体段落的 `audio_reference`，其中 `audio_url` 必须是公开可读 HTTP(S) URL。本地文件先上传。`start_ms` / `end_ms` 为整数毫秒，end 大于 start，统一窗口最多 30000 毫秒；**官方实际窗口要求 10000–30000 毫秒**。省略 end 使用 start 后 30 秒或音频结尾，短素材由服务器检查。CLI 保留统一 Schema 对 Fal 的范围，不据此声称短窗口支持官方。非零起点裁切与官方上传由 Gateway 完成，上传成本由平台承担，不另行裁切或直接上传 ElevenLabs；可选 strength 为 low / medium / high / xhigh。

旧 Lyria 的 `inputs.images` / `image_urls`、`negative_prompt` 无法直接映射。未知字段、未定位到段落的 `inputs.audios` 和嵌套未知字段都会拒绝，不静默丢弃。用户确需这些要求时保留原请求，报告当前候选不兼容。Gemini 原生 `music-native` 继续使用独立协议，不能改成异步请求。

## Scribe 转写

显式选 `scribe-v2` / `scribe-v3`，`inputs.audios` 恰好一个 URL 或本地路径。URL 通过 JSON audio_url 提交，本地文件通过 multipart file 直接提交。客户端本地整文件上限为 256 MiB（内存保护，非服务端能力上限），更大文件用公开 URL；不套用 Paraformer 分段、转码、声道和语言字段，不自动把 V3 降为 V2。

可选 language_code、keyterms、diarize、tag_audio_events、num_speakers、diarization_threshold、timestamps_granularity、no_verbatim、temperature、seed；V3 另支持 secondary_language_codes、numbers_format。完整范围见 describe。diarize / tag_audio_events 默认 true；num_speakers 与 diarization_threshold 互斥且要求 diarize=true。nullable 控制省略／null 表示不指定，false、0、空数组保留。客户端 multipart 数组使用 JSON 数组字符串；Gateway 也接受重复字段，不逗号拼接。官方 keyterms 每项最多 5 词及括号限制由 Gateway 检查；非空 keyterms 使用增强价格。

```json
{
  "operation": "audio-transcribe",
  "original_request": "用 Scribe V3 转写录音并保留字符时间戳。",
  "model": "scribe-v3",
  "inputs": {"audios": ["./meeting.wav"]},
  "requirements": {"timestamps_granularity": "character", "secondary_language_codes": ["en"], "numbers_format": "digits"}
}
```

完整结构化 JSON 和转写 text 均保留，包括 words、字符时间戳和说话人；不重新累计偏移。

## 下载、时间戳与费用

任务提交到 `POST /e/v1/audios/generations`，用 `GET /e/v1/tasks/{task_id}` 查询。生成完成但核账未结束时仍可能 processing；继续查询原 ID，不能另提生成。已有 run 用 `continue`，task 记录用 `resume`。查询或下载失败只恢复原任务，输出链接没有固定 24 小时保留保证，应及时下载。

`requested_options_unavailable` / `unsupported_parameters`：完整展示 message、unsupported_parameters 与 suggested_remove_parameters 的全部项目。停止自动切换，让用户选择保留要求稍后处理，或明确修改全部相关要求后新建请求。建议移除项不是自动删参授权，不改声音、参考音、专业克隆或时间戳，不保证修改后成功。新请求前核对旧任务受理／完成状态；退款只转述实际服务证据。

TTS／Music 最终音频 URL 来自 `results[0].url`。下载以实际内容和 ffprobe 解析结果确定 MIME/扩展名，不以请求编码或 URL 后缀命名；历史 `pcm_44100` 诊断得到 WAV，不代表官方 Music 当前支持 PCM。Opus 可封装在 Ogg 中。无法解析的原始编码保持 download_failed，保留任务与 URL 供恢复，不猜测格式或再次生成。

TTS 的 timestamps、alignment、normalized_alignment、voice_segments 和 Music 的 composition_plan、song_metadata、words_timestamps 保存在任务记录并通过 result_metadata 暴露；run 位于 result.result_metadata。Turbo 的公开 timestamps 已是全局时间数组，原样保留所有字符和空段，不重新累计；原生分块 alignment 不与公开 timestamps 混算，不把估计末端当账单时长。未返回 lyrics / duration / seed 时不补造。

2026-11-12 合同参考价格：v4／custom $0.08/千 Unicode 字符，Turbo／custom $0.04/千字符，含标签、空格和标点，不含前后文；Music $0.60/实际解码输出分钟，向上取整。Scribe V2/V3 在分组倍率 1 时每秒 $0.000136，非空 keyterms 为 $0.000176，按响应 audio_duration_secs 向上取整秒。实际扣费以服务账单及账户倍率为准，不从请求时长、时间戳末端或 MP3 padding 推导权威账单；缺少上游成本不阻塞客户结算。旧 PCM/WAV 诊断不是官方 Music 当前能力，Opus 可为 Ogg，按实际容器保存。
