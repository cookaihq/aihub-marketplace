---
name: tikin-social-media-downloader
metadata:
  version: "1.3.0"
description: v1.3.0｜Download video, audio, or images (no-watermark where available) from a social-media URL or list of URLs. Use when the user pastes a TikTok/Douyin/Instagram/YouTube/Twitter/Xiaohongshu link and wants the media file, or says "download this video", "save without watermark", "grab the audio". Dispatches to the right per-platform tikin endpoint.
---

# Social Media Downloader

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Turn a post URL into a saved media file by routing it to the correct platform endpoint, extracting
the media URL from the response, and downloading it.

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

## Step 1 — Detect the platform from the URL and pick the endpoint

| Platform | Endpoint | Input | Media field |
|---|---|---|---|
| TikTok | `GET /api/v1/tiktok/app/v3/fetch_one_video_by_share_url` | `share_url` | no-watermark `play_addr` / `download_addr` `url_list` |
| TikTok (by id) | `GET /api/v1/tiktok/app/v3/fetch_one_video` | `aweme_id` | `url_list` |
| Douyin | `GET /api/v1/douyin/app/v3/fetch_one_video_by_share_url` | `share_url` | video `url_list` |
| Douyin (by id) | `GET /api/v1/douyin/app/v3/fetch_one_video_v2` | `aweme_id` | video `url_list` |
| YouTube | `GET /api/v1/youtube/web_v2/get_video_streams_v2` | `video_id` \| `video_url` | stream URLs (pick resolution) |
| Instagram | `GET /api/v1/instagram/v2/fetch_post_info` | `code_or_url` | media URL(s) |
| Xiaohongshu | `GET /api/v1/xiaohongshu/app_v2/get_video_note_detail` (video) / `get_image_note_detail` (images) | `note_id` | video / image URLs |
| Twitter/X | `GET /api/v1/twitter/web/fetch_tweet_detail` | `tweet_id` | media `url_list` |

For TikTok/Douyin, the `*_by_share_url` endpoints take the raw URL directly — no need to extract an
id. For the others, pull the id/code from the URL (or resolve it via the platform skill).

## Step 2 — Call the endpoint

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/tiktok/app/v3/fetch_one_video_by_share_url",
  "query": {
    "share_url": "$URL"
  }
}
```

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/youtube/web_v2/get_video_streams_v2",
  "query": {
    "video_id": "dQw4w9WgXcQ"
  }
}
```

Timeouts, which failures to retry (and which never to): follow the **Reliability** section in
`tikin-rest-api`.

## Step 3 — Extract the media URL, then download

Parse the response for the highest-quality (no-watermark, for TikTok/Douyin) media URL — usually a
`url_list` array or a stream URL. Use Python's standard `json` module for structured parsing;
do not introduce a `jq` dependency unless it is already available and the user prefers it. Then
save the returned media URL:

```bash
curl -L --max-time 300 "<media_url_from_response>" -o video.mp4
file video.mp4   # confirm it's a real media container
```

`--max-time 300` is the media-download limit from `tikin-rest-api`'s **Reliability** section. For a
file known to be much larger, raise the value explicitly and say so — never drop the flag.

## Batch downloads

Loop over a URL list, **one at a time with a small delay** (respect QPS 10/sec). Each parse is one
billed call — warn the user for large batches and hand off to `tikin-bulk-data-export` for big jobs.

**Budget the batch.** The user's list length is the budget when they gave one. **With no stated
target, stop after 50 URLs in a single run.** On hitting the cap, stop and report it as
`budget exhausted`: how many URLs were downloaded, how many failed, and exactly which URLs are
still unprocessed, so the user can approve a follow-up run. Never trim the list silently.

Transient errors (429/5xx/timeouts) and the retry budget: follow the **Reliability** section in
`tikin-rest-api`. A URL that fails all 3 attempts is reported as failed for that entry — keep going
through the rest of the batch rather than aborting the whole run.

## Verification gate

1. Response is `code: 200` and contains a non-empty media URL.
2. Downloaded file is non-empty and the expected type (`file video.mp4` shows a video container).
3. Not an auth/credit error.

## Red flags

- Claiming a download succeeded without checking the file is non-empty/valid.
- Using the wrong platform endpoint for a URL — detect the platform first.
- Unbounded batch loops (credit burn + rate limits).
- Re-hosting/redistributing copyrighted media — respect platform ToS and the user's rights.
