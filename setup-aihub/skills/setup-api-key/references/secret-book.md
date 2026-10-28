# Secret Book 衔接

只在用户选择 Secret Book 时读取。Setup 默认以**凭证使用者**处理：“本次从已有令牌表为所选 Plugin 配置密钥。”这句话不增加角色确认。远端表只读；使用本人飞书身份连接已有表，不自动建表、补列、补记录 ID 或切管理员。用户明确要求自建或维护时，交 Secret Book 对应角色处理后返回。

## 安装与兼容

先核对当前宿主的实际安装、启用、发现及调用。缺少某个工具或市场搜索无结果不是未安装的证据。

| 实际状态 | 处理 |
| --- | --- |
| 确认未安装 | 展示“安装并继续／自行填写本机文件／暂不配置”；沿用已有安装授权，未授权则待用户选择 |
| 已装未加载/未启用 | 按实际宿主恢复入口，保留目标，不重复安装 |
| 安装状态未知 | 核对原生入口及官方来源，报告具体未知原因 |
| 已确认版本低于本次要求 | 说明当前版本和最低可用版本，依次提供“升级到最新版／升级到最低可用版本（具体版本）／手动配置”，见下方流程 |
| 文件不完整、版本无法确认或运行依赖缺失 | 说明实际路径、缺失文件或依赖与检查范围，协助核对/修复，也可手填或暂缓；不把未知状态说成版本过低 |
| 缺本人连接/无权限 | 进入 Secret Book 使用者连接/修复，不重新安装或另建表 |

官方来源是独立 Skill 仓库 **https://github.com/cookaihq/secret-book**；仅网络故障时回退 **https://cnb.cool/zhidateam/tannt/secret-book.git**，保持同一版本/提交。它不是 Plugin Marketplace。获取完整 Skill，包括脚本、锁文件与引用；按当前宿主已核实的独立 Skill 入口导入。WorkBuddy 推荐市场的单 Skill 搜索不代替官方源导入，也不能据此承诺能添加任意 Git 源。只有实际有适用工具时才代办，否则给用户当前界面的具体步骤。下载、发现、实际调用分别检查；需要新会话时保留 Setup 任务编号。

**共享配置最低版本为 2.5.1；有真实业务 Skill 的既有路径最低为 2.5.0。** 基线联调版本为官方 `v2.5.1`，提交 `ee9c7ec0899ab63174b2b28010fa279376c2fa47`；已补测 `v2.5.2` 和采用新版版本字段的 `v2.5.4`（提交 `bf47274850e617aebd68d456f1257e1fc3a0c20c`）。Windows 原生公开 CLI 的合成飞书联调通过；2.5.2 的 AIhub 与 tikin 真实表配置均已通过，覆盖临时保存、公开恢复、业务加载器复查和测试副本清理。各宿主的验证范围见 [Plugin 使用说明](../../../README.md)；线上鉴权和业务请求未执行。2.3.0 的保存和 2.4.0 的 Windows 支持不足以替代新角色能力。

使用 `handoff --availability available --secret-book-root "<当前宿主选用的完整 Skill 实体>"`；已经发现不兼容时使用 `--availability incompatible`，同样传实际实体路径进行核对。helper 先只读核对 `pyproject.toml` 与 Skill 名称/稳定版本是否一致，再比较最低版本，最后检查该版本所需文件；旧版尚未提供的新流程文件不会遮蔽明确的版本过低原因。兼容标准 `metadata.version` 和旧顶层 `version`，两者同时出现时须同号；缺失、非法、重复或冲突的版本不会回退放行，也不能据此猜测当前版本。失败不创建已委托状态，原任务与位置选择保留。返回的 `dependency` 是实际实体路径/版本，测试提交另列；公开元数据检查不证明宿主已加载或运行依赖可用。Agent 仍需读取所选产物的公开 Skill/引用/CLI 帮助核对角色与恢复能力。

没有真实业务 Skill 时，2.5.1 接受 `skill: null`，只处理业务报告的共享层；保留 caller、cwd 和全局开关，不借用其他 Skill 名称。共享模式不使用 `--skill-only`。2.5.0 的共享报告在委托前被版本检查拒绝，不能通过虚构 caller 绕过。

## 版本过低：升级或手动配置

