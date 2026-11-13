---
name: aihub-music
metadata:
  version: "5.0.0"
description: v5.0.0｜通过 AIhub 的 elevenlabs-music-v2.5 默认异步任务或独立的 Gemini 原生 lyria-3-pro-preview 协议生成音乐，支持按配置选择 lyria-3-pro，保存并核验音频文件。
---

# AIhub Music

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../../references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

凭证缺失、主动配置或有依据需修复时，先按[统一凭证流程](../../references/credential-setup.md)实际打开本 Plugin 配置中心；已有可读配置正常执行业务。保留真实 caller、cwd、全局开关与原任务提交状态。

Windows 原生命令统一使用 [共用 CLI](../../references/cli.md) 中的 `scripts/aihub.ps1` 入口；下方 Bash 示例用于说明相同的业务参数。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../../references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

执行本 Skill 时，使用当前宿主提供的实际完整调用标识并核对来源，按下述流程实际调用 AIHub；不能只加载说明后改用其他通道完成同一任务。提示词整理、确定性文件处理和按流程进行的宿主结果检查仍可使用适用工具。用户已对本任务明确选择或授权其他通道时沿用该决定。

## 凭证配置


先读取 [共用 CLI](../../references/cli.md) 和 [任务 JSON、模型配置与切换](../../references/model-selection.md)。新任务默认选 `operation=music-async`，没有模型配置时用 `elevenlabs-music-v2.5`。用户选择 Gemini 原生音乐时选 `music-native`，内置型号为 `lyria-3-pro-preview`，不能静默切换协议或用短片段型号替代完整音乐。

保存 `original_request` 和提交提示词 `prompt`，仅用户本次指定型号才填 `model`。其余情况由 CLI 读取 `AIHUB_MUSIC_MODELS`，按已选协议筛选候选并逐一构造参数。Lyria 异步音乐可将图片参考放入 `inputs.images`、负面提示词放入 `requirements.negative_prompt`；原生音乐尚无可验证的额外参数/参考素材转换，不能删除用户要求后提交。先执行 `doctor`、`plan`，核对后 `run`。

使用 `elevenlabs-music-v2.5` 时，先读取并遵守 [ElevenLabs 参数与恢复](../../references/elevenlabs.md)。Issue #29 合同已随 Gateway v0.9.16 于2026-11-13上线，线上调用沿用既有账号检查、付费授权和任务流程。prompt 与 requirements.composition_plan 二选一；计划模式不填写顶层 prompt，也不传 force_instrumental（包括 false），seed 仅用于计划。歌曲用整数 music_length_ms，段落用整数 duration_ms，参考音频用 start_ms/end_ms，单位均为毫秒。output_format 默认 auto，解析为 mp3_48000_192；sign_with_c2pa 仅支持 auto/MP3，不改变指定格式。显式 timestamps=false 保留，当前可用来源的能力由 Gateway 判断，不删参兜底。旧秒制 duration、Lyria 图片参考及 negative_prompt 无直接映射，须修改原请求后重新 plan，不自动转换或重发。费用按真实输出时长向上整分钟及账单结算；请求时长不保证等于实际输出时长。

```bash
AIHUB_PLUGIN_DIR="<实际 Plugin 目录>"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" doctor --skill aihub-music
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" models --skill aihub-music --media audio
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" plan --skill aihub-music --request-file "/任务目录/music-request.json"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" run --skill aihub-music --request-file "/任务目录/music-request.json" --output-dir "/任务目录/data/aihub-studio" --wait-seconds 30
```

已有 `run.json` 用 `continue`；旧异步 `task.json` 用 `resume`。原生音乐的 `inlineData` 直接保存音频，新流程会保存 run 记录，但没有可查询的远端任务 ID，提交结果不明时不自动重发。`confirmation_required` 时用户确认下一模型及参数后才传 `--confirm`，不能直接执行含 token 的 `next_action`。只交付通过文件检查的音频，说明实际试听范围和尝试过的模型；内容不符或下载失败不触发替换生成。


## 结果检查与用户提示

新任务与交付前读取 [结果检查与错误反馈](../../references/result-checks.md)。保存原始需求及具体检查项，完成生成后读取 `result_check`：`pending` 时实际查看产物并通过 `review-submit` 提交证据；`auto` 下宿主缺少必要能力才使用 `review --provider aihub`，`host` 下明确报告无法检查。`checking` 查询原检查任务，不提交新请求。

检查开启时，每次完成检查都必须告诉用户：“如果想关闭结果检查，可以直接在对话中告诉我‘关闭结果检查’；也可以说‘仅本次关闭结果检查’。”通过、不符、证据不足或无法检查都要提示，不能只保留在 JSON 中。用户要求关闭时按参考说明执行，沿用已明确作用范围；范围不明再询问。关闭后仍执行文件检查。

每次出现 `feedback` 都按[本地错误报告](../../references/error-reports.md)逐条提供 `artifact_links`，链接文字显示真实完整绝对路径；首次、再次失败、恢复和最终答复均包含。公开只用脱敏草稿，不自动发送。结果不符、检查或报告保存失败不触发重新生成。
