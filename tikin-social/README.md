# tikin Social

tikin Social targets Claude Code, Codex and WorkBuddy to retrieve social-media
posts, profiles, comments, search results and trends, download media, and analyze accounts across
TikTok, Douyin, Instagram, YouTube, Twitter/X, Threads, Xiaohongshu and more through
[tikin](https://tikin.net). The `tikin-social` Plugin includes 17 `tikin-*` Skills.

Current version: **1.3.0**. All 17 Skills now share native JSON requests and automatic local error reports. Credential handoff uses the
`setup-api-key` Skill in Setup AIHub 2.0.0. The following results apply to **1.2.0**:
native Windows Plugin installation and Skill discovery are verified
in Claude Code, Codex and WorkBuddy. Credential configuration passed in Codex's default sandbox
and WorkBuddy; Claude Code natural invocation passed, while its configuration loop was not tested.
Real social-data workflows require separate validation.

For 1.3.0, synthetic request/report/recovery tests pass on native Windows. WorkBuddy host
acceptance is still incomplete; Claude Code and Codex received structure/document checks only
for this version. These results do not validate real social-data calls or media downloads.
The full native Windows test suite retains four pre-existing failures in configuration tests
that assert POSIX file-mode bits; the same failures reproduce on the 1.2.1 baseline.

## Default Skills and reminders

On the first use of any tikin-social Skill in a session, the Agent checks its active global and project instructions for an equivalent default-Skill preference. Existing equivalent rules need no prompt. Otherwise it offers **Set as default / Skip this time / Do not remind again**, at most once per Plugin per session, while continuing your original task.

“Set as default” shows the exact task-to-Skill mapping, complete proposed text and actual global rule file before asking for your confirmation. It prioritizes the applicable tikin-social Skills only when you have not chosen another tool. Shared rule files and conflicts are explained before any edit. Saving a rule and verifying that a new host session loads it are reported separately.

“Do not remind again” only saves the reminder choice; it does not install or remove default rules. You can ask:

> Stop reminding me to make tikin-social the default in this Agent.

> Enable tikin-social default-Skill reminders again in this Agent.

The choice is automatically read from `~/.config/tikin-social/settings.json`, separately for each Agent type and actual configuration directory. All 17 Skills and future versions share that Plugin preference; aihub-studio is independent. Existing routing and other settings are preserved. This preference does not come from environment variables or `.env` files. Missing preferences mean reminders are enabled; read-only checks create no files. Only an explicit disable/enable request saves a choice. Running without global configuration also skips this check and refuses preference writes.

The check needs no API key or network. Codex, Claude Code and WorkBuddy have rule-entry guidance; unknown hosts or failed checks are reported without blocking the task. The configuration helper now selects Windows `Scripts/python.exe` or POSIX `bin/python`. Linux/WSL use their own runtime user directory and do not read Windows preferences. Real host-session loading and non-credential workflows require separate validation.

## Install through your agent

Paste this into your agent:

> Install the complete tikin-social Plugin from the aihub-marketplace repository,
> https://cnb.cool/zhidateam/tannt/aihub-marketplace.git, in its tikin-social/ directory.
> Prefer CNB; if it fails because of a network problem, try
> https://github.com/cookaihq/aihub-marketplace.git with the same Plugin and version.
> Preserve my existing settings, then verify that this agent can discover and invoke its Skills.

Claude Code and Codex have native Plugin installations. WorkBuddy uses the **套件** market:
**专家·技能·连接器 → 技能 → 套件 → circular ＋ beside the marketplace names**. This opens the
**添加市场** dialog. After adding the repository, click the ＋ on the **tikin-social** card to
install it. Adding the market and installing its Plugin are separate steps.

Agent Skills clients can also install the Skills from this repository’s `tikin-social/` directory.
Include `tikin-setup` with the operational Skills; its helper loads their API configuration.
Start a new session after installation so the agent can discover the newly installed Skills.
The agent should report installation, Skill invocation and a real API request as separate checks.

API requests and endpoint search use `uv` 0.8 or newer and the bundled pinned Python environments.
The Agent invokes both helpers with explicit project and interpreter paths on native Windows,
macOS or Linux; API requests no longer require a POSIX shell or curl. The initial runtime setup
needs network access; endpoint search then works offline. Skills-only installations must include
`tikin-setup`, which supplies the shared bootstrap and request helper.

Final media downloads still need an available download tool (`curl.exe` on native Windows).
Saving private reports on Windows requires the built-in Windows PowerShell 5.1 and a filesystem
supporting Windows access controls. Files are restricted before private contents are written;
a report save failure does not cause another API request. A WorkBuddy card does not prove runtime
compatibility. This version's local synthetic tests and host acceptance are recorded separately;
real social-data business, Linux and WSL flows remain unverified. Do not switch Windows tasks to WSL
automatically.

## Configure API access

可对当前 Agent 说“用 setup-api-key 帮我检查或更换刚才的 tikin 密钥”。Setup 统一入口不可用时，
沿用下面的最小手填／Secret Book 流程；正确配置的业务不依赖它。完整安装请求见同包的
[凭证衔接说明](skills/tikin-setup/references/credential-setup.md)。本版新增配置契约，配合 Setup 1.0.0 或更新的兼容版本使用。

Secret Book 使用本人身份连接已有表，远端只读；缺列、缺 ID 或无权限不自动修复远端。
未安装时可选安装并继续、手填或暂缓。有实际业务 Skill 的本机接入基线为 2.5.0，已通过
Windows 合成数据测试；共享空 caller 需要 2.5.1 或更新版本。2.5.2 的 Windows 真实表配置、
恢复及清理已通过；Codex 默认沙箱和 WorkBuddy 本机配置闭环通过，Claude Code 安装、发现
及自然触发通过，配置闭环未实测。
配置检查不会初始化路由、创建远端 Key 或发送业务请求。

Get your own API key from <https://console.tikin.net>. Never paste a complete key into chat.
`tikin-setup` can help with browser-based setup while you control login and authentication, or
help you enter the key locally without displaying it.

> Help me configure tikin-social. Keep any configuration method I already chose, or let me
> choose secret-book or a local .env file. Save new shared configuration in my personal
> ~/.config/tikin-social/.env; repair existing errors in their actual source file. Tell me the
> written file and effective sources without showing secret values.

| Field | What to provide |
| --- | --- |
| `TIKIN_API_KEY` | Required for API requests; the key from your tikin account. Offline endpoint search needs no key. |
| `TIKIN_BASE_URL` | Optional API service root, default `https://console.tikin.net`; it must belong to the same service as your key. |

The confirmed default for new shared credentials is the Plugin’s personal `.env` file. Existing
project or Skill-specific choices remain valid. Each field independently uses the first nonempty
value below. For example, when `tikin-douyin` makes a request:

1. The process environment.
2. `.env.tikin-douyin` in the command’s working folder.
3. `.env.local` in that folder.
4. `.env` in that folder.
5. `~/.config/tikin-social/tikin-douyin/.env.local`.
6. `~/.config/tikin-social/tikin-douyin/.env`.
7. `~/.config/tikin-social/.env.tikin-douyin`.
8. `~/.config/tikin-social/.env.local`.
9. `~/.config/tikin-social/.env`.
10. `~/.config/tikin-douyin/.env`.

Other Skills replace `tikin-douyin` with their own exact `tikin-*` name. The working folder is
where the agent executes the command, not the installation directory; parent folders and other
Skills’ files are not searched. Empty fields or empty Plugin directories continue to lower
sources. Existing unreadable files report an error instead of silently selecting another account.
Files contain literal values; they are never executed as shell programs.

The six global sources are read automatically. Ask “Run this task without global configuration”
to disable both Plugin and ordinary Skill global files for that invocation; the helper’s
`--no-global-config` option also uses default routing without reading saved settings. A helper
call explicitly made without a caller Skill uses only project shared and Plugin shared files.
The default save location remains the Plugin shared `.env`; do not create 17 separate directories
unless some Skills actually need different settings. The ordinary Skill `.env` fallback can be
shared by the same Skill installed through another distribution, with Plugin configuration taking
priority. Reading a configuration never creates or migrates it.

The user folder is the home directory resolved by the helper’s Python runtime:

| Runtime | Plugin shared file and limits |
| --- | --- |
| macOS / Linux | The runtime user’s `~/.config/tikin-social/.env`; macOS has local test coverage, Linux is not yet verified. |
| Native Windows | `%USERPROFILE%\.config\tikin-social\.env`, for example `C:\Users\your-name\.config\tikin-social\.env`. Python resolves the runtime user's home. Local synthetic configuration tests cover this path; complete business/host workflows remain unverified. |
| WSL | A Linux process uses its own Linux user folder’s `.config/tikin-social/.env`; it does not automatically read the Windows user folder. WSL remains unverified. |

Skill overrides and fallback files use that same runtime user folder. `XDG_CONFIG_HOME` and
old `tikin` / `tikin-plugin` directories are not configuration sources for the new Plugin.

To diagnose an unexpected account or missing key, ask:

> Check tikin-social’s configuration for tikin-douyin. Report the working folder, which file or
> environment variable supplies each field, whether fields are missing, and any read errors.
> Do not print values or call a business API.

The agent uses the actual loader’s local source report. After saving or repairing settings it
checks those sources again. Local configuration checks do not prove API authentication;
network failures, quota errors and permission errors do not automatically mean a bad key.
Configuration repair does not automatically resend your previous business request.

For removal, ask the Agent to preview the effective sources after deleting only your selected
fields. Preview uses the same loader without touching the files; another source or the default
service may become effective. Confirm the key/service relationship before using the result.
`set-key` initializes routing and writes only the shared location; it is not used for general
source-file repair by Setup.

## Migrate an existing installation

This release replaces `tikin-plugin` with `tikin-social` in **aihub-marketplace**. The 17 Skill
names and API field names stay unchanged. Install `tikin-social` and prepare its configuration,
then disable the old `tikin-plugin@plugin-marketplace` or `tikin-plugin@tikin-plugins` instance.
Open a new session and verify that the Plugin identity and actual `tikin-*` Skill sources belong
to `tikin-social`. After validation succeeds, uninstall the old instance. The Skills retain the
same names, so do not test with both Plugin copies active in the same agent.

Old `~/.config/tikin/.env`, `~/.config/tikin/settings.json`, or files under a custom
`XDG_CONFIG_HOME/tikin/` are not read or moved automatically. You can ask:

> Show me the source and target paths for migrating my old tikin configuration to
> ~/.config/tikin-social/.env and ~/.config/tikin-social/settings.json. Preserve existing
> settings, report conflicts without showing secrets, and get my confirmation before writing.

The existing ordinary `~/.config/<skill-name>/.env` fallback needs no migration. Do not combine
several accounts into one shared file without choosing which account each Skill should use.

## First use

Start with this offline check in a new session:

> Find the tikin endpoint for retrieving one TikTok video. Search the bundled index without
> calling the API.

`tikin-endpoint-discovery` should return `GET /api/v1/tiktok/app/v3/fetch_one_video` and its
required parameters. This proves local endpoint search, not access to your account.

After API configuration, requests to tikin send the URL, account identifier or query needed for
your task and can consume prepaid API balance. For a first real request, provide your own post:

> Retrieve the details of this TikTok video: <my video URL>. Make only the request needed for
> this post and tell me whether the API returned data.

## Routing and common tasks

Routing preferences live separately at `~/.config/tikin-social/settings.json`. The default is
`auto`, which uses tikin for supported social URLs. `confirm` asks once for the user task; a
platform-specific setting overrides the default and an explicit instruction in your request
overrides both. Ask `tikin-setup` to change the policy, for example “Ask before Xiaohongshu
requests; use tikin automatically for the other supported platforms.”

| Request | Result |
| --- | --- |
| “Download the media from this post: <URL>” | Media files, with their saved paths and any unavailable items. |
| “Analyze this creator’s recent posts: <profile URL>” | Profile details, recent performance and top content. |
| “Summarize the comments on this post: <URL>” | Recurring themes, questions and sentiment from retrieved comments. |
| “Compare these two creators: <profile URLs>” | A comparison based on the returned profile and post data. |

Supported source-platform pages are accessed through tikin. The agent can download final media
URLs returned by tikin; it should not silently fetch a source social page through a generic
HTTP tool when you decline tikin. Large pulls use explicit pagination and request budgets and
may return a partial result with a resume cursor.

## Local error reports

The first API, protocol or remote-task failure automatically saves one readable `error-report.md`
for the user task. It includes original requirements, submitted parameters, necessary source
information, sanitized request/response JSON, timing, retries and observed error fields.
Follow-up requests and pagination reuse that task's record. Repeated observations of the same
failed task do not inflate the error count; recovery updates the same report.

Every failure, repeat, recovery and final reply includes clickable links labelled with the complete
absolute paths to the report, `diagnostic.json`, `issue-draft.md` and `run.json`. You can ask:

> Open this task's local error report, explain the observed failure and unknown fields, and
> continue from its existing record without repeating an uncertain submission.

Reports stay on this computer and can contain private queries and media identifiers. API keys,
Authorization, cookies and signed URL query values are redacted; binary and oversized content
have explicit omission markers. Public Issue drafts exclude private requests, links and raw IDs.
Nothing is sent to an administrator or issue tracker automatically.

Client HTTP status, asynchronous task status and API-exposed provider evidence are separate.
Missing upstream status, provider, routing or internal retries remain unknown; `service_unavailable`
does not prove an upstream outage. An administrator can locate backend logs using the local IDs.
Report saving never changes retry decisions; a save warning preserves the original request outcome.
The shared [request reference](skills/tikin-setup/references/requests.md) describes recovery and
how the Agent supplies these links.

## Skills

### Foundation
| Skill | What it does |
|-------|--------------|
| `tikin-setup` | Install or repair tikin, configure a key and routing, and check for updates |
| `tikin-rest-api` | REST best practices: auth, paths, pagination, rate limits, cost |
| `tikin-endpoint-discovery` | Search 1,000+ endpoints with `tikin-find-endpoint` |

### Platforms
| Skill | Coverage |
|-------|----------|
| `tikin-tiktok` | Videos, users, search, ads/trends, creator analytics, shop |
| `tikin-douyin` | Videos, users, search series, comments |
| `tikin-instagram` | Users, posts, search, comments, hashtags (V2) |
| `tikin-youtube` | Video info, streams, captions, comments, search (Web-V2) |
| `tikin-twitter-threads` | Tweets/posts, profiles, timelines, search, trends |
| `tikin-xiaohongshu` | Note details, users, search, comments (App-V2) |

### Tasks
| Skill | Outcome |
|-------|---------|
| `tikin-social-media-downloader` | Download video/audio/images (no-watermark) from any URL |
| `tikin-creator-analytics` | Profile + engagement + cadence + top content for an account |
| `tikin-trend-research` | Trending content, rising hashtags, hot sounds, ranking boards |
| `tikin-social-listening` | Mentions → sentiment → themes → cited digest |
| `tikin-competitor-analysis` | Benchmark multiple accounts side by side |
| `tikin-hashtag-research` | Hashtag volume, top content, related tags |
| `tikin-comments-analysis` | Comment sentiment, themes, top comments for a post |
| `tikin-bulk-data-export` | Paginate large lists → dedup → CSV/JSON, with cost estimate |

## Troubleshooting and updates

If the market shows `tikin-social` but no Skills are available, ask the agent to verify that the
Plugin itself was installed and then start a new session. On Windows, check which runtime actually
executes the tools; marketplace visibility alone cannot validate the configuration or business runtime.

For API errors, ask the agent to inspect local sources and distinguish authentication, permission,
quota and network failures. For an update, say “Update only my tikin-social installation, keep
my configuration, and tell me which version will load in the next session.” Plugins use the
owning host’s update channel; Agent Skills installations use their source-aware updater. The
first tikin use in a session performs the existing best-effort check through that channel;
network or update failures do not block the current task. Credentials and routing preferences
are kept outside the installation directory.

- [Changelog](CHANGELOG.md)
- [tikin website](https://tikin.net) · [Console](https://console.tikin.net)
- [CNB mirror](https://cnb.cool/zhidateam/tannt/aihub-marketplace)
  · [GitHub source](https://github.com/cookaihq/aihub-marketplace/tree/main/tikin-social)

MIT — see [LICENSE](LICENSE).
