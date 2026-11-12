# 模型配置与可恢复的多模型执行

六个 Skill 的新任务使用 `plan` → `run` → `continue`。Agent 保存用户需求及素材用途，共用 CLI 读取当前 Skill 的配置，分别构造候选模型的参数，再按策略执行。旧 `generate`、`understand`、`native-music` 仍是指定单模型的入口；旧 `resume` / `task` 只查询和下载原任务。配置与上传方式见 [共用 CLI](cli.md)。

## 可选配置

凭证配置只需 `AIHUB_API_KEY`，服务地址固定为 `https://api.aihubmax.com`。下列业务选项独立于凭证配置，沿用相同的环境变量、项目文件、Plugin 全局文件、当前 Skill 普通全局文件的读取顺序：

| Skill | 有序模型列表 |
| --- | --- |
| aihub-image | `AIHUB_IMAGE_MODELS` |
| aihub-video | `AIHUB_VIDEO_MODELS` |
| aihub-audio | `AIHUB_AUDIO_MODELS` |
| aihub-music | `AIHUB_MUSIC_MODELS` |
| aihub-understanding | `AIHUB_UNDERSTANDING_MODELS` |
| aihub-document | `AIHUB_DOCUMENT_MODELS` |

列表用逗号分隔精确模型 ID，顺序就是优先级。首个非空来源整体替换低优先级列表，不合并、不追加内置模型。空项、重复 ID 报错。只解析当前 Skill 的模型列表；未配置时沿用对应 Skill 的内置选型，仅产生一个候选。本次用户明确指定模型时固定该模型，忽略配置列表并关闭 fallback。Agent 自己选出的推荐型号不能写成用户指定。

```dotenv
AIHUB_IMAGE_MODELS=gpt-image-2.5-flare,gpt-image-2.5-sunburst
AIHUB_MODEL_FALLBACK_POLICY=auto
AIHUB_MODEL_MAX_ATTEMPTS=2
```

| `AIHUB_MODEL_FALLBACK_POLICY` | 行为 |
| --- | --- |
| `auto`（默认） | 按序跳过能力不匹配或不可见候选；可确认的模型失败后尝试下一候选。 |
| `confirm` | 首个适用候选之后，每次实际切换到另一模型前暂停，列出模型及参数，取得用户确认后继续。预检跳过首个候选也算切换。 |
| `off` | 只尝试任务用途匹配的首个候选；其不可见、能力不符或失败时停止。 |
| `preflight_only` | 尚未提交生成时可以跳过不兼容或不可见候选；提交过一次生成请求后不再切换。 |

`AIHUB_MODEL_MAX_ATTEMPTS` 是可选正整数，包含首个模型。默认等于适用候选数；预检跳过、查询和下载不计数。每个普通候选最多提交一次，不循环列表；转写候选可包含多个分片，每片最多一次生成提交，次数限制仍按模型尝试计算。全局策略可在当前 Skill 的专用文件中覆盖；`doctor` 和 `models` 的 `model_selection` 提供实际值与来源。

## MiniMax Speech 默认音色

`AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID` 是可选单值，仅由 `aihub-audio` 的真实配置链读取，适用于 `speech-2.8-hd` 和 `speech-2.8-turbo`。没有内置默认音色。环境变量、项目文件、Plugin 全局文件及音频 Skill 专用回退沿用现有优先级；空白值回退到下一层。即使从其他 Skill 打开统一配置中心，该项仍显示音频 Skill 的值与来源。

新 `audio-tts` 计划和独立 `generate` 只在参数未提供 `voice_setting.voice_id` 时补入配置值，同时保留语速、音量等其他已传字段。显式音色优先；显式空值或无效值交给原参数校验，不用默认值掩盖错误。用户未指定音色时，Agent 不应自行填一个推荐值覆盖已配置默认值。`run.json` 冻结解析后的候选；`continue` 及旧任务恢复不会套用后来修改的默认音色，也不会重新生成已提交任务。

可在配置中心搜索、筛选、试听预设音色后选用，也可手填自定义 / 克隆音色 ID。ID 保留大小写和内部空格，例如 `Chinese (Mandarin)_Warm_Girl`；拒绝首尾空白和控制字符。音色库失败时保留已有值，未收录不代表无效。

收藏独立保存在 `~/.config/aihub-studio/settings.json` 的 `audio.minimax_speech.favorite_voice_ids`，最多 2000 个唯一 ID，每项不超过 512 字符。收藏只是候选列表，不参与自动选型、轮换或合成参数。点击星标保留草稿，需明确保存收藏；“使用此音色”只回填原编辑面板，需另行保存默认音色。关闭全局配置时不读取或保存收藏。样音从服务返回的受支持公开 HTTPS 地址播放，不提交生成请求。

## 任务 JSON

请求文件由 Agent 写在调用项目的任务目录中。`original_request` 保留用户原文，`prompt` 是提交给模型的提示词；后者不能代替前者。只在用户本次明确指定型号时填 `model`。

