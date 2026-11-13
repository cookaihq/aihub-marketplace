# Changelog

## 6.1.0 — 2026-11-14

- 移除 ElevenLabs 音色克隆占位场景、配置加载与配置中心字段，清理音频 Skill 的触发简介及使用说明；旧 audio-clone 请求按不支持的操作拒绝。
- 旧占位配置不再生效，保存其他设置时保留用户文件中的原字段。ElevenLabs 预置音色库、默认音色及收藏继续使用原来的项目／全局协议。
- Plugin 按用户指定发布 6.1.0；音频 Skill 以 6.0.1 修正不可执行的占位声明，其他 Skill 保持版本。
- Windows 整包回归首轮 188/189，唯一 review 用例的子进程空输出解析失败保留；原测试串行复测 1/1 通过，未修改产品或放宽测试。UI 40/40，五个 Skill 官方格式、工作区及准入检查通过。
- 独立 Codex 0.167.2 默认沙箱验证 Speech／Dialogue 默认选型与克隆拒绝；配置中心首次 uv 访问失败后，仅前置测试子进程的既有可读 uv 路径，实际启动、HTML／脚本、授权 state、18 字段无克隆及停止后端口关闭通过。WorkBuddy 本次跳过；ffprobe 的 EPERM、macOS、安装／隐式发现、付费业务及本版新的浏览器操作保持未验或受限状态。

## 6.0.0 — 2026-11-13

- 适配 Gateway Issue #29：Speech 显式 `voice_id`、Dialogue 逐段 `voice_id`，嵌套语音设置；旧字段明确给出迁移提示。两款 Speech 统一 10000 字符上限，对话保留顺序及最多 10 个不同音色，逐段显式指定。
- 同步 Speech 28 种、Music 26 种格式，以及音效、plan/seed/C2PA 约束。Scribe V2 改用 `source_url` 或文件，默认不分离说话人，新增关键词、角色、改写、多声道和实体校验；V3 保持原合同。
- 保留显式 false/0、完整转写和扩展结果、原始 `task.usage`；预扣不标为最终费用，无效音色停止候选切换，历史任务继续原 ID 查询与下载。
- 不兼容参数迁移使 Plugin / 音频 Skill 升至 6.0.0，音乐 Skill 升至 5.0.0；其他保留的 Skill 版本不变；显式型号、个人列表及历史任务优先。
- 合同适配阶段的 Windows 定向回归、当时六个 Skill 的规范检查和 Codex 默认沙箱离线验证完成，最终音乐四项复测通过。首轮两份音乐验收输入缺少必填 positive_styles，原失败保留，另用完整输入验证通过。
- Gateway v0.9.16 及对应文档已于 2026-11-13 上线，线上调用沿用既有账号检查与付费授权。本批 Windows 整包回归 188/189，唯一超时用例所在文件串行复测 3/3；UI 40/40，当前五个 Skill 规范检查通过。Codex 0.167.2 默认沙箱开发源九份离线计划、两项预期拒绝与配置中心启动／停止通过；独立浏览器验证筛选、试听、项目／全局保存及 390×844 布局。WorkBuddy 按用户确认本次跳过，doctor 的 ffprobe 因 EPERM 受限；macOS、客户端生产联调、安装／隐式发现及人工听审未验。

- 单人语音／旁白默认改为 `eleven-v4-text-to-speech`，有序对话默认 `eleven-v4-text-to-dialogue`；ASR 保持 `paraformer-v2`。GPT Image 2.6 已上线，图片编辑继续使用 2.5。
- 音乐改为按描述生成歌曲、按已有歌词演唱、纯音乐／背景音乐三个场景，全部默认 `suno-v6`；保留可选 ElevenLabs Music 与 Lyria，旧已保存任务按原计划恢复。
- 完整配置中心新增“ElevenLabs 预置音色库”：语言／风格筛选、样音试听、收藏、选音色；选择项目或全局后同时保存默认音色和收藏，通过真实音频加载器回读。Speech 未显式指定 voice_id 时才继承，对话不自动分配。
- 添加 ElevenLabs 克隆空模型占位，本版拒绝提交；移除 `aihub-document` 的注册、配置和默认路由，整包保留五个 Skill。旧文件和任务不自动迁移或删除。

