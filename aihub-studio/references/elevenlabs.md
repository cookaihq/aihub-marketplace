# ElevenLabs 语音、对话、音乐与转写

Studio 6.0.0 对齐 Gateway Issue #29 的合同，部署基线为 **Gateway v0.9.16（2026-11-13 已上线）**，对应[在线文档](https://docs.aihubmax.com/pages/zh/api-manual/audio-series/elevenlabs/eleven-v4-text-to-speech)已发布。线上任务沿用既有账号检查、付费授权和提交流程；使用其他 Gateway 入口时先核对合同版本。服务端上线与客户端生产业务验收分别记录。

先按[模型选择与恢复](model-selection.md)执行 describe → plan → run。内置 TTS 为 `eleven-v4-text-to-speech`，对话为 `eleven-v4-text-to-dialogue`，ASR 为 `paraformer-v2`，三个音乐场景为 `suno-v6`；本页 ElevenLabs Music 需显式或配置选用；用户显式型号、个人有序列表及保存任务优先。本页不将新增控制写入个人配置。

## 参数迁移

| 旧参数 | 新请求 |
| --- | --- |
| Speech `voice` | 必填 `voice_id`，无默认音色 |
| Dialogue `inputs[].voice` | 必填 `inputs[].voice_id`，保持顺序 |
| Speech 平铺 stability / similarity_boost / clone_strength | `voice_settings` 对象内同名字段 |
| Dialogue 平铺 stability / similarity_boost / clone_strength | `settings.stability` / **`settings.similarity`** / `settings.clone_strength` |
| Speech `future_text` | `next_text`；Dialogue 仍为 `future_text` |
| Scribe v2 `audio_url` | `source_url` 或 multipart `file` 二选一；v3 保持 `audio_url` |
| Music `duration` 秒制 | 歌曲 `music_length_ms`、段落 `duration_ms`，均为整数毫秒 |

旧字段（含 null）明确拒绝并给出迁移提示；未知嵌套字段也拒绝。不设长期别名、不自动删参、截断、换音色或换型号。已受理任务与账单沿用原合同；continue / resume / task 只查询和下载原结果，不按新默认值重建或重发历史请求。

## Speech 与 Dialogue

| 用途 | 普通模型 | 支持已有私有音色的模型 | 输入 |
| --- | --- | --- | --- |
| 单段语音 `audio-tts` | `eleven-v4-text-to-speech` | `eleven-v4-text-to-speech-custom-voice` | task 的 prompt 原样映射为 API text；requirements.voice_id 必填 |
| 多音色对话 `audio-dialogue` | `eleven-v4-text-to-dialogue` | `eleven-v4-text-to-dialogue-custom-voice` | requirements.inputs 原样映射 API inputs；省略 prompt |

两款 Speech 的 text 都为 1–10000 Unicode 字符，含标签、空格与标点；voice_id 必须是用户选定、非空白的已有音色原始 ID。两款均可传可空的 enable_safety_checker，显式 false 保留。Speech 不接收 inputs。

Dialogue inputs 是非空有序数组，每段必填非空 text 与非空白 voice_id，最多 10 个不同 ID；重复 ID 只计一次，可超过 10 段。总文本**建议不超过 2000 字符**，更长内容有截断或失败风险；保留用户原文，不作为硬限制或自动拆分。整组一次提交，不跨账号拼接。Dialogue 不接收顶层 text、voice_id 或 enable_safety_checker。

Speech 可选 voice_settings：stability 默认 0.5、similarity_boost 默认 0.75、clone_strength 可选，均为可空的 0–1。Dialogue 可选 settings 使用 stability、**similarity**、clone_strength，范围及默认值相同。设置对象省略或 null 时保持省略，沿用音色已保存设置；传空对象与省略不同，不能主动补对象。对象内 null 原样保留，不替换为 0；false、0、空数组继续保留。clone_strength 仅适用于已有的 v4 专业克隆音色，本 Skill 不提供创建、训练或声音克隆。

共用 seed 为整数 0–4294967295，language_code 可选；apply_text_normalization 为 auto/on/off，默认 auto；timestamps 默认 false；output_format 默认 mp3_44100_128，完整 28 项以 describe 为准，包括 WAV 各采样率、mp3_24000_48、pcm_32000。previous_text 和 Speech next_text / Dialogue future_text 不再有 100 字符硬限制，也不计正文字符费。pronunciation_dictionary_locators 最多 3 项，每项词典 ID 和固定 version_id 均须非空。

Speech audio_effects 可包含可空非空字符串 filter_preset_id、environment_id、background_noise_id，以及 distance（0–1，默认0）、send_level（0–1，默认1）、pan（-1–1，默认0）。environment_id 非 null 或 pan 非零时不能使用 pcm_、ulaw_、alaw_ 输出；不为适配音效改变用户格式。音效不另加客户费用。