```json
{
  "operation": "image-generate",
  "original_request": "生成一张正方形插画：戴红围巾的橘猫坐在窗边，不要文字。速度优先。",
  "prompt": "正方形插画，一只戴红围巾的橘猫坐在窗边，画面简洁，无文字。",
  "image_priority": "speed",
  "requirements": {"resolution": "1024x1024"}
}
```

`audio-transcribe` 的 `inputs.audios` 接受本地路径或 HTTP(S) URL，由程序按[转写约束](audio-transcription.md)准备；其他操作的 `inputs` 只接受远程 HTTP(S) URL，本地文件先通过 `upload` 取得真实 URL。列表字段为 `images`、`videos`、`audios`、`files`；`mask` 是单个 URL。省略未使用字段，不放空列表。`requirements` 保存用户要求的输出参数，未知字段、无法保留的输入和参数冲突都会拒绝该候选，不能为了切换删除要求。

结果检查项单独使用 `review_requirements`（`id`、`text`、`priority=required|preference`），不发送为生成模型参数；用户批准的完整需求变更保存到 `requirement_revisions`（`request`、`user_confirmation`）。字段格式、默认开启的检查流程与每次结束后的关闭提示见 [结果检查与错误反馈](result-checks.md)。没有拆分项时仍检查完整用户原文，生成 prompt 不能代替原文。

| `operation` | 输入和用途 | 当前已验证的自动参数转换 |
| --- | --- | --- |
| `image-generate` | 提示词，静态文生图 | 默认 GPT Image 2.6 Flare / Sunburst；`resolution`、`quality`、`complexity`、`background`、`output_format`、`num_outputs`；省略尺寸为 auto，2.5 可显式选择 |
| `image-edit` | 提示词和 `inputs.images`，可选 `mask` | 默认 GPT Image 2.5 Flare / Sunburst；`resolution`、`quality`、`background`、`output_format`、`num_outputs`；2.6 不接受参考图或遮罩 |
| `video-text` | 文字 | Seedance 2.5、2.0 / Fast 对应文生型号 |
| `video-start-frame` | 一张固定首帧 `inputs.images` | 对应图生型号；不把参考图改作首帧 |
| `video-reference` | 参考图、视频或音频 | 对应参考生型号；2.0 只自动接入图片参考，视频/音频严格限制尚缺可验证的素材元数据 |
| `video-lipsync` | 一个视频和一个音频 | 默认 `sync-3`；仅可选 `sync_mode`。显式或配置的 `lipsync-2` 另支持 `active_speaker`、`temperature` |
| `video-avatar` | 一张图片和一个音频 | 默认 `fabric-1.0`；`resolution=480p/720p`，未指定为 `720p`，不接受提示词。显式或配置的 `omnihuman-1.5` 另支持提示词、`advanced`、`turbo_mode` |
| `audio-tts` | 提示词中的待朗读文本 | 默认 `eleven-v4`，prompt → text，独立 voice；显式 Speech 2.8 保留 `voice_setting` 等原参数，彼此不混用 |
| `audio-transcribe` | 原录音路径或 URL 的 `inputs.audios` | `paraformer-v2` / `paraformer-8k-v2`；按模型检查格式、大小、时长并自动分段，8 kHz 型号不接受 `language_hints` |
| `music-async` | 提示词或段落计划 | 默认 `elevenlabs-music-v2.5`，整数毫秒；显式 `lyria-3-pro` 保留图片参考与 `negative_prompt`，不向 ElevenLabs 转换 |
| `music-native` | 提示词 | `lyria-3-pro-preview`；不接收额外要求或参考素材，不与异步音乐静默互换 |
| `understanding` | 提示词及至少一种媒体输入 | 默认 `gemini-4-carbon`；从线上 LLM 注册表检查精确 ID 和所需媒体能力；`system_prompt`、`max_tokens`、`temperature` |
| `document` | 一个 PDF 的 `inputs.files` | `doc2x-v3`；`page_count`、`convert_mode`、`filename`、`formula_mode`、`merge_cross_page_forms` |

Seedance 视频的基础要求为 `duration`、`resolution`、`aspect_ratio`。未指定时固定为 5 秒、720p、9:16，再分别构造候选请求，避免各模型默认值不同。2.0 可额外设置 `seed`、`generate_audio`，但这两个字段不能无依据地传给 2.5。字段的枚举、条件必填和限制继续以 `describe` 及 CLI 校验为准。

C1/C2 使用各自的契约，不套用 Seedance 时长或比例。`sync-3` 的 `sync_mode` 可为 `bounce`、`loop`（服务默认）、`cut_off`、`silence`、`remap`。Fabric 音频最多 30 秒，实际音频决定视频时长；提交前核对素材时长。`models` 将账号列表中的 `fabric-1.0[480p]` / `fabric-1.0[720p]` 对应为生成型号 `fabric-1.0` 及 `available_resolutions`；请求保留指定分辨率，可见性不足时停止，不自动降级。理解模型以 `/e/v1/configs/llm_generations_models` 的能力为准；仅在通用模型列表可见不足以提交 llm-custom 请求。

