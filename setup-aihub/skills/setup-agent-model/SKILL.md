---
name: setup-agent-model
metadata:
  version: "2.1.1"
description: v2.1.1｜检查、配置、更换或修复 Hermes、WorkBuddy、ChatGPT 桌面客户端、Codex CLI、Claude 桌面客户端和 Claude Code CLI 的 AIhub 模型与原生 Key 配置。可只说名称开始，支持已有配置选择、模型目录、Secret Book 和中断恢复。AIhub 创作服务或 tikin 的业务密钥使用 setup-api-key。
compatibility: Windows native and macOS; uv >= 0.8, Python 3.13; complete setup-aihub Plugin and local filesystem execution required. Six host entry points and verification limits are in references/hosts.md.
---

# Setup Agent Model

将既有 AIhub Key 写入用户选定客户端的原生配置字段。用户只说名称即可开始；中文为默认，英文请求沿用其语言。六个执行宿主与六个配置目标分别记录，保留产品名称。

## 进入任务

1. 沿用已选目标、操作、配置项、Key 来源和具体授权。无目标时列出 **Hermes、WorkBuddy、ChatGPT 桌面客户端、Codex CLI、Claude 桌面客户端、Claude Code CLI**，让用户选；执行宿主可以与配置目标不同。
2. 先读[宿主入口](references/hosts.md)，核对真实宿主、版本、Windows 原生/macOS、完整 Plugin 实体和本机目录可达性。只读检查不创建任务，不联网调用模型。不把云端/VM 的 home 当本机，不用另一客户端替代实际入口。
3. 恢复时读本 Skill，并用[helper](references/helper.md) `status`；无编号用 `list`，多个任务由用户选择。任务绑定实际宿主、cwd、系统及安装实体；换环境后重新检查，旧确认不跨环境消费。

## 检查与选择

读[客户端字段与验证](references/clients.md)，执行 helper `inspect`。先展示已有文件和配置项、当前文件中的选择、Key 是否存在及覆盖来源；不读取或展示原文件全文。用户选择一项或新建，使用该客户端真实的 Provider、profile、设置范围或模型配置概念。保留同名/相同模型 ID 的不同记录，不自动选保存范围。

仅检查到此返回。首次配置、更换或修复则：

1. **每次模型选择前**运行 `catalog`。显示模型名称和简短用途，结合客户端协议及服务分组解释可用项。刷新失败使用报告中的有效目录并说明；本次目录不含客户端名单。普通用户从目录选，只有主动要求才开启自定义 ID；协议证据由 Agent 查证，不让用户猜。
2. 当前目录的 Claude-Max 组仅用于 Claude Code CLI。GPT 的公开目录尚未证明 Responses，ChatGPT/Codex 所需路由须另有确切证据才能计划；模型名称不构成证据。能力为 `null` 时报告未知，不写成支持。
3. 按原生能力多选；默认模型另问，未指定不切换。Codex/ChatGPT 单个 profile 只能持久化一个 `model`：改变该字段须明确选它作为该 profile 的模型。WorkBuddy 的会话默认从原生模型选择器操作。新 Provider 可以先保存为未启用项。
4. 无值报告发现覆盖时先定位真实来源。修复该来源或明确变更原生机制；helper 拦截的认证池、managed policy、未核实配置库格式等，不通过手写文件绕过。

## Key 与保存

沿用 Key 来源；未定时提供 **在本机填写／从 Secret Book 选择配置并保存**。只换模型且保留当前 Key 时使用 `preserve`。请求文件只含非敏感选择，Key 不进聊天、argv、日志、进度或备份。

- **本机填写**：helper `plan --source manual` 固定目标、模型和变更。展示完整路径/字段、替换项、默认选择、共享影响与覆盖结果。用户明确同意本次摘要后 `apply`；默认打开本机隐藏输入框，用户粘贴 Key，值仅经私有管道进入写入器。无法显示时保留任务并说明，可让用户在自己的交互终端运行同包入口；不要求发 Key 到聊天。取消输入不写配置。
- **Secret Book**：先读[公开衔接](references/secret-book.md)。Setup `plan --source secret-book → handoff`，让 Secret Book 管理实际记录、映射、一次确认和保存；Setup 不重复确认/写入，也不查看其私有任务文件。收到公开 receipt 后 `accept-secret-book` 独立回读。
- **保留 Key**：`plan --source preserve`，确认文件和模型变更后 `apply`，不查表、不提示输入 Key。

原子写入前重验文件、来源、模型、范围和确认。Git 内的 Secret 文件及临时文件必须未跟踪且实际忽略；其他字段与格式注释尽量保留。输入或来源变化重新规划受影响部分；`applying/result_unknown` 先 `recheck`，不能重放保存。取消只结束未执行步骤，不自动回滚已保存值。

## 加载与结果

分别报告 **文件已保存、实际来源核对、目标客户端加载、真实模型调用**。helper 只证明文件回读，始终不冒称客户端已加载。按客户端引用的实际入口刷新或开启新会话，检查所选配置/模型和读取来源；当前会话可能仍持有旧 Key。

配置流程不请求模型。用户另有具体测试请求时，说明会按该请求消耗额度，再沿用已有请求授权执行；没有额外的付费确认流程。网络、权限、分组和余额错误不能直接当作 Key 文本错误，修复不自动重发原请求。

本 Plugin 的程序更新通过实际宿主管理入口进行；[模型目录](references/catalog.md)只自动刷新公开数据。注册、创建 Key、充值不属于本 Skill。
