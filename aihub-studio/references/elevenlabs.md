# ElevenLabs 语音、对话、音乐与转写

使用下列型号前，读取本页并按[模型选择与恢复](model-selection.md)执行 describe → plan → run。Studio 5.0.0 接收 Gateway Spec #28；四个新 Speech / Dialogue 模型尚待对应 Gateway 版本生产部署，目录收录不代表线上可用。TTS 内置默认为 `speech-2.8-hd`，ASR 为 `paraformer-v2`；ElevenLabs Speech / Dialogue 为可选能力，异步音乐仍为 `elevenlabs-music-v2.5`。用户指定型号、个人有序列表和保存任务优先。

## Speech 与 Dialogue

| 用途 | 普通模型 | 已有音色 custom 模型 | 输入 |
| --- | --- | --- | --- |
| 单段语音 `audio-tts` | `eleven-v4-text-to-speech` | `eleven-v4-text-to-speech-custom-voice` | task 的 prompt 原样映射为 API text，独立 voice |
| 多音色对话 `audio-dialogue` | `eleven-v4-text-to-dialogue` | `eleven-v4-text-to-dialogue-custom-voice` | task 的 requirements.inputs 原样映射为 API inputs，省略 prompt |

Speech 的 text 为 1–5000 Unicode 字符（含空格、标点及标签），普通 voice 省略时为 Rachel。custom 必须显式提供非空已有音色 ID，拒绝 Rachel 默认别名，text 最多 2000 字符。Speech 不接收 inputs；普通超过 2000 字符时部分控制组合可能被 Gateway 能力检查拒绝，不截断或删参重试。

Dialogue 的 inputs 是非空有序数组，每段只含必填 text 和 voice。每段 text 非空，累计最多 2000 Unicode 字符，最多 10 个不同音色 ID；可超过 10 段且重复使用音色。每段必须显式提供已有音色 ID，拒绝 Rachel 默认别名；拒绝顶层 text、voice、enable_safety_checker（包括 null）及分段未知字段。整组一次提交，不分片生成或跨账号拼接。

custom 表示使用可访问的已有音色，支持已有私有音色，也可使用公共音色；普通模型不做公私分类预查。custom Dialogue 可混用同一实际账号能够访问的公共／私有音色。不添加用户音色 ACL、账号定位、目录白名单、创建／克隆／训练或换声音流程，可用性由上游判断。

共享控制为整次生成生效：stability 默认 0.5、范围 0–1；similarity_boost 范围 0–1，省略／null 不指定，上游默认 0.75；seed 为 0–4294967295 整数，0 有效；language_code 为 ISO 639-1，不添加完整客户端白名单；apply_text_normalization 为 auto/on/off，默认 auto；timestamps 默认 false；output_format 保留 describe 中原 19 项，默认 mp3_44100_128，不支持 WAV 请求。previous_text / future_text 各最多 100 Unicode 字符；pronunciation_dictionary_locators 最多 3 项，每项词典 ID 和固定 version_id 必须非空；clone_strength 为 0–1，仅适用于已有且为模型微调的专业音色，不等同于 similarity，不创建声音。

enable_safety_checker 仅普通 Speech 可显式设置 boolean；custom Speech 的非 null false／true 均拒绝；Dialogue 不接收此字段。仅合同声明可空的控制在发送时省略 null，原需求仍保存；显式 false、0 和空数组保留。MiniMax 的默认音色、voice_setting、audio_setting、voice_modify、pronunciation_dict、language_boost 不向 ElevenLabs 转换。

查找已有音色可使用 `voices --skill aihub-audio`：鉴权读取完整目录及元数据，不扣生成 quota；不把目录当成白名单，也不为每次合成额外读取目录。选定 ID 原样用于本次请求，不写入 MiniMax 默认音色配置。

```json
{
  "operation": "audio-dialogue",
  "original_request": "按顺序用这两个已有音色合成对话，保留时间戳。",
  "model": "eleven-v4-text-to-dialogue",
  "requirements": {
    "inputs": [
      {
        "text": "欢迎收听今天的节目。",
        "voice": "existing-first-voice-id"
      },
      {
        "text": "很高兴来到这里。",
        "voice": "existing-second-voice-id"
      }
    ],
    "timestamps": true,
    "seed": 0
  }
}
```

上例替换为用户选择的真实已有 ID。task 顶层 inputs 仍表示媒体 URL 对象；对话台词必须放 requirements.inputs。直接 generate 则使用 API 参数 `{ "inputs": [{ "text": "你好", "voice": "已有音色ID" }] }`。Speech task 使用 prompt，直接 generate 使用 text。

## 旧 ID 迁移

`eleven-v4`、`eleven-v4-turbo`、`eleven-v4-custom-voice`、`eleven-v4-turbo-custom-voice` 不再接受新请求，没有别名或 Turbo 回退。按用途选择上表 Speech 或 Dialogue；Dialogue 必须准备完整台词数组，不能只替换模型名。个人模型列表不静默改写，先解释失效及迁移方法，明确修改后才保存。已有 task ID 和账单保留原名称，continue / resume / task 只查询与下载原结果，不用新模型重提。旧“上线后启用 eleven-v4 默认”的待办已撤销。
## 音乐

`music-async` 使用 `elevenlabs-music-v2.5` 时，提示词与 `requirements.composition_plan` 必须且只能有一个。提示词模式使用顶层 `prompt`（1–4100 字符），可选整数 `requirements.music_length_ms`（3000–600000 **毫秒**）和 `force_instrumental`。省略或 null 由服务决定，CLI 不补入时长。两种模式均可设置 `output_format`、`enable_safety_checker`、`timestamps`。统一目录保留 25 种编码；**官方 Music 仅 MP3／Opus，PCM／μ-law／A-law 保留 Fal**，不能宣称所有渠道支持全部枚举。默认 mp3_48000_192。

Fal 不支持 `timestamps` 字段，显式 `false` 也会被能力检查拒绝；不需要此能力时省略该字段。不得把用户明确要求的时间戳删除后提交。生产的 3000ms 请求分别得到官方 3.024s 和 Fal 6.024s 音频，均按 1 分钟结算；请求时长、实际时长与计费分钟分别报告。

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

TTS 的 timestamps、alignment、normalized_alignment、voice_segments 和 Music 的 composition_plan、song_metadata、words_timestamps 保存在任务记录并通过 result_metadata 暴露；run 位于 result.result_metadata。Speech / Dialogue 原样保留 timestamps、独立且可 null 的 alignment / normalized_alignment，以及完整 voice_segments：voice_id、start_time_seconds、end_time_seconds、character_start_index、character_end_index（exclusive）、dialogue_input_index。不重新累计或从 normalized_alignment 伪造原文对齐；原文 alignment 为 null 时 timestamps 为 []。历史任务分段和空段继续保留。未返回 lyrics / duration / seed 时不补造。

Spec #28 四模型各为 $0.00008/实际 Unicode 字符（$0.08/1000），不补千；Dialogue 累计各段 text，含标签、空格和标点，不计音色 ID、前后文和控制。最终用量以实际 Billing Event／账单为准，不从原文长度填补缺失账单。Music $0.60/实际解码输出分钟，向上取整。Scribe V2/V3 在分组倍率 1 时每秒 $0.000136，非空 keyterms 为 $0.000176，按响应 audio_duration_secs 向上取整秒。实际扣费以服务账单及账户倍率为准，不从请求时长、时间戳末端或 MP3 padding 推导权威账单；缺少上游成本不阻塞客户结算。旧 PCM/WAV 诊断不是官方 Music 当前能力，Opus 可为 Ogg，按实际容器保存。
