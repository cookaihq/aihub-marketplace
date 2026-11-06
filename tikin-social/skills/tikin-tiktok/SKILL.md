---
name: tikin-tiktok
metadata:
  version: "3.1.0"
description: v3.1.0｜通过 Tikin 处理 TikTok 链接与数据，获取视频、用户资料、作品列表，搜索内容，并查询趋势、广告洞察、创作者分析、评论关键词和商店搜索结果。用户提供 TikTok 链接或任务针对该平台时使用；覆盖 App-V3、Ads、Creator、Analytics 与 Shop 接口。
---

# TikTok (via tikin)

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../tikin-setup/references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开本 Plugin 配置中心；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Deep coverage of TikTok. For exhaustive endpoints use `tikin-endpoint-discovery`
(`tikin-find-endpoint "<goal>" --platform tiktok`). For outcomes (download, analyze a creator,
trends), hand off to the task skills noted below.

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

**Coverage:** App-V3, Ads, Creator, Analytics, Shop-Web. (TikTok-Web is de-scoped — reach it via discovery.)

## Key endpoints

| Goal | Method + path | Key params |
|---|---|---|
| One video | `GET /api/v1/tiktok/app/v3/fetch_one_video` | `aweme_id` |
| Video by share URL | `GET /api/v1/tiktok/app/v3/fetch_one_video_by_share_url` | `share_url` |
| User profile | `GET /api/v1/tiktok/app/v3/handler_user_profile` | `sec_user_id` \| `unique_id` |
| User's videos | `GET /api/v1/tiktok/app/v3/fetch_user_post_videos` | `sec_user_id`, `max_cursor`, `count` |
| Video search | `GET /api/v1/tiktok/app/v3/fetch_video_search_result` | `keyword`, `offset`, `count`, `sort_type`, `publish_time` |
| User search | `GET /api/v1/tiktok/app/v3/fetch_user_search_result` | `keyword`, `offset`, `count` |
| Video comments | `GET /api/v1/tiktok/app/v3/fetch_video_comments` | `aweme_id`, `cursor`, `count` |
| Hashtag video list | `GET /api/v1/tiktok/app/v3/fetch_hashtag_video_list` | `ch_id`, `cursor`, `count` |
| Trending hashtags | `POST /api/v1/tiktok/ads/get_trends_hashtag_list` | `time_range`, `country_code`, `page` |
| Hashtag detail | `POST /api/v1/tiktok/ads/get_trends_hashtag_detail` | `hashtag_id`, `country_code` |
| Creator video analytics | `POST /api/v1/tiktok/creator/get_video_analytics_summary` | JSON body |
| Comment keywords | `GET /api/v1/tiktok/analytics/fetch_comment_keywords` | `item_id` |
| Product detail | `GET /api/v1/tiktok/shop/web/fetch_product_detail_v3` | `product_id`, `region` |

The old popular-trends, sound-rank and creator-search paths are retired in this
batch; no equivalent replacement is asserted. Ads POST parameters belong in the
JSON body; inspect `--describe` and the migration guide before using them.

## Example

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/tiktok/app/v3/fetch_user_post_videos",
  "query": {
    "sec_user_id": "SEC_UID",
    "count": "20",
    "max_cursor": "0"
  }
}
```

## Pagination

User/video lists use `max_cursor` (start `0`) + `count`; search uses `offset` + `count`; comments
and hashtag video lists use `cursor` + `count`. Read the next cursor and `has_more` from the
response; loop until exhausted.

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
- Trends/hashtags/sounds → `tikin-trend-research`, `tikin-hashtag-research`
- Comment mining → `tikin-comments-analysis`
- Large list pulls → `tikin-bulk-data-export`

## Red flags

- Need `sec_user_id` (not the @handle) for user endpoints — resolve via `handler_user_profile` with `unique_id` first.
- Unbounded `max_cursor` loops burn credits.
