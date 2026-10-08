---
name: tikin-hashtag-research
metadata:
  version: "1.2.0"
description: v1.2.0｜Research a hashtag or keyword via tikin — popularity signals, top and recent content, and related hashtags across supported platforms. Use when the user asks about a hashtag, related tags, content ideas, or supplies a supported hashtag URL.
---

# Hashtag Research

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Assess a hashtag/keyword and surface its top content and related tags.

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
    --skill tikin-hashtag-research run -- "$@"
}
```

Resolve `TIKIN_SETUP_DIR` from the installed `tikin-setup` Skill before using the command.
Run API examples through `tikin_run` in the same shell as this definition. The helper reads
`TIKIN_API_KEY` and `TIKIN_BASE_URL` independently from process environment →
`$PWD/.env.tikin-hashtag-research` → `$PWD/.env.local` → `$PWD/.env` →
`~/.config/tikin-social/<skill-name>/.env.local` → that directory’s `.env` →
`~/.config/tikin-social/.env.<skill-name>` → the Plugin root’s `.env.local` → `.env` →
`~/.config/<skill-name>/.env`. Global sources are automatic; add `--no-global-config`
before `run` to skip all six for this call and use default routing without reading saved settings. Empty values fall through. Project files are read only in the
invocation directory; other Skills' dedicated files are not read. File contents are literal, never
sourced as shell code. Resolved values are passed only to the child command and are not printed.

If the loader reports a missing key or there is evidence of a configuration problem, follow the linked credential flow. If the user declines tikin, explain the
limitation and ask before selecting an alternative; do not silently fetch the original page.

## Workflow

1. **Pick platform(s)** and the hashtag/keyword.
2. **Pull signals + content:**
   - TikTok: `ads/get_trends_hashtag_detail` (`hashtag_id`) and `ads/get_trends_hashtag_list`;
     pull videos under a hashtag with `app/v3/fetch_hashtag_video_list` (`ch_id`).
   - Douyin: `search/fetch_general_search_v2` (POST) for hashtag/keyword content.
   - Instagram: `v2/search_hashtags` + `v2/fetch_hashtag_posts`.
   - Xiaohongshu: `app_v2/search_notes` (keyword).
   - Discover exact paths via the `tikin-endpoint-discovery` skill (`tikin-find-endpoint "hashtag" --platform <slug>`).
3. **Summarize**: estimated popularity/volume, top posts (engagement), recent momentum, and a list
   of related/co-occurring hashtags pulled from the top posts.
4. **Recommend** a tag set for the user's niche.

## Cost awareness

Detail/list calls are 1 each; pulling top-posts pages multiplies calls. Warn before deep pulls.
Every call carries `--max-time 30` (see the **Reliability** section in `tikin-rest-api`).

**Budget the top-posts loop.** With a user target post count, that target is the budget; with no
target, stop at **5 pages per hashtag per platform**, inside the overall 50-page / 5,000-item
default from `tikin-rest-api`'s **Reliability** section. When the budget ends the loop, report it
as `budget exhausted` (pages and posts fetched, whether more remain) and say that the related-tag
list is derived from that sample only.

Transient errors (429/5xx/timeouts): follow the **Reliability** section in `tikin-rest-api` —
3 attempts total, 1s then 2s backoff, `Retry-After` wins on a 429, and 401/403/404/422 are never
retried. A 404 here usually means the hashtag does not exist — report "no data", do not retry.

## Verification gate

1. Hashtag resolved (or clearly report "no data / low volume").
2. Top posts are actually tagged with the hashtag.
3. Related tags derived from real co-occurrence, not guessed.
4. Sample size stated, including whether the budget capped the pull.

## Red flags

- Inventing volume numbers — only report what the API returns; otherwise say "not available".
- Recommending banned/irrelevant tags.
