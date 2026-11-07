---
name: tikin-youtube
metadata:
  version: "3.1.0"
description: v3.1.0｜通过 Tikin 处理 YouTube 链接与数据，获取视频信息、可下载的媒体流链接、字幕、评论与回复及频道资料，执行综合搜索或 Shorts 搜索。用户提供 YouTube 链接或任务针对该平台时使用；覆盖 YouTube Web-V2 接口。
---

# YouTube (via tikin)

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../tikin-setup/references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开本 Plugin 配置中心；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

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
5. Before any business API request, read [shared requests and local error reports](../tikin-setup/references/requests.md). Use `tikin-config request` with this Skill as caller and reuse the returned `--record` for the same task. On every failure, recovery and final reply, copy all `feedback.artifact_links` with full absolute paths as link labels.

If the loader reports a missing key or there is evidence of a configuration problem, follow the linked credential flow. If the user declines tikin, explain the
limitation and ask before selecting an alternative; do not silently fetch the original page.

**Coverage:** YouTube-Web-V2. (The older YouTube-Web API is de-scoped — reach it via discovery.)

## Key endpoints

| Goal | Method + path | Key params |
|---|---|---|
| Video info | `GET /api/v1/youtube/web_v2/get_video_info` | `video_id`, `language_code` |
| Video info by URL | `GET /api/v1/youtube/web_v2/get_video_info_v2` | `video_url` |
| Download streams | `GET /api/v1/youtube/web_v2/get_video_streams_v2` | `video_id` \| `video_url` |
| Proxy download streams (candidate) | `POST /api/v1/youtube/web_v2/get_video_streams_v3` | JSON: `video_id`, `proxy_url`, optional `itags`, `verify_download` |
| Captions/subtitles | `GET /api/v1/youtube/web_v2/get_video_captions` | `video_id`, `language_code`, `format` |
| Caption job result | `GET /api/v1/youtube/web_v2/get_video_captions_result` | `job_id`, `format` |
| Video comments | `GET /api/v1/youtube/web_v2/get_video_comments` | `video_id`, `sort_by`, `continuation_token` |
| Comment replies | `GET /api/v1/youtube/web_v2/get_video_comment_replies` | `continuation_token` |
| Channel id (from URL) | `GET /api/v1/youtube/web_v2/get_channel_id` | `channel_url` |
| Channel info | `GET /api/v1/youtube/web_v2/get_channel_description` | `channel_id`, `continuation_token` |
| General search | `GET /api/v1/youtube/web_v2/get_general_search` | `search_query`, `upload_time` |
| Shorts search | `GET /api/v1/youtube/web_v2/get_shorts_search` | `search_query`, `upload_time` |

## Example

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/youtube/web_v2/get_video_info",
  "query": {
    "video_id": "dQw4w9WgXcQ"
  }
}
```

## Proxy download workflow

For V3, follow [metadata and same-proxy downloading](../tikin-setup/references/downloads.md).
Retain the successful request output and original proxy in private files, then use
`tikin-config download` with the explicit exit-check URL. Metadata HTTP 200 and sampled
bytes are not a complete download; verify all selected streams and report any required
local merge separately. Do not silently use the V2 route or direct downloading to bypass
missing proxy, verification or candidate-service prerequisites.

## Caption workflow

Treat `get_video_captions` as a request that may create a paid job, even though it
uses GET. The executor enforces side effects for this operation. First omit
`language_code` to obtain available languages; choose an actual returned language
when requesting content. A synchronous response does not validate the async path.

On `status: processing` with `job_id`, retain the same `--record` and query
`get_video_captions_result` using that job and selected format. The executor returns
`waiting` for processing/queued/active states; an empty intermediate array is not
final absence. A repeated known creation in the same record returns `task_exists`
with the existing job instead of creating another one.

```json
{
  "original_request": "<用户原始字幕需求>",
  "method": "GET",
  "path": "/api/v1/youtube/web_v2/get_video_captions_result",
  "query": {"job_id": "<returned job_id>", "format": "srt"}
}
```

The result query is explicitly zero-priced in this frozen catalog; real free
billing still requires current configuration/usage evidence. The shared executor
marks it read-only, spaces waiting queries by at least 2 seconds, and preserves a
maximum of 10 query attempts / 60 seconds per job in the same record. Retries count
toward those limits. On `poll_budget_exhausted`, preserve the job and report waiting;
do not restart creation or discard the record to renew a loop. Resume only within
an explicitly approved new polling budget and the same regression allowance, if used.

Only completed/ready output with verified final content is a result. A failed job
remains a failure with its original ID and report. A timeout or uncertain creation
is not permission to resubmit. A completed empty/no-caption response may still be
charged; do not infer free usage from HTTP 200 or an empty list. This workflow
is separate from the LinkedIn task workflow in the second-batch guide.

## Pagination

Comments, replies, channel feeds, and the `*_v2` search endpoints use `continuation_token` — pass
the token from the previous response; stop when none is returned.

**Each page is billed — every loop needs a budget.** With a user target, that target is the budget;
with no target, stop at the default 50 pages / 5,000 items from `tikin-rest-api`'s **Reliability**
section. When the budget ends the loop, report it as `budget exhausted` — pages and items fetched,
whether more remains, and the continuation token to resume from — instead of presenting a partial
pull as complete.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
let the shared executor enforce side effects, the full cooldown and remaining attempt budget.
Do not add an outer retry loop or resubmit an unknown operation.

## Hand off to task skills

- Download videos / captions → `tikin-social-media-downloader`
- Analyze a channel → `tikin-creator-analytics`
- Comment mining → `tikin-comments-analysis`
- Search/listening → `tikin-social-listening`
- Large pulls → `tikin-bulk-data-export`

## Red flags

- Use a supported streams operation for media URLs; `get_video_info` is metadata only.
- V3 links require the original proxy, exit, headers and expiry conditions through the
  shared download entry. A missing real proxy sample leaves that capability unverified.
- A `video_id` is the 11-char id; pass full URLs to the `*_v2` variants.
