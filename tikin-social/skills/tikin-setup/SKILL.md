---
name: tikin-setup
metadata:
  version: "1.3.0"
description: v1.3.0｜安装、更新或修复 tikin 套件，管理平台路由和默认 Skill 提醒。既有接口密钥的填写、更换、缺项与修复优先交给 setup-api-key；其不可用时提供本机配置回退。Install or maintain tikin; delegate existing credential setup to setup-api-key.
---

# tikin Setup

## 先确定当前任务

用户问“接口密钥怎么填”、配置既有 Key、首次配置或修复缺项时，**先读取[统一凭证流程](references/credential-setup.md)**。当前宿主能调用兼容的 `setup-aihub:setup-api-key`，就实际调用该 Skill 并将来源/范围选择、原任务和真实 caller 交给它；没有业务 caller 时保持共享检查。只询问填写方法而尚未授权执行检查时，同样由该入口提供说明，不运行程序。

Setup 不可用时，按同一引用的最小回退办理。此凭证分支以真实加载器的本机复查结束；下面的安装、更新、路由和远端 Key 管理是其他任务，只有用户明确请求对应动作时才进入。已有可读配置的正常业务直接返回原业务 Skill。

## 默认 Skill 检查

每次会话首次使用本 Plugin 时，先按[默认 Skill 检查与提醒](references/default-skills.md)核对当前 Agent 的实际规则。已有等效默认规则或已关闭提醒时不询问；否则提供“设为默认 / 本次跳过 / 不再提醒”。同一 Plugin 本会话只提示一次，不阻塞当前任务；禁用全局配置时跳过。

Use this entry for the specific installation, credential, routing or update task requested. A credential-only request follows the linked credential flow and returns without the other setup stages.

## Local state

Resolve local state through `scripts/tikin-config`; do not parse or print secrets yourself.
Use `config-check` or `status` for a read-only diagnosis. Run `init` only when initializing
routing is authorized. If this task disables global configuration, skip `init`, `set-key`,
`set-routing` and any direct settings-file read; use built-in routing and pass
`--no-global-config` before each read-only helper subcommand.

```bash
uv run --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-config" init
uv run --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-config" status
```

(`<this-skill-dir>` = the directory containing this SKILL.md.)