## 5.0.0 — 2026-11-13

- 接收 Gateway Spec #28，退出旧 v4/Turbo 四个新请求 ID，无别名或 Turbo 回退；历史任务继续原 ID 恢复，个人列表给出用途迁移说明但不改写。
- 新增 audio-dialogue：有序 text/voice 台词数组，一次提交；累计最多 2000 Unicode 字符、10 个不同音色，可超过 10 段重复音色。Speech / Dialogue 各有普通与已有音色 custom 变体。
- 完整校验共享控制、词典固定版本、custom 安全开关边界；保留 false / 0，仅省略合同允许的 null 控制。保留独立可空 alignment、normalized_alignment 和完整 voice_segments。
- 内置 TTS=speech-2.8-hd、ASR=paraformer-v2；新 Eleven 四模型为可选能力，等待对应 Gateway 版本生产部署。音乐与 Scribe 行为保持，其他 Skill 版本保持。
- Studio 与音频 Skill 升至 5.0.0；Windows 脚本首轮 171/177、覆盖全部失败的串行复测 37/37、增强历史恢复后 7/7，Codex 0.167.2 默认沙箱开发源显式调用九项离线验证与六个 Skill 规范校验通过。WorkBuddy 本次跳过；macOS、安装／隐式发现、新合同生产调用与人工听审未验；Codex 沙箱内 ffprobe 启动受 EPERM 限制。

## 4.0.0 — 2026-11-13

- 移除 `aihub-audio` 的声音克隆能力、`audio-clone` 操作及其参数映射。
- `voice-clone`、`minimax-voice-clone` 及其可解析的提供方／变体 ID 不再出现在可用模型列表中，`describe` 和直接 `generate` 均拒绝，旧配置不能重新启用克隆。
- 同步音频 Skill 简介、Codex 展示名、默认 Skill 路由模板和使用说明；文本转语音与语音识别／转写继续提供。
- Gateway v0.9.15 正式上线后启用已确认默认：TTS `eleven-v4`、异步音乐 `elevenlabs-music-v2.5`；静态文生图使用 GPT Image 2.6，图片编辑使用 2.5，保留 Flare／Sunburst 的速度与细节选择。ASR 和 Gemini 原生音乐默认保持原值，显式型号及个人列表优先。
- 合入官方 Relay 适配：两个 custom-voice 型号使用已有音色 ID；Scribe V2/V3 支持单 URL JSON 或本地 multipart，保留词、说话人与时间戳；只读 voices 返回完整音色目录，不自动将 V3 降为 V2。
- ElevenLabs 音乐退出秒制 duration，歌曲使用整数 music_length_ms、段落使用整数 duration_ms；旧字段报迁移错误，不自动换算或重发。官方 Music 支持 MP3/Opus，其余统一编码保留 Fal，实际时长与请求时长分别报告。
- 共享客户端和诊断保留 requested_options_unavailable / unsupported_parameters 的完整错误、type 与字段数组，停止自动切换，由用户决定修改要求。
- 克隆移除与音乐字段迁移属于不兼容变化，Plugin、音频、音乐均为 4.0.0；图片 3.1.0，视频 3.1.1，文档／理解 3.0.4。三宿主清单与 Node/Python/Hermes 版本实体同步。
- Gateway 13 个生产样本及账务证据复用，未重复生成；音频人工试听仍待评审。Windows 原生 Codex 0.167.2 的开发源显式调用、七份成功离线计划及克隆拒绝通过，六个 Skill 规范校验通过。完整回归首轮 165/173，更新图片默认的旧测试夹具后，原失败 8 项复测全部通过。
- 本批 Claude Code／WorkBuddy 免验；macOS、重新安装与隐式发现待验。当前验收凭证可见 ElevenLabs 七款，未返回 GPT Image 2.6；该账号限制不改变已批准默认，实际调用继续预检，不能自动换回旧版或将生产样本视作所有账号可用。

## 3.2.0 — 2026-11-12

