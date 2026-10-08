---
name: tikin-youtube
metadata:
  version: "1.2.0"
description: v1.2.0｜Work with YouTube URLs and data via tikin — fetch video info, downloadable stream URLs, captions/subtitles, comments and replies, channel info, and run general/shorts search. Use when the user provides a YouTube URL or the task targets YouTube. Covers the YouTube Web-V2 API.
---

# YouTube (via tikin)

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Deep coverage of YouTube via the Web-V2 API. Exhaustive endpoints via the
`tikin-endpoint-discovery` skill: `tikin-find-endpoint "<goal>" --platform youtube`.

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
    --skill tikin-youtube run -- "$@"
}
```

Resolve `TIKIN_SETUP_DIR` from the installed `tikin-setup` Skill before using the command.
Run API examples through `tikin_run` in the same shell as this definition. The helper reads
`TIKIN_API_KEY` and `TIKIN_BASE_URL` independently from process environment →
`$PWD/.env.tikin-youtube` → `$PWD/.env.local` → `$PWD/.env` →
`~/.config/tikin-social/<skill-name>/.env.local` → that directory’s `.env` →
`~/.config/tikin-social/.env.<skill-name>` → the Plugin root’s `.env.local` → `.env` →
`~/.config/<skill-name>/.env`. Global sources are automatic; add `--no-global-config`
before `run` to skip all six for this call and use default routing without reading saved settings. Empty values fall through. Project files are read only in the
invocation directory; other Skills' dedicated files are not read. File contents are literal, never
sourced as shell code. Resolved values are passed only to the child command and are not printed.

If the loader reports a missing key or there is evidence of a configuration problem, follow the linked credential flow. If the user declines tikin, explain the
limitation and ask before selecting an alternative; do not silently fetch the original page.

**Coverage:** YouTube-Web-V2. (The older YouTube-Web API is de-scoped — reach it via discovery.)

## Key endpoints

| Goal | Method + path | Key params |
|---|---|---|
| Video info | `GET /api/v1/youtube/web_v2/get_video_info` | `video_id`, `language_code` |
| Video info by URL | `GET /api/v1/youtube/web_v2/get_video_info_v2` | `video_url` |
| Download streams | `GET /api/v1/youtube/web_v2/get_video_streams_v2` | `video_id` \| `video_url` |
| Captions/subtitles | `GET /api/v1/youtube/web_v2/get_video_captions` | `video_id`, `language_code`, `format` |
| Video comments | `GET /api/v1/youtube/web_v2/get_video_comments` | `video_id`, `sort_by`, `continuation_token` |
| Comment replies | `GET /api/v1/youtube/web_v2/get_video_comment_replies` | `continuation_token` |
| Channel id (from URL) | `GET /api/v1/youtube/web_v2/get_channel_id` | `channel_url` |
| Channel info | `GET /api/v1/youtube/web_v2/get_channel_description` | `channel_id`, `continuation_token` |
| General search | `GET /api/v1/youtube/web_v2/get_general_search` | `search_query`, `upload_time` |
| Shorts search | `GET /api/v1/youtube/web_v2/get_shorts_search` | `search_query`, `upload_time` |

## Example

```bash
tikin_run sh <<'TIKIN_COMMAND'
BASE="${TIKIN_BASE_URL:-https://console.tikin.net}"
curl -s --max-time 30 "$BASE/api/v1/youtube/web_v2/get_video_info?video_id=dQw4w9WgXcQ" \
  -H "Authorization: Bearer $TIKIN_API_KEY"
TIKIN_COMMAND
```

## Pagination

Comments, replies, channel feeds, and the `*_v2` search endpoints use `continuation_token` — pass
the token from the previous response; stop when none is returned.

**Each page is billed — every loop needs a budget.** With a user target, that target is the budget;
with no target, stop at the default 50 pages / 5,000 items from `tikin-rest-api`'s **Reliability**
section. When the budget ends the loop, report it as `budget exhausted` — pages and items fetched,
whether more remains, and the continuation token to resume from — instead of presenting a partial
pull as complete.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
3 attempts total, 1s then 2s backoff, `Retry-After` wins on a 429, and 401/403/404/422 are never
retried.

## Hand off to task skills

- Download videos / captions → `tikin-social-media-downloader`
- Analyze a channel → `tikin-creator-analytics`
- Comment mining → `tikin-comments-analysis`
- Search/listening → `tikin-social-listening`
- Large pulls → `tikin-bulk-data-export`

## Red flags

- Use `get_video_streams_v2` for downloadable media URLs; `get_video_info` is metadata only.
- A `video_id` is the 11-char id; pass full URLs to the `*_v2` variants.
