---
name: tikin-creator-analytics
metadata:
  version: "1.2.1"
description: v1.2.1｜Analyze a creator or account via tikin — profile stats, recent post performance, engagement rate, posting cadence, and top content. Use when the user asks for creator performance or provides a supported profile/channel URL or handle.
---

# Creator Analytics

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Profile a single account and summarize its performance. For comparing multiple accounts, use
`tikin-competitor-analysis`.

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
    --skill tikin-creator-analytics run -- "$@"
}
```

Resolve `TIKIN_SETUP_DIR` from the installed `tikin-setup` Skill before using the command.
Run API examples through `tikin_run` in the same shell as this definition. The helper reads
`TIKIN_API_KEY` and `TIKIN_BASE_URL` independently from process environment →
`$PWD/.env.tikin-creator-analytics` → `$PWD/.env.local` → `$PWD/.env` →
`~/.config/tikin-social/<skill-name>/.env.local` → that directory’s `.env` →
`~/.config/tikin-social/.env.<skill-name>` → the Plugin root’s `.env.local` → `.env` →
`~/.config/<skill-name>/.env`. Global sources are automatic; add `--no-global-config`
before `run` to skip all six for this call and use default routing without reading saved settings. Empty values fall through. Project files are read only in the
invocation directory; other Skills' dedicated files are not read. File contents are literal, never
sourced as shell code. Resolved values are passed only to the child command and are not printed.

If the loader reports a missing key or there is evidence of a configuration problem, follow the linked credential flow. If the user declines tikin, explain the
limitation and ask before selecting an alternative; do not silently fetch the original page.

## Workflow

1. **Identify platform + handle** from the user's input (URL or @handle).
2. **Resolve the user** to the id the API needs (e.g. TikTok/Douyin `sec_user_id` via
   `handler_user_profile`; Twitter `screen_name`/`rest_id`; Instagram `username`). See the
   platform skill for the exact endpoint.
3. **Fetch the profile** (followers, following, total likes/posts, bio) — the user-info endpoint.
4. **Fetch recent posts** (e.g. last 30–100) via the user's post-list endpoint, paginating with
   the platform's cursor under the page budget below, and tell the user the cost.
5. **Compute metrics** from the posts:
   - Engagement rate ≈ avg(likes + comments + shares) / followers.
   - Posting cadence (posts/week from timestamps).
   - Top 5 posts by engagement; median vs. top performance.
   - Trend over time (rising/declining views).
6. **Deliver** a concise report: headline stats, engagement rate, cadence, top content, and 2–3
   observations.

## Endpoint pointers (per platform)

Use the `tikin-endpoint-discovery` skill (`tikin-find-endpoint "user info" --platform <slug>`
and `"user posts" --platform <slug>`), or
the platform skill: `tikin-tiktok`, `tikin-douyin`, `tikin-instagram`, `tikin-youtube`,
`tikin-twitter-threads`, `tikin-xiaohongshu`.

## Cost awareness

Profile = 1 call; each page of posts = 1 call. Estimate before running (1 + pages) and warn the
user before pulling many pages. Check balance/usage anytime:

```bash
tikin_run sh <<'TIKIN_COMMAND'
BASE="${TIKIN_BASE_URL:-https://console.tikin.net}"
curl -s --max-time 30 "$BASE/api/usage/token/" -H "Authorization: Bearer $TIKIN_API_KEY"
TIKIN_COMMAND
```

**Budget the post-list loop.** With a user target post count, that target is the budget; with no
target, stop at **10 pages** — well inside the 50-page / 5,000-item default from `tikin-rest-api`'s
**Reliability** section, and enough for the 30–100 recent posts this report needs. When the budget
ends the loop, report it as `budget exhausted` (posts and pages fetched, whether more remain) and
say that the metrics describe that sample only.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
3 attempts total, 1s then 2s backoff, `Retry-After` wins on a 429, and 401/403/404/422 are never
retried.

## Verification gate

1. Profile resolved (non-empty follower/post counts).
2. Post list non-empty and timestamps parse.
3. Engagement math sanity-checked (rates between 0–100%).
4. Sample size stated, including whether the budget rather than the account ended the pull.

## Red flags

- Reporting an engagement rate from too few posts — note the sample size.
- Forgetting to resolve `sec_user_id`/numeric id before the post-list call.
