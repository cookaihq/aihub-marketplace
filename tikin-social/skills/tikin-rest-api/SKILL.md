---
name: tikin-rest-api
metadata:
  version: "2.0.1"
description: v2.0.1｜通过共享请求工具调用 Tikin REST API，并保存本地错误报告。涵盖服务地址、Bearer 鉴权、/api/v1/{platform}/... 路径、分页、限流、重试、错误处理，以及单次调用费用与余额信息；适用于直接调用 Tikin 数据接口。
---

# tikin — REST API

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开 Setup 配置网页；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Direct HTTP access to all 1,000+ tikin endpoints. Use `tikin-endpoint-discovery` to find the
right path, then call it here.

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

## Essentials

- **Base URL:** `https://console.tikin.net` (override with `TIKIN_BASE_URL`).
- **Auth header:** `Authorization: Bearer $TIKIN_API_KEY`.
- **Path scheme:** `/api/v1/{platform}/{api}/{action}` — e.g. `/api/v1/tiktok/app/v3/fetch_one_video`.
- **Most reads are GET** with query params; batch/multi endpoints are POST with a JSON body.

## Action — example request files

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/tiktok/app/v3/fetch_one_video",
  "query": {
    "aweme_id": "7372484719365098283"
  }
}
```

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/instagram/v2/fetch_user_info",
  "query": {
    "username": "instagram"
  }
}
```

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "POST",
  "path": "/api/v1/douyin/search/fetch_general_search_v1",
  "body": {
    "keyword": "美食",
    "offset": 0,
    "count": 10
  }
}
```

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "POST",
  "path": "/api/v1/tiktok/app/v3/fetch_multi_video",
  "body": [
    "7372484719365098283",
    "7372484719365098284"
  ]
}
```

Save each JSON example as a separate request file and execute it through the shared helper. Use the actual original user request. See [Reliability](#reliability) for failure handling.

Paths, methods, and parameters are exactly as returned by `tikin-find-endpoint` (the
`tikin-endpoint-discovery` skill's bundled search CLI) — pass them through unchanged.

## Pagination (param name varies by platform)

| Platform | Cursor param | Notes |
|---|---|---|
| TikTok / Douyin | `max_cursor` / `cursor` | response returns next cursor + `has_more` |
| Instagram | `pagination_token` | pass the token from the previous response |
| YouTube | `continuation_token` | pass to `..._replies` / next-page endpoints |
| Twitter | `cursor` | from previous timeline response |
| Threads | `end_cursor` | from previous response |
| Xiaohongshu | `cursor` (+ `index`) | |

Loop until the response's `has_more` is false or no next cursor is returned. **Each page is a
billed call — every loop needs a budget** (see [Reliability](#reliability); hand off to
`tikin-bulk-data-export` for big jobs).

## Reliability

**This section is the single source of truth for timeouts, retries, and pagination budgets across
every tikin skill.** Other skills point here instead of restating the numbers.

### Timeouts and retries

The shared helper implements 30-second API requests and a 90-second invocation budget.
At most 3 attempts are allowed in a transient failure sequence for verified reads explicitly
marked `side_effects: false`, using 1s/2s fallback backoff. Valid numeric/date Retry-After
is honored in full and persists across processes. A wait beyond the time budget returns
`cooldown` with the next allowed time. Deterministic 4xx stop. Unknown operations and
GET calls that may create tasks retain write protection; only DNS failure or connection
refusal proves nothing was sent. An ambiguous result preserves the original record and
must not be replayed. Use an existing task's query if available.
Report generation never changes these decisions. Do not wrap the helper in another retry loop.

Final media downloads use a 300-second limit (curl.exe on native Windows); explicitly raise
the limit for unusually large files. API `timeout_seconds` can be set to a positive finite
value no greater than 300 in the request JSON. Keep every polling operation within a wall-clock
deadline; on expiry preserve the task ID and report waiting instead of resubmitting.

### Pagination budget

- Follow the operation's documented rate limit and actual Retry-After. There is no uniform
  10 RPS allowance across all operations; use sequential calls when the limit is unknown.
- When the user gave a target (row count, post count, time window), that target is the budget.
- **When the user gave no target, the default budget is 50 pages or 5,000 items, whichever comes
  first.** Retries do not count against it — only pages actually retrieved do.
- Stop the loop on whichever comes first: `has_more` is false / no next cursor, the user's target,
  or the default budget.
- **When the budget stops the loop, say so explicitly** — report it as `budget exhausted`, state
  how many pages and items were fetched, whether more data remains (`has_more` still true), and the
  cursor to resume from. Never truncate silently and never present a budget-capped pull as complete.

## Cost & balance awareness

tikin bills per call against your prepaid balance. Check balance/usage anytime:

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/usage/token/"
}
```

Prices vary per endpoint. Cap pagination and estimate a run's cost (pages × per-call price)
before bulk pulls.

## Verification gate

Before claiming success:
1. HTTP 2xx and body is valid JSON; also inspect helper status and business error fields.
2. Not an auth/balance error (401 / insufficient balance).
3. Expected fields present (e.g. a video fetch returns a play/download URL).

## Red flags

- Hardcoding the API key in code/commits — always read `$TIKIN_API_KEY`.
- A `curl` call with no `--max-time` — one hung connection stalls the whole task.
- Retrying a 401/403/404/422 — it will fail identically; fix the cause instead.
- Unbounded pagination loops (runs up cost).
- Reporting a budget-capped pull as if it were complete.
- Ignoring `has_more` / next-cursor and re-fetching page 1.
