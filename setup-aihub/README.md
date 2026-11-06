# Setup AIHub

4.0.0 的 setup-api-key 保留业务任务与恢复编号，打开目标 Plugin 自带的配置页面。业务密钥配置退出 Secret Book 入口；既有文件继续按原优先级读取。setup-agent-model 的客户端模型配置流程独立保留。

本轮 Windows 原生已完成本地合成回归、正式页面桌面与手机视口检查，以及 Codex 0.166.0 / WorkBuddy 5.9.3 的原生安装、Skill 发现和代表性运行验收。macOS、真实鉴权与线上业务待验；Claude Code 兼容入口保留，本轮未实测。

已发布的 **3.0.1**：默认设置采用“设为默认 (推荐)”，选择一次后直接设置并展示实际内容。Windows 默认设置测试 15 项通过、1 项既有 symlink 用例跳过，凭证回归 26 项及分发检查 7 项通过。Codex 已验证两个业务 Plugin 的开发流程与隔离规则文件；Setup 完整原生流程仍待验，Claude Code 因额度 403、WorkBuddy 因输入与发送受阻。本版 macOS 待验，本次按用户明确指令发布，以上待验项继续保留。以下历史验收记录仅覆盖各自所列版本。

通过对话管理业务服务密钥和客户端模型接入。`setup-api-key` 检查、配置、更换或清除 **AIhub 创作与文档服务**、**tikin 社交媒体数据服务**的本机接口密钥。你可以在目标 Plugin 的本机配置页面直接填写；配置仍由原业务 Plugin 读取，Setup 不建立集中 Key 库。

当前 Plugin 版本为 **4.0.0**（setup-api-key 4.0.0、setup-agent-model 2.2.1），包含两个独立入口：

| Skill | 用途 |
| --- | --- |
| `setup-aihub:setup-api-key` | AIhub Studio / tikin Social 的业务密钥，沿用本页流程 |
| [setup-aihub:setup-agent-model](skills/setup-agent-model/README.md) | Hermes、WorkBuddy、ChatGPT 桌面客户端、Codex CLI、Claude 桌面客户端、Claude Code CLI 的原生模型与 Key 配置 |

模型配置需要完整 2.1.0 或更新版本的 Plugin，Secret Book 原生写入需要 2.7.0 或更新版本。六类文件写入与公开契约已实现，客户端验证与技术限制见对应 README；不能用下面 setup-api-key 的历史验收代替新 Skill 的六宿主验收。旧的 setup-aihub Skill 调用名不再提供。

以下历史验证、配置位置和使用流程针对 **setup-api-key**。模型配置的六宿主、两系统、原生字段与恢复步骤见上方独立入口。

业务配置页面由 AIhub Studio / Tikin Social 自带，Setup 负责选择已安装服务、保存任务关联及配置后的检查。业务 Plugin 没有新页面入口时先更新完整 Plugin；本机文件编辑、清除和仅本轮使用仍可用。

本版支持 **AIhub Studio 1.x / 2.x（最低 1.2.0）** 和 **Tikin Social 2.x / 3.x（最低 2.0.0）** 的配置检查；网页需要业务 Plugin 自带新入口。Tikin 3.x 使用 Setup 4.0.0 或更新版本。旧版提示先更新完整 Plugin，随后继续原配置任务；不会降级或迁移既有密钥。

3.0.0 在 macOS 通过 93 项回归，另 10 项 Windows 或可选独立 Secret Book 集成跳过。Codex 0.166.0 已用原生安装的 Setup 3.0.0 与 Tikin 2.0.1 验证缺 Key、网页预览保存、原加载器复查与跨轮恢复，保留默认沙箱并使用单次命令审批。Claude Code 2.1.318 因账号额度不足（403）未完成调用；WorkBuddy 5.9.3 已通过原生安装、加载、缺 Key 检查与网页启动，但预览时被宿主安全删除机制阻断。本次发布保留这两项待验；Windows 原生、真实飞书授权及线上业务也待验，不能视为三宿主全流程通过。

## 让 Agent 帮你安装

将下面一段复制到你使用的 Claude Code、Codex 或 WorkBuddy，让 Agent 核对来源和版本后安装。Tikin 3.x 配置续接需要 setup-api-key / Setup Plugin 4.0.0；setup-agent-model 需要 2.1.0 或更新版本。若仍加载旧版，先让 Agent 核对并更新实际安装，再在新会话继续。

> 请安装完整的 setup-aihub Plugin：优先从 https://github.com/cookaihq/aihub-marketplace.git 的 setup-aihub/ 获取，网络故障时同版本回退到 https://cnb.cool/zhidateam/tannt/aihub-marketplace.git。保留已有设置，并按当前宿主的原生 Plugin 入口安装，告诉我实际来源、版本以及是否能发现和调用本次所需的 setup-api-key 或 setup-agent-model。

