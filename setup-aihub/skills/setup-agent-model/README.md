# Setup Agent Model

通过对话管理 **Hermes、WorkBuddy、ChatGPT 桌面客户端、Codex CLI、Claude 桌面客户端和 Claude Code CLI** 的 AIhub 模型配置。先看已有配置，再选择修改哪项或新建；模型从目录选，Key 可在本机填写或从 Secret Book 取用。默认模型由你单独决定。

本目录属于 **Setup AIHub 2.1.0 开发候选**，需要安装完整 Plugin；远端尚未发布时，安装请求不能取得此版本。目标系统为 Windows 原生和 macOS；Linux/WSL 暂不在本 Skill 范围内。

当前已实现六类原生文件的无值检查、保存和恢复，以及 Secret Book 公开契约。Windows 合成测试通过不等于六客户端实机通过；macOS 尚未验证。Claude 桌面首次配置仍需其原生界面创建条目，未识别的库格式会停止写入。ChatGPT/Codex 需要的 GPT Responses 路由尚无精确型号证据，默认不会盲写；Claude-Max 组只用于 Claude Code CLI。

| Windows 原生客户端 | 2.1.0 候选的实际验证范围 |
| --- | --- |
| Codex CLI 0.164.0 | 隔离配置下严格解析原生 Key/模型、完整 Plugin 安装及新 Skill 发现通过；会话配置闭环、默认沙箱执行与真实模型调用待验 |
| Claude Code CLI 2.1.293 | 本机合成 API 下实际加载新 Skill、读取原生 Key/模型并执行本机检查脚本通过；自然语言选择、保存确认/恢复及真实服务调用待验 |
| Hermes 0.22.2（本机源码 d923a5eb487a） | 原生 Plugin Doctor/validate 通过；本机合成 API 下实际加载新 Skill、读取原生 Key/模型并执行本机检查脚本通过；保存确认/恢复及真实服务调用待验 |
| WorkBuddy 5.8.3 / ChatGPT 桌面 26.1016.8622.0 | 本次桌面自动化连接不可用，界面发现/调用/加载尚未验证 |
| Claude 桌面 | 未定位到可运行安装，本地 Code 和原生配置库尚待实机验证 |

## 让 Agent 帮你安装

```text
请安装完整 setup-aihub Plugin，使用含 setup-agent-model 的 2.1.0 或更新版本。来源优先 https://github.com/cookaihq/aihub-marketplace.git 的 setup-aihub/，网络故障时同版本回退 https://cnb.cool/zhidateam/tannt/aihub-marketplace.git。先核对版本是否可取得，再按当前宿主的原生入口安装，保留已有设置；告诉我实际来源、版本，以及是否能在本机发现和调用 setup-agent-model。
```

