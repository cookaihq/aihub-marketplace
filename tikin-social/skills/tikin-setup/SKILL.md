---
name: tikin-setup
version: 1.0.0
description: v1.0.0｜Install, update, and configure tikin social-media skills or plugins. Use when the user first mentions tikin, needs to install or repair the tikin package, has a missing or invalid TIKIN_API_KEY, wants browser-assisted API-key creation, or wants to change per-platform auto/confirm routing settings.
---

# tikin Setup

Use this skill as the bootstrap entry point. Complete installation, authentication, and routing
configuration, then hand the user's task to the owning `tikin-*` skill.

## Local state

Resolve local state through `scripts/tikin-config`; do not parse or print secrets yourself.
Use `config-check` or `status` for a read-only diagnosis. Run `init` only when initializing
routing is authorized. If this task disables global configuration, skip `init`, `set-key`,
`set-routing` and any direct settings-file read; use built-in routing and pass
`--no-global-config` before each read-only helper subcommand.

```bash
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config init
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config status
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
- `~/.config/tikin-social/settings.json` stores non-secret routing preferences.

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

[Credential requirements](references/credentials.json) declare the real fields, defaults and
service/key relationship. Start with the actual loader’s local, secret-free inspection:

```bash
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config --skill tikin-setup config-check
```

It prints `secret-book.config-inspection/v1` with exact file/field sources and revision hashes;
exit 3 means missing/invalid configuration or an unreadable file. No API call is made. Offer
“edit local configuration / choose configuration through secret-book and save it”, respecting
an existing choice. For secret-book use its installed 2.3.0+ flow with the bundled declaration
and this inspection; do not duplicate its account, record-selection or confirmation protocol.
For manual entry, do not require secret-book and never ask for a key in chat.

Fix an existing problem in its actual source file; for environment values first locate their
injection source. New shared global configuration uses `~/.config/tikin-social/.env` after
explicit save authorization. A single Skill may use `.env.<skill-name>` in the Plugin root;
project saving uses the caller’s `.env.local`. Confirm that a Secret target inside Git is
untracked and ignored before writing. Do not add a lower-priority home value to mask a broken
higher-priority setting. After saving, report the exact target and effective field sources,
then distinguish local validation from online authentication. Configuration repair does not
authorize replaying a business request. `set-key` writes only the Plugin shared `.env`; use it
only when that is the confirmed target. It is not a generic source-file repair command.

Old `~/.config/tikin/.env`, `~/.config/tikin/settings.json` and custom XDG locations are not read.
Migration is optional and requires an explicit source, target and overwrite decision; preserve
unrelated fields and existing higher-priority settings. Ordinary `~/.config/<skill-name>/.env`
fallback needs no migration. Never expose credentials in chat, logs or commits.

Run API commands with the selected configuration in a child process:

```bash
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config \
  --skill tikin-setup run -- sh -c \
  'curl -s --max-time 30 "${TIKIN_BASE_URL}/api/usage/token/" -H "Authorization: Bearer ${TIKIN_API_KEY}"'
```

`run` requires a nonempty API key, reads configuration without writing files, and passes
only supported resolved values to the child environment. It never prints or shell-sources
the configuration. Keep shell programs quoted so variable expansion happens inside that child.

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
its available native tools and current UI. Native Windows execution is not supported by the
current POSIX bootstrap (`bin/python`) and shell examples; do not label a visible or installed
marketplace card as a working Windows runtime. macOS is the tested development environment;
Linux/WSL need their own runtime validation.

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

## Validate or create an API key

Run the helper instead of treating a non-empty value as valid:

```bash
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config validate
```

`validate` classifies its own failures the way `tikin-rest-api` describes under **Reliability**:
401/403 fails immediately as authentication/permission rejection; check the selected key and
service URL before attributing it to a bad key, while a transient failure (429, 5xx, timeout,
connection error) is retried up to 3 attempts total with a 1s then 2s backoff — honouring
`Retry-After` on a 429 — and logs each retry to stderr without the key. Each attempt uses a 30s
timeout, matching the `--max-time 30` that **Reliability** mandates for JSON calls against
`$BASE`; override it with `--timeout <seconds>` only when you have a reason to. Treat its exit
status as final; do not wrap it in a retry loop of your own.

If validation succeeds, continue. If configuration is missing or there is evidence of an invalid
key, first follow the local-configuration/secret-book choice above. For the browser-assisted
manual branch:

1. Look for a browser-control MCP, an in-app browser, Chrome control, or a browser-opening CLI.
2. Open `https://console.tikin.net` directly when one is available. Otherwise give the URL and
   wait while the user opens it.
3. Let the user complete sign-in, passwords, CAPTCHA, passkeys, and 2FA. Never enter, request, or
   inspect those credentials.
4. After the user is signed in, navigate through the visible UI to the API Keys page. Do not guess
   an undocumented URL path.
5. Explain that a new credential will be created and get confirmation once. Create the key with a
   descriptive label that the user approves.
6. Prefer the page's Copy action. Do not take a screenshot, DOM snapshot, or tool response that
   reveals the secret. Use automatic transfer only when the browser/CLI can copy the value without
   returning it to the model.
7. Pipe the clipboard into the helper without command-line interpolation, for example on macOS:

   ```bash
   pbpaste | uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config set-key
   ```

   Use the equivalent clipboard reader on other operating systems. If no secret-safe transfer is
   available, ask the user to copy the key and provide it to `set-key` through a local hidden or
   non-echoing stdin prompt. Do not ask the user to paste it into chat.
8. Run `validate` again. Report only whether validation passed, not the key or response body.

If an invalid key comes from the process environment or a project file, use `status` to identify
that source; do not silently write a home key that the higher-priority value will override.

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
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config set-routing --default auto --clear-platforms

# Every supported platform requires confirmation.
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config set-routing --default confirm --clear-platforms

# Only selected platforms are automatic; all others require confirmation.
uv run --project <this-skill-dir> <this-skill-dir>/scripts/tikin-config set-routing --default confirm --clear-platforms \
  --platform xiaohongshu=auto --platform douyin=auto
```

Supported policy slugs are `tiktok`, `douyin`, `instagram`, `youtube`, `twitter`, `threads`, and
`xiaohongshu`. A platform override wins over `routing.default`; an explicit instruction in the
current user request wins over both. In `confirm` mode, ask once per user task, group all affected
platforms/actions into that prompt, and do not ask again for pagination within the approved task.

## Route the task

| User outcome | Owning skill |
|---|---|
| Install, authentication, updates, routing settings | `tikin-setup` |
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
2. The key validates, or the task is stopped with a clear authentication next step.
3. The task’s effective routing policy has been applied: saved settings when enabled, or built-in defaults when global configuration is disabled.
4. Any update result and new-session requirement are clear.