- C1 默认使用 `sync-3`，C2 默认使用 `fabric-1.0`，多模态理解默认使用 `gemini-4-carbon`。显式模型、配置顺序和已保存任务继续采用原选择。
- 补齐 Sync 3 / Fabric 的任务参数映射与提交前校验；Fabric 默认 720p，保留显式 480p，按请求分辨率核对账号型号，不自动降级。Sync 3 的参数说明不再展示其不支持的字段。
- 修复账号模型列表路径：`/v1/models` 保留在主 API，不再错误改写为 `/e/v1/models`；其他生成、任务与专用配置接口继续使用 `/e/v1/`。
- 准备 Eleven v4 / Turbo TTS 和 ElevenLabs Music v2.5 的目录、请求预览与严格参数映射；保留显式型号及个人列表。音乐支持提示词或分段计划，校验秒/毫秒范围与互斥字段；旧 Speech/Lyria 参数无法映射时明确拒绝。
- 时间戳分段及空段原样交付；下载识别实际 MP3、Ogg Opus、WAV 容器，等待核账和恢复下载继续查询原任务。音乐费用按实际账单，不能把 60 秒请求视为固定 1 分钟计费。
- ElevenLabs API 待人工试听验收及生产正式上线，因此 TTS / 异步音乐内置默认仍为 `speech-2.8-hd` / `lyria-3-pro`；满足条件后才启用已确认的新默认。
- Plugin 为 3.2.0；视频 Skill 为 3.1.0，音频为 3.2.0，音乐为 3.1.0；理解、图片和文档为 3.0.3。音频与音乐的新映射升 MINOR，共享模型查询路径修复保留在其他受影响 Skill 的 PATCH 中。
- Carbon 已进入正式 llm-custom 能力清单，并通过图片、中文录音、短视频和 PDF 的四次真实请求及内容核对；音频另用 Paraformer 独立转写交叉核对。保留账号能力预检及原任务恢复，不新增纯文本业务入口。
- Windows 原生 Codex 的开发源显式调用、六类默认模型计划、五项 ElevenLabs 计划/拒绝场景及完整 162 项本地回归通过；本批 Claude Code / WorkBuddy 免验。macOS、重新安装和隐式触发待验；Sync/Fabric 与 ElevenLabs 的线上生成效果不由 Carbon 验收代替。
- 保留结果检查的真实状态：音频／视频 URL 原素材缺少绑定时长时，自动检查仍为 inconclusive；图片、PDF 检查为 matched。独立内容验收与自动检查状态分别记录。

## 3.1.0 — 2026-11-12

- 统一配置中心新增 MiniMax Speech 默认音色，支持预设库搜索、筛选、分页、已有样音试听和独立收藏；选择音色后在原编辑面板保存。按 Skill / 特殊模型拆分源码，保留现有页面导航。
- 新计划和独立生成仅在未显式指定音色时采用默认值，保留其他语音参数；已保存候选与旧任务恢复不重新应用默认值。支持官方 ID 内部空格，补齐 Speech 2.8 Turbo 目录映射。
- 实际 `/v1/` API 迁移到 `/e/v1/`，保留 `/v1beta/` 与定价接口；旧路径在请求边界只转换一次，不重发已提交任务。只读查询尊重完整 Retry-After，超出总预算则停止。
- Plugin 与音频 Skill 为 3.1.0，其余五个 Skill 因共享 API 路径修复升至 3.0.2。
- Windows 原生 Codex 0.167.1 开发源调用、合成保存 / 回读、浏览器桌面与 390×844 验收通过；真实只读接口返回 715 个预设音色，抽样试听通过。用户明确免除本次 Claude Code / WorkBuddy 实测；macOS 待验。未重新安装或执行付费合成。

## 3.0.1 — 2026-11-08

- 修复首次保存配置因缺少 Git 忽略规则而中断：保存时自动补齐当前文件、临时文件和私有恢复目录的必要规则并核验，保留既有规则；浏览和预览不写入。
- 配置项标题下显示实际字段名，例如 TIKIN_API_KEY、AIHUB_API_KEY 或 routing.default；密钥值继续脱敏。
- 已跟踪的配置继续拒绝覆盖，不自动移出 Git 索引；权限失败保留草稿，恢复后可重试。
- Windows 18 项集成回归、分发/版本/生命周期检查、Codex 0.166.0 默认沙箱下两套正式配置入口的 HTTP 保存与原加载器回读通过；独立浏览器验证保存、字段名和 390×844 布局。本次 WorkBuddy 按用户要求免验，macOS 待验；未重新安装或调用线上业务。

