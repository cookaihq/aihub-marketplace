# tikin Social

tikin Social targets Claude Code, Codex and WorkBuddy to retrieve social-media
posts, profiles, comments, search results and trends, download media, and analyze accounts across
TikTok, Douyin, Instagram, YouTube, Twitter/X, Threads, Xiaohongshu and more through
[tikin](https://tikin.net). The `tikin-social` Plugin includes 17 `tikin-*` Skills.

Plugin version: **2.0.0**. The 16 Skills using the shared business request
entry are **2.0.0**; offline `tikin-endpoint-discovery` remains **1.6.0**. New API runs
require the Agent to supply a concise task name; existing records resume by their saved paths.
This release includes the previously unpublished 1.5.0/1.6.0 changes and the
second-batch catalog of 1029 operations; the retained first-batch catalog contains
919. Neither catalog is evidence of live availability. Native host acceptance remains partial.

For the task-directory update on macOS, 119 automated behavior tests, 68 structural checks
and all 17 official Skill schemas pass. Codex 0.166.0 loads the native test Plugin and
creates/resumes the named local record; its default sandbox blocks loopback HTTP. Claude
Code 2.1.318 selects the existing Opus 5.5 default but quota 403 prevents invocation.
WorkBuddy 5.9.3 retains another task's unsent draft; no independent test window was available.
These are partial host results; successful host HTTP calls and native Windows remain unverified.

Includes the credential flow introduced in published **1.4.0**: missing API Keys
open the local configuration page in Setup AIHub 2.3.0. The page supports direct
entry or Secret Book, confirms the Key’s service address, saves to the selected
source, and rechecks through the business loader before resuming the original task.

For published 1.4.0 on macOS, all 50 regression tests and synthetic browser configuration pass. Codex 0.166.0 passes native test Plugin installation, tikin-douyin missing-Key invocation, browser save and cross-turn recovery, preserving its default sandbox with per-command approval for the local server. Claude Code 2.1.317 loads the complete Plugins, but account quota (403) blocks invocation. WorkBuddy's native window is blocked by macOS accessibility permissions. These limitations do not constitute host acceptance; native Windows, real Feishu authorization and online business calls remain unverified for this release.

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
> https://github.com/cookaihq/aihub-marketplace.git, in its tikin-social/ directory.
> Prefer GitHub; if it fails because of a network problem, try
> https://cnb.cool/zhidateam/tannt/aihub-marketplace.git with the same Plugin and version.
> Preserve my existing settings, then verify that this agent can discover and invoke its Skills.

Claude Code and Codex have native Plugin installations. WorkBuddy uses the **套件** market:
**专家·技能·连接器 → 技能 → 套件 → circular ＋ beside the marketplace names**. This opens the
**添加市场** dialog. After adding the repository, click the ＋ on the **tikin-social** card to
install it. Adding the market and installing its Plugin are separate steps.

Other Agent Skills clients can install the **complete 17-Skill suite** from this same
repository's `tikin-social/` directory and one fixed Plugin release. Setup, discovery,
shared helpers and the index travel together; individual Skill updates are not supported.
Ask your Agent to preserve local edits and verify the complete suite's content identity.
Start a new session after installation so the agent can discover the newly installed Skills.
The agent should report installation, Skill invocation and a real API request as separate checks.

API requests and endpoint search use `uv` 0.8 or newer and the bundled pinned Python environments.
The Agent invokes both helpers with explicit project and interpreter paths on native Windows,
macOS or Linux; API requests no longer require a POSIX shell or curl. The initial runtime setup
needs network access; endpoint search then works offline. Skills-only installations must include
`tikin-setup`, which supplies the shared bootstrap and request helper.

YouTube V3 same-proxy downloads use the same pinned Python runtime. Other final media
downloads need an available download tool (`curl.exe` on native Windows).
Saving private reports on Windows requires the built-in Windows PowerShell 5.1 and a filesystem
supporting Windows access controls. Files are restricted before private contents are written;
a report save failure does not cause another API request. A WorkBuddy card does not prove runtime
compatibility. This version's local synthetic tests and host acceptance are recorded separately;
real social-data business, Linux and WSL flows remain unverified. Do not switch Windows tasks to WSL
automatically.

## Configure API access

可对当前 Agent 说“用 setup-api-key 帮我检查或更换 tikin 密钥”。本版 1.4.0 在业务发现缺 Key 时实际打开同一个本机配置网页，使用完整 Setup Plugin 2.3.0 或更新版本；已能读取配置时直接继续业务。

> 请用 tikin 查抖音数据。若缺少 API Key，请打开本机配置页；保留原需求，我填写保存后再检查并继续，不要让我把 Key 发到聊天。

页面可手动填写 `TIKIN_API_KEY`，也可从 Secret Book 选择本人可见记录。默认服务地址为 `https://console.tikin.net`，可同时填写与 Key 对应的其他 HTTPS 地址。首次共享保存到 `~/.config/tikin-social/.env`；选择当前项目或修复已有来源时，预览会列出实际文件和替换项。

Secret Book 只读能力随 Setup 分发，不需额外安装独立 Skill。本人核对身份、已有表、记录与字段后确认保存；缺列、缺 ID 或权限不足由维护者处理。配置检查不初始化路由、不创建远端 Key、不发业务请求。

Setup 缺失或本会话未加载时先核对并协助安装/加载兼容完整 Plugin，见[凭证衔接说明](skills/tikin-setup/references/credential-setup.md)。明确选择文件编辑或没有本机浏览器时保留文件填写方式。保存后用真实加载器复查并完成默认设置检查；原请求未提交且授权有效才继续，已提交或状态未知先查询原结果，不重发。

### Configuration sources and repair

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

Older releases replaced `tikin-plugin` with `tikin-social` in **aihub-marketplace**. The 17 Skill
names and API field names stay unchanged. Install `tikin-social` and prepare its configuration,
then disable the old `tikin-plugin@plugin-marketplace` or `tikin-plugin@tikin-plugins` instance.
Open a new session and verify that the Plugin identity and actual `tikin-*` Skill sources belong
to `tikin-social`. After validation succeeds, uninstall the old instance. The Skills retain the
same names, so do not test with both Plugin copies active in the same agent.

Standalone `tikin-*` copies can also duplicate the Plugin. Ask:

> Migrate this Agent to the native tikin-social Plugin from aihub-marketplace. First
> list its actual sources and any shared copies or local edits. Preserve my current
> account configuration, stage a fixed complete version, and verify its actual loaded
> source, offline endpoint search and configuration in a new session before retiring
> this Agent's duplicate. Keep every copy still needed by another Agent.

The Agent follows the bundled [installation and migration procedure](skills/tikin-setup/references/installation.md).
The status check reports the loaded helper's resolved path, complete Plugin version,
individual Skill versions and index hash. Content verification alone does not prove
that a new host session has loaded that source or that a real API call succeeded.

Old `~/.config/tikin/.env`, `~/.config/tikin/settings.json`, or files under a custom
`XDG_CONFIG_HOME/tikin/` are not read or moved automatically. You can ask:

> Show me the source and target paths for migrating my old tikin configuration to
> ~/.config/tikin-social/.env and ~/.config/tikin-social/settings.json. Preserve existing
> settings, report conflicts without showing secrets, and get my confirmation before writing.

The existing ordinary `~/.config/<skill-name>/.env` fallback needs no migration. Do not combine
several accounts into one shared file without choosing which account each Skill should use.

## Candidate catalog and request behavior

The development candidate carries the frozen second-batch catalog and full
offline request contracts. Read the [second-batch workflow guide](skills/tikin-endpoint-discovery/references/second-batch.md)
for platform prerequisites, limits, asynchronous tasks and candidate scope. Read the [migration guide](skills/tikin-endpoint-discovery/references/first-batch.md)
for method/parameter changes and retired routes. Its `catalog-identity.json` reports
the actual operation count and hashes. Service-dependent changes are not yet published
or proven live; native host migration and Windows acceptance remain incomplete.

For YouTube V3, follow the [same-proxy download guide](skills/tikin-setup/references/downloads.md).
Provide an existing authorized proxy and an explicit JSON exit-check URL; the helper
retains the successful metadata request, verifies every selected stream and preserves
partial files. It does not purchase a proxy, refresh metadata or merge audio and video.

> Download this YouTube video using my existing proxy and exit-check URL. Keep the
> proxy credentials local, preserve the metadata result, and tell me separately which
> streams finished, which remain partial, and whether audio/video still need merging.

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

## Local task records and error reports

API calls save a task record even when they succeed. By default it is under the command's
working folder at `data/tikin-social/`, in a directory such as
`20261103143025-抖音评论分析-run-a1b2c3d4/`. The name combines the computer's local date/time,
a short Chinese or English task summary chosen by the Agent, and eight random characters.
You can ask the Agent to use another output location. New tasks get separate directories;
pagination, queries and recovery for the same task keep its existing directory.

`run.json` retains observed requests, sanitized responses, timing, retries and task state;
`run.json.lock` coordinates access to that record. There is no automatic expiry cleanup.
The record is not a full data backup or a transcript of the Agent's analysis. A process
interrupted before saving a response can leave its outcome unknown. You can ask:

> Read this task's run.json and explain which interfaces were actually called, what they
> returned, what was retried, and which results still cannot be determined. Do not send
> another API request just to reconstruct the history.

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
| `tikin-endpoint-discovery` | Search the bundled supported endpoints with `tikin-find-endpoint` |

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
owning host’s update channel; Skills-only installations replace the complete suite from
one fixed Plugin tag and commit. Updates require your request or confirmation, preserve
local changes, and are checked in a new session before the previous source is retired.
The first tikin use in a session performs a best-effort check through its owning channel;
network or update failures do not block the current task. Credentials and routing preferences
are kept outside the installation directory.

- [Changelog](CHANGELOG.md)
- [tikin website](https://tikin.net) · [Console](https://console.tikin.net)
- [CNB mirror](https://cnb.cool/zhidateam/tannt/aihub-marketplace)
  · [GitHub source](https://github.com/cookaihq/aihub-marketplace/tree/main/tikin-social)

MIT — see [LICENSE](LICENSE).
