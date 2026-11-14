# tikin Social

4.0.2 的凭证配置直接使用本套件自带配置中心，移除已退役 Setup 的转交和续接入口；`tikin-setup` 为 4.0.2。既有业务配置与用户任务数据保留。

以下为历史 4.0.1 的功能与验收记录。

4.0.1 修复首次保存被 Git 忽略检查拦住的问题：点击保存后自动准备所需保护，填写后即可保存，无需手动添加规则。配置项标题下新增实际字段名，便于对照文件；密钥值仍脱敏显示。

本版通过 Windows 回归、Codex 0.166.0 默认沙箱的正式配置入口保存与回读，以及两套浏览器页面和 390×844 布局检查。本次 WorkBuddy 按用户要求免验；macOS 待验，未重新安装或调用线上业务。

以下为历史 4.0.0 的功能与验收记录。

4.0.0 新增项目 `.env.local.tikin-social`、`.env.tikin-social`，17 个 Skill 共用；依次优先于普通 `.env.local`、`.env`。

本版停止读取两种旧 Skill 后缀路径，保留 Skill 子目录及普通 Skill 全局回退。仅在退出位置保存过 Key 时，请按下方配置说明选择受支持位置；程序不会自动迁移。通过 Setup 委托配置时须使用 Setup AIHub 4.2.0 或更新版本，也可直接打开本 Plugin 自带配置页。

本批 Windows Codex 开发源显式加载、真实配置入口和页面 HTTP 闭环已通过，桌面与 390×844 浏览器检查通过；按用户对本批次的明确决定，WorkBuddy 免验；macOS 待验。本版未重新安装或验证原生发现、隐式触发及线上业务。

以下为历史 3.2.0 的功能与验收记录。

3.2.0 接入新版分层配置中心：查看当前生效值及逐项来源，辨认项目覆盖与全局继承，选择具体文件编辑，并在保存或移除覆盖前预览真实结果。一次只保存选中的文件，其他草稿继续保留。

本版已在 Windows 原生通过 Codex CLI 0.166.0 的开发源显式调用、两套随包服务启动、HTTP 配置预览/保存、原加载器回读和停止检查；独立浏览器完成桌面与 390×844 窄屏验证。71 项定向回归通过。按本次用户决定，WorkBuddy 不作为验收要求；macOS 待验。未替换现用 Plugin 安装，未验证原生重新安装、隐式触发、线上鉴权或付费业务。

以下为历史 3.1.1 的功能与验收记录。

3.1.1 修复 Markdown 产物的图片与富文本预览；共享入口缺少解析依赖时，会按锁文件恢复运行环境。

本版在 Windows 通过 Codex 0.166.0 的开发源显式调用、两套服务的启动/资源/下载检查，以及独立浏览器的图片显示与手机视口检查。原业务文档 29 张图片全部显示，真实文件保持不变。按本次用户决定，WorkBuddy 不要求实测；macOS 待验。未复测原生安装发现、隐式触发或线上业务；Codex 子会话自身的浏览器控制受限，独立浏览器结果另行记录。

以下为历史 3.1.0 的功能与验收记录。

3.1.0 新增 Hermes 原生入口，完整注册 17 个 Skill，共用请求、配置与离线索引；默认规则和提醒识别当前 Hermes Profile。

本版已通过 Windows 原生 Codex、WorkBuddy、Hermes 的入口加载与本机合成配置流程；Hermes 另验证 Profile 隔离及任务身份。未调用付费业务，未验证真实线上鉴权；macOS 本轮待验，Claude Code 保持兼容但未实测。历史结果仅覆盖所列版本。

以下为历史 3.0.0 的功能与验收记录。

3.0.0 自带配置中心、`task-info.json` 和按任务、会话、文件查看的产物页。任务卡采用不同格式的横排预览，图片/视频显示封面；页面显示当前 Git 分支。具名任务继续保存在 `data/tikin-social/`，历史任务不索引或迁移。