## 3.0.0 — 2026-11-08

- 新增项目 `.env.local.aihub-studio`、`.env.aihub-studio`，六个 Skill 共用；依次优先于普通 `.env.local`、`.env`。
- 不兼容变更：不再读取项目 `.env.<skill-name>` 与 Plugin 全局根 `.env.<skill-name>`，来源列表及修复/删除目标同步退出。仅在这些位置有值的用户须重新配置受支持位置；不自动读取旧文件进行迁移，也不移动或删除它们。
- 保留 Skill 子目录 `.env.local` / `.env`、Plugin 全局共享文件、普通 Skill 全局 `.env` 回退和普通项目文件。
- 配置页默认项目保存到 local Plugin 文件；来源、共享影响、遮蔽、保存与清除回退均由原加载器校验。普通 Plugin 文件仍可修复已有 Secret。
- 六个 Skill 共用加载器，均升至 3.0.0。
- Windows Codex CLI 0.166.0 默认 workspace-write 沙箱通过开发源显式加载、真实配置入口及页面 HTTP 闭环；Setup 委托、任务绑定和仅配置回读通过。独立浏览器验证两套业务页桌面及 390×844 布局。按用户本批次决定，WorkBuddy 免验；macOS 待验。未重新安装、验证隐式触发或调用线上业务。


## 2.2.0 — 2026-11-07

- 配置中心升级为“当前生效配置 + 逐项来源 + 分层编辑”，明确显示项目覆盖、全局继承和进程环境来源。
- 可选择实际参与加载的文件；保存及移除覆盖前，用原加载器预览回退结果。仅提交选定文件，保留未知配置、其他草稿及失败输入。
- 检查修订号并拒绝过期保存；私密值默认脱敏，按需查看沿用会话鉴权。真实配置优先级、caller 隔离及全局开关保持一致。
- 六个 Skill 共用配置入口，均升至 2.2.0。
- 本版已在 Windows 原生通过 Codex CLI 0.166.0 的开发源显式调用、两套随包服务启动、HTTP 配置预览/保存、原加载器回读和停止检查；独立浏览器完成桌面与 390×844 窄屏验证。71 项定向回归通过。按本次用户决定，WorkBuddy 不作为验收要求；macOS 待验。未替换现用 Plugin 安装，未验证原生重新安装、隐式触发、线上鉴权或付费业务。

## 2.1.1 — 2026-11-07

- 修复 Markdown 预览：使用锁定的解析器显示富文本与文档相对附图，支持外置文档、中文及空格路径。
- 附图沿用鉴权与文档归属，拒绝远程、越界、SVG、伪装格式及超限文件；文件变化后旧资源失效，不增加产物计数。复制和下载保留原文。
- 启动时按锁文件恢复缺失的解析依赖。
- 六个 Skill 共用产物入口，均升至 2.1.1。
- 本版在 Windows 通过 Codex 0.166.0 的开发源显式调用、两套服务的启动/资源/下载检查，以及独立浏览器的图片显示与手机视口检查。原业务文档 29 张图片全部显示，真实文件保持不变。按本次用户决定，WorkBuddy 不要求实测；macOS 待验。未复测原生安装发现、隐式触发或线上业务；Codex 子会话自身的浏览器控制受限，独立浏览器结果另行记录。

## 2.1.0 — 2026-11-07

- 新增 Hermes 原生 plugin.yaml / register 入口，注册原六个 Skill，继续共享业务脚本与完整包资源。
- 默认规则检查支持当前 HERMES_HOME / 平台默认 Profile 的 SOUL.md；提醒按 Profile 隔离，保留三宿主入口与业务配置来源。
- 六个 Skill 升至 2.1.0，补充完整包安装、固定 ref 与原生更新说明。
- 共享配置/产物网页接受 Hermes 宿主参数；任务元数据支持 Hermes 会话身份，多宿主环境变量并存时要求显式身份。
- 本版已通过 Windows 原生 Codex、WorkBuddy、Hermes 的入口加载与本机合成配置流程；Hermes 另验证 Profile 隔离及任务身份。未调用付费业务，未验证真实线上鉴权；macOS 本轮待验，Claude Code 保持兼容但未实测。历史结果仅覆盖所列版本。

