# Changelog

## 1.2.1 — 2026-10-08

- `tikin-setup` 及配置缺项提示改用 Setup AIHub 2.0.0 的 `setup-api-key` Skill；Plugin 安装名和业务配置位置保持兼容。

## 1.2.0 — 2026-10-08

- 将既有密钥的自然语言配置请求优先交给 Setup；远端 Key 创建说明按明确任务读取，避免与本机配置流程冲突。

- 配置 helper 支持 Windows `Scripts/python.exe`、含中文/空格路径与锁文件环境恢复。
- Windows 的配置子进程使用等待/转发退出码，避免 POSIX 风格进程替换在本机出现崩溃。
- 新增通过真实加载器计算的只读删除投影，支持真实 caller、共享模式及关闭全局读取。
- 凭证分支衔接 Setup AIHub 与最小回退，不执行路由初始化或完整 setup；其他业务的 Windows 适配另行验证。
- Codex 默认 Windows 沙箱、WorkBuddy 本机配置闭环及 Secret Book 真实表联调通过；Claude Code 安装、发现和自然触发通过，配置闭环未实测。

All notable changes to the tikin plugin are documented here.

## Unreleased

## 1.1.0

- Check the current Agent's applicable global/project instructions once per Plugin per session, with explicit task-to-Skill mappings for Codex, Claude Code and WorkBuddy.
- Offer set-as-default, skip-once or stop-reminding without blocking the original task. Rule writes require the user's approval of the exact text and target; existing equivalent rules, overrides and shared files are reviewed before editing.
- Add the offline `default-skills` helper and per-Agent/configuration-directory preferences in the Plugin's `settings.json`. Preserve other settings and routing, support re-enabling, and skip the workflow when global configuration is disabled.
- Keep business APIs, credentials and runtime support unchanged. File checks do not establish actual host-session loading.

## 1.0.0

- Moved the Plugin to `cookaihq/aihub-marketplace/tikin-social`, mirrored at
  `cnb.cool/zhidateam/tannt/aihub-marketplace`. The Plugin identity is now `tikin-social`;
  all 17 `tikin-*` Skill names and `TIKIN_*` API configuration fields are unchanged.
- Added a WorkBuddy Plugin manifest and native marketplace installation guidance. Native
  Windows execution is not yet supported by the POSIX helpers; marketplace visibility does
  not establish runtime compatibility.
- Configuration now uses `~/.config/tikin-social/`: current Skill overrides, Plugin shared
  files, then the current Skill’s `~/.config/<skill-name>/.env` fallback. Added per-call
  global disabling, exact field-source inspection, and read-only diagnostics. Old
  `~/.config/tikin/` or XDG locations are not read or migrated automatically.
- Updated both Python runtime versions and all Skill descriptions to 1.0.0. Installation,
  update and optional migration instructions now reference the new marketplace.

## 0.3.0

- Added per-Skill project configuration: process environment → `.env.<skill-name>` →
  `.env.local` → `.env` → the existing tikin home configuration. Values resolve independently,
  empty values fall through, and project files are read only in the invocation directory.
- Replaced shell sourcing in all operational Skills with the bundled `tikin-config --skill
  <name> run -- <command>` helper. Dotenv files contain literal values; credentials are passed
  to the child command without being printed. API workflows use the existing `tikin-setup`
  uv runtime, with no new Python dependencies.
- `status` and `validate` now use the same selected Skill configuration as API commands.
  Existing home fallback, routing preferences, and authentication behavior remain available.

## 0.2.1

- Gave every documented `curl` call an explicit time limit: `--max-time 30` for JSON reads and
  `--max-time 300` for media downloads. A call with no limit can hang a whole task.
- Added a **Reliability** section to `tikin-rest-api` as the single source of truth for timeouts,
  failure classification, retry budget, and pagination budgets. The other 16 skills reference it
  instead of restating their own numbers.
- Defined the retry policy concretely: 3 attempts in total with a 1s then 2s backoff for transient
  failures (429, 5xx, timeouts, connection errors), honouring `Retry-After` on a 429; 401, 403,
  404, and 422 are never retried.
- Replaced the qualitative "cap it" pagination guidance with quantified budgets. With no user
  target, the default is 50 pages or 5,000 items, plus tighter per-skill defaults where the task
  warrants them. A budget-capped pull is now reported as `budget exhausted` — how much was
  fetched, whether more remains, and the cursor to resume from — instead of being presented as
  complete.
- `tikin-config` now retries transient key-validation failures on that same schedule and logs each
  retry without the key; 401 and 403 still fail immediately. Its `validate --timeout` default is
  30s, matching the `--max-time 30` that **Reliability** mandates for JSON calls against `$BASE`;
  the previous 10s cap classified slow-but-healthy responses as transient failures.
- Pinned the runtime for both bundled Python CLIs. `tikin-setup` and `tikin-endpoint-discovery`
  each carry a `pyproject.toml`, `uv.lock` and `.python-version` (3.13), run from their own
  `.venv`, and re-exec themselves onto that interpreter (rebuilding it from the lockfile with
  `uv sync --no-dev` when missing) instead of using whatever `python3` the PATH resolves to.
  Documented invocations now use `uv run --project <this-skill-dir>`; uv >= 0.8 is required.
  The README now states this per skill instead of claiming the whole plugin needs only `curl`
  and `python3`.
- `tests/test_tikin_config.py` launches `tikin-config` on that prebuilt `.venv` interpreter rather
  than on `sys.executable`, so the suite no longer triggers the script's own bootstrap mid-test.
  Without a prebuilt runtime it builds one via `uv sync --no-dev`, and on a machine with no uv at
  all it skips with the exact build command instead of failing every test.
- Removed the inline `python3 -c` URL-encoding helper from `tikin-social-media-downloader` in
  favour of curl's own `-G --data-urlencode`.

## 0.2.0

- Added a native Codex plugin manifest and Codex marketplace catalog alongside the Claude Code
  plugin distribution.
- Standardized all 17 skill identifiers and directory names under the `tikin-*` namespace, with
  `tikin-setup` as the installation, authentication, routing-configuration, and update entry point.
- Moved the dotenv fallback to `~/.config/tikin/.env` and added non-secret behavior settings at
  `~/.config/tikin/settings.json`.
- Added all-platform and per-platform `auto` or `confirm` routing. Fresh installs default to
  automatic tikin routing for every supported platform; confirmation is once per user task.
- Required supported social-media URLs to go through the corresponding tikin skill instead of
  being fetched directly from the source platform with a generic HTTP client.
- Added a non-blocking update check on the first tikin use in each agent session. Updates preserve
  user configuration, do not interrupt the current task, and take effect in the next session.
- Added browser-assisted API-key setup with user-controlled login and a safe local-input fallback.

## 0.1.0

Initial release.

- **Cross-agent by design:** skills follow the [Agent Skills](https://agentskills.io) open
  standard and work in Claude Code, Codex, and other skills-compatible agents. Install via
  `npx skills add`, the Claude Code plugin marketplace, or manual copy.
- 17 foundation, platform, and task skills, including a bundled endpoint-search CLI over more
  than 1,000 endpoints.
- Single REST path against `https://console.tikin.net` with a tikin API key; per-call prepaid
  billing; balance/usage via `GET /api/usage/token/`.
- Bundled endpoint index covering 1,000+ endpoints across the supported platforms.
