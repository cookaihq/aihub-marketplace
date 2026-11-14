# 共用 CLI、配置与任务恢复

WorkBuddy 的 Plugin 安装、查询或更新按 [workbuddy-install.md](workbuddy-install.md) 使用当前应用的原生套件管理；给用户手动操作步骤时按该说明同时展示随包截图，指明“技能 → 套件 → 市场名称右侧的＋”。禁止另起 CodeBuddy CLI（包括帮助或校验命令）。下面的 `scripts/aihub.mjs` 是业务程序，使用 AIhub 配置；它不管理宿主插件安装。

五个 Skill 共用 Plugin 根目录下的 `scripts/aihub.mjs`。每会话的默认选择检查先按 [default-skills.md](default-skills.md) 执行；该离线入口只需要 Node，不读取业务凭证、不要求 ffprobe。业务调用再按“首次配置、缺项与配置修复”核对来源。以下命令中的 `AIHUB_PLUGIN_DIR` 必须替换为实际安装目录，`AIHUB_CALLER` 固定为当前 Skill 的名称：`aihub-image`、`aihub-video`、`aihub-audio`、`aihub-music`、`aihub-understanding`。当前工作目录是用户任务目录，决定项目配置从哪里读取。

**Windows 原生统一使用 `scripts/aihub.ps1` 入口。** 它检查 Node.js 18+ 并固定入口/模块的路径解析选项，避免 Codex 默认沙箱中 Node 在启动前遍历不可列举的用户目录而报 `EPERM`；不修改沙箱、权限、环境配置或 cwd。下面及各 Skill 的 Bash 示例在 Windows 中将 `node ".../scripts/aihub.mjs"` 换为 `& ".../scripts/aihub.ps1"`，参数保持原样；无需由 Agent 每次补 Node 选项。纯凭证请求按下一节使用 `config-check --credentials-only`，不先跑 doctor。

```powershell
& "<实际 Plugin 目录>/scripts/aihub.ps1" config-check --skill aihub-image --credentials-only
```

```bash
AIHUB_PLUGIN_DIR="<实际 Plugin 目录>"
AIHUB_CALLER="aihub-image"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" doctor --skill "${AIHUB_CALLER}"
```

程序使用 Node.js 18 或更新版本；媒体文件检查需要 `ffprobe`。`doctor` 只检查本机运行条件和配置来源，不请求 AIhub，也不证明 Key 有效或生成渠道可用。`generate` 在提交前也会检查媒体工具。macOS 缺少 `ffprobe` 时安装命令是 `brew install ffmpeg`，程序不会自动安装系统工具。发行产物包含编译后的 JavaScript 和模型目录，安装者不需要运行 `npm install`，也不需要原 MCP 服务。

## 首次配置、缺项与配置修复

先按[统一凭证检查、Setup 衔接及最小回退](credential-setup.md)执行。保留真实业务 cwd、caller 与关闭全局的选择；检查无需媒体工具或线上请求。

## 配置来源