## 2.0.0 — 2026-11-06

- 固定 API 服务地址为 `https://api.aihubmax.com`，删除 `AIHUB_BASE_URL` 的环境变量及文件覆盖能力，配置检查只报告仍支持的字段。原配置文件保留。
- 六个 Skill 共用固定服务；其他服务的旧任务在联网前拒绝恢复，官方服务已有任务继续使用原恢复流程。
- Plugin 自带配置中心：固定底部保存栏、API Key 获取提示和真实来源校验。业务配置退出 Secret Book，既有本机配置继续按原优先级读取。
- 新任务根改为 `data/aihub-studio/`，目录采用 `YYYYMMDDHHmmss-任务摘要-run-8hex/`；每个任务保存 `task-info.json`、可靠会话/Agent 身份及最终文件。历史任务不索引或迁移。
- 新增按任务、会话、文件查看的产物页，显示当前分支；任务文件夹采用最多三个不同格式的横排预览，图片/视频显示封面，支持逐层返回。
- 保留业务恢复状态、登记去重与部分/失败交付事实；修复 Windows 私有文件权限及项目所有者回读。离线测试使用独立网络夹具，业务程序没有测试地址设置。
- Windows 本机回归与 Codex/WorkBuddy 验收范围见 README。本轮 macOS、真实鉴权和线上业务待验。

## 1.5.1 — 2026-11-06

- 默认设置首项固定为“设为默认 (推荐)”。用户选择后直接设置，完成后展示回读到的完整规则、文件位置和影响范围，不再二次确认。
- 保留文件变化检查、已有规则去重、同一实体文件合并编辑及跨轮恢复；未答复不写配置。
- Windows 默认规则测试 7 项通过；Codex 隔离文件的菜单、写入、恢复与完整展示通过，原生安装及真实全局加载未验证。Claude Code 额度 403、WorkBuddy 输入与发送受阻，macOS 待验；按用户明确要求发布，保留上述待验项。

## 1.5.0 — 2026-11-03

六个业务 Skill 缺少 API Key 时实际启动 Setup 2.3.0 配置网页；保存后复查并按原请求提交状态接续，避免重复提交。六个 Skill 均为 1.5.0。

macOS 合成脚本、网页与 Codex 0.166.0 的业务缺 Key / 保存 / 跨轮恢复通过；Claude Code 2.1.317 被额度不足阻断，WorkBuddy 被辅助功能权限阻断，Windows 原生待验。完整范围见 README；未使用真实业务 Key 或计费请求做本轮验证。

## 1.4.0 — 2026-10-28

- 原始录音按实际模型和上传限制检查，自动分析波形、优先停顿分段，无合适停顿时使用低能量切点与短重叠；切后实测字节数、时长和覆盖。
- 保存源快照、分片、上传和远端任务状态，跨进程恢复查询与下载，结果不明不重发，成功片段不重复付费。
- 合并全部转写、全局时间戳与结构化结果，保留重叠去重证据；说话人按片段作用域标识，结果检查绑定完整原录音。
- 自动契约覆盖 Paraformer V2 / 8 kHz 中文型号；其他模型限制未核实则明确拒绝。合成测试不代表真实录音、线上业务或三宿主全部通过。
- 验证：Windows 原生完整套件 131 项及后续定向回归通过。三宿主业务闭环仍未完成：Codex 默认沙箱私有文件 ACL 拒绝，Claude Code 账号额度不足，WorkBuddy 界面请求未能发送；详见 README。

## 1.3.1 — 2026-10-27

- 分发校验分别检查 Plugin 安装包与每个 Skill 的版本来源，允许独立版本；六个 Skill 保持 1.3.0，业务行为不变。
- 三宿主清单、共享运行时和市场条目同步到 Plugin 1.3.1；更新发布说明中的版本组合。

