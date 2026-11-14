---
name: aihub-audio
metadata:
  version: "6.1.0"
description: v6.1.0｜通过 AIhub 合成语音和旁白、按台词顺序生成多音色对话、转写录音；支持 ElevenLabs 预置音色库和音色设计。
compatibility: Claude Code, Codex, WorkBuddy and Hermes; Node.js 18 or newer, FFmpeg and ffprobe on PATH for transcription, AIhub API access.
---

# AIhub 音频与语音任务

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../../references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

凭证缺失、主动配置或有依据需修复时，先按[统一凭证流程](../../references/credential-setup.md)实际打开本 Plugin 配置中心；已有可读配置正常执行业务。保留真实 caller、cwd、全局开关与原任务提交状态。

Windows 原生命令统一使用 [共用 CLI](../../references/cli.md) 中的 `scripts/aihub.ps1` 入口；下方 Bash 示例用于说明相同的业务参数。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../../references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

执行本 Skill 时，使用当前宿主提供的实际完整调用标识并核对来源，按下述流程实际调用 AIHub；不能只加载说明后改用其他通道完成同一任务。提示词整理、确定性文件处理和按流程进行的宿主结果检查仍可使用适用工具。用户已对本任务明确选择或授权其他通道时沿用该决定。

## 凭证配置


D1 处理文本转语音、文字转多音色对话和语音识别/转写。用户本次指定模型时固定执行；否则读取 `AIHUB_AUDIO_MODELS`，按用途筛选，不跨用途替换。没有配置时 TTS／旁白使用 `eleven-v4-text-to-speech`，按台词顺序生成多音色对话使用 `eleven-v4-text-to-dialogue`，ASR 使用 `paraformer-v2`。音乐属于 `aihub-music`，素材理解属于 `aihub-understanding`。

使用 `eleven-v4-text-to-speech`、`eleven-v4-text-to-dialogue`、两者的 `-custom-voice` 变体或 `scribe-v2` / `scribe-v3` 时，先读取并遵守 [ElevenLabs 参数与恢复](../../references/elevenlabs.md)。Speech 将 prompt 原样映射为 text，任务显式 requirements.voice_id 优先，否则读取已配置的 ElevenLabs 默认音色；可选 voice_settings；Dialogue 将有序台词及 voice_id 放在 requirements.inputs，可选 settings 使用 similarity，不填 prompt。两款 Speech 均为1–10000字；Dialogue 最多10种音色、2000字仅为可靠性建议，不截断或拆分。设置对象省略时不主动填充，false/0保留；MiniMax 默认音色不适用。Issue #29 合同已随 Gateway v0.9.16 于2026-11-13上线，线上调用沿用既有账号检查、付费授权和任务流程。旧 v4/Turbo 四 ID 无别名或回退，个人列表只报告迁移方法，不静默改写。Scribe 使用一个完整 URL 或本地文件：v2 的 URL 为 source_url、diarize 默认 false，支持角色、改写、实体及多声道；v3 保持旧合同与默认值。保留完整结果，不套用 Paraformer 分段，不自动将 v3 降为 v2；旧任务恢复不重发。

先读取 [共用 CLI](../../references/cli.md) 和 [任务 JSON、模型配置与切换](../../references/model-selection.md)。已有 `run.json` 用 `continue`；旧 `task.json` / 任务 ID 用 `resume` / `task` 查询原任务。

新任务先执行 `doctor`。保存 `original_request`，选择 `audio-tts`、`audio-dialogue` 或 `audio-transcribe`。TTS 将待朗读文本写入 `prompt`，按 `describe` 填写用户要求的 `requirements`。Speech 2.8 HD / Turbo 未显式指定 `voice_setting.voice_id` 时，由程序补入已配置的默认音色；不要自行填一个推荐音色覆盖用户默认值。用户本次明确指定的音色优先，其他语音参数继续保留。转写先读[大文件转写与恢复](../../references/audio-transcription.md)，将原始本地路径或 URL 直接写入 `inputs.audios`；程序按实际模型与上传通道决定整段、转换或波形分段。仅用户本次指定型号才填 `model`。先 `plan` 检查每个候选，再 `run`；不能为了换模型改变指定音色、语言或丢弃输入。