Claude Code 使用实际技能选择器，可能显示完整的 `/setup-aihub:setup-api-key`；Codex 输入 `$` 选择对应入口，完整 Plugin 入口为 `setup-aihub:setup-api-key`；WorkBuddy 在当前会话点名或选择 `setup-api-key`，具体控件以客户端为准。都不要求额外参数。WorkBuddy 安装完整套件使用“专家·技能·连接器 → 技能 → 套件 → 市场行右侧圆形＋”；需要手工操作时，Agent 会按[同包指引](skills/setup-api-key/references/hosts.md#workbuddy-原生套件)展示截图与步骤。

运行需要 uv 0.8 或更新版本，由 Agent 协助检查；首次准备 Python 环境可能联网下载。AIhub 本机配置检查还需要 Node.js 18+；tikin 使用自己的 Python 环境。配置检查不要求先安装媒体工具，不会调用图片、视频或数据业务来测试密钥。

目标业务 Plugin 尚未安装时会显示实际状态，你选择后可以安装并继续，或返回菜单。市场已添加、文件已下载、Plugin 已安装、当前会话已加载是不同状态。

## 第一次使用

在已加载 Skill 的会话中只输入：

> setup-api-key

没有已有目标时，将看到以下三项；安装状态按当前宿主实际检查填写：

- **aihub-studio｜AIhub 创作与文档服务【实际状态】**
- **tikin-social｜tikin 社交媒体数据服务【实际状态】**
- **先检查当前已安装服务的配置**

回复“第一个”即可继续，也可以直接说“我想用 AIhub 画图，密钥怎么填？”或“刚才的 tikin 密钥换了，帮我修复”。选择检查时只报告本机来源和缺项，不修改文件、不向服务发送鉴权请求。没有具体业务 Skill 的总览仅检查共享配置，不能证明所有 Skill 的专用配置都可用。

## 配置密钥

> 请用 setup-api-key 打开 AIhub 的配置中心。我会在网页填写 Key；保存后检查原业务能否读取，再继续原任务。

Agent 给出可点击链接，在运行 Agent 的同一电脑打开。字段按用途分组，必要/全部配置共享同一草稿；页面底部固定保存栏显示变更摘要，点击一次保存。首次新增默认个人全局，明确项目保存使用 `.env.local`；已有值写回真实生效来源，环境变量在原注入处修复。

页面不展示服务地址。AIhub Key 下可打开 [AIhub 控制台](https://api.aihubmax.com/console)，Tikin Key 下可打开 [Tikin 控制台](https://console.tikin.net)，也可联系团队负责人分配。完整 Key 不进入聊天、argv 或进度记录。

网页闲置 60 分钟退出，也可结束配置立即停止。**📱 手机或其他设备访问需要 FRP / Tailscale，实际配置状态由 Agent 核对。** 保存后回到 Agent 回复“继续”；服务重启不会保留未保存的手填值。文件冲突时先重新载入并核对，保留其他操作的修改。

明确选择文件编辑或环境没有浏览器时，Agent 提供完整本机路径及字段供本人填写。仅本轮使用时请说明不允许落盘。业务配置已退出 Secret Book 方式，既有本机配置继续可读；客户端模型配置的独立流程见上方 `setup-agent-model`。

## 配置完成后的默认设置

密钥配置或修复成功后，回复还会包含 **Plugin默认设置检查**。Agent 检查开发者指定且在当前宿主已安装的全部 Plugin 或 Skill，当前清单包含 AIhub 和 tikin；即使这次只配置 AIhub，也会核对已安装的 tikin。结果分别说明已配置全局默认规则、仅当前项目、尚未设置、存在冲突或检查未完成。规则文件已写入与当前会话已加载分别说明。

尚未设置且提醒开启时，Agent 会列出本次待设置的项目，并告诉你可以回复选项文字或数字：

1. **设为默认 (推荐)**：例如，“以后让 ChatGPT/Codex 生成图片、视频、配音或音乐时，默认使用 AIhub，不用每次再说‘用 AIhub’。”tikin 会说明查询抖音、小红书等平台数据的用途。你明确指定其他工具时，按你的要求执行。
2. **本次跳过**：暂时不设置，以后仍可提醒。
3. **不再提醒**：以后不再询问是否将这些项目设为默认。

名称根据当前 Agent 显示为 ChatGPT/Codex、Claude Code 或 WorkBuddy。选择 1 后直接写入当前 Agent 的全局规则，不再二次确认；完成后展示实际写入的完整内容、文件位置和影响范围。共享文件的影响会在选择前说明。选择 3 只关闭对应项目、当前 Agent 配置的提醒，保留已有规则。中断后可以继续原任务，Agent 会核对原菜单及规则是否变化。

未安装的项目不会因检查而自动安装；检查失败或本次跳过不影响已经保存的密钥。关闭全局配置读取时跳过此项。纯查询密钥、清除密钥或已有配置正常时直接返回业务，不自动开始默认设置。

## 配置位置与生效顺序

首次共享默认位置如下，已有项目或 Skill 专用范围继续沿用。个人文件夹属于**实际运行业务程序的用户**，不是 Plugin 安装目录。

| 环境 | AIhub Studio | tikin Social |
| --- | --- | --- |
| macOS / Linux | `~/.config/aihub-studio/.env` | `~/.config/tikin-social/.env` |
| Windows 原生 | `%USERPROFILE%\.config\aihub-studio\.env` | `%USERPROFILE%\.config\tikin-social\.env` |
| WSL | Linux 用户的 `~/.config/aihub-studio/.env` | Linux 用户的 `~/.config/tikin-social/.env` |

例如 Windows 用户文件夹为 `C:\Users\你的用户名`，WSL 通常为 `/home/你的Linux用户名`。Windows 原生与 WSL 不自动互读；本版本机配置已在 Windows 原生验证；本轮 macOS 待验，Linux 和 WSL 未验。脚本通过不等于三宿主会话通过。

普通字段各自取首个非空值。以真实调用方 `aihub-image` 为例，按以下顺序读取：

1. 运行进程的环境变量。
2. 任务工作文件夹的 `.env.aihub-image` → `.env.local` → `.env`。
3. `~/.config/aihub-studio/aihub-image/.env.local` → 同目录 `.env`。
4. `~/.config/aihub-studio/.env.aihub-image` → Plugin 根 `.env.local` → 根 `.env`。
5. 普通 Skill 的 `~/.config/aihub-image/.env`。

tikin 例如 `tikin-douyin` 使用相同次序，将 Plugin 名换为 `tikin-social`、Skill 名换为 `tikin-douyin`。其他 Skill 按自己的真实名字对应。默认共用 Plugin 根 `.env`，确有差异才建专用文件；空子目录、缺项、空值不阻断回退。现有文件不可读会报错，不静默选别的账号。

“工作文件夹”是本次业务任务实际运行的位置。程序不向父目录找配置，也不扫描兄弟 Skill、旧产品别名或备份文件。没有业务 Skill 时只读工作文件夹 `.env.local/.env` 和 Plugin 共享 `.env.local/.env`；普通 Skill 回退不参与。全局层默认自动读取，可以说“这次关闭全局配置读取”，同时跳过 Plugin 与普通 Skill 的全局文件。

修复写回实际来源；环境变量错误先找注入位置，不另写低层全局文件。首次选择项目保存使用工作文件夹 `.env.local`，写前检查未跟踪且被 Git 忽略。原子替换的临时文件也要被忽略，规则不足时 Agent 会说明需补哪项，不自动改索引。既有普通 Skill 配置无需迁移即可回退；需要迁移时可说“列出原文件和目标文件，经我确认后整理”，不会自动合并不同账号。

同一操作系统用户、同一运行环境的多个宿主和 Plugin 版本可能共用这些文件。修改共享 Key 会影响它们。安装作用域与凭证作用域分别说明；读取配置不代表获准保存或迁移。

## 清除、继续与结果

> 请清除我指定文件中的 tikin 密钥，先告诉我清除后会不会读到别处的值，其他字段保留。

Agent 先只读预览，再按你确认的文件和字段清除；同一字段的旧重复赋值也会删除。低优先级值可能重新生效，清除本机文件不等于平台撤销 Key。取消只关闭尚未执行的步骤，不自动回滚已保存配置。

中断后说“继续刚才的配置”，或“请用 setup-api-key 继续任务〈编号〉”。编号来自上次回复。Setup 的进度文件位于 `~/.config/setup-aihub/tasks/`，Windows 为 `%USERPROFILE%\.config\setup-aihub\tasks\`，仅保存路径、选择、校验值和结果元数据，不保存业务密钥。可要求清理已结束任务的进度；卸载 Setup 不会清除业务凭证。

结果分别说明**已保存、当前生效、本机读取、线上鉴权、宿主加载和业务调用**。本版尚无已核实免费的线上鉴权入口，默认不执行；配置成功不代表业务已完成。已提交或状态未知的原任务先核对结果，修复 Key 不会自动重发。

## 遇到问题时

| 现象 | 可以对 Agent 说 |
| --- | --- |
| 改了密钥仍无效 | “只检查这个项目和真实业务 Skill 的来源，看看是否被覆盖。” |
| 提示文件变了或结果不明 | “先核对现在的文件和来源，再决定下一步，保留别人的修改。” |
| Tikin 提示版本不兼容或网页无法打开 | “核对业务 Plugin 是否包含自带配置中心，以及 Setup 的实际版本；保留配置和原任务，更新支持的完整组合后继续。” |
| WorkBuddy 找不到入口 | “请展示同包截图，核对当前页面和版本，指导我走原生套件入口。” |
| 想配置客户端的 AIhub 模型 | “请用 setup-agent-model，先列出现有原生配置。” |

更新完整 Plugin 时使用当前宿主的 Plugin 管理入口；可说“检查 Setup AIHub 的版本，告诉我可以取得哪个版本，等我决定后再更新”。WorkBuddy 使用原生套件界面；未核实的更新 API 不会调用。本 Plugin 不使用独立 Skill 的自动检查更新开关。更新或卸载不搬移业务配置。

[更新记录](CHANGELOG.md) · [MIT 许可](LICENSE)