## 1.3.0 — 2026-10-09

- 六个 Skill 首次 HTTP、协议或远端执行错误即保存本地 Markdown 汇总与实际脱敏请求/响应；跨轮追加、终止失败去重及恢复持续提供完整绝对路径链接。
- 修正固定填写的终止失败 HTTP 200；区分客户端状态、异步状态和服务暴露的上游证据，并解释旧报告。
- 公开草稿继续排除私密输入、素材链接和原始 ID；报告写入失败保留业务结果，不改变重试或模型切换。
- 验证范围：Windows 原生自动测试全量 122 项通过，后续修改对应的 47 项回归通过；WorkBuddy 5.7.6 界面验收尚未完成，Claude Code/Codex 本版仅做结构与说明检查。

## 1.2.1 — 2026-10-08

- 凭证配置提示与转交改用 Setup AIHub 2.0.0 的 `setup-api-key` Skill；本机检查契约和最小回退流程保持兼容。

## 1.2.0 — 2026-10-08

- 新增 Windows 原生 PowerShell 入口，自动核对 Node 版本并固定模块路径解析，修复 Codex 默认沙箱内安装包启动时的用户目录 `EPERM`，保留业务 cwd、参数与退出码。
- 新增无调用方 `config-check --plugin-only` 与声明字段的只读删除投影，沿用真实加载器。
- 凭证缺项衔接 Setup AIHub，保留独立手填/Secret Book 最小回退、真实 cwd/caller 与业务提交状态。
- 配置检查与媒体工具、线上鉴权分开；Codex 默认 Windows 沙箱、WorkBuddy 本机配置闭环及 Secret Book 真实表联调通过。Claude Code 安装、发现与自然触发通过，配置闭环未实测。
- Windows 私有任务/诊断文件在写入前设置并回读 DACL，仅当前用户和 SYSTEM 可访问；使用系统 Windows PowerShell 路径，不依赖媒体工具的 PATH。
- 修复 Windows 的已退出进程锁恢复与竞争中的文件忙处理；按真实文件名注入保存失败，验证结果未知或已提交的任务不会重复提交。
- ZIP/DOCX 测试使用固定压缩夹具，权限测试在 Windows 核对真实 DACL；原生 Windows 完整回归 108 项通过。

## 1.1.3 — 2026-10-06

- Keep the product name Secret Book untranslated in credential choices and guidance, including all six Skills, configuration errors, CLI help and the README. Preserve `secret-book` as the Skill identifier and the existing configuration inspection schema.

- Require actual AIHub execution for applicable default tasks, including image generation within websites and presentations; expand task mappings to the six Skills' current scope.
- Preserve host tools for prompt preparation, deterministic file processing and Skill-directed result checks. Other execution channels require the user's authorization for the task; unaffected subtasks continue.
- Keep ordinary conversation, coding, search, charts, screenshots and general Office work outside forced routing. Future default routing applies only to available, verified Skills in aihub-studio.
- Align all six Skill entrypoints and the shared default-rule workflow. Review existing older rules without treating them as entirely missing or rewriting them automatically; show differences when the user requests an upgrade.
- Remove the generic permissions, privacy, fee-confirmation and request-budget clause from the proposed rule.

## 1.1.2 — 2026-10-06

- Offer local file entry or secret-book whenever an API Key is missing or needs repair, including direct guidance in all six Skills and configuration errors. Preserve the user's chosen method.
- Limit credential setup and the secret-book declaration to `AIHUB_API_KEY`; use the built-in service address for first setup. Existing service overrides and business settings remain compatible.
- Add `config-check --credentials-only` for the exact single-key Secret Book contract while preserving source paths and file revision checks.
- Follow secret-book's workflow directly when selected. Handle installation, invocation or compatibility problems only when encountered; remove the obsolete native Windows restriction for secret-book 2.4.0+.
- Preserve the original request through configuration, then continue only within existing authorization and query uncertain submissions before any retry.

## 1.1.0 — 2026-10-03

