# Setup AIHub

通过对话管理业务服务密钥和客户端模型接入。`setup-api-key` 检查、配置、更换或清除 **AIhub 创作与文档服务**、**tikin 社交媒体数据服务**的本机接口密钥。你可以在本机网页直接填写，也可以在同一页选择 Secret Book；配置仍由原业务 Plugin 读取，Setup 不建立集中 Key 库。

当前版本为 **2.3.0**，包含两个独立入口：

| Skill | 用途 |
| --- | --- |
| `setup-aihub:setup-api-key` | AIhub Studio / tikin Social 的业务密钥，沿用本页流程 |
| [setup-aihub:setup-agent-model](skills/setup-agent-model/README.md) | Hermes、WorkBuddy、ChatGPT 桌面客户端、Codex CLI、Claude 桌面客户端、Claude Code CLI 的原生模型与 Key 配置 |

模型配置需要完整 2.1.0 或更新版本的 Plugin，Secret Book 原生写入需要 2.7.0 或更新版本。六类文件写入与公开契约已实现，客户端验证与技术限制见对应 README；不能用下面 setup-api-key 的历史验收代替新 Skill 的六宿主验收。旧的 setup-aihub Skill 调用名不再提供。

以下历史验证、配置位置和使用流程针对 **setup-api-key**。模型配置的六宿主、两系统、原生字段与恢复步骤见上方独立入口。

2.3.0 将业务凭证配置接入本机网页。AIhub / tikin 执行业务发现缺 Key 时也进入同一页面，保存后复查并接续原任务。手填值直接从浏览器写入已确认的配置位置；Secret Book 的只读连接、身份和字段映射使用随包固定依赖，不需要另装独立 Skill。原有文件编辑、清除、仅本轮使用及旧任务恢复继续可用。

本版在 macOS 通过 92 项回归，另 10 项 Windows 或可选独立 Secret Book 集成跳过；合成网页手填、Secret Book 选记录、确认保存与原加载器复查通过。Codex 0.166.0 已通过原生测试 Plugin 安装、业务缺 Key 触发、网页保存与跨轮恢复，保留默认沙箱并使用单次命令审批。Claude Code 2.1.317 加载完整 Plugin 后被账号额度不足（403）阻断；WorkBuddy 原生窗口因辅助功能权限不可操作，本版会话流程未验证。Windows 原生、真实飞书授权及线上业务待验收；历史结果不自动代表本版通过。

## 让 Agent 帮你安装

将下面一段复制到你使用的 Claude Code、Codex 或 WorkBuddy，让 Agent 核对来源和版本后安装。网页配置需要 setup-api-key / Setup Plugin 2.3.0 或更新版本，setup-agent-model 需要 2.1.0 或更新版本；若仍加载旧版，先让 Agent 核对并更新实际安装。

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

> 请用 setup-api-key 打开本机配置页，让我选择手动填写或 Secret Book，并在页面预览保存范围和实际文件位置。不要让我把 Key 发到聊天；保存后检查原业务是否已能读取，再继续原任务。

Agent 给出可点击的配置链接。请在运行 Agent 的同一电脑浏览器打开，直接输入 API Key，选择个人全局或当前项目，点击“预览保存”核对实际位置，再确认保存。已有错误写回实际生效的来源；配置被环境变量覆盖时，Agent 会协助修复注入位置。网页空闲 60 分钟退出，结束配置也可立即停止服务。

AIhub 只需 `AIHUB_API_KEY`。tikin 需要 `TIKIN_API_KEY`；关联地址默认 `https://console.tikin.net`，可以在页面同时配置其他 HTTPS 服务地址，保存前核对 Key 对应该服务。没有 Key 时请从业务服务的官方入口或管理员取得。

选择 Secret Book 后，在同一页选择本人账号或已有连接、核对身份、连接已有多维表格，再选择可见记录和字段。页面不回显 Key。需要登录时点击飞书官方授权链接，完成后回来检查。首次缺少 Lark CLI 时会准备本机依赖；没有应用配置则由 Agent 协助本人配置。缺列、缺 ID 或无权限需表管理员处理，页面不创建或修改远端表。

连接身份不匹配时，可以恢复原账号，或选择“修复所选连接的身份”并预览改绑。项目/环境中的来源由 Agent 在原处修复，不另建低层配置掩盖。连接和业务 Key 分别确认保存。

