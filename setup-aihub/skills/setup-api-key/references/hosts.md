# 宿主安装与加载（给 Agent）

适用于 Setup 自身、`aihub-studio` 与 `tikin-social` 的完整 Plugin。三宿主共用一份 Skill/代码，manifest 分别适配。安装远端前核对所需版本是否可取得，不能用旧发布版替代新增契约。

先从当前会话和实际原生管理入口取得：宿主、来源、版本、作用域、实体位置、安装/启用状态、本会话发现/调用状态。未知项留空并说明原因。工具不在当前会话、查询失败、只添加了市场、只有开发目录或另一个宿主已安装，均不是“未安装”的证据。helper 只验证传入业务产物，不是安装探测器。

市场来源为 <https://github.com/cookaihq/aihub-marketplace.git>，网络故障时同版本回退 <https://cnb.cool/zhidateam/tannt/aihub-marketplace.git>。权限、鉴权、缺失仓库或版本错误不触发回退。复用正确来源的已有市场与安装范围，只处理选中 Plugin。选服务不等于安装授权；已有明确要求安装则直接沿用。安装结果不明先查询实际状态，避免重复登记或盲目重装。

| 宿主 | 操作与入口 |
| --- | --- |
| Claude Code | 原生 Plugin 管理：市场添加后安装完整 `<plugin>@aihub-marketplace`，保留实际 `user/project/local/managed` 范围。读取当前工具/CLI schema 再用。技能选择器显示的命名空间为准，例如 `/setup-aihub:setup-api-key`；不要求用户提供业务参数 |
| Codex | 原生 Plugin 管理添加市场和安装完整 Plugin，核对实际目录/版本；输入 `$` 选择实际入口。完整 Plugin 的入口为 `setup-aihub:setup-api-key`，独立 Skill 挂载显示短名称；不要求用户另填参数。CLI/IDE 可按实际版本查看 `/skills`。不把开发目录或当前执行 Codex 当作加载证据；真实最小闭环保留默认沙箱 |
| WorkBuddy | 使用当前实例的原生“专家·技能·连接器 → 技能 → 套件”。Windows 5.6.2 的推荐市场 `workbuddy_marketplace_skill` 只装 BuiltinMarket 单 Skill，不能用于自定义 Git 市场的完整 Plugin。按下方步骤与截图指导；当前会话有已核实适用的原生工具/UI 能力时才代办 |

安装完先核对完整组件，再分别验证启用、Skill 发现与调用。已安装但未启用或未加载时，能独立执行真实配置检查就继续；需要业务调用时引导实际刷新/新会话，不要求重装。来源冲突或旧版不兼容时确认实际加载对象，提供兼容版本选择，不强制更新。

## WorkBuddy 原生套件

1. 打开“专家·技能·连接器”，点击顶部“技能”，再点“套件”（位于 SkillHub 右侧）。
2. 核对并复用已有 `aihub-marketplace`。没有时点**市场名称一行最右侧圆形“＋”**，此后弹窗才叫“添加市场”。填上述来源，不是卡片的加号，也不是右上角“添加技能”。
3. 选择本次已获授权的 `setup-aihub`、`aihub-studio` 或 `tikin-social` 卡片，安装完整套件。若所需版本尚未发布或界面空列表，报告实际状态，不冒称安装成功。
4. 从同一管理入口核对安装/启用结果；必要时新会话查看入口 Skill。保存 Setup 任务编号与选择，继续配置。本机检查通过不证明业务调用成功。

![WorkBuddy 添加市场入口：技能 → 套件 → 市场名称右侧圆形＋](assets/workbuddy-add-marketplace.png)

图来自 Windows WorkBuddy 5.6.2 的既有实机入口截图，红色 1/2/3 依次定位上述三个控件；图中的“此市场暂无套件”不是本 Plugin 的安装证据。图随 Setup 分发，不要求先安装 AIhub Studio。

**需要用户手工找入口时，回复须同时展示截图和文字路径。** 先确认同包 `assets/workbuddy-add-marketplace.png` 可读，支持本地 Markdown 图片时用已解析的实际绝对路径；有 `present_files` 则读当前 schema 后按宿主展示规则提供。没有内嵌能力时给可打开的本机图片链接并明确未能内嵌，不只说“见截图”、不编造公网图片链接。

不另起 `codebuddy`、`cbc` 或 WorkBuddy 内嵌 CLI，包含 help/list；不调用未公开 RPC，不手写注册表，不用上传一份 `SKILL.md` 冒充完整 Plugin。查询和更新也使用同一原生入口。不能确认控件/版本时先核对实际界面，保留进度。

## 更新与范围

更新由实际宿主的完整 Plugin 管理入口负责，保留业务配置。Claude Code、Codex、WorkBuddy 的更新能力分别核对，不能从一个宿主推断另两个；没有公开 API 就说明需要原生界面操作。Setup 不带独立 Skill 更新检查器，也不读取 `AUTO_UPDATE_CHECK`。更新后的版本与当前已加载版本分别报告。

Windows 原生、WSL 和远程进程各按自身用户目录与 cwd 检查。Orca/执行 Agent、原生 manifest 校验、本机脚本测试、宿主加载与业务请求分别记录，彼此不能替代。
