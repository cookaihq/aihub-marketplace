# 六执行宿主的入口

先分别记录宿主、配置目标、版本、操作系统、安装实体、运行环境、cwd 与 home。只有本机工具能访问目标真实文件时才能保存；云端、容器、SSH、WSL 和桌面 VM 不自动代表本机。六宿主使用同一份 Skill/代码和完整 Plugin，不单独复制 `SKILL.md`。

| 执行宿主 | 安装、发现、调用与环境 |
| --- | --- |
| Claude Code CLI | 按[既有原生 Plugin 说明](../../setup-api-key/references/hosts.md)安装完整 setup-aihub；实际选择器中的 `/setup-aihub:setup-agent-model`。本机 shell 与 home 单独检查 |
| Codex CLI | 同包原生 Plugin 入口，`$` 选择 `setup-aihub:setup-agent-model`。保留默认沙箱验收；app-server 的 skills/list 只证明发现，不等于调用通过 |
| WorkBuddy | 原生“专家·技能·连接器 → 技能 → 套件”，按[同包说明和截图](../../setup-api-key/references/hosts.md#workbuddy-原生套件)；选择或点名 setup-agent-model。使用 GUI 的实际工具，不另启内嵌 CLI 或未公开 RPC |
| ChatGPT 桌面客户端 | 当前本地工作入口的 Plugin 管理及 Skill 选择器；保留独立 `chatgpt` 身份。应用版本和本地 app-server 版本都要记录。云端 hosted skills 不能代替本机加载；不根据共享 `.codex` 路径报告 CLI 结果 |
| Claude 桌面客户端 | 官方 [Code 本地会话](https://code.claude.com/docs/en/desktop.md)：选择 Local 环境/本机目录，使用 Plugins 与 `/` 或 `+ → Slash commands`。Chat/Cowork 上传技能或云端同步不证明本机脚本访问。原生 Windows/macOS 的本版闭环待实机验证 |
| Hermes | 完整目录含 `plugin.yaml`、`__init__.py`、所有 skills 与运行时锁文件；原生 Plugin 安装/启用后 `skill_view("setup-aihub:setup-agent-model")`。显式加载是本次稳定入口；当前安装源码还将 Plugin skills 列入 skills_list/索引，随包文档与之有差异，实际版本的隐式发现单独验收。使用实际 local backend；Windows local backend 的 Git Bash 不等于 WSL |

Hermes 原生入口来源：[Plugin 开发文档](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/)。本 Plugin 位于市场子目录，不能把整个市场仓当作根目录 Plugin 直接传给只接受仓根的安装器。取得确切版本的完整 `setup-aihub/` 后，按原生目录布局放入实际 Hermes home 的 `plugins/setup-aihub/`，通过当前 `hermes plugins enable` 入口启用并核对列表；更新同样替换完整 Plugin 并核对来源/版本，不臆造子目录安装参数。`register(ctx)` 只注册共享 Skill 路径，不运行配置脚本。可用 `plugins doctor <目录>` 检查注册，仍须实际会话验证加载、调用和文件访问。

如果某版本的桌面入口不可用，保留进度并报告具体缺项；不切换到另一客户端假称完成。Claude 桌面当前安装/原生配置库格式仍需实机证据；首次配置需先在其原生界面创建条目。没有可靠 `_meta.json` schema 时不伪造配置库选择。

完整 Plugin 来源：<https://github.com/cookaihq/aihub-marketplace.git> 的 `setup-aihub/`；网络故障时同版本回退 <https://cnb.cool/zhidateam/tannt/aihub-marketplace.git>。核对实际安装版本及当前会话加载来源。支持范围见 [README](../README.md)。

程序更新通过对应宿主原生 Plugin 入口；没有已核实更新接口时由原生界面完成。不会运行独立 Skill 自更新脚本。Hermes 更新整个原生 Plugin；ChatGPT 和 Claude 桌面分别检查，不由 CLI 推断。安装、发现、调用、实际来源、模型请求分别验收。