仅在 helper 返回 `secret_book_version_incompatible` 时，使用 `dependency.version` 与 `compatibility.minimum_verified_release` 给出明确提示。例如共享配置检查发现 2.0.1：

> 本机已安装的 Secret Book 版本过低：当前为 v2.0.1，本次配置至少需要 v2.5.1。升级后才能继续从 Secret Book 配置。请选择：
>
> 1. 升级到最新版
> 2. 升级到最低可用版本（v2.5.1）
> 3. 手动配置

实际回复替换为本次检查值；存在多个副本时指出当前宿主选中的完整路径。展示菜单前只读查询可选升级目标，在选项 1 后补充查到的最新稳定版本，并附本次来源、目标版本和安装位置；选择后固定已核对的 tag/SHA 执行。查询失败时标注“最新版待确认”，仍展示手动配置，不猜版本或阻塞用户选 3。不用“未安装”“安装兼容版本”代替升级提示，也不把测试基线版本当作最新版。版本满足要求但文件缺失时说明 `missing_artifacts`；没有可信版本信息时先说明无法确认版本。

- **选 1**：查询上述官方仓库的最新稳定发布，核对版本不低于本次最低值，取得对应 tag 和 commit SHA；不固定写死“最新版”为某个历史测试版本，不用开发分支或预发布代替稳定版。
- **选 2**：使用 `minimum_verified_release` 对应的确切稳定 tag 和 commit SHA（共享配置为 `v2.5.1`，真实 caller 为 `v2.5.0`），不顺带升级到最新版；目标不可取得时说明原因，保留该选择，不擅自改装其他版本。
- **升级共用流程**：按当前宿主已经核实的独立 Skill 安装/更新入口处理当前安装，展示目标版本、来源、tag/SHA 和实际安装位置。先只读解析可选目标，用户对已明确目标的选择就是本次升级授权，不再询问“是否允许升级”；目标或作用范围改变才补充确认。查询失败时报告网络/权限等实际原因，不声称已是最新。保留用户配置、原 Setup 任务和字段/目标选择；升级后回读实际安装版本与完整性，并核对当前会话加载，随后用原任务再次 `handoff`。需要新会话时给出具体刷新步骤和恢复任务编号。
- **宿主及安装形态**：Claude Code、Codex 使用各自实际独立 Skill 入口；WorkBuddy 使用当前客户端已核实的导入/更新入口，不臆造 API 或另起内嵌 CLI。Git 安装沿用其公开更新工具的能力限制；现有 `--pull` 只前进到 main，不能用它实现“升级到最低可用版本”。需安装固定发布时使用可校验 commit 的完整产物安装方式，不强制切换、重置或覆盖已有开发工作树。复制安装固定确认过的 SHA，完整获取、校验后替换，失败保留原安装；缺少精确版本安装能力时如实说明并给当前宿主的可执行步骤。网络查询有超时，瞬时失败有限重试。
- **选 3**：将原 Setup 任务切换为 `source --source manual`，沿用原服务、真实 caller、工作文件夹和已选目标/字段；未指定目标时按业务既定位置与真实来源确定。按 `plan → apply` 准备文件，已有具体写入授权沿用。随后展示 `result.manual_input` 的完整路径、每个 `KEY=` 的值含义及保存步骤；不再要求升级 Secret Book，也不查令牌表。例如 `AIHUB_API_KEY=<你的 AIhub API Key>`：去掉示例行的 `#`，将尖括号及其中说明替换为实际 Key；用户在本机填写并保存，回复“继续”后由原业务加载器复查。

升级与手动配置均不重新提交原业务请求。用户自行提出暂缓或取消时保留既有取消流程，不额外加入本菜单。

## 交接与返回

由 helper `handoff` 提供 consumer/版本、真实 caller、cwd、全局开关、业务凭证声明路径、原生无值检查报告、操作与已有字段/位置选择。兼容基线是 `credentials.json`、`secret-book.config-inspection/v1`、`configure/configure-status`。helper 的版本元数据表示测试依据，不表示当前宿主已安装或已加载该版本。

在真实业务 cwd 中使用 Secret Book 自有运行时：

```text
uv run --locked --no-dev --project "<Secret Book 实体>" python "<Secret Book 实体>/scripts/secret_book.py" <公开子命令及参数>
```