- Check the current Agent's applicable global/project instructions once per Plugin per session, with explicit task-to-Skill mappings for Codex, Claude Code and WorkBuddy.
- Offer set-as-default, skip-once or stop-reminding without blocking the original task. Rule writes require the user's approval of the exact text and target; existing equivalent rules, overrides and shared files are reviewed before editing.
- Add the offline `default-skills` helper and per-Agent/configuration-directory preferences in the Plugin's `settings.json`. Preserve other settings and routing, support re-enabling, and skip the workflow when global configuration is disabled.
- Keep business APIs, credentials and runtime support unchanged. File checks do not establish actual host-session loading.

## 1.0.0 — 2026-10-02

- Move the Plugin to `cookaihq/aihub-marketplace` and its CNB mirror, under the new installation identity `aihub-studio@aihub-marketplace`.
- Rename the shared global configuration root to `~/.config/aihub-studio/`; report the new consumer identity and document explicit migration from `~/.config/aihub/`. Old Plugin configuration is never read or moved automatically.
- Preserve all six `aihub-*` Skill names, `AIHUB_*` configuration fields, task records, business CLI and result-check behavior.
- Update bundled installation instructions, manifests and Issue links; retain the WorkBuddy screenshot and the existing limits on host and Windows validation.

## 0.9.2 — 2026-10-02

- Include the user-provided Windows screenshot in the Plugin and installation README, and require Agents to show it alongside manual WorkBuddy installation steps.
- Identify the visible entry as the round **+** beside marketplace names under **技能 → 套件**, with “添加市场” appearing as the dialog title. Windows and macOS entry locations are confirmed; full installation and Skill execution remain unverified.

## 0.9.1 — 2026-10-02

- Route WorkBuddy installation, discovery and updates through the running app's native plugin manager. Stop instructing Agents to launch a separate CodeBuddy CLI, including for help and validation, which can create an unwanted user `.codebuddy` directory.
- Explain why configuration-directory environment variables alone cannot prevent the bundled CLI's hardcoded diagnostic directory. Preserve custom WorkBuddy directories and existing CodeBuddy data; no host binary patches or automatic cleanup.
- Ship host-specific installation and recovery instructions, distinguish installation from Skill execution checks, and remove the outdated unpublished notice. Windows end-to-end validation remains pending.

## 0.9.0 — 2026-10-02

- Check delivered results against preserved user requirements by default. Prefer available host media tools, or use configurable AIhub reviewers with `gemini-3.8-flash` as the built-in default.
- Add `review` and `review-submit`, per-requirement evidence, file hashes, bounded document text extraction and resumable review tasks. Incomplete coverage cannot pass; check failures never regenerate media or automatically switch reviewers.
- Remind users after every enabled completed check that they can disable checks through conversation; document single-task and persistent configuration actions in all six Skills.
- Count independent upstream errors, deduplicate terminal task failures, and produce a local public Issue draft plus private administrator diagnostics. Never send feedback automatically or copy raw responses into reports.
- Add optional check and feedback settings to the layered loader, source inspection, credential declaration and packaged instructions. Only the API Key remains required.

## 0.8.0 — 2026-10-01

- Read ordered per-Skill model lists and `auto`, `confirm`, `off`, or `preflight_only` fallback policies; only the API Key is required and the built-in service URL remains overridable.
- Add `plan`, `run`, and `continue` with saved requirements, independently validated model requests, attempt limits and persistent confirmation. Explicit user model choices stay fixed.
- Keep uncertain submissions, active tasks, query/download errors and content mismatches on their original task. Legacy `resume` never submits another generation; native music now checks media tools before submission.
- Route all six Skills through the configured model workflow, documenting verified parameter mappings and unsupported conversions.
- Add `config-check` to report effective configuration files, missing or invalid settings and stale-report checks without exposing values or requiring network/media tools.
- Use secret-book to preview and save consumer configuration, repairing the actual source file and using Plugin globals only for new settings without an existing location. Normal AIhub commands read local configuration directly; table rotation does not automatically overwrite it.
- Report authentication rejection with configuration sources, separately from balance, permissions, rate limits and network errors. Configuration repair does not resubmit a business request.
- Update the first-configuration prompt and shared workflow; keep record/key confirmation and Agent rule inspection in secret-book.