custom 表示支持已有私有音色，也可使用公共音色；普通模型不做公私分类预查，可用性由服务端核实。Dialogue 必须能在同一执行账号访问整组音色。原始 ID 不建立别名或跨来源映射，不承诺永久可用、账号间可移植或用户间隔离。`audio_voice_unavailable` 时停止，不换音色或型号。

`voices --skill aihub-audio` 鉴权读取完整目录及元数据，不扣生成 quota；目录不是白名单，不为每次合成额外查询。选定 ID 仅用于当前请求，不写入 MiniMax 默认配置。MiniMax 默认音色及 voice_setting、audio_setting 等不向 ElevenLabs 转换。

```json
{
  "operation": "audio-dialogue",
  "original_request": "按顺序用两个已有音色合成对话。",
  "model": "eleven-v4-text-to-dialogue",
  "requirements": {
    "inputs": [
      {"text": "欢迎收听。", "voice_id": "existing-first-voice-id"},
      {"text": "很高兴来到这里。", "voice_id": "existing-second-voice-id"}
    ],
    "settings": {"stability": 0, "similarity": 0.75},
    "seed": 0
  }
}
```

替换为用户选择的真实 ID。task 顶层 inputs 仍表示媒体 URL 对象，对话台词放 requirements.inputs；直接 generate 使用 API inputs / text。

旧 `eleven-v4`、`eleven-v4-turbo` 及其 custom 变体不接受新请求，没有别名或 Turbo 回退。按用途迁移模型及完整参数；不静默改写个人列表。历史 ID 继续可查询。

## Music

`music-description` / `elevenlabs-music-v2.5` 的 prompt 与 requirements.composition_plan 严格二选一。prompt 为 1–4100 非空白字符；可选整数 music_length_ms（3000–600000毫秒）及 force_instrumental。省略时长由服务决定，不构造时长默认值。

计划模式不填顶层 prompt。composition_plan.chunks 按序提供 1–30 段，每段必填 text、duration_ms（整数3000–120000）、positive_styles 字符串数组；总时长3000–600000毫秒。text 可空，最多30行、每行200 Unicode字符；以 `[` 开头时须有1–100字符的完整 `[段落名]`。可选 negative_styles、context_adherence（low/medium/high）。风格列表没有额外50项限制。seed 仅用于计划，整数0–2147483647，不保证复现。计划中显式 force_instrumental（**包括 false**）及非 null music_length_ms 均拒绝。

参考音频放在具体段落 audio_reference，audio_url 为公开 HTTP(S) URL；start_ms 为非负整数，end_ms 大于 start 且窗口不超过30000毫秒。省略 end 采用 start 后30秒或音频结尾，以较早者为准。可选 strength 为 low/medium/high/xhigh。不另行裁切或直接请求上游。

output_format 默认 **auto**，解析为 mp3_48000_192，完整26项见 describe。sign_with_c2pa 默认false，仅 auto/MP3可为true；不为签名改变格式。timestamps 可空，显式false也保留其完整请求含义。参考音频、详细结果及其他组合由 Gateway 核对当前可用来源，不能从目录枚举推断一定可执行，也不删参兜底。

```json
{
  "operation": "music-description",
  "original_request": "按两段计划创作纯音乐。",
  "model": "elevenlabs-music-v2.5",
  "requirements": {
    "composition_plan": {"chunks": [
      {"text": "[Intro]", "duration_ms": 10000, "positive_styles": ["ambient", "soft piano"]},
      {"text": "", "duration_ms": 15000, "positive_styles": ["ambient"], "context_adherence": "high"}
    ]},
    "seed": 42
  }
}
```

旧 Lyria 的 inputs.images / image_urls、negative_prompt 无直接映射；未知字段或未定位段落的 inputs.audios 拒绝。明确指定 lyria-3-pro-preview 的描述创作保持 Gemini 原生协议。歌词时间戳、composition_plan、song_metadata 仅在实际返回时保存，不伪造详细结果。

## Scribe

显式选 scribe-v2 / scribe-v3，inputs.audios 恰好一个 URL 或本地路径。v2 URL 映射为 JSON **source_url**，v3 为 audio_url；本地使用 multipart file，与 URL 二选一。v2要求音频至少100毫秒、小于5GB；客户端直接上传另有 **256 MiB整文件内存保护**，更大输入使用可访问 URL，既有 upload 通道仍受自身限制。不套用 Paraformer 分段、转码或声道字段，不自动将v3降为v2。