Claude Code/Codex/WorkBuddy 的完整 Plugin 安装见[共享说明](../../README.md#让-agent-帮你安装)。Hermes 使用同包的原生 Plugin 入口；ChatGPT 使用实际本地工作入口；Claude 桌面使用 Code 的 Local 会话。Agent 会按[六宿主指引](references/hosts.md)核对本机访问能力，不能用云端或另一客户端替代验证。

调用时，Claude Code 可在 `/` 选择器中选 `setup-aihub:setup-agent-model`，Codex 在 `$` 中选择；其他客户端使用其实际技能选择入口，Hermes 显式加载同名 Plugin Skill。依赖为 uv 0.8+ 和随包锁定的 Python 3.13 环境，Agent 会协助准备；首次准备可能下载依赖。只有选择 Secret Book 才需要它及已登录本人身份的 lark-cli。

## 第一次使用

> setup-agent-model

你会先看到六个目标。选定后，Agent 列出现有配置及 Key 是否存在，不显示值；然后选择已有项或新建，从模型目录选一款或多款，并单独决定默认模型。原生入口只支持一个模型时会说明。

保存前会展示准确文件、字段、替换项、影响范围及共享影响。本机手填会打开隐藏输入框，粘贴后保存；完整 Key 无需发到聊天。也可选择 Secret Book，由它确认记录和映射，再保存到同一原生文件。已有来源选择会沿用。

预期结果是准确路径、保存结果、来源检查，以及客户端加载/真实调用是否已验证。只做配置不会发送模型请求。若需要实际试用，可提出具体请求，Agent 会说明额度消耗；配置成功本身不等于模型请求成功。

## 常用请求

- “用 setup-agent-model 检查我的 WorkBuddy 配置，只告诉我来源和缺项。”
- “给 Hermes 新建一个 AIhub Provider，从目录选两个模型，先保留当前默认。”
- “更换 Claude Code 的 Key，从 Secret Book 取，先列出会修改的文件和字段。”
- “只换刚才选中的模型，保留 Key，让我单独决定是否设为默认。”
- “继续 setup-agent-model 任务〈编号〉，先核对现状。”

普通流程不需要寻找模型 ID；只有主动要求自定义型号时才输入 ID，并核对其协议和能力。当前目录含 GPT-6.1 Sol、GPT-6 Astra、Claude Sonnet 5.5、Opus 5.5、Fable 5.1、Gemini 4 Argon 和 Gemini 3.8 Flash；目录列出不表示每个客户端或每把 Key 均可使用。

## 保存位置与作用范围

**不预选保存范围。** 根据你选择的客户端、配置项和实际来源确定目标；修复写回原来源，保留其他配置。Key 直接写入客户端原生字段，不建立集中 Key 库。下表的个人目录是运行该客户端的同一个本机用户。

| 客户端 | Windows 原生 / macOS 的位置 |
| --- | --- |
| Hermes | Windows `%LOCALAPPDATA%/hermes/config.yaml`，macOS `~/.hermes/config.yaml` 或所选 profile；HERMES_HOME 优先，HERMES_DATA_DIR_SUFFIX 影响原生根目录 |
| WorkBuddy | 用户 `.workbuddy/models.json` 中所选条目；实际 CODEBUDDY_CONFIG_DIR / WORKBUDDY_CONFIG_DIR 可改变目录 |
| ChatGPT 桌面、Codex CLI | 用户 `.codex/config.toml` 或所选独立 profile 文件；CODEX_HOME 可改变位置。两者可能共享文件，修改前会提醒 |
| Claude Code CLI | 用户 `.claude/settings.json`，或所选工作文件夹的 `.claude/settings.json/settings.local.json`；CLAUDE_CONFIG_DIR 可改变用户目录 |
| Claude 桌面 | Windows `%LOCALAPPDATA%/Claude-3p/configLibrary/`；macOS `~/Library/Application Support/Claude-3p/configLibrary/` 中的原生配置条目 |

Windows 用户目录通常是 `%USERPROFILE%`，macOS 为 `~`。“工作文件夹”是当前项目实际运行位置，影响项目设置和恢复。Windows 与 WSL、云端、远程主机之间不自动互读。

客户端按自己的顺序读取配置：Codex/ChatGPT 的基础与 profile/项目信任层，Claude Code 的用户→项目→本机项目及 managed 设置，Hermes 的 profile 与认证池，Claude 桌面的应用配置与管理策略。Agent 会检查已知覆盖并核对实际客户端来源；存在覆盖时不会另写低层文件假称修好。这里不使用业务 Plugin 的 `.env` 分层，也没有自动启用个人全局凭证层。

Secret Book 需要 **2.7.0+**；它只读已有表，写本机前确认。后续客户端直接读自己的文件，表中轮换不会自动同步。两者进度仅存非敏感元数据；Setup 进度在用户 `.config/setup-aihub/agent-model/tasks/`。取消不回滚已经保存的配置，卸载 Plugin 不删除客户端的 Key。

## 遇到问题时

| 现象 | 可以对 Agent 说 |
| --- | --- |
| 保存后仍用旧模型 | “检查实际 profile、启动参数和高优先级来源，再核对新会话加载。” |
| 提示来源或文件变了 | “保留现有修改，重新检查后展示新的保存摘要。” |
| 写入结果不明 | “先恢复任务并回读，不要重复保存。” |
| 目录检查失败 | “使用最后有效目录，说明这次更新检查结果。” |
| 桌面入口不能执行脚本 | “记录当前版本和本机访问限制，保留任务，不把 CLI 结果当作桌面通过。” |

模型目录每次选择前自动检查，发现有效新版会下载到用户缓存；不会修改已保存的模型。Windows 缓存在 `%LOCALAPPDATA%/setup-aihub/setup-agent-model/catalog/`，macOS 在 `~/Library/Caches/setup-aihub/setup-agent-model/catalog/`。网络失败可用缓存或包内目录。

Plugin 程序更新仍使用当前宿主的原生更新入口，可说“检查 Setup AIHub 可取得的版本，等我决定后更新完整 Plugin”。更新公开模型数据与更新程序是两件独立的事。
