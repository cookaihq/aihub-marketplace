---
name: tikin-comments-analysis
metadata:
  version: "1.3.0"
description: v1.3.0｜Pull and analyze comments from a supported post or video URL via tikin — sentiment breakdown, recurring themes, top comments, and notable questions or complaints. Use when the user asks to analyze comments, summarize discussion, or provides a social-media post URL.
---

# Comments Analysis

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Mine a single post's comment section for sentiment and themes.

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

## Workflow

1. **Identify the post** (platform + id/URL).
2. **Fetch comments**, paginating to a target count (cap it):
   - TikTok: `app/v3/fetch_video_comments` (`aweme_id`, `cursor`). Douyin: `app/v3/fetch_video_comments` (`aweme_id`, `cursor`).
   - Instagram: `v2/fetch_post_comments` (+ `fetch_comment_replies`).
   - YouTube: `web_v2/get_video_comments` (+ `get_video_comment_replies`).
   - Twitter: `web/fetch_post_comments`. Xiaohongshu: `app_v2/get_note_comments`.
3. **Optional fast keywords:** TikTok `analytics/fetch_comment_keywords` (`item_id`) gives a
   comment keyword summary directly.
4. **Analyze:** sentiment breakdown, top themes with example quotes, most-liked comments, and any
   recurring questions/complaints.
5. **Deliver** a summary with cited example comments.

## Cost awareness

Each comment page (and reply page) is a billed call. Warn for viral posts with huge threads. Check
balance/usage with
the shared request helper with `method=GET` and `path=/api/usage/token/`.

**Every comment and reply loop needs a budget.** With a user target comment count, that target is
the budget; with no target, stop at the default 50 pages / 5,000 comments from `tikin-rest-api`'s
**Reliability** section — counted across the comment and reply loops combined, not per loop. When
the budget ends the pull, report it as `budget exhausted`: comments fetched, pages fetched, and
whether more remain.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
3 attempts total, 1s then 2s backoff, `Retry-After` wins on a 429, and 401/403/404/422 are never
retried.

## Verification gate

1. Comments fetched and tied to the right post.
2. Themes/sentiment backed by quoted comments.
3. Report the sample size (comments analyzed vs. total) and whether the budget capped the pull.

## Red flags

- Summarizing 50 comments on a 50k-comment post as representative — disclose the sample.
- Unbounded reply pagination.
- Presenting a budget-capped sample as if the whole thread was read.