配置一个模型 ID 不代表已接入其参数转换。CLI 先按任务用途筛选，再逐个检查；TTS 不能替代转写、首帧图生不能替代参考生成。不兼容型号会列出原因。有目录说明但尚无自动转换的型号，只能在用户明确选择且按其契约准备参数后使用旧单模型入口；不能借此绕过已经保存的多模型任务或确认要求。

`audio-tts` 另支持 `eleven-v4` / `eleven-v4-turbo` 及其 `-custom-voice` 变体的 prompt → text 映射；custom 必须显式提供已有音色 ID，不属于声音克隆。`music-async` 支持 `elevenlabs-music-v2.5` 的提示词或分段计划，时长使用整数 music_length_ms / duration_ms，拒绝旧秒制 duration。`audio-transcribe` 支持 `scribe-v2` / `scribe-v3` 的单 URL 或 multipart 本地文件输入，不使用 Paraformer 分段与转码；有 V3 的候选列表排除 V2，不能自动降级，需要 V2 时显式新建请求。

选择这些型号前读取并遵守 [ElevenLabs 参数与交付](elevenlabs.md)，包括模式互斥、nullable 控制、时间戳空段、实际容器和计费边界。官方 Music 仅 MP3/Opus，其余统一编码保留兼容渠道；不强制官方或静默移除参数。`describe.request_schema` 保留完整嵌套约束，`plan` 展示实际请求；新增型号不自动加入个人列表。requested_options_unavailable / unsupported_parameters 停止自动切换，保留完整错误与字段列表，交由用户决定修改要求或稍后处理。Gateway v0.9.15 正式上线后启用上述 TTS／异步音乐默认；ASR 和 Gemini 原生音乐默认保持原值，音频人工试听仍待评审。

## 执行与继续

```bash
AIHUB_PLUGIN_DIR="<实际 Plugin 目录>"
AIHUB_CALLER="aihub-image"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" plan --skill "${AIHUB_CALLER}" --request-file "/任务目录/request.json"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" run --skill "${AIHUB_CALLER}" --request-file "/任务目录/request.json" --wait-seconds 30
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" continue --skill "${AIHUB_CALLER}" --record "/任务目录/data/aihub-studio/20261106143025-任务摘要-run-a1b2c3d4/run.json" --wait-seconds 30
```

`plan` 只读配置和随包契约，不联网；转写的实际音频探测、快照与分片在 `run` 中完成。先检查输出的 `candidates` 与 `excluded` 是否忠实于用户需求。`run` 默认写调用项目的 `data/aihub-studio/`，也可传 `--output-dir`。在 Git 项目中开始写任务文件前确认输出目录被忽略。`run.json` 保存原始需求、候选请求、策略、尝试历史和确认；每次异步尝试在其 `attempt-N/aihub-UUID/` 下保存自己的 `task.json` 和 `files/`。

`continue` 读取已保存计划，不用新配置替换候选或策略；仍核对原 Skill、服务地址和密钥。每次调用的轮询预算由全部候选共享，最高 600 秒。进程中断后仍然恢复原任务；原生音乐无可查询任务 ID，提交结果不明时不能自动重发。

当 `status=confirmation_required` 时，Agent 向用户展示 `confirmation.model`、`params` 和失败原因，取得对这次切换的明确确认后，才可运行 `continue --record ... --confirm <confirmation.token>`。**输出的 `next_action` 含确认 token 不代表用户已经同意，不能直接执行。** 更改请求需要另建任务，不能编辑记录绕过确认。

| 新流程状态 | 下一步 |
| --- | --- |
| `delivered` | 读取独立的 `result_check`，按其状态完成检查；交付 `files`、实际型号、尝试摘要、检查结论和开启检查时的关闭提示。 |
| `confirmation_required` | 等用户确认当前候选后再提交。 |
| `submitted` / `waiting` / `query_failed` / `download_failed` / `partial` | 用 `continue` 恢复原任务；部分成功先交付已通过检查的文件。 |
| `preflight_failed` | 修复预检问题后继续；模型清单查询失败不等于某模型不可用。 |
| `submission_unknown` / `persistence_failed` | 保留全部记录及已知任务 ID；先核对原提交或按内层 `result.next_action` 恢复，不能再生成。 |
| `failed` / `no_compatible_model` / `attempt_limit` | 当前计划停止。报告 `attempts`、`excluded` 和已知任务 ID；不自动另建 run 来绕过限制。 |

只有明确的模型不可用/能力不支持错误可切换：已结束任务的 `model_unavailable`、`model_not_support_capability`，或确定未受理的 HTTP 422 同类错误。已结束且未返回结构化错误的任务也可按策略切换。鉴权、余额、内容拒绝、未知服务错误、超时和提交结果不明不触发自动切换；查询失败、下载失败、画面或音频不符合需求也不触发重新生成。真实服务返回的分类不明确时停止并报告，不能根据文字猜测可安全重发。