凭证配置只需 `AIHUB_API_KEY`。业务行为另支持当前 Skill 的 `AIHUB_<类型>_MODELS`、`AIHUB_MODEL_FALLBACK_POLICY` 和 `AIHUB_MODEL_MAX_ATTEMPTS`，完整名称与语义见 [模型配置](model-selection.md#可选配置)。`AIHUB_RESULT_CHECK_*`、`AIHUB_ERROR_REPORT_THRESHOLD` 与 `AIHUB_SUPPORT_URL` 见 [结果检查与错误反馈](result-checks.md)，不属于 Secret Book 的凭证声明。每个变量独立按以下顺序使用首个非空值，模型列表整体替换、不跨层合并：

1. 当前进程环境变量。
2. 当前工作目录 `.env.local.aihub-studio`，五个 Skill 共用。
3. 当前工作目录 `.env.aihub-studio`，五个 Skill 共用。
4. 当前工作目录 `.env.local`。
5. 当前工作目录 `.env`。
6. 自动读取 `~/.config/aihub-studio/<skill-name>/.env.local`。
7. `~/.config/aihub-studio/<skill-name>/.env`。
8. `~/.config/aihub-studio/.env.local`。
9. `~/.config/aihub-studio/.env`。
10. `~/.config/<skill-name>/.env`，只补齐以上来源中缺失或为空的字段。

`<skill-name>` 必须是当前调用方的真实名称，与其 `SKILL.md` frontmatter `name` 一致。Plugin 名固定为 manifest 的 `aihub-studio`，不随安装目录、Agent 或版本变化。缺项、空值及空子目录继续回退；Plugin 目录存在或其中已有部分字段，也不阻断其他缺项读取第 10 层。文件存在但无法读取时明确报错。不向父目录搜索，不读取普通 Skill 目录的 `.env.local`，不扫描兄弟 Skill、旧产品别名目录、其他 Plugin 或任意 `.env.*`。普通字段分别取值；密钥须属于固定 AIhub 服务。业务命令要求有效的 `--skill`。无调用方的配置检查显式使用 `config-check --plugin-only`，只读项目和 Plugin 共享文件，跳过所有 Skill 专属层；与 `--skill` 互斥。

首次新增配置时，个人全局配置是 AIhub 已确认的默认方案，共享配置保存到 `~/.config/aihub-studio/.env`。需要一个 Skill 使用不同全局值时使用其子目录 `.env` 或 `.env.local`。写入前确认具体作用域并保留已有内容；仅提供凭证或允许读取不代表授权持久化。首次选择项目保存默认使用调用工作目录的 `.env.local.aihub-studio`，明确选择普通 `.env.local` 时沿用；修复已有字段写回其实际来源文件。普通 `.env.aihub-studio` 可编辑非 Secret 项或修复已有密钥。写入 Secret 前检查未跟踪且被忽略。

3.0.0 起不读取项目 `.env.<skill-name>` 和 Plugin 全局根 `.env.<skill-name>`，也不接受它们作为修复或删除预览目标。需要迁移时先由用户确认准确源和受支持目标，不自动读取、搬移或删除退出文件；保留的 Skill 子目录和普通 Skill 全局回退继续生效。

全局读取由加载器自动执行，正常调用不加参数。`--no-global-config` 关闭本次命令的全部五个全局层，同时跳过 Plugin 目录和普通 Skill 目录；`--use-global-config` 仅为旧命令兼容，不再是必填项，两者同时传入报冲突。正常请求不需要逐次向用户征求读取全局文件的许可。`doctor` 报告每个字段的最终来源，包括普通 Skill 回退文件的实际路径，但不验证账号鉴权或生成通道。

已有 `~/.config/aihub-image/.env` 等当前 Skill 配置无需迁移即可作为末层来源。同一用户下，同名 Skill 的独立分发与 Plugin 分发可能共用这一文件；Plugin 配置优先。迁移只是可选整理操作，须先列出准确源与目标，让用户确认后再写入；相同配置可合并到共享文件，不同配置分别放到已选定的 Skill 子目录。默认写入位置仍在 Plugin 目录，加载器不创建、复制、移动或删除配置。用户文件夹由 Node `os.homedir()` 定位，Windows 原生与 WSL 使用各自用户目录；具体平台路径见随包 README。

从旧 `aihub` Plugin 迁移时另行处理 `~/.config/aihub/`：新加载器只认 manifest 的 `aihub-studio`，旧 Plugin 目录不会作为回退来源。用户确认迁移后，将实际选定的旧共享文件及 Skill 子目录映射到 `~/.config/aihub-studio/` 下相同相对位置；旧根 Skill 后缀另行选择受支持的子目录目标，保留共享与专用覆盖关系。先检查目标文件和更高优先级来源，列出新增或替换项；不得自动搬迁、覆盖新配置或将不同账号合并。普通 Skill 文件、项目文件及 `AIHUB_*` key 无需因 Plugin 改名而移动或改名。写完运行 `config-check` 核对新 consumer 与实际来源；配置迁移不授权重发业务请求。

服务地址固定为 `https://api.aihubmax.com`。用户只配置 `AIHUB_API_KEY`；环境变量和各层配置文件中的旧 `AIHUB_BASE_URL` 均被忽略，来源报告不再将地址列为配置字段。原文件保持不变。官方固定地址的已有任务仍可恢复；其他服务地址的旧记录在联网前拒绝恢复，提示使用原服务客户端继续。配置缺失或鉴权失败时明确报告。

`.env` 文件只解析 `KEY=value`、单引号或双引号包裹的值、整行注释和空行；同名项取最后一次，不执行 shell 展开或命令替换。不要用 `source` 加载配置，不把 API Key 放入命令行参数、参数 JSON、任务记录或聊天回复。

## 模型与参数

新任务先读 [任务 JSON、模型配置与切换](model-selection.md)，使用 `plan` / `run` / `continue`。选择顺序是本次用户明确型号、当前 Skill 配置列表、内置任务选型；Agent 不应先选内置型号再写入 `model`，否则会覆盖用户的配置。`plan` 不联网，`run` 在提交前检查当前可见性。只有模型清单可见不能证明通道或效果可用。

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" models --skill "${AIHUB_CALLER}" --media image
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" models --skill "${AIHUB_CALLER}" --media video --keyword "<搜索词>"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" describe --skill "${AIHUB_CALLER}" --model "<线上模型 ID>"
```

`--media` 可取 `image`、`video`、`audio`；E1 使用 `models --media understanding` 查询独立的 LLM 注册表。`models` 的 `preferred` 仍是随包目录推荐；生效的列表和策略以 `model_selection` 为准，具体任务候选以 `plan` 为准。没有配置时按 [图片 Skill](../skills/aihub-image/SKILL.md#选择图片模型) 或 [视频 Skill](../skills/aihub-video/SKILL.md#选择视频模型) 的规则选择；C1/C2 保留各自专用用途。

`describe` 离线读取随包模型目录说明字段，无需 API Key。只有 `catalog_only` 中的目录记录不能证明模型在线可用，`availability_known: false` 或 `status: availability_unknown` 应报告可用性未知。账号模型列表使用 `/v1/models`；生成、任务和专用配置查询使用 `/e/v1/`。提交时使用 `models` 返回的请求型号，不自行泛化模型名。Fabric 是已核实的特例：账号的带分辨率 ID 对应生成型号 `fabric-1.0` 和 `resolution`，可用分辨率列在 `available_resolutions`。新流程只在已配置且适用的候选间按保存的策略切换；不得自动追加旧版本或其他模型。Plugin 会在提交前拒绝图片增强/材质/Profile、视频高清放大（B10）/插帧/Topaz、Sora 角色、字幕、提示词数字人和旧声音克隆模型；ElevenLabs 音色设计与创建使用专用流程。

当前无配置时，静态文生图使用 GPT Image 2.6，编辑使用 2.5；图片列表的 default_for 区分 image-generate 与 image-edit。2.6 拒绝参考图、遮罩、markup 和非静态格式，省略尺寸为 auto，允许独立的 complexity。TTS 默认 eleven-v4-text-to-speech，多音色对话默认 eleven-v4-text-to-dialogue；三类音乐场景默认 suno-v6，ASR 默认 paraformer-v2。

以下为保留的单模型底层入口，供旧任务流程或用户明确选择尚无自动参数转换的型号使用，**不读取配置列表来换模型**。D1 的 `speech-2.8-hd`（TTS）、`paraformer-v2`（ASR）和 D2 的 `lyria-3-pro` 使用 `generate --media audio`；`lyria-3-pro-preview` 使用 `native-music`。E1 先查询独立 LLM 注册表再调用 `understand`，必须含媒体内容块，纯文本请求属于 F 组并拒绝。

`eleven-v4-text-to-speech` / `eleven-v4-text-to-dialogue`、两者的 `-custom-voice` 变体、`elevenlabs-music-v2.5` 和 `scribe-v2` / `scribe-v3` 均使用异步音频路径，完整参数及上线条件见 [ElevenLabs](elevenlabs.md)。新任务优先使用 `plan/run`；单模型 `generate` 的 TTS 参数为 text，新流程 prompt 原样映射为 text。custom-voice 必须提供已有音色 ID，不创建或克隆声音。`voices --skill aihub-audio` 通过鉴权配置接口读取完整 ElevenLabs 音色目录及元数据，不扣生成 quota，也不限制为官方白名单。

ElevenLabs 音乐歌曲/段落时长分别使用整数 music_length_ms / duration_ms（毫秒），旧 duration 秒制字段明确拒绝；30 秒歌曲须改为 music_length_ms: 30000。已受理任务继续原 ID，未提交旧请求迁移后重新 plan。Scribe 的 inputs.audios 恰好一个 URL 或本地路径，分别以 V2 source_url／V3 audio_url 或 multipart file 提交；不套用 Paraformer 分段/转码，不自动把 V3 降为 V2。`describe.request_schema` 保留嵌套计划、范围及可空字段约束，Scribe 的 file 表示本地文件路径。

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" models --skill aihub-understanding --media understanding
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" understand --skill aihub-understanding \
  --params-file "/任务目录/understanding.json" --output-dir "/任务目录/outputs" --wait-seconds 30
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" native-music --skill aihub-music \
  --model lyria-3-pro-preview --params-file "/任务目录/gemini-music.json" --output-dir "/任务目录/outputs"
```

根据 `describe` 选定用户实际需要的请求变体。必须字段与条件必填字段不是同一集合；互斥输入不得同时填写。Seedance 2.5 参考生视频的 `image_urls`、`video_urls`、`audio_urls` 是可混合的参考素材列表，要求至少一项非空，不属于三选一。它的文生和首帧图生型号分别有独立输入契约，不能为了通过校验丢弃用户素材。三个型号均为整数 `4–30` 秒，`1080p` 仅接受 `5`、`10`、`30` 秒；不静默改用户的时长或分辨率。

图片型号和 `quality` 分开选择；参考图、透明背景或 `mask_url` 不自动决定 Flare/Sunburst。参数保存在用户任务目录的 JSON 文件中；旧 `generate` 的模型 ID 通过 `--model` 传入，不在参数 JSON 重复填写；旧 `understand` 则在其参数 JSON 中填写 `model`、`prompt`、`content`。新 `run` 使用另一套任务 JSON，不能混用两者。不在 shell 命令里拼接 prompt 或媒体 URL。参数名、枚举、尺寸和音色从该模型说明取得，不照搬其他模型。

## 上传输入文件

先完成 `doctor`。当所选模型需要远程输入，而用户只提供本地文件时，写一个上传 JSON 文件并调用：

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" upload --skill "${AIHUB_CALLER}" \
  --input-file "/任务目录/upload-input.json"
```

JSON 中 `path`、`url`、`base64` 必须且只能选一个；可选 `file_name`。此通用上传入口的本地文件须非空且不超过 20 MiB；这是客户端适配器上限。录音转写直接把原路径交给 `audio-transcribe` 的 `plan/run`，按[大文件转写](audio-transcription.md)自动处理，勿先手工分片。其他较大输入使用模型支持且远端可访问的 URL。本地文件示例：

```json
{
  "path": "/任务目录/reference.png",
  "file_name": "reference.png"
}
```

读取上传结果中的实际文件地址，再按所选生成模型说明填入参数。不要猜测上传响应 URL 或把文件系统路径作为公开 URL。上传或生成请求若返回结果不明，不自动再次上传或生成。

## 旧单模型提交与继续查询

本节保留 `task.json` 的恢复契约。新任务的 `run.json` 和可确认切换使用 [多模型执行流程](model-selection.md#执行与继续)，不能把 `continue` 描述为只查询：它可能按保存策略提交下一候选。

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" generate --skill "${AIHUB_CALLER}" \
  --media image --model "<线上模型 ID>" \
  --params-file "/任务目录/params.json" --output-dir "/任务目录/outputs"
```

`generate` 默认不轮询尚未完成的任务。程序先保存任务记录，拿到任务 ID 后立即写回记录；提交直接返回完成状态时，当次命令会下载并检查文件后返回。响应包含 `record` 时保留其绝对路径；尚未完成交付时，下一步使用该记录恢复：

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" resume --skill "${AIHUB_CALLER}" \
  --record "/任务目录/outputs/aihub-UUID/task.json" --wait-seconds 30
```

`resume` 默认等待预算为 30 秒；`generate`、`resume`、`task` 的单次 `--wait-seconds` 最高 600 秒。该值控制远端任务等待，不表示全部媒体下载也必须在同一时长完成。下载有独立的超时与重试限制。

一次等待到期且状态仍是 `waiting` 时，可根据用户任务继续下一次有界等待；中断或本轮无法继续时交付记录路径与当前任务 ID。不能把等待到期当成远端失败，更不能重新生成。

只有用户提供任务 ID 而没有记录时，使用同一 AIhub 环境和账号导入任务：

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" task --skill "${AIHUB_CALLER}" \
  --task-id "<现有任务 ID>" --media image --output-dir "/任务目录/outputs" --wait-seconds 30
```

`task` 查询已有任务并创建可恢复记录，不提交新生成请求。`resume` 使用记录中的任务信息；不要修改记录来绕过配置身份检查。配置路径变更不改变任务身份；恢复时仍须保持原 Skill、服务地址与密钥。需要本次禁用全局配置时使用 `--no-global-config`。

## 读取结果并决定下一步

程序输出结构化 JSON。`doctor`、`describe`、`plan`、成功的 `models` 和 `upload` 使用 `status: ok`。下表适用于旧单模型入口和新 run 的内层 `result`；新 run 顶层状态见 [多模型状态表](model-selection.md#执行与继续)。应读取 JSON 状态，不仅看进程退出码。

| `status` | 含义与下一步 |
| --- | --- |
| `submitted` | 已拿到远端任务并保存记录；用 `resume` 查询同一任务。 |
| `waiting` | 远端任务尚未完成，本次等待预算已结束；继续恢复或交付恢复路径。 |
| `query_failed` | 本次查询失败；保留原任务，用 `resume` 重试查询。 |
| `recovery_failed` | 恢复命令的配置、记录读取或锁检查失败；保留已有 `record` 或 `task_id`，修复本地错误后重试恢复。该状态不表示原任务未创建，不能重新生成。 |
| `persistence_failed` | 远端任务已知，但本地记录保存失败；保留 `task_id`、`record`、`remote_status` 和 `record_saved: false`。按 `next_action: task` 的参数，在修复存储问题后用 `task` 恢复已有任务，不能重新 `generate`。 |
| `submission_unknown` | 无法确认提交是否生效；报告结果不明并保留记录，不能自动重新生成。 |
| `not_submitted` | 本次提交未成功；根据错误修正输入或配置后再决定是否提交。 |
| `remote_failed` | 远端任务已失败；旧单模型入口只报告 ID 和原因。新 run 由保存策略和结构化错误分类决定是否切换，Agent 不自行重发。 |
| `download_pending` | 已有结果待下载；恢复原记录。 |
| `download_failed` | 全部下载或校验失败；保留结果信息，用 `resume` 继续下载。 |
| `partial` | 只有部分文件下载并校验成功；交付 `files`，列出 `failed`，继续恢复原记录。 |
| `delivered` | 全部结果文件已下载并通过程序检查；新 run 同时返回独立的 `result_check`，按 [检查流程](result-checks.md) 完成后交付结论与文件。 |

结果为空、错误页或无效媒体不能作为成功文件交付。程序检查非空、适用的响应长度、实际媒体类型和 `ffprobe` 可解析性；这不等于逐帧解码，也不证明视觉或音频内容符合用户要求。语义检查默认开启，由宿主读取实际媒体并执行 `review-submit`；`auto` 模式下宿主能力不足时执行 `review --provider aihub`。完成检查必须转述 `user_notice`，告知可通过对话关闭；不能只保存到 JSON。旧单任务记录缺少原始需求时报告无法检查，不能用生成 prompt 冒充。任务特有的 `seed`、`lyrics`、`degraded_reason`、`map_type`、`result_type`、`duration` 和 `resolution` 等字段会在 CLI 结果的 `result_metadata` 中返回；完整远端任务仍保存在 `task.json`，这些字段不是单独的业务能力。

ElevenLabs TTS 的 timestamps、alignment、normalized_alignment、voice_segments 及 Music 的 composition_plan、song_metadata、words_timestamps 在 result_metadata 中返回，保留原数组和空段；run 的对应位置为 result.result_metadata。Scribe 保留完整 JSON、转写文本及词/字符时间戳。未返回的歌词、时长、种子和用量不补造，文件实测时长不作为账单。

requested_options_unavailable / unsupported_parameters 会停止自动切换模型。HTTP 错误 details 和远端任务 error 保留完整结构，须向用户逐项展示 unsupported_parameters / suggested_remove_parameters；不自动删参、换声音或重新生成。由用户决定保留要求稍后处理，或明确修改相关要求后另起请求。

## 文件位置与保留

旧单模型命令在 `--output-dir` 下创建独立目录：

```text
outputs/
└── aihub-UUID/
    ├── task.json
    └── files/
```

程序写入 `task.json` 供下一次 `resume` 读取；下载成功的媒体或文档 ZIP 放在 `files/`；E1 文本理解结果同时保存为 `files/result-<local-id>.txt`。恢复时继续使用该目录，不把已成功文件重新生成。任务记录、输入 JSON 和生成文件均放在用户任务目录，不能写入 Plugin 安装目录。

新 `run` 默认在调用项目 `data/aihub-studio/20261106143025-任务摘要-run-a1b2c3d4/` 保存 `run.json`；异步候选各自的 `task.json` 和 `files/` 位于其 `attempt-N/aihub-UUID/` 下。原生音乐也保存 run 与返回文件，但没有可查询任务 ID，提交不明时不能自动重发。旧 `native-music` 直接保存返回文件，没有上述任务记录。

交付后的 `review.json`、远端检查的 `review-task/`、首次错误生成的 `error-report.md`、`diagnostic.json`、`issue-draft.md` 和请求证据 `request-context.json` 均放在同一 run 目录。每次存在报告时 `feedback.show_notice=true`；首次/再次失败、恢复及最终总结都须逐条转述 `feedback.artifact_links`，保留完整绝对路径作为链接文字。只有真实存在的文件才提供链接。报告不自动发送，不改变生成或检查状态。证据语义与旧报告说明见 [本地错误报告](error-reports.md)，检查命令见 [结果检查](result-checks.md)。

程序不自动删除任务目录。用户决定何时归档或删除；删除 `task.json` 会失去该记录提供的恢复入口。任务记录可能含 prompt、输入或结果 URL，应和生成文件一起按用户的访问范围保存。

交付时提供可点击的实际文件路径；远程宿主有已授权的附件能力时可用它交付。只有任务 ID、URL 或 `submitted` 状态不算完成媒体交付。

文字转对话使用 audio-dialogue，台词放 task 的 requirements.inputs，省略 prompt；直接 generate 用 API inputs 数组。新四模型等待对应 Gateway 合同生产部署；旧 v4/Turbo 四 ID 无别名，报告用途迁移说明，历史 task 只恢复原 ID。

## ElevenLabs 音色设计与创建

`audio-voice-design` 使用 plan/run/continue。全部候选试听并明确选择后使用 `voice-create --skill aihub-audio --record <Design的task.json> --selection-file <selection.json>`；再次调用省略选择文件，只恢复原 Create。通用 generate 禁止直接 Create。完整字段、计费、选择记录和 ID 保存提醒见[专用流程](elevenlabs-voice-creation.md)。
