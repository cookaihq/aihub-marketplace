# tikin Social

tikin Social helps Claude Code, Codex and compatible Agent Skills clients retrieve social-media
posts, profiles, comments, search results and trends, download media, and analyze accounts across
TikTok, Douyin, Instagram, YouTube, Twitter/X, Threads, Xiaohongshu and more through
[tikin](https://tikin.net). The `tikin-social` Plugin includes 17 `tikin-*` Skills.

## Default Skills and reminders

On the first use of any tikin-social Skill in a session, the Agent checks its active global and project instructions for an equivalent default-Skill preference. Existing equivalent rules need no prompt. Otherwise it offers **Set as default / Skip this time / Do not remind again**, at most once per Plugin per session, while continuing your original task.

“Set as default” shows the exact task-to-Skill mapping, complete proposed text and actual global rule file before asking for your confirmation. It prioritizes the applicable tikin-social Skills only when you have not chosen another tool. Shared rule files and conflicts are explained before any edit. Saving a rule and verifying that a new host session loads it are reported separately.

“Do not remind again” only saves the reminder choice; it does not install or remove default rules. You can ask:

> Stop reminding me to make tikin-social the default in this Agent.

> Enable tikin-social default-Skill reminders again in this Agent.

The choice is automatically read from `~/.config/tikin-social/settings.json`, separately for each Agent type and actual configuration directory. All 17 Skills and future versions share that Plugin preference; aihub-studio is independent. Existing routing and other settings are preserved. This preference does not come from environment variables or `.env` files. Missing preferences mean reminders are enabled; read-only checks create no files. Only an explicit disable/enable request saves a choice. Running without global configuration also skips this check and refuses preference writes.

The check needs no API key or network. Codex, Claude Code and WorkBuddy have rule-entry guidance; unknown hosts or failed checks are reported without blocking the task. Existing runtime limits still apply: native Windows remains unsupported by the tikin bootstrap; Linux/WSL use their own runtime user directory and do not read Windows preferences. Real host-session loading is a separate validation step.

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

Agent Skills clients can also install the Skills from this repository’s `tikin-social/` directory.
Include `tikin-setup` with the operational Skills; its helper loads their API configuration.
Start a new session after installation so the agent can discover the newly installed Skills.
The agent should report installation, Skill invocation and a real API request as separate checks.

API workflows require `curl`, a POSIX shell and `uv` 0.8 or newer. The two bundled Python helpers
need an initial runtime setup with network access; endpoint search then works offline. Your
agent can check these tools. The helpers currently use a POSIX `bin/python` runtime path:
**native Windows execution is not supported yet**. A WorkBuddy marketplace card does not prove
Windows runtime compatibility. Development verification runs on macOS; Linux and WSL still need
runtime validation, and a Windows host cannot be assumed to execute its tools inside WSL.

## Configure API access

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
| Native Windows | The present POSIX helper does not support this runtime; no working native Windows configuration path is claimed. |
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
executes the tools; marketplace visibility alone cannot validate the current POSIX helpers.

For API errors, ask the agent to inspect local sources and distinguish authentication, permission,
quota and network failures. For an update, say “Update only my tikin-social installation, keep
my configuration, and tell me which version will load in the next session.” Plugins use the
owning host’s update channel; Agent Skills installations use their source-aware updater. The
first tikin use in a session performs the existing best-effort check through that channel;
network or update failures do not block the current task. Credentials and routing preferences
are kept outside the installation directory.

- [Changelog](CHANGELOG.md)
- [tikin website](https://tikin.net) · [Console](https://console.tikin.net)
- [GitHub source](https://github.com/cookaihq/aihub-marketplace/tree/main/tikin-social)
  · [CNB mirror](https://cnb.cool/zhidateam/tannt/aihub-marketplace)

MIT — see [LICENSE](LICENSE).
