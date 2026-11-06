---
name: tikin-creator-analytics
metadata:
  version: "3.0.0"
description: v3.0.0｜通过 Tikin 分析创作者或账号的资料统计、近期内容表现、互动率、发布频率和热门内容。适用于创作者表现分析，或用户提供受支持平台的账号、频道链接或用户名。
---

# Creator Analytics

新建、继续或交付业务任务前，读取并遵守[任务保存与产物页面](../tikin-setup/references/artifacts.md)；它规定任务命名、可靠会话/Agent 身份、最终文件登记与页面入口。离线查询或配置本身不创建成果任务。

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并实际打开本 Plugin 配置中心；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则按该流程的固定顺序和推荐项提供选择；选择设为默认后直接设置，完成后展示内容。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Profile a single account and summarize its performance. For comparing multiple accounts, use
`tikin-competitor-analysis`.

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

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/usage/token/"
}
```

**Budget the post-list loop.** With a user target post count, that target is the budget; with no
target, stop at **10 pages** — well inside the 50-page / 5,000-item default from `tikin-rest-api`'s
**Reliability** section, and enough for the 30–100 recent posts this report needs. When the budget
ends the loop, report it as `budget exhausted` (posts and pages fetched, whether more remain) and
say that the metrics describe that sample only.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
let the shared executor enforce side effects, the full cooldown and remaining attempt budget.
Do not add an outer retry loop or resubmit an unknown operation.

## Verification gate

1. Profile resolved (non-empty follower/post counts).
2. Post list non-empty and timestamps parse.
3. Engagement math sanity-checked (rates between 0–100%).
4. Sample size stated, including whether the budget rather than the account ended the pull.

## Red flags

- Reporting an engagement rate from too few posts — note the sample size.
- Forgetting to resolve `sec_user_id`/numeric id before the post-list call.
