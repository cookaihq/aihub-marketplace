---
name: aihub-music
metadata:
  version: "5.0.0"
description: v5.0.0｜通过 AIhub 默认使用 Suno 按描述生成歌曲、为已有歌词谱曲演唱，或生成纯音乐与背景配乐；也支持明确选择 ElevenLabs Music 和 Lyria。
---

# AIhub Music

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../../references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

凭证缺失、主动配置或有依据需修复时，先按[统一凭证流程](../../references/credential-setup.md)实际打开本 Plugin 配置中心；已有可读配置正常执行业务。保留真实 caller、cwd、全局开关与原任务提交状态。

Windows 原生命令统一使用 [共用 CLI](../../references/cli.md) 中的 `scripts/aihub.ps1` 入口；下方 Bash 示例用于说明相同的业务参数。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../../references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

执行本 Skill 时，使用当前宿主提供的实际完整调用标识并核对来源，按下述流程实际调用 AIHub；不能只加载说明后改用其他通道完成同一任务。提示词整理、确定性文件处理和按流程进行的宿主结果检查仍可使用适用工具。用户已对本任务明确选择或授权其他通道时沿用该决定。

## 凭证配置


先读取[共用 CLI](../../references/cli.md)、[任务 JSON、模型配置与切换](../../references/model-selection.md)和 [Suno 场景与参数](../../references/suno.md)，保存 original_request，按创作目的选择场景：

| 场景 | operation | prompt 内容 |
| --- | --- | --- |
| 按描述生成歌曲 | music-description | 歌曲主题、风格和人声构想；Suno 自动创作歌词 |
| 已有歌词谱曲演唱 | music-lyrics | 用户提供的完整歌词原文；不改写、不删减 |
| 纯音乐／背景配乐 | music-instrumental | 风格、氛围、乐器和使用场景 |

三场景均默认 suno-v6。用户本次指定型号时固定执行；否则已有 AIHUB_MUSIC_MODELS 优先，不把推荐值填入 model 覆盖个人配置。先 doctor、plan，再 run；要求与候选冲突时保留原要求并说明原因，不丢参兜底。目标时长、显式 0/false 与 Mini 限制按 Suno 参考执行，Max 不自动开启。

明确选择 elevenlabs-music-v2.5 时，先读取并遵守[ElevenLabs 参数与恢复](../../references/elevenlabs.md)。描述创作可用 prompt 或 composition_plan；纯音乐使用 force_instrumental=true。已有歌词场景尚无跨模型精确映射时拒绝，不把歌词换成风格描述。Lyria 异步 lyria-3-pro 和 Gemini 原生 lyria-3-pro-preview 保留为描述创作的可选模型；额外要求不能丢弃。旧 music-async / music-native 不再作为新任务场景；已有 run 记录继续保存的候选和协议。

Suno 一次返回一首或两首独立歌曲，分别交付；每首的 url / audio_url 是别名，不重复下载，不为补齐第二首重新生成。

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
