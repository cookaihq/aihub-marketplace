---
name: tikin-twitter-threads
metadata:
  version: "2.0.1"
description: v2.0.1｜通过 Tikin 处理 Twitter/X 与 Threads 链接和数据，获取帖子详情、用户资料、用户时间线、粉丝与关注列表，搜索时间线、查询评论回复及 X 热门话题。用户提供相关链接或任务针对任一平台时使用；覆盖 Twitter-Web 与 Threads-Web 接口。
---

# Twitter / X & Threads (via tikin)

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开 Setup 配置网页；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Coverage of Twitter/X and Threads (both microblog platforms). Exhaustive endpoints via the
`tikin-endpoint-discovery` skill: `tikin-find-endpoint "<goal>" --platform twitter` or
`--platform threads`.

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

**Coverage:** Twitter-Web, Threads-Web.

## Twitter / X endpoints

| Goal | Method + path | Key params |
|---|---|---|
| Tweet detail | `GET /api/v1/twitter/web/fetch_tweet_detail` | `tweet_id` |
| User profile | `GET /api/v1/twitter/web/fetch_user_profile` | `screen_name` \| `rest_id` |
| User tweets | `GET /api/v1/twitter/web/fetch_user_post_tweet` | `screen_name`, `cursor` |
| Search timeline | `GET /api/v1/twitter/web/fetch_search_timeline` | `keyword`, `search_type`, `cursor` |
| Tweet comments | `GET /api/v1/twitter/web/fetch_post_comments` | `tweet_id`, `cursor` |
| Trending | `GET /api/v1/twitter/web/fetch_trending` | `country` |
| Followers | `GET /api/v1/twitter/web/fetch_user_followers` | `screen_name`, `cursor` |
| Following | `GET /api/v1/twitter/web/fetch_user_followings` | `screen_name`, `cursor` |

## Threads endpoints

| Goal | Method + path | Key params |
|---|---|---|
| User info | `GET /api/v1/threads/web/fetch_user_info` | `username` |
| User posts | `GET /api/v1/threads/web/fetch_user_posts` | `user_id`, `end_cursor` |
| Search posts (candidate) | `GET /api/v1/threads/web/search_posts` | `query` |

Threads top/recent search and the old post-comments route are retired. The new
search candidate is not yet verified as response/billing equivalent. Threads user
post/reply/repost listing currently documents no effective pagination; do not loop
`end_cursor` merely because it remains in the schema.

## Example

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/twitter/web/fetch_search_timeline",
  "query": {
    "keyword": "ai",
    "search_type": "Top"
  }
}
```

## Pagination

Twitter/X uses `cursor`; Threads uses `end_cursor`. Pass the value returned by the previous
response; stop when none is returned.

**Each page is billed — every loop needs a budget.** With a user target, that target is the budget;
with no target, stop at the default 50 pages / 5,000 items from `tikin-rest-api`'s **Reliability**
section. When the budget ends the loop, report it as `budget exhausted` — pages and items fetched,
whether more remains, and the cursor to resume from — instead of presenting a partial pull as
complete.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
let the shared executor enforce side effects, the full cooldown and remaining attempt budget.
Do not add an outer retry loop or resubmit an unknown operation.

## Hand off to task skills

- Analyze an account → `tikin-creator-analytics`
- Trending/search → `tikin-trend-research`, `tikin-social-listening`
- Comment/reply mining → `tikin-comments-analysis`
- Competitor benchmarking → `tikin-competitor-analysis`
- Large pulls → `tikin-bulk-data-export`

## Red flags

- Twitter user endpoints accept `screen_name` or `rest_id`; Threads user posts need the numeric
  `user_id` (resolve via `fetch_user_info` first).
- Don't mix the two cursor params — `cursor` (Twitter) vs `end_cursor` (Threads).