The helper runs on this skill's own pinned interpreter, declared by `pyproject.toml`,
`uv.lock` and `.python-version` beside this file. Always launch it through `uv run --project <this-skill-dir>`; never
through a bare `python3`, which resolves to whatever the PATH happens to point at. It needs
[uv](https://docs.astral.sh/uv/) >= 0.8 — if `uv` is missing the helper says so and prints the
install command. The helper also re-execs itself into `<this-skill-dir>/.venv` and rebuilds that
environment from `uv.lock` when it is missing, so a wrong or absent interpreter is repaired rather
than silently used.

The stable Plugin identity is `tikin-social`, shared by its Claude Code, Codex and WorkBuddy
manifests. The helper also carries this explicit identity for Agent Skills installs without a
Plugin manifest; it never guesses from the installation path. Global files use the runtime
user’s home directory, not `XDG_CONFIG_HOME` or old product aliases:

- `~/.config/tikin-social/.env` is the confirmed default for new shared credentials.
- `~/.config/tikin-social/settings.json` stores non-secret routing and default-Skill reminder preferences.

Each API field resolves independently from environment → `$PWD/.env.<skill-name>` →
`$PWD/.env.local` → `$PWD/.env` → `~/.config/tikin-social/<skill-name>/.env.local` →
that directory’s `.env` → `~/.config/tikin-social/.env.<skill-name>` → Plugin root `.env.local`
→ Plugin root `.env` → `~/.config/<skill-name>/.env`. Missing or empty fields fall through;
empty directories do not block fallback. Only the invocation directory and current Skill’s
listed files are read. Existing unreadable files fail explicitly. Dotenv values are literal,
never shell-sourced; only `TIKIN_API_KEY` and `TIKIN_BASE_URL` are recognized.

Pass the calling Skill’s exact name before `status`, `config-check`, `validate` or `run`, for
example `--skill tikin-douyin config-check`. The default caller is `tikin-setup`.
`--plugin-only` selects no caller and reads only project shared files and Plugin shared global
files. `--no-global-config` skips both Plugin and ordinary Skill global files for that invocation
(and uses default routing); `--use-global-config` is a compatibility no-op and conflicts with it.
Put these options before the subcommand. `status`, `config-check`, `get-policy`, `validate`, and
`run` do not create, chmod or migrate configuration files. `init` only initializes routing and
protects the current Plugin’s shared files; it does not migrate old `tikin` or XDG locations.

For credentials, read [the unified inspection, Setup handoff and fallback](references/credential-setup.md). That flow uses config-check, preserves the real caller and never initializes routing. `set-key` is reserved for an explicitly authorized shared-file write that also allows its routing initialization; it is not a generic repair command.

Old `~/.config/tikin/.env`, `~/.config/tikin/settings.json` and custom XDG locations are not read.
Migration is optional and requires an explicit source, target and overwrite decision; preserve
unrelated fields and existing higher-priority settings. Ordinary `~/.config/<skill-name>/.env`
fallback needs no migration. Never expose credentials in chat, logs or commits.

Before any business API request, read [shared requests and local error reports](references/requests.md). Use `tikin-config request` with this Skill as caller and reuse the returned `--record` for the same task. On every failure, recovery and final reply, copy all `feedback.artifact_links` with full absolute paths as link labels.

`run -- <command>` remains a configuration utility; it does not record arbitrary child HTTP traffic.

## Install or repair

Detect the active host and existing installation from its CLI/configuration. Do not infer it from
directory or branch names. Before a first install or installation-scope change, tell the user what
will be written and get confirmation. Use exactly one matching path:

| Host | Install path |
|---|---|
| Codex plugin | If absent, run `codex plugin marketplace add cookaihq/aihub-marketplace`, then `codex plugin add tikin-social@aihub-marketplace`. |
| Claude Code plugin | If absent, run `claude plugin marketplace add cookaihq/aihub-marketplace`, then `claude plugin install tikin-social@aihub-marketplace --scope <scope>` with the confirmed `user`, `project`, or `local` scope. |
| WorkBuddy | Use the native marketplace installer with `https://github.com/cookaihq/aihub-marketplace.git` and select `tikin-social`. When manual UI is required: 专家·技能·连接器 → 技能 → 套件 → circular ＋ beside the marketplace names; after adding the market click ＋ on the `tikin-social` card. “添加市场” is the dialog title, not the visible initial button. |
| Agent Skills client | Run `npx skills add https://github.com/cookaihq/aihub-marketplace/tree/main/tikin-social --skill '*'` and select only the active agent and requested project/user scope. |

If GitHub has a network failure, use the same marketplace and Plugin from
`https://cnb.cool/zhidateam/tannt/aihub-marketplace.git`. Keep the same requested version and
scope; authentication, missing repository or missing version is not a network fallback trigger.
Report which source succeeded. Do not guess a WorkBuddy CLI command or tool schema: inspect
its available native tools and current UI. Do not start codebuddy/cbc or an embedded CLI, even for help/list. The shared request and endpoint helpers use pinned Python and quoted paths on native Windows; final media downloads use curl.exe there. Local configuration tests do not prove host loading or complete Windows business support; macOS/Linux/WSL and all three host sessions require their own evidence.

Do not install through several channels in the same host. If an old manual copy contains
unprefixed skill names, migrate to the managed channel and remove only obsolete tikin-owned
copies; never delete a user-modified or unrelated skill without confirmation.

Newly installed plugin components become available in a new chat or CLI session. Finish local
configuration in the current session, then tell the user when a new session is required.

## Session update gate

On the first tikin use in each Agent session, start one best-effort update check. Do not repeat it
for later tikin calls in the same session and do not block the user's current task.

1. Detect the channel owning this installation. The new Plugin is
   `tikin-social@aihub-marketplace`. `tikin-plugin@plugin-marketplace` and
   `tikin-plugin@tikin-plugins` are old identities; do not silently upgrade those into a new
   identity or move credentials. Prepare the new installation and configuration, disable the old
   Plugin, then open a new session and verify the new Plugin identity and actual Skill sources.
   Only after verification succeeds remove the old instance authorized by the user. Never test
   while both Plugin copies supply the same `tikin-*` names.
2. Check only that channel and only tikin-owned components.
3. For Codex, record the installed version from `codex plugin list --marketplace aihub-marketplace
   --json`, refresh with `codex plugin marketplace upgrade aihub-marketplace`, then run `codex plugin
   add tikin-social@aihub-marketplace`. Repeated `plugin add` is the idempotent reinstall/update path
   for Git-backed plugin sources; compare the before/after installed versions only when reporting
   whether an update occurred.
4. For Claude Code, read the owning installation's `scope` from `claude plugin list --json`, then
   use `claude plugin update tikin-social@aihub-marketplace --scope <scope>`. Do not let the command's
   `user` default redirect an update for a `project`, `local`, or `managed` installation.
5. For WorkBuddy use its actual native Plugin update UI/tool for `tikin-social`; do not write
   cache/index files manually. For Agent Skills, use the source-aware `npx skills` updater for installed `tikin-*` skills only.
6. If an update succeeds, keep using the already-loaded version for the current task and state
   that the new version applies in a new session.
7. If the network, updater, sandbox, or approval policy prevents the check, continue silently
   with the installed version; mention it only when the user asks about updates or setup health.

Never send the API key, user URLs, or task data during a version check. Never update unrelated
plugins or skills. Preserve `.env` and `settings.json` across updates.

## Remote key creation or online validation

Only when the user explicitly requests creation of a remote key or online authentication, read [remote key maintenance](references/remote-key-maintenance.md). Existing-key configuration uses the credential branch above; it ends with a local check.

## Configure routing

If `settings.json` is absent, `init` creates this default:

```json
{
  "routing": {
    "default": "auto",
    "platforms": {}
  }
}
```

Offer these choices during first setup and when the user asks to change preferences:

```bash
# All supported platforms use tikin automatically (default).
uv run --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-config" set-routing --default auto --clear-platforms

# Every supported platform requires confirmation.
uv run --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-config" set-routing --default confirm --clear-platforms

# Only selected platforms are automatic; all others require confirmation.
uv run --project "<this-skill-dir>" python "<this-skill-dir>/scripts/tikin-config" set-routing --default confirm --clear-platforms \
  --platform xiaohongshu=auto --platform douyin=auto
```

Supported policy slugs are `tiktok`, `douyin`, `instagram`, `youtube`, `twitter`, `threads`, and
`xiaohongshu`. A platform override wins over `routing.default`; an explicit instruction in the
current user request wins over both. In `confirm` mode, ask once per user task, group all affected
platforms/actions into that prompt, and do not ask again for pagination within the approved task.

## Route the task

| User outcome | Owning skill |
|---|---|
| 既有接口密钥配置、更换、缺项或修复 | 当前发现的 `setup-aihub:setup-api-key`；不可用时按[凭证回退](references/credential-setup.md) |
| Install, updates, routing settings; explicitly requested remote key creation or online validation | `tikin-setup` |
| Find an endpoint among 1,000+ | `tikin-endpoint-discovery` |
| Direct REST details | `tikin-rest-api` |
| Platform-specific work | `tikin-tiktok`, `tikin-douyin`, `tikin-instagram`, `tikin-youtube`, `tikin-twitter-threads`, `tikin-xiaohongshu` |
| Download, analytics, trends, listening, comparison, hashtags, comments, bulk export | The matching `tikin-*` task skill |

For a supported social-media URL, invoke the owning tikin skill. Never use `curl`, WebFetch, or a
generic browser fetch against the user-provided social-media content page. It is valid to parse an
ID locally, pass the original URL/share text to a tikin API endpoint, call the configured tikin
base URL, and download a final media URL returned by tikin. If the user declines tikin, explain
the limitation and ask before choosing an alternative; do not silently fetch the original page.

## Completion gate

Before handing off, confirm without revealing secrets that:

1. The intended package is installed or already present.
2. Local credential status and any separately requested online authentication result are reported independently.
3. The task’s effective routing policy has been applied: saved settings when enabled, or built-in defaults when global configuration is disabled.
4. Any update result and new-session requirement are clear.