v2默认 diarize=false、tag_audio_events=true、timestamps_granularity=word、no_verbatim=false、file_format=other。file_format也支持 pcm_s16le_16（16kHz、16位小端单声道PCM）。num_speakers（1–32）与diarization_threshold（0.1–0.4）互斥，均要求显式diarize=true。temperature可选0–2，不强制填默认值；seed为0–2147483647。timestamps_granularity和no_verbatim不可为null。language_code去首尾空白并转小写，2–3个字母；普通话使用zh/zho，不用cmn。

v2 keyterms最多1000项，每项1–50 Unicode字符、最多5词，禁止 `< > { } [ ]` 和反斜杠；不截断。detect_speaker_roles要求diarize=true且非多声道。transcript_edit最多2000字符，非空时不可与实体处理或多声道合用。use_multi_channel最多5个实际声道，不可与diarize、人数、阈值或pcm_s16le_16合用；声道数由服务端检查，不用配置猜测。

entity_detection / entity_redaction接受单字符串或字符串数组：all、pii/phi/pci/other/offensive_language类别或具体类型，完整类型见describe。redaction展开后必须为detection子集；原选择原样发送。检测结果保留entities，打码可能不返回entities，不填造结果。

```json
{
  "operation": "audio-transcribe",
  "original_request": "用 Scribe v2 转写并识别说话人角色。",
  "model": "scribe-v2",
  "inputs": {"audios": ["./meeting.wav"]},
  "requirements": {"diarize": true, "detect_speaker_roles": true, "keyterms": ["Gateway"]}
}
```

**v3继续原合同、默认值和收费**：audio_url或file，diarize默认true，keyterms最多100；另支持secondary_language_codes、numbers_format，不接受v2扩展。nullable控制按原合同处理。multipart数组以JSON数组字符串提交，不逗号拼接；false/0保留。

## 结果、恢复与费用

提交到 POST /e/v1/audios/generations，用 GET /e/v1/tasks/{task_id}查询。生成成功但核账尚未结束时可能仍processing，只查询原ID。run用continue，task记录用resume，已知ID用task；超时未知、下载失败、存储或账务恢复均不重复生成。及时下载，链接没有固定24小时保证。

requested_options_unavailable / unsupported_parameters停止自动切换，完整展示message、unsupported_parameters、suggested_remove_parameters（含嵌套路径）。让用户选择保留要求稍后处理，或明确修改后新建请求；建议移除项不授权自动删参。无效音色audio_voice_unavailable同样停止。退款只转述实际证据。

音频按实际内容、ffprobe及返回的采样率/声道/MIME核验，不按URL后缀或请求格式猜容器；Opus可封装Ogg。无法解析的原始编码保持download_failed，保留原任务与URL供恢复。

原始任务和完整Scribe JSON均保存，保留words[].speaker_id的agent/customer、起止时间、空白、事件、edited_transcript成功或错误对象、entities及transcripts各声道。多声道audio_duration_secs可能是各声道合计，不当作文件时长。展示text不替代完整JSON。result_metadata暴露真实扩展字段；usage原样显示（run在result.usage），例如credits_reserved仅为预扣，不能冒充最终扣费。

Speech/Dialogue原样保留timestamps、可null的alignment/normalized_alignment和voice_segments，包括历史空段；不从规范化对齐反造原文。Music仅保留真实返回的composition_plan、song_metadata、words_timestamps。未返回时间戳、歌词、时长、种子或详细元数据时不补造。

收费以服务端提交时的模型价格及分组快照为准，客户端不硬编码覆盖管理员合法价格，零倍率仍有效，历史账单不重算。

| 用法 | 计量 |
| --- | --- |
| 四个v4 | 提交正文Unicode字符，含标签、空格、标点；Dialogue累计各段text，不计ID、设置、前后文，不补齐千字符；当前基准$0.00008/字符 |
| Music | 真实完整输出时长向上取整分钟，当前基准$0.60/分钟；请求时长只用于预扣估算 |
| Scribe v2转写 | 完整时长向上整秒；非空keyterms选关键词价，不重复叠加；超过100项仅转写部分最低20秒 |
| v2角色识别 | 额外加保存的**基础价**10% × 计费时长 |
| v2非空改写 | 额外加保存的**基础价**30% × max(计费时长,10秒)，最低时长仅作用于改写组件 |
| v2多声道 | 按真实声道数，每声道各计完整时长向上整秒，最多5声道 |
| v2实体 | 无附加费 |

基础价与关键词价分别保存；角色和改写比例相加，不连乘、也不以关键词价为基数。例如4.2秒仅改写：转写5秒、改写组件10秒；101关键词的转写至少20秒。当前分组倍率1的Scribe基础/关键词示例为每秒$0.000136/$0.000176，仅为示例。最终账单只依据实际服务返回证据，不从请求长度、时间戳末端、MP3 padding或预扣字段推造最终价格。
