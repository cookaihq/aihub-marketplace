---
name: tikin-douyin
metadata:
  version: "3.0.0"
description: v3.0.0｜通过 Tikin 处理抖音链接与数据，获取视频、用户资料、作品列表和视频评论，并使用抖音专用搜索接口搜索视频、用户或综合内容。用户提供抖音链接或任务针对抖音时使用；覆盖 App-V3 与抖音搜索系列接口。
---

# Douyin / 抖音 (via tikin)

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../tikin-setup/references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开本 Plugin 配置中心；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Deep coverage of Douyin. Exhaustive endpoints via the `tikin-endpoint-discovery` skill:
`tikin-find-endpoint "<goal>" --platform douyin`.

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

**Coverage:** App-V3 (video/user/comments) and the dedicated Douyin **Search** series.
(Douyin-Web, Douyin-Creator, Douyin-Index, Xingtu, and Billboard are de-scoped — reach them via
discovery.)

> **Search note:** Douyin has its own specialized search series (`/douyin/search/...`, POST with a
> JSON body). Prefer it over the App-V3 search endpoints.

## Key endpoints

| Goal | Method + path | Key params |
|---|---|---|
| One video | `GET /api/v1/douyin/app/v3/fetch_one_video_v2` | `aweme_id` |
| Video by share URL | `GET /api/v1/douyin/app/v3/fetch_one_video_by_share_url` | `share_url` |
| User profile | `GET /api/v1/douyin/app/v3/handler_user_profile` | `sec_user_id` |
| User's videos | `GET /api/v1/douyin/app/v3/fetch_user_post_videos` | `sec_user_id`, `max_cursor`, `count` |
| Video comments | `GET /api/v1/douyin/app/v3/fetch_video_comments` | `aweme_id`, `cursor`, `count` |
| Video search | `POST /api/v1/douyin/search/fetch_video_search_v2` | body: `keyword`, `cursor`, `sort_type`, `publish_time` |
| User search | `POST /api/v1/douyin/search/fetch_user_search_v2` | body: `keyword`, `cursor` |
| General search | `POST /api/v1/douyin/search/fetch_general_search_v2` | body: `keyword`, `cursor`, `sort_type` |

The owning-account collection operation is now
`POST /api/v1/douyin/web/fetch_user_collects_videos`, with `collects_id` and
`cookie` required in its JSON body. Obtain the authorized account Cookie through
the existing private configuration workflow; do not echo it or claim a public
collection ID alone is sufficient. The shared migration guide contains the example.

## Example

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "POST",
  "path": "/api/v1/douyin/search/fetch_video_search_v2",
  "body": {
    "keyword": "美食"
  }
}
```

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/douyin/app/v3/fetch_one_video_v2",
  "query": {
    "aweme_id": "7637462264047710705"
  }
}
```

## Pagination

App-V3 user/video lists use `max_cursor` + `count`; comments use `cursor` + `count`; the Search
series pages via a `cursor` field in the JSON body. Loop on the returned cursor/`has_more`.

**Each page is billed — every loop needs a budget.** With a user target, that target is the budget;
with no target, stop at the default 50 pages / 5,000 items from `tikin-rest-api`'s **Reliability**
section. When the budget ends the loop, report it as `budget exhausted` — pages and items fetched,
whether `has_more` is still true, and the cursor to resume from — instead of presenting a partial
pull as complete.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
let the shared executor enforce side effects, the full cooldown and remaining attempt budget.
Do not add an outer retry loop or resubmit an unknown operation.

## Hand off to task skills

- Download videos → `tikin-social-media-downloader`
- Analyze an account → `tikin-creator-analytics`
- Competitor benchmarking → `tikin-competitor-analysis`
- Hashtag/keyword work → `tikin-hashtag-research`
- Comment mining → `tikin-comments-analysis`
- Large pulls → `tikin-bulk-data-export`

## Red flags

- The Search series is **POST with a JSON body** (`keyword`, `cursor`) — not GET query params.
- User endpoints need `sec_user_id`; resolve it first if you only have a share URL/nickname.
