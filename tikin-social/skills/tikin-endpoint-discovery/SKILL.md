---
name: tikin-endpoint-discovery
metadata:
  version: "1.3.0"
description: v1.3.0｜Find the right tikin endpoint among 1,000+ across 16+ platforms. Use when you know the goal (e.g. "get a user's posts on Douyin") but not the exact API path, or when a platform has no dedicated skill (LinkedIn, Reddit, Bilibili, Weibo, WeChat, Kuaishou, Zhihu, Lemon8, etc.). Searches a bundled index and maps results to REST calls.
---

# tikin — Endpoint Discovery

纯凭证请求、首次配置或实际配置错误时，先按[统一凭证流程](../tikin-setup/references/credential-setup.md)检查真实来源并衔接 Setup 或最小回退；不为检查密钥执行整套 tikin-setup。已有可读配置正常执行业务，保留实际 caller、cwd、全局开关和原任务提交状态。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](../tikin-setup/references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

tikin has 1,000+ endpoints. This skill finds the one you need, then hands off to `tikin-rest-api`.

## Runtime gate

On the first tikin use in each Agent session, follow the `tikin-setup` session update gate once
without blocking endpoint discovery. The bundled index remains searchable offline without a key.

When the user supplies a supported social-media URL, identify its platform before making a
call. If this task disables global configuration, do not read
`~/.config/tikin-social/settings.json`; use the built-in routing
`{"routing":{"default":"auto","platforms":{}}}` and pass `--no-global-config` before every
helper subcommand. Otherwise read that file as JSON from the runtime user’s home directory
(no XDG or legacy alias lookup), using the same built-in routing when the file is absent.
An explicit user instruction wins over the platform override and routing default. Ask once per
task for `confirm` platforms.

Never request the user-provided social-media content page with `curl`, WebFetch, or a generic
browser fetch. Parse identifiers locally or pass the original URL/share text to the selected tikin
endpoint. Before calling an endpoint, resolve and require the key:

Before any business API request, read [shared requests and local error reports](../tikin-setup/references/requests.md). Use `tikin-config request` with this Skill as caller and reuse the returned `--record` for the same task. On every failure, recovery and final reply, copy all `feedback.artifact_links` with full absolute paths as link labels.

## Use the bundled search CLI

`scripts/tikin-find-endpoint` — bundled **inside this skill's directory** — searches a trimmed
index of every endpoint (method, path, tag, summary, params). Run it by path relative to this
skill's directory (it works from any cwd; no PATH setup needed):

```bash
# goal-based search, scoped to a platform
uv run --frozen --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-find-endpoint" "one video" --platform tiktok
uv run --frozen --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-find-endpoint" "user posts" --platform douyin
uv run --frozen --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-find-endpoint" "comments" --platform youtube --method GET

# no platform filter — search everything
uv run --frozen --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-find-endpoint" "trending hashtag"
```

(`<this-skill-dir>` = the directory containing this SKILL.md. Other skills refer to this tool
as `tikin-find-endpoint` for short — it always means this script.)

The CLI runs on this skill's own pinned interpreter, declared by `pyproject.toml`, `uv.lock`
and `.python-version` beside this file. Install the sibling `tikin-setup` Skill for the shared bootstrap. Always launch it through `uv run --frozen --project "<this-skill-dir>" python`; never through a
bare `python3` or the bare script path, which resolve to whatever the PATH happens to point at. It
needs [uv](https://docs.astral.sh/uv/) >= 0.8 — if `uv` is missing the CLI says so and prints the
install command. The CLI also re-execs itself into `<this-skill-dir>/.venv` and rebuilds that
environment from `uv.lock` when it is missing, so a wrong or absent interpreter is repaired rather
than silently used. Searching the index needs no network and no API key.

Output lines look like:
```
GET  /api/v1/tiktok/app/v3/fetch_one_video  [TikTok-App-V3-API]  params: aweme_id
```

The index lives at `references/endpoint-index.json` (beside the script, inside this skill),
ships with the skill, and is refreshed on new releases when the API surface changes.

## Map a result to a call

Given `GET /api/v1/{platform}/{api}/{action}`, call it via REST (see `tikin-rest-api`):

```json
{
  "original_request": "<用户原始需求原文>",
  "method": "GET",
  "path": "/api/v1/tiktok/app/v3/fetch_one_video",
  "query": {
    "aweme_id": "..."
  }
}
```

Timeouts, which failures to retry (and which never to), and pagination budgets: follow the
**Reliability** section in `tikin-rest-api`.

## Platforms without a dedicated skill

For LinkedIn, Reddit, Bilibili, Weibo, WeChat, Kuaishou, Zhihu, Lemon8, Toutiao, Xigua,
and more, discovery + REST is the path — there are no dedicated platform skills.

## Red flags

- Guessing endpoint paths instead of searching the index (paths and param names are specific).
- Forgetting param names — the CLI prints them; pass them exactly.
