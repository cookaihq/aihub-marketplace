# Setup AIHub

通过对话检查、配置、更换或清除 **AIhub 创作与文档服务**、**tikin 社交媒体数据服务**的本机接口密钥。你可以自行在本机填写，也可以选择 Secret Book；配置仍由原业务 Plugin 读取，Setup 不建立集中 Key 库。

当前版本为 **1.0.0**，支持本机手填、清除和恢复；Secret Book 已接入 2.5.1 的共享配置与实际业务 Skill 流程，两个服务均已通过 2.5.2 的 Windows 原生真实表配置联调。

Windows 原生的客户端验证范围如下；这里只说明凭证配置能力，不代表媒体生成或社交数据业务已完成验证。

| 宿主 | 已验证范围 |
| --- | --- |
| Codex 0.160.1 | 完整 Plugin 安装、发现和触发；默认沙箱下两个服务的业务缺项转交、手填、恢复、最小回退及配置正常时跳过 Setup |
| WorkBuddy 5.6.2 | 原生套件安装、发现和触发；两个服务的缺项转交、手填与最小回退，AIhub 配置正常时跳过 Setup；临时安装清理及原版恢复 |
| Claude Code 2.1.143 | 完整 Plugin 安装、发现，以及 AIhub / tikin 自然请求触发；本机配置闭环未实测 |

## 让 Agent 帮你安装

将下面一段复制到你使用的 Claude Code、Codex 或 WorkBuddy，让 Agent 核对来源和版本后安装。

> 请安装完整的 setup-aihub Plugin：优先从 https://github.com/cookaihq/aihub-marketplace.git 的 setup-aihub/ 获取，网络故障时同版本回退到 https://cnb.cool/zhidateam/tannt/aihub-marketplace.git。保留已有设置，并按当前宿主的原生 Plugin 入口安装，告诉我实际来源、版本以及是否能发现和调用 setup-aihub。