完成后回到 Agent 回复“继续”。刷新会保留本轮选择；服务重启会清除未保存的手填值和旧确认，需要重新填写、预览。上次保存结果不明时先“核对实际结果”，不会重放。明确选择本机编辑器或当前环境没有可用浏览器时，Agent 也可提供完整文件位置供本人填写。

后续业务直接读取本机，不必每次运行 Setup 或查 Secret Book。表中轮换不会自动同步。仅本轮使用、不允许落盘时直接说明，Agent 按实际可用的安全输入方式处理。

## 配置完成后的默认设置

密钥配置或修复成功后，回复还会包含 **Plugin默认设置检查**。Agent 检查开发者指定且在当前宿主已安装的全部 Plugin 或 Skill，当前清单包含 AIhub 和 tikin；即使这次只配置 AIhub，也会核对已安装的 tikin。结果分别说明已配置全局默认规则、仅当前项目、尚未设置、存在冲突或检查未完成。规则文件已写入与当前会话已加载分别说明。

尚未设置且提醒开启时，Agent 会列出本次待设置的项目，并告诉你可以回复选项文字或数字：

1. **设为默认**：例如，“以后让 ChatGPT/Codex 生成图片、视频、配音或音乐时，默认使用 AIhub，不用每次再说‘用 AIhub’。”tikin 会说明查询抖音、小红书等平台数据的用途。你明确指定其他工具时，按你的要求执行。
2. **本次跳过**：暂时不设置，以后仍可提醒。
3. **不再提醒**：以后不再询问是否将这些项目设为默认。

名称根据当前 Agent 显示为 ChatGPT/Codex、Claude Code 或 WorkBuddy。选择 1 后，先展示完整规则、目标文件和影响范围，经你确认才写入当前 Agent 的全局规则；共享文件的影响会提前说明。选择 3 只关闭对应项目、当前 Agent 配置的提醒，保留已有规则。中断后可以继续原任务，Agent 会核对原菜单及规则是否变化。

未安装的项目不会因检查而自动安装；检查失败或本次跳过不影响已经保存的密钥。关闭全局配置读取时跳过此项。纯查询密钥、清除密钥或已有配置正常时直接返回业务，不自动开始默认设置。

## 配置位置与生效顺序

首次共享默认位置如下，已有项目或 Skill 专用范围继续沿用。个人文件夹属于**实际运行业务程序的用户**，不是 Plugin 安装目录。

| 环境 | AIhub Studio | tikin Social |
| --- | --- | --- |
| macOS / Linux | `~/.config/aihub-studio/.env` | `~/.config/tikin-social/.env` |
| Windows 原生 | `%USERPROFILE%\.config\aihub-studio\.env` | `%USERPROFILE%\.config\tikin-social\.env` |
| WSL | Linux 用户的 `~/.config/aihub-studio/.env` | Linux 用户的 `~/.config/tikin-social/.env` |

例如 Windows 用户文件夹为 `C:\Users\你的用户名`，WSL 通常为 `/home/你的Linux用户名`。Windows 原生与 WSL 不自动互读；本版已在 macOS 测试本机配置；Windows 原生、Linux 和 WSL 待验。脚本通过不等于三宿主会话通过。

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
| 网页入口不存在 | “核对当前加载的 setup-api-key 与完整 Setup Plugin 是否为 2.3.0 或更新版本，告诉我实际安装来源。” |
| Secret Book 读取失败 | “保留原任务，检查 Lark CLI、实际身份、原连接与可见范围，再回到页面重试。” |
| WorkBuddy 找不到入口 | “请展示同包截图，核对当前页面和版本，指导我走原生套件入口。” |
| 想配置客户端的 AIhub 模型 | “请用 setup-agent-model，先列出现有原生配置。” |

更新完整 Plugin 时使用当前宿主的 Plugin 管理入口；可说“检查 Setup AIHub 的版本，告诉我可以取得哪个版本，等我决定后再更新”。WorkBuddy 使用原生套件界面；未核实的更新 API 不会调用。本 Plugin 不使用独立 Skill 的自动检查更新开关。更新或卸载不搬移业务配置。

[更新记录](CHANGELOG.md) · [MIT 许可](LICENSE)
