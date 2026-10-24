# AIhub 凭证缺项、修复与 Setup 衔接

所有六个业务 Skill 共用本流程。Windows 原生环境通过随包 PowerShell 入口运行真实 caller 的无网络检查，入口自动检查 Node 版本和设置模块加载选项，保留业务 cwd：

```powershell
& "<Plugin实体>/scripts/aihub.ps1" config-check --skill <实际业务Skill> --credentials-only
```

macOS / Linux 使用同一业务程序：

```text
node "<Plugin实体>/scripts/aihub.mjs" config-check --skill <实际业务Skill> --credentials-only
```

保留实际业务 cwd 和 `--no-global-config`。只管理 [credentials.json](credentials.json) 的 `AIHUB_API_KEY`；首配不增加地址字段。没有 caller 的主动共享检查使用 `--plugin-only`，与 `--skill` 互斥；不要借用 `aihub-image`。退出 `3` 是缺项/不可读；执行失败不是缺 Key。凭证检查不依赖媒体工具，`doctor` 不是配置前提。

配置已可读时继续正常任务。首次配置、实际缺项或有依据需要修复时，先报告字段与实际来源；402、403、429、网络问题分别核对余额、权限、限流、连接，不直接要求换 Key。401 也要核对 Key 所属账号与最终服务组合。

## Setup 可用时

核对当前宿主已发现的 `setup-aihub:setup-api-key` 来自正确完整 Plugin 且兼容，再进入其凭证流程。交付 consumer `aihub-studio`、实际版本/实体、caller、真实 cwd、全局开关、声明与无值报告、已有来源/范围选择，以及原业务记录引用和提交状态。只保留无密钥元数据。Setup 的配置检查不再次转回本流程，避免递归。

实际读取 Setup 的 Skill 并执行流程；宿主没有跨 Skill 调用能力时按可用的文件读取/技能入口衔接，不能只声称“已转交”。一个配置操作只有一个当前负责人；Setup/Secret Book 完成后，AIhub 用真实加载器复查，不重复写文件或确认同一摘要。

Setup 尚未发布、未安装、未加载或不可调用时，保留原任务，提供安装完整 Plugin 的请求或下面的最小回退。不能因为未安装的 Setup 没有 description，就声称用户中文请求必然能触发它。

> 请从 https://github.com/cookaihq/aihub-marketplace.git 安装完整的 setup-aihub Plugin；网络故障时使用同版本 https://cnb.cool/zhidateam/tannt/aihub-marketplace.git，安装后用 setup-api-key 继续刚才的 AIhub 凭证配置。

先核对 Setup AIHub 2.0.0 或更新的兼容版本可取得，不以旧条目代替新功能。WorkBuddy 沿用[原生套件指引与截图](workbuddy-install.md)，只将安装对象换成获授权的完整 `setup-aihub`，不另起 CLI 或手写注册表。

## Setup 不可用时的最小回退

沿用选择，或提供 **自行填写本机文件／从 Secret Book 选择配置并保存**。Secret Book 保留英文名；“继续用 AIhub”只选择服务，不表示选择手填。

手填直接给完整路径与字段，用户本机编辑，不查表、不要求安装 Secret Book。首次共享默认为 `~/.config/aihub-studio/.env`；修复写回真实来源，环境变量先查注入位置，已有作用域沿用。保存前确认具体目标、替换项与影响；Git 中目标须未跟踪且已忽略，保护权限与无关内容，不要求用户回贴 Key。

Secret Book 分支读取它的当前公开 Skill 流程，以凭证使用者处理；身份、已有表、记录、映射、目标确认及实际保存归它负责。只读配置报告按原样交给兼容的 `configure/configure-status`，不得改成投影报告或拼造 caller。所需角色/只读连接能力未核实时说明不兼容，提供手填/暂缓；2.4.0 的 Windows 支持不证明新角色能力。使用者不补列/ID、不自动建表。确认未安装时提供安装并继续/手填/暂缓；独立来源 https://github.com/cookaihq/secret-book，网络故障同版本回退 https://cnb.cool/zhidateam/tannt/secret-book.git，不当作 Plugin Marketplace。

Secret Book 的共享空 caller 需要已发布 2.5.1 或更新版本，真实 caller 仍兼容 2.5.0；保持原始报告，不虚构或更换 caller。按实际安装包的 `references/roles.md` 创建或恢复 `consumer` 任务，业务命令带公开 workflow 参数，确认使用 `workflow status` 的最新任务 token。2.5.1、2.5.2、2.5.4 已有配置契约联调，两个服务已通过 2.5.2 本人真实表到临时项目的保存、恢复和本机复查；客户端加载、线上鉴权与业务完成仍分别报告。

保存后只用 `config-check --credentials-only` 完成本机凭证复查；业务工具检查按实际任务需要另做。线上鉴权仅用户要求且已核实接口非计费时执行，不能因代码有 `models` 就假定免费，不生成媒体来验 Key。来源、保存、本机读取、线上鉴权和真实业务分别报告。

原任务未提交且原授权/内容仍有效才继续；已提交或状态未知先查原结果。修复不授权重发。正常业务继续读本机，表轮换不自动同步；仅本轮使用才走安全进程注入，不擅自保存。

## 删除投影

`config-check --skill <实际Skill> --credentials-only --delete-from "<已知来源文件>" --delete-fields AIHUB_API_KEY` 返回 `config-deletion-preview/v1` 的 `before/after`，磁盘不变。共享检查可换 `--plugin-only`。只能清除经用户选定的本机字段，不将投影作为真实写后报告；字段可能回退到低层或仍被高层覆盖。