3.0.0 Windows 原生已完成本地合成回归、正式页面桌面与手机视口检查，以及 Codex 0.166.0 / WorkBuddy 5.9.3 的原生安装、Skill 发现和代表性运行验收。macOS、真实鉴权与线上业务待验；Claude Code 兼容入口保留，本轮未实测。

历史版本 **2.0.2**：默认设置采用“设为默认 (推荐)”，选择一次后直接设置并展示实际内容。Windows 默认规则、分发与版本定向回归 13 项通过；Codex 已在隔离测试文件中完成菜单、写入、恢复及完整内容展示。Claude Code 因额度 403 受阻，WorkBuddy 的输入与发送未能完成；本版原生安装及真实全局加载、macOS 仍待验，本次按用户明确指令发布，以上待验项继续保留。以下历史验收记录仅覆盖各自所列版本。

2.0.2 的 Windows 完整行为套件未通过并在 300 秒上限停止：代理测试依赖和轮询断言问题已在基线复现；仅在测试进程补充已有 OpenSSL 路径后，代理双流代表用例通过。其余执行安全用例失败仍待定位，定向回归结果不代表全量通过。

tikin Social targets Claude Code, Codex, WorkBuddy and Hermes to retrieve social-media
posts, profiles, comments, search results and trends, download media, and analyze accounts across
TikTok, Douyin, Instagram, YouTube, Twitter/X, Threads, Xiaohongshu and more through
[tikin](https://tikin.net). The `tikin-social` Plugin includes 17 `tikin-*` Skills.

Plugin version: **4.0.2**. `tikin-setup` is **4.0.2**; the other 15 Skills using the shared business request
entry remain **4.0.1**; offline `tikin-endpoint-discovery` remains **3.0.0**. New API runs
require the Agent to supply a concise task name; existing records resume by their saved paths.
This release includes the previously unpublished 1.5.0/1.6.0 changes and the
second-batch catalog of 1029 operations; the retained first-batch catalog contains
919. Neither catalog is evidence of live availability. The previous 3.0.0 release has native Windows Codex/WorkBuddy acceptance; current host checks are recorded separately. macOS and live requests remain pending.

For the 2.0.0 task-directory update on macOS, 119 automated behavior tests, 68 structural checks
and all 17 official Skill schemas pass. Codex 0.166.0 loads the native test Plugin and
creates/resumes the named local record; its default sandbox blocks loopback HTTP. Claude
Code 2.1.318 selects the existing Opus 5.5 default but quota 403 prevents invocation.
WorkBuddy 5.9.3 retains another task's unsent draft; no independent test window was available.
These are partial host results; successful host HTTP calls and native Windows remain unverified.

Missing API Keys now open this Plugin’s own configuration center. Existing Setup tasks can continue through Setup AIHub 4.0.0 or newer; the business Plugin remains the configuration loader and writer.

For 2.0.1, all 119 automated tests pass on macOS. Codex 0.166.0 passes the native
Setup 3.0.0 missing-Key, browser-save, loader-recheck and conversation-resume flow.
WorkBuddy 5.9.3 installs and loads both Plugins and opens the page, but its safe-delete
guard blocks the save preview. Claude Code 2.1.318 remains blocked by quota 403.
This release retains those two pending host checks; it does not claim complete
acceptance across all three hosts. Native Windows and live service calls remain unverified.

For published 1.4.0 on macOS, all 50 regression tests and synthetic browser configuration pass. Codex 0.166.0 passes native test Plugin installation, tikin-douyin missing-Key invocation, browser save and cross-turn recovery, preserving its default sandbox with per-command approval for the local server. Claude Code 2.1.317 loads the complete Plugins, but account quota (403) blocks invocation. WorkBuddy's native window is blocked by macOS accessibility permissions. These limitations do not constitute host acceptance; native Windows, real Feishu authorization and online business calls remain unverified for this release.

For 1.3.0, synthetic request/report/recovery tests pass on native Windows. WorkBuddy host
acceptance is still incomplete; Claude Code and Codex received structure/document checks only
for this version. These results do not validate real social-data calls or media downloads.
The full native Windows test suite retains four pre-existing failures in configuration tests
that assert POSIX file-mode bits; the same failures reproduce on the 1.2.1 baseline.

## Default Skills and reminders

On the first use of any tikin-social Skill in a session, the Agent checks its active global and project instructions for an equivalent default-Skill preference. Existing equivalent rules need no prompt. Otherwise it offers **Set as default (Recommended) / Skip this time / Do not remind again**, in that order, at most once per Plugin per session, while continuing your original task.

Choosing “Set as default” authorizes the Agent to write the current Agent’s global rules directly, without a second confirmation. After reading the result back, it shows the complete saved rules, actual file and scope. It prioritizes the applicable tikin-social Skills only when you have not chosen another tool. Shared rule files and conflicts are explained before the choice. Saving a rule and verifying that a new host session loads it are reported separately.

“Do not remind again” only saves the reminder choice; it does not install or remove default rules. You can ask:

> Stop reminding me to make tikin-social the default in this Agent.

> Enable tikin-social default-Skill reminders again in this Agent.

The choice is automatically read from `~/.config/tikin-social/settings.json`, separately for each Agent type and actual configuration directory. All 17 Skills and future versions share that Plugin preference; aihub-studio is independent. Existing routing and other settings are preserved. This preference does not come from environment variables or `.env` files. Missing preferences mean reminders are enabled; read-only checks create no files. Only an explicit disable/enable request saves a choice. Running without global configuration also skips this check and refuses preference writes.

The check needs no API key or network. Codex, Claude Code, WorkBuddy and Hermes have rule-entry guidance; Hermes uses the active Profile’s SOUL.md and records reminders separately per HERMES_HOME; unknown hosts or failed checks are reported without blocking the task. The configuration helper now selects Windows `Scripts/python.exe` or POSIX `bin/python`. Linux/WSL use their own runtime user directory and do not read Windows preferences. Real host-session loading and non-credential workflows require separate validation.

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

Hermes installs the complete native Plugin from `https://github.com/cookaihq/aihub-marketplace.git#tikin-social` (same-version CNB fallback: `https://cnb.cool/zhidateam/tannt/aihub-marketplace.git#tikin-social`). Ask your Agent to preserve existing settings, install and enable the package, and verify all 17 Skills in the active Profile. Explicitly load `tikin-social:tikin-endpoint-discovery` for an offline search before reporting a business result. Fixed refs and native updates are described in the [packaged installation guide](skills/tikin-setup/references/installation.md); [Profile rules](skills/tikin-setup/references/default-skills.md#hermes-入口与-profile) identify the active SOUL.md and reminder scope. Missing-Key recovery for Tikin 4.x requires Setup 4.2.0 or later.

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
Saving private reports on Windows uses native access controls and requires a filesystem
supporting them. Files are restricted before private contents are written;
a report save failure does not cause another API request. A WorkBuddy card does not prove runtime
compatibility. This version's local synthetic tests and host acceptance are recorded separately;
real social-data business, Linux and WSL flows remain unverified. Do not switch Windows tasks to WSL
automatically.

## Configure API access

> 打开 Tikin Social 的配置中心。我会在网页填写 API Key，保存后请检查本机配置，再继续原任务。

无需另装 Setup 即可打开。页面先展示当前生效配置，逐项标出项目覆盖、继承全局或其他来源。点击“编辑”可选择保存范围和具体文件，在保存或移除设置前预览实际生效值及来源；“来源与优先级”显示该项真实的读取顺序。Key 下提供 [Tikin 控制台](https://console.tikin.net) 链接及“或联系团队负责人分配”。页面不展示服务地址；既有地址配置仍按原加载器读取。

首次新增默认个人全局 `~/.config/tikin-social/.env`；新增项目密钥默认使用 `.env.local.tikin-social`，也可明确选择普通 `.env.local`，已有密钥可选择原文件修复或移除，环境变量在原注入处修复。每次只保存所选文件，其他文件的草稿继续保留；保存较低优先级的文件时，预览会说明是否仍被上层覆盖。路由与提醒偏好保存在独立的全局 `settings.json`，平台路由可移除后继承默认方式，默认方式移除时重置为 `auto`。密钥直接在浏览器填写，不放入聊天。本页校验本机配置，不验证在线鉴权；受支持的既有文件继续读取，不迁移或删除；4.0.0 退出来源见下文。

已有 Setup 任务沿用原编号打开同一配置中心，保存后用真实加载器复查，再核对原业务提交状态。已提交或结果不明先查原结果，不重发；没有浏览器或明确选择文件编辑时，沿用[本机配置流程](skills/tikin-setup/references/credential-setup.md)。

默认同机访问、闲置 60 分钟结束。**📱 手机或其他设备访问需要 FRP / Tailscale，实际配置状态由 Agent 核对。**

### Upgrading from 3.x

4.0.0 adds the two Plugin project files below and stops reading project `.env.<skill-name>` and global `~/.config/tikin-social/.env.<skill-name>`. If your key exists only there, configure a supported location before running a task. Skill subdirectory `.env.local/.env`, ordinary Skill `~/.config/<skill-name>/.env` fallback and plain project files remain supported. No file is automatically read for migration, moved or deleted.

Ask your Agent to list the old and proposed locations without revealing values, then wait for your migration choice. Use `.env.local.tikin-social` for a shared project key, or the retained Skill subdirectory for a distinct global account. The ordinary `.env.tikin-social` file supports nonsecret settings and repair of an existing key; new project keys use the declared local files and must be untracked and Git-ignored.

### Configuration sources and repair

The confirmed default for new shared credentials is the Plugin’s personal `.env` file. Existing
supported project or Skill-specific choices remain valid. Each field independently uses the first nonempty
value below. For example, when `tikin-douyin` makes a request:

1. The process environment.
2. `.env.local.tikin-social` in the command’s working folder, shared by this Plugin’s Skills.
3. `.env.tikin-social` in that folder, shared by this Plugin’s Skills.
4. `.env.local` in that folder.
5. `.env` in that folder.
6. `~/.config/tikin-social/tikin-douyin/.env.local`.
7. `~/.config/tikin-social/tikin-douyin/.env`.
8. `~/.config/tikin-social/.env.local`.
9. `~/.config/tikin-social/.env`.
10. `~/.config/tikin-douyin/.env`.

Other Skills replace `tikin-douyin` with their own exact `tikin-*` name. The working folder is
where the agent executes the command, not the installation directory; parent folders and other
Skills’ files are not searched. Empty fields or empty Plugin directories continue to lower
sources. Existing unreadable files report an error instead of silently selecting another account.
Files contain literal values; they are never executed as shell programs.

The five global sources are read automatically. Ask “Run this task without global configuration”
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

## 浏览任务、会话和文件

Markdown 详情现在显示标题、强调、列表、表格和文档同目录或子目录内的 PNG、JPEG、GIF、WebP 附图，支持中文和空格路径。缺图或不允许的引用显示原因；远程图片、越界路径和 SVG 不加载。复制与下载保留原始 Markdown，附图不增加产物数量。

> 打开当前项目的 Tikin Social 产物页面。

默认按任务显示文件夹，点击后看该任务的报告、数据或媒体，再进入详情；按会话在桌面左边选择会话、右边查看任务，手机逐层进入；按文件平铺全部成果。顶部显示当前项目真实 Git 分支。任务卡片最多横排 3 个不同格式的缩略图，图片和视频使用封面。

每项新任务的 `task-info.json` 记录创建者、可靠会话和实际参与 Agent。未知会话放入“未关联会话”；继续原任务追加参与者，不覆盖创建者。完整成功响应保存在 `files/`，最终分析结论默认另存 Markdown，CSV/JSON 保存完整数据；这些文件由工具自动关联或由 Agent 本地登记。源素材、诊断和 `.part` 不计最终成果。失败、部分和零成果任务也会显示。

只展示当前项目的新规范任务，不补历史记录。外置任务目录由 Agent 显式指定，文件仍可保存在你明确要求的位置。配置和产物服务独立，产物可选择本次常驻；结束页面不删除文件。**📱 跨设备访问需要 FRP / Tailscale，实际配置状态由 Agent 核对。**

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