用户要求获取、筛选、试听、选择或收藏 ElevenLabs 预置音色时，读取并遵守[ElevenLabs 预置音色库](../../references/elevenlabs-voices.md)，实际启动统一配置中心并返回可点击的 HTML 页面链接，定位此音色库。用户选择全局／项目范围后，点击“保存并使用”将所选音色和收藏原子保存并回读；关闭或到期不算已保存。已保存选择用于 Eleven Speech 的单人语音默认值，对话仍逐段指定音色，收藏不会自动轮换。未配置默认音色时打开此页面让用户选择，不能由 Agent 随意填一个音色。

MiniMax Speech 仍为显式可选模型。用户明确要求其音色时，按[统一凭证流程](../../references/credential-setup.md)打开完整配置中心中的“MiniMax Speech 默认音色”。搜索、筛选和试听已有样音不生成新语音；选用音色先回填草稿，在原编辑面板保存才生效。其收藏继续使用原全局偏好，不与 ElevenLabs 收藏混用。

```bash
AIHUB_PLUGIN_DIR="<实际 Plugin 目录>"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" doctor --skill aihub-audio
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" models --skill aihub-audio --media audio
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" describe --skill aihub-audio --model "<线上模型 ID>"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" plan --skill aihub-audio --request-file "/任务目录/audio-request.json"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" run --skill aihub-audio \
  --request-file "/任务目录/audio-request.json" --output-dir "/任务目录/data/aihub-studio" --wait-seconds 30
```

用返回的 `run_record` 继续任务。`confirmation_required` 必须展示下一模型与参数，用户同意后才传 `--confirm`；不能直接执行含 token 的 `next_action`。只交付已检查的文件及实际转写结果，报告最终模型和尝试摘要。提交结果不明、查询/下载失败或试听不符合要求不触发替换生成。


## ElevenLabs 音色设计

用户询问或要求设计、创建新音色时，读取并遵守 [ElevenLabs 音色设计与创建](../../references/elevenlabs-voice-creation.md)。使用 `audio-voice-design` / `elevenlabs-voice-design` 生成候选，展示返回的全部试听文本、音频及候选编号；让用户试听全部候选后明确选择，再用 `voice-create` / `elevenlabs-voice-create` 保存所选候选。不能自动选择第一个、自动全部创建、把试听当成创建成功，也不能把 `generated_voice_id` 当作合成音色 ID。可选参考音频仅使用本人或已授权素材，不承诺专业克隆或精确复刻。

保留完整 Design、Create 结果及任务 ID。用户选择前停在候选交付；选择文件只记录真实用户确认和全部试听候选，不能由 Agent 填造。Create 的重复调用只恢复同一任务；提交结果不明、容量失败或下载失败不重发。创建成功后醒目展示 `voice_id` 并逐字提醒：**生成的 `voice_id` 请自行妥善保存。平台不提供音色列表、音色查询或 ID 找回功能。** 任务查询仍可用。默认语音模型及预置音色库配置不因此改变，后续新音色合成显式使用适用的 custom-voice 模型及真实 `voice_id`。

## 结果检查与用户提示

新任务与交付前读取 [结果检查与错误反馈](../../references/result-checks.md)。保存原始需求及具体检查项，完成生成后读取 `result_check`：`pending` 时实际查看产物并通过 `review-submit` 提交证据；`auto` 下宿主缺少必要能力才使用 `review --provider aihub`，`host` 下明确报告无法检查。`checking` 查询原检查任务，不提交新请求。

检查开启时，每次完成检查都必须告诉用户：“如果想关闭结果检查，可以直接在对话中告诉我‘关闭结果检查’；也可以说‘仅本次关闭结果检查’。”通过、不符、证据不足或无法检查都要提示，不能只保留在 JSON 中。用户要求关闭时按参考说明执行，沿用已明确作用范围；范围不明再询问。关闭后仍执行文件检查。

每次出现 `feedback` 都按[本地错误报告](../../references/error-reports.md)逐条提供 `artifact_links`，链接文字显示真实完整绝对路径；首次、再次失败、恢复和最终答复均包含。公开只用脱敏草稿，不自动发送。结果不符、检查或报告保存失败不触发重新生成。