1. 读其 `references/roles.md`、`references/consumer-setup.md`。先 `workflow status --agent <实际宿主>`，只恢复目标匹配的任务；已有公开引用时加 `--id <引用>`。新任务用 `workflow start --role consumer --basis inferred --goal <不含密钥的目标> --agent <实际宿主>`。取得 `task.id` 后用 Setup 的 `handoff-result --status pending --reference <task.id>` 保存公开引用。
2. 后续 Secret Book 业务命令都加 `--workflow <task.id> --workflow-agent <实际宿主>`。规则只读检查用 `agent-rule --agent <实际宿主>`；其结果不授权安装或修改 Agent 规则。无本人连接时，按其公开流程使用 `init-connect --url <已有表> --lark-profile <本人profile>`；展示身份后，经用户确认再带 `--confirm-identity <最新任务token>`。本机连接保存沿用返回的公开命令与既有授权，不自行拼接私有状态。
3. 按公开 `list/get` 流程核对可见候选、字段与关联组。沿用 Secret Book 自身的配置选择：项目/进程来源，或显式 `--use-global-config` / `--config-name`。这个开关控制 Secret Book 的表连接，不更改业务报告中的 `global_enabled`。把 handoff 的 `inspection` 原样保存成无值 JSON 文件，不能改 caller、layers、revision 或覆盖来源。
4. 使用 `configure --requirements <declaration_path> --inspection <无值报告文件> --agent <实际宿主> --id <选定记录ID> --key <选定业务字段>`，加任务参数与刚才相同的表连接选项。映射用 `--map TARGET=SOURCE`；新增项目范围用 `--scope project`，新增已选定的 Skill 专用范围用 `--skill-only`；修复由真实来源决定，不能用 scope 迁移。预览返回的目标/替换项必须符合 Setup 已保留的选择；无法表达该位置时停止，不静默换目标。
5. `confirmation_required` 时展示 Secret Book 的完整 `review`，由它负责本次唯一写入确认。续轮通过 `configure-status --requirements <声明>` 读摘要，并从 `workflow status --id <task.id> --agent <宿主>` 取**任务最新 token**；不用底层配置记录的 token。用户已确认且输入未变时，在原 configure 参数上追加 `--confirm <任务token>`。输入变化先重新预览。
6. `written` 后只通过业务加载器复查；用 `workflow finish --id <task.id> --agent <宿主>` 关闭已完成任务，再向 Setup 返回 `completed` 与同一引用。用户取消时按 Secret Book 公开流程关闭待办（`--outcome cancelled`），再向 Setup 返回 `cancelled`。取消不会撤销已有文件写入。

按该版本公开流程处理本人身份、已有表连接、候选记录、真实 key 映射、目标与替换项确认；唯一候选首次也确认。无表链接请用户向管理员取得，或选择手填/暂缓。缺列、缺 ID、不可见/无权限分别交适当角色；读取成功不证明写权限。

一次操作只由 Secret Book 写业务文件；Setup 不复制它的确认状态机、不再写一次、不为相同摘要重复确认。只保存公开的不透明恢复引用及必要结果元数据，不访问 `consumer-configurations.json`、`workflows.json` 等私有结构。无法获得公开恢复引用时由 Secret Book 的公开状态入口继续，Setup 保留自身任务，不能臆造引用。

实际完成/取消/待用户/失败/结果待核对后，向 helper `handoff-result` 传入相应元数据。`verification_required`、`write_incomplete` 或写入结果不明均返回 `unknown`，先依 Secret Book 公开恢复流程核对已保存文件与剩余目标，不重放 configure；只有确认原写入方无剩余待办时才能返回 `failed` 或更换来源。完成仍要由业务加载器独立复查，来源覆盖就如实报告。配置保存、实际生效、线上鉴权、宿主加载和业务结果分开；失败不授权重发业务，表轮换不自动同步本机。

已有委托尚待操作或结果不明时，由 Secret Book 公开入口核对或取消，取得明确结果后再更换来源；Setup 的本机核对不能证明另一个写入方已经停止，也不能授权重复保存。

已发布代码的合成 CLI 联调覆盖真实 caller 与共享空 caller 的本机契约；本人真实表配置另有 Windows 原生 CLI 证据，均不能代替宿主验收。按实际宿主和验证层级报告结果；Claude Code 本机配置闭环未实测，不把已有触发证据写成该闭环通过。
