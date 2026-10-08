---
name: tikin-douyin
metadata:
  version: "1.2.0"
description: v1.2.0｜Work with Douyin (抖音) URLs and data via tikin — fetch videos, user profiles and post lists, video comments, and run video/user/general search via Douyin's dedicated search series. Use when the user provides a Douyin URL or the task targets Douyin. Covers App-V3 and the Douyin Search series.
---

# Douyin / 抖音 (via tikin)

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Deep coverage of Douyin. Exhaustive endpoints via the `tikin-endpoint-discovery` skill:
`tikin-find-endpoint "<goal>" --platform douyin`.

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
5. Resolve and require the key:

```bash
TIKIN_SETUP_DIR="<installed tikin-setup directory>"
tikin_run() {
  uv run --project "${TIKIN_SETUP_DIR}" "${TIKIN_SETUP_DIR}/scripts/tikin-config" \
    --skill tikin-douyin run -- "$@"
}
```

Resolve `TIKIN_SETUP_DIR` from the installed `tikin-setup` Skill before using the command.
Run API examples through `tikin_run` in the same shell as this definition. The helper reads
`TIKIN_API_KEY` and `TIKIN_BASE_URL` independently from process environment →
`$PWD/.env.tikin-douyin` → `$PWD/.env.local` → `$PWD/.env` →
`~/.config/tikin-social/<skill-name>/.env.local` → that directory’s `.env` →
`~/.config/tikin-social/.env.<skill-name>` → the Plugin root’s `.env.local` → `.env` →
`~/.config/<skill-name>/.env`. Global sources are automatic; add `--no-global-config`
before `run` to skip all six for this call and use default routing without reading saved settings. Empty values fall through. Project files are read only in the
invocation directory; other Skills' dedicated files are not read. File contents are literal, never
sourced as shell code. Resolved values are passed only to the child command and are not printed.

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

## Example

```bash
tikin_run sh <<'TIKIN_COMMAND'
BASE="${TIKIN_BASE_URL:-https://console.tikin.net}"
# Video search — POST with a JSON body
curl -s --max-time 30 -X POST "$BASE/api/v1/douyin/search/fetch_video_search_v2" \
  -H "Authorization: Bearer $TIKIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"keyword": "美食"}'

# One video by id
curl -s --max-time 30 "$BASE/api/v1/douyin/app/v3/fetch_one_video_v2?aweme_id=7637462264047710705" \
  -H "Authorization: Bearer $TIKIN_API_KEY"
TIKIN_COMMAND
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
3 attempts total, 1s then 2s backoff, `Retry-After` wins on a 429, and 401/403/404/422 are never
retried.

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
