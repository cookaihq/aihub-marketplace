---
name: aihub-understanding
metadata:
  version: "1.1.3"
description: v1.1.3｜Understand image, audio, video, or file content through AIhub llm-custom models and return resumable text results.
---

# AIhub Understanding

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../../references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

执行本 Skill 时，使用当前宿主提供的实际完整调用标识并核对来源，按下述流程实际调用 AIHub；不能只加载说明后改用其他通道完成同一任务。提示词整理、确定性文件处理和按流程进行的宿主结果检查仍可使用适用工具。用户已对本任务明确选择或授权其他通道时沿用该决定。

## 凭证配置

本 Skill 只需配置 `AIHUB_API_KEY`。首次配置、缺 Key 或需要修复时，按[共用配置流程](../../references/cli.md#首次配置缺项与配置修复)提供“自行填写本机文件 / 从 Secret Book 选择凭证”，已有选择就沿用。向用户展示时保留 **Secret Book** 原名，不翻译为中文；实际 Skill 标识为 `secret-book`。选择 Secret Book 后直接按它的流程配置；只有实际发现未安装、无法调用或版本不兼容时，才提示并协助处理。

先读取 [共用 CLI](../../references/cli.md) 和 [任务 JSON、模型配置与切换](../../references/model-selection.md)。E1 只接受图片、音频、视频或文件内容，不能提交纯文本请求。保存 `operation=understanding`、`original_request`、分析提示词 `prompt` 和媒体实际 URL 列表 `inputs`；本地文件先上传。`requirements` 可含 `system_prompt`、`max_tokens`、`temperature`。

仅用户本次指定型号时填 `model` 并固定执行；否则使用 `AIHUB_UNDERSTANDING_MODELS`，未配置时用 `gemini-3.1-pro-preview`。CLI 逐个读取 `/v1/configs/llm_generations_models` 核对精确 ID 与所需媒体能力，并把请求转换为对应内容块。图片能力不能证明能读取音频或视频，能力不符的候选按保存的策略跳过或停止。

```bash
AIHUB_PLUGIN_DIR="<实际 Plugin 目录>"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" doctor --skill aihub-understanding
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" models --skill aihub-understanding --media understanding
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" plan --skill aihub-understanding --request-file "/任务目录/understanding-request.json"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" run --skill aihub-understanding --request-file "/任务目录/understanding-request.json" --output-dir "/任务目录/data/aihub" --wait-seconds 30
```

已有 `run.json` 用 `continue`；旧 `task.json` / 任务 ID 用 `resume` / `task`。`confirmation_required` 时展示下一模型及参数，用户同意后才传 `--confirm`，不能直接执行含 token 的 `next_action`。完成后交付内层 `result.text` 与文本文件，说明实际模型、尝试摘要及无法从素材证实的结论。提交结果不明、查询/下载失败或答案不符合要求不触发替换生成。


## 结果检查与用户提示

新任务与交付前读取 [结果检查与错误反馈](../../references/result-checks.md)。保存原始需求及具体检查项，完成生成后读取 `result_check`：`pending` 时实际查看产物并通过 `review-submit` 提交证据；`auto` 下宿主缺少必要能力才使用 `review --provider aihub`，`host` 下明确报告无法检查。`checking` 查询原检查任务，不提交新请求。

检查开启时，每次完成检查都必须告诉用户：“如果想关闭结果检查，可以直接在对话中告诉我‘关闭结果检查’；也可以说‘仅本次关闭结果检查’。”通过、不符、证据不足或无法检查都要提示，不能只保留在 JSON 中。用户要求关闭时按参考说明执行，沿用已明确作用范围；范围不明再询问。关闭后仍执行文件检查。

`feedback.show_notice=true` 时提供报告路径与 Issue/管理员入口；公开只使用脱敏草稿，不自动发送。结果不符或检查失败不触发重新生成。