Claude Code 使用实际技能选择器，可能显示完整的 `/setup-aihub:setup-aihub`；Codex 输入 `$` 选择对应入口，完整 Plugin 在 CLI 0.160.1 中显示 `setup-aihub:setup-aihub`；WorkBuddy 在当前会话点名或选择 `setup-aihub`，具体控件以客户端为准。都不要求额外参数。WorkBuddy 安装完整套件使用“专家·技能·连接器 → 技能 → 套件 → 市场行右侧圆形＋”；需要手工操作时，Agent 会按[同包指引](skills/setup-aihub/references/hosts.md#workbuddy-原生套件)展示截图与步骤。

运行需要 uv 0.8 或更新版本，由 Agent 协助检查；首次准备 Python 环境可能联网下载。AIhub 本机配置检查还需要 Node.js 18+；tikin 使用自己的 Python 环境。配置检查不要求先安装媒体工具，不会调用图片、视频或数据业务来测试密钥。

目标业务 Plugin 尚未安装时会显示实际状态，你选择后可以安装并继续，或返回菜单。市场已添加、文件已下载、Plugin 已安装、当前会话已加载是不同状态。

## 第一次使用

在已加载 Skill 的会话中只输入：

> setup-aihub

没有已有目标时，将看到以下三项；安装状态按当前宿主实际检查填写：

- **aihub-studio｜AIhub 创作与文档服务【实际状态】**
- **tikin-social｜tikin 社交媒体数据服务【实际状态】**
- **先检查当前已安装服务的配置**

回复“第一个”即可继续，也可以直接说“我想用 AIhub 画图，密钥怎么填？”或“刚才的 tikin 密钥换了，帮我修复”。选择检查时只报告本机来源和缺项，不修改文件、不向服务发送鉴权请求。没有具体业务 Skill 的总览仅检查共享配置，不能证明所有 Skill 的专用配置都可用。

## 配置密钥

> 请帮我配置 AIhub 的密钥，沿用已有选择，或让我选择自行填写本机文件 / 从 Secret Book 选择配置并保存。首次共享使用个人全局文件，已有问题修复实际来源；告诉我位置和生效结果，隐藏密钥，只做本机检查。

AIhub 首配仅需 `AIHUB_API_KEY`。tikin 需要 `TIKIN_API_KEY`；关联的 `TIKIN_BASE_URL` 可省略，默认 `https://console.tikin.net`，有自定义地址时须核对 Key 属于同一服务。没有 Key 时让 Agent 指向业务服务已核实的官方入口，或向服务管理员取得；首版不代办开户或创建远端 Key。

选择手填后，Agent 列出完整文件位置、字段、范围与替换项，经你授权后准备安全文件。你在本机编辑器填写，保存后说“继续”；无需把完整 Key 发到聊天。选择 Secret Book 后，由它核对本人身份、已有表、记录、映射与保存目标，Setup 再检查业务是否实际读到。Secret Book 未安装时可以选“安装并继续／自行填写本机文件／暂不配置”；没有连接时使用本人身份连接已有表，缺列、缺 ID 或无权限不会自动建表或切管理员。

只做 Plugin 共享配置时，Secret Book 需要 2.5.1 或更新版本；已有具体业务 Skill 的路径仍兼容 2.5.0。Agent 会核对实际使用的安装版本；版本不兼容时可安装兼容版本、手填或暂缓，不会替你假定一个业务 Skill。AIhub 与 tikin 均已通过 Windows 原生真实表取用、临时保存、恢复和本机生效检查；线上鉴权、业务请求与三宿主完整验收不在该结果范围内。

后续业务直接读取本机，不必每次运行 Setup 或查 Secret Book。表中轮换不会自动同步。仅本轮使用、不允许落盘时直接说明，Agent 按实际可用的安全输入方式处理。

已知限制：Secret Book 2.5.2 可能把可自动刷新的飞书登录态误报为未登录，2.5.4 源码仍有相关判断。遇到时可说“先核对我的飞书身份和令牌是否可刷新，保留当前配置任务”，也可改为自行填写本机文件；不要仅因该提示更换业务密钥。

## 配置位置与生效顺序

首次共享默认位置如下，已有项目或 Skill 专用范围继续沿用。个人文件夹属于**实际运行业务程序的用户**，不是 Plugin 安装目录。

| 环境 | AIhub Studio | tikin Social |
| --- | --- | --- |
| macOS / Linux | `~/.config/aihub-studio/.env` | `~/.config/tikin-social/.env` |
| Windows 原生 | `%USERPROFILE%\.config\aihub-studio\.env` | `%USERPROFILE%\.config\tikin-social\.env` |
| WSL | Linux 用户的 `~/.config/aihub-studio/.env` | Linux 用户的 `~/.config/tikin-social/.env` |

例如 Windows 用户文件夹为 `C:\Users\你的用户名`，WSL 通常为 `/home/你的Linux用户名`。Windows 原生与 WSL 不自动互读；macOS/Linux、WSL 的本版运行尚未验证。Windows 合成配置测试不等于三宿主会话验收。

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

中断后说“继续刚才的配置”，或“请用 setup-aihub 继续任务〈编号〉”。编号来自上次回复。Setup 的进度文件位于 `~/.config/setup-aihub/tasks/`，Windows 为 `%USERPROFILE%\.config\setup-aihub\tasks\`，仅保存路径、选择、校验值和结果元数据，不保存业务密钥。可要求清理已结束任务的进度；卸载 Setup 不会清除业务凭证。

结果分别说明**已保存、当前生效、本机读取、线上鉴权、宿主加载和业务调用**。本版尚无已核实免费的线上鉴权入口，默认不执行；配置成功不代表业务已完成。已提交或状态未知的原任务先核对结果，修复 Key 不会自动重发。

## 遇到问题时

| 现象 | 可以对 Agent 说 |
| --- | --- |
| 改了密钥仍无效 | “只检查这个项目和真实业务 Skill 的来源，看看是否被覆盖。” |
| 提示文件变了或结果不明 | “先核对现在的文件和来源，再决定下一步，保留别人的修改。” |
| Secret Book 不可用 | “保留原配置任务，说明缺少的安装或角色能力，让我选择手填或暂缓。” |
| WorkBuddy 找不到入口 | “请展示同包截图，核对当前页面和版本，指导我走原生套件入口。” |
| 想配置宿主模型或登录 Key | “说明这是否属于 Setup 当前的业务 Plugin 凭证范围。” |

更新完整 Plugin 时使用当前宿主的 Plugin 管理入口；可说“检查 Setup AIHub 的版本，告诉我可以取得哪个版本，等我决定后再更新”。WorkBuddy 使用原生套件界面；未核实的更新 API 不会调用。本 Plugin 不使用独立 Skill 的自动检查更新开关。更新或卸载不搬移业务配置。

[更新记录](CHANGELOG.md) · [MIT 许可](LICENSE)