## 0.7.0 — 2026-10-01

- Add the current Skill's `~/.config/<skill-name>/.env` after all five Plugin global files, filling each missing or empty field without overriding Plugin, project or process settings.
- Report the fallback file in configuration sources and make `--no-global-config` skip both Plugin and standalone Skill directories.
- Keep new file configuration in the Plugin directory by default; existing Skill files can be reused without migration. Do not read standalone `.env.local`, other Skills or old product aliases.

## 0.6.0 — 2026-10-01

- Offer secret-book or self-managed `.env` during first configuration, retaining personal global files as the default for the file option.
- Ship a credential requirements declaration and route all six Skills through secret-book consumer connections when selected. Record/key confirmation, scope and subsequent injection belong to secret-book 2.3.0 or newer.
- Keep the installation and first-configuration prompts short; distinguish local configuration checks from remote authentication.

## 0.5.0 — 2026-09-30

- Automatically read shared configuration from `~/.config/aihub/.env` and `.env.local`, with per-Skill `.env.<skill-name>` files and optional Skill subdirectory overrides. Process and project settings remain higher priority.
- Add `--no-global-config` to skip all global files for one command; retain `--use-global-config` as a compatibility no-op and reject conflicting flags.
- Stop reading the old parallel `~/.config/aihub-*/.env` directories. Existing users must explicitly migrate shared settings or per-Skill overrides; credentials are never moved automatically.
- Rewrite installation and first configuration guidance for users, including GitHub/CNB sources, personal global configuration, platform paths and source diagnostics.

## 0.4.0 — 2026-09-30

- Choose GPT Image 2.5 Flare for speed, or for drafts and iteration without an explicit detail priority; choose Sunburst when fine detail is the priority and speed is secondary. Clarify conflicting priorities and preserve explicit model choices.
- Select Seedance 2.5 text, first-frame image or reference generation according to the intended role of the inputs. Keep dedicated lip-sync and digital-human workflows separate.
- Refresh the bundled GPT Image 2.5 and Seedance 2.5 parameter contracts and reject incompatible inputs before submitting a generation request.
- Replace Seedance 2.0 defaults for new generation while retaining its six variants for explicit user selection; existing tasks remain resumable without resubmission. Unavailable models never trigger an automatic fallback.
- Treat strict first/last-frame control, source-preserving edits and video extension as requiring separate capability verification; model selection alone does not establish support.

## 0.3.0 — 2026-09-23

- Split D1 audio and speech processing, D2 music generation, E1 multimodal understanding, and E2 document conversion into separate Skills.
- Add default model planning for `speech-2.8-hd`, `paraformer-v2`, `lyria-3-pro`, `lyria-3-pro-preview`, `gemini-3.1-pro-preview`, `gemini-3.5-flash`, and `doc2x-v3`.
- Add LLM task results, Gemini native music inline audio, and Doc2X ZIP validation to the shared CLI.
- Add WorkBuddy/CodeBuddy manifests and marketplace registration.
- Remove B10 video upscaling from the current scope and regression target.


## 0.2.0 — 2026-09-22

- Restrict image workflows to A1/A2 and expose `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst` in the bundled catalog.
- Add Seedance 2.0 standard and fast model IDs, C1/C2 digital-human model variants, and explicit rejection for excluded profile, subtitle, interpolation, Sora-character and voice-creation tasks.
- Preserve task-specific result metadata such as seeds, lyrics, degradation reasons and output types in normal CLI results.
- Update image/video Skill instructions for the confirmed scope and document the Seedance 2.5 replacement condition.

## 0.1.0 — 2026-09-15

- Add `aihub-image`, `aihub-video`, and `aihub-audio` for image generation/editing, video generation, music, and text-to-speech.
- Share one CLI for configuration, model discovery, parameter descriptions, uploads, generation, task recovery, and verified downloads.
- Persist task records outside the installation so interrupted queries and downloads can resume without submitting another generation request.
- Package native Claude Code and Codex manifests, compiled JavaScript, and the model catalog in one Plugin directory.
- Support caller-specific `.env.<skill-name>` configuration before shared project configuration; home configuration requires an explicit flag.
