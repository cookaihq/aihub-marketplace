---
name: tikin-bulk-data-export
metadata:
  version: "4.0.0"
description: v4.0.0｜通过 Tikin 批量获取社交媒体帖子、粉丝、搜索结果或评论，支持分页、去重及 CSV、JSON 导出。适用于获取全部帖子、构建数据集、导出数据，或从受支持平台和链接重复拉取大量数据。
---

# Bulk Data Export

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../tikin-setup/references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开本 Plugin 配置中心；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Paginate a list endpoint at scale, dedup, and write a clean dataset — safely and with a cost
estimate up front.

Before constructing a changed request, read the [first-batch contract and migration guide](../tikin-endpoint-discovery/references/first-batch.md) and use the discovery CLI's `--describe` output for its exact method, body shape and constraints. Candidate catalog content requires the matching service release before live use.

For selected new queries, read the [second-batch workflow guide](../tikin-endpoint-discovery/references/second-batch.md) before constructing a request. It records exact cohort scope, platform-specific inputs, pagination, Cookie prerequisites, prices and candidate limitations; LinkedIn task creation uses its shared asynchronous workflow.

## Runtime gate

On the first tikin use in each Agent session, follow the `tikin-setup` session update gate once
without blocking this task. Before the first tikin API call for the current user task:

1. Determine every affected platform. If this task disables global configuration, do not read
   `~/.config/tikin-social/settings.json`; use the built-in routing
   `{"routing":{"default":"auto","platforms":{}}}` and pass `--no-global-config` before every
   helper subcommand. Otherwise read that file as JSON from the runtime user’s home directory
   (no XDG or legacy alias lookup), using the same built-in routing when the file is absent.
2. Resolve each policy from `routing.platforms[platform]`, then `routing.default`. An explicit
   instruction in the current user request wins over stored settings.
3. For any `confirm` platform, ask once for the whole task and group the affected
   platforms/actions. Do not ask again for pagination within the approved task.
4. Never request a supported user-provided social-media content URL with `curl`, WebFetch, or a
   generic browser fetch. Parse identifiers locally or pass the original URL/share text to tikin.
   Calls to the configured tikin base URL and downloads from final media URLs returned by tikin are
   allowed.
5. Before any business API request, read [shared requests and local error reports](../tikin-setup/references/requests.md). Use `tikin-config request` with this Skill as caller and reuse the returned `--record` for the same task. On every failure, recovery and final reply, copy all `feedback.artifact_links` with full absolute paths as link labels.

If the loader reports a missing key or there is evidence of a configuration problem, follow the linked credential flow. If the user declines tikin, explain the
limitation and ask before selecting an alternative; do not silently fetch the original page.

## Step 1 — Estimate cost FIRST (mandatory)

Bulk pulls are the biggest cost spender. Before fetching, compute the call count and check your
balance:

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/usage/token/"
}
```

State the estimated calls and get the user's go-ahead before running.

## Step 2 — Paginate safely

- Use the platform's cursor (`max_cursor` / `pagination_token` / `continuation_token` / `cursor` /
  `cursor`+`index`) — see `tikin-rest-api` and the platform skill.
- **The budget is the smaller of the user's target row count and the default hard cap of 50 pages
  or 5,000 rows** (the default from `tikin-rest-api`'s **Reliability** section). A user target
  above the default cap does not lift it — confirm the larger budget with the user first, then
  state the raised number explicitly before running.
- Loop until whichever comes first: `has_more` is false, the user's target row count, or that cap.
- Follow the operation-specific rate and the **Reliability** section in `tikin-rest-api`.
  The shared executor owns retries and durable cooldowns; do not resubmit an unknown operation.
- Retries do not consume the pagination budget; only pages actually retrieved do.
- **When the cap ends the loop, report it as `budget exhausted`** — rows fetched, pages fetched,
  whether `has_more` is still true, and the cursor to resume from. This is a distinct outcome from
  "the source ran out of data"; never present it as a complete export.
- Dedup by stable id (e.g. `aweme_id` / post id) as you go.

LinkedIn user posts do not have verified pagination through the listed `start` or
`pagination_token`; company posts use only the documented effective `start`.
Threads user lists likewise document ineffective pagination in this batch. Report
the available first result and limitation instead of promising a complete export.

## Step 3 — Export

- **JSON:** write the deduped array to `output.json`.
- **CSV:** flatten the fields the user cares about (id, author, text, likes, comments, shares,
  timestamp, url) into `output.csv`.
- Report row count, pages fetched, duplicates removed, and the file path.

## Verification gate

1. Row count ≈ requested, and the stop reason is stated: source exhausted, user target reached, or
   `budget exhausted`.
2. No duplicate ids in the output.
3. File written and non-empty; CSV header matches columns.

## Red flags

- Skipping the cost estimate — never start a bulk pull without one.
- Ignoring the user's row cap / `has_more` (infinite loop, credit burn).
- Running with no cap at all because the user gave no target — the 50-page / 5,000-row default
  applies exactly then.
- Silent truncation — always report how many rows were actually fetched vs. requested, and say
  when the budget rather than the source ended the pull.
