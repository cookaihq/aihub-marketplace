# 原生字段、来源与加载核验

字段证据基于 2026-10-25 的公开文档/实际安装代码；helper 的文件回读不是客户端运行证明。先确认当前版本与下述配置形态一致；遇到新格式先补证据再适配。

| 目标 | 文件与 Key 字段 | 覆盖、默认与加载 |
| --- | --- | --- |
| Hermes | 当前 Windows 默认 `%LOCALAPPDATA%/hermes/config.yaml`，macOS 默认 `~/.hermes/config.yaml`；HERMES_HOME 优先，原生根目录受 HERMES_DATA_DIR_SUFFIX 影响。profile 位于所属根的 `profiles/<name>/config.yaml`；`providers.<name>.api_key` / 已有 `model.api_key` | named provider 使用 `api/transport/models/default_model`；`model.provider=custom:<name>` 和 `model.default` 激活。key_cmd/key_env、匹配的 credential pool 等优先时需原生修复；确认当前 profile/local backend，再查当前提供者和模型 |
| WorkBuddy | Windows `%USERPROFILE%/.workbuddy/models.json`；macOS `~/.workbuddy/models.json`，数组中选定记录的 `apiKey` | 按数组下标+摘要选择，保留重复 ID 和其他字段；当前证据为 Chat Completions。新模型能力未知时不沿用旧模型 supportsToolCall/supportsImages，原生默认行为需核对。重开模型选择器核对自定义条目，默认由用户另选 |
| ChatGPT 桌面 | `CODEX_HOME` 或 `~/.codex/` 的 `config.toml` / 当前实际 profile 文件；`model_providers.<id>.experimental_bearer_token` | 原生 Responses；与 Codex 可能共享配置，保存前显示共享影响。在桌面实际本地工作入口核对 profile/provider/model 与 config 来源，不能用 CLI 检查代替 |
| Codex CLI | 同上；当前 0.164.0 的 `-p` 使用 `<name>.config.toml`，不是旧 `[profiles.<name>]` 表 | provider 的 env_key/auth/header/登录机制、基础与项目层可能覆盖。明确默认才写顶层 model/model_provider。`config/read` 的来源与新会话当前模型可作加载证据；CLI `-c/--model` 等启动覆盖须另查 |
| Claude Code CLI | `CLAUDE_CONFIG_DIR/settings.json` 或 `~/.claude/settings.json`、项目 `.claude/settings.json`、`.claude/settings.local.json`；`env.ANTHROPIC_AUTH_TOKEN` 保存真实 Key | env.ANTHROPIC_BASE_URL；SONNET/OPUS/FABLE 原生别名映射，多选不改管理用 availableModels。默认单独写 model。更高项目层、managed settings、apiKeyHelper/其他认证机制和启动变量需核对；原生 `/model`、状态与新会话验收 |
| Claude 桌面 | Windows `%LOCALAPPDATA%/Claude-3p/configLibrary/<id>.json`；macOS `~/Library/Application Support/Claude-3p/configLibrary/<id>.json`；`inferenceGatewayApiKey` | gateway/static/bearer；inferenceModels 第一项是默认。HKLM policy 整层遮蔽 HKCU；非 app 行为 managed 字段、bootstrap/helper 优先。本工具只识别已有顶层推理配置，其他包装形态拒绝；`_meta.json` 不改，原生配置库选择/应用后核对 diagnostics 的有效来源 |

实际工作文件夹是业务会话执行目录，影响项目层与任务恢复；它不是 Plugin 安装目录。当前适配器检查所列本机层，不解析客户端所有 CLI 参数、远端 managed policy 或所有祖先项目信任条件；报告这些待核对项，不能将静态目标路径命名为“已生效”。

Claude 桌面 [配置格式](https://claude.com/docs/third-party/claude-desktop/configuration-format.md)、[配置参考](https://claude.com/docs/third-party/claude-desktop/configuration.md)、[网关](https://claude.com/docs/third-party/claude-desktop/gateway.md)描述了本地库、策略优先级和 gateway 字段。原生库包装/选择文件尚缺实机证据，因此创建/激活仍须原生界面。Claude-Max 当前仅限 Claude Code CLI；可解析原生字段不说明该服务分组可在桌面使用。

Claude Code [设置](https://code.claude.com/docs/en/settings.md)与[模型配置](https://code.claude.com/docs/en/model-config.md)；Codex [配置参考](https://developers.openai.com/codex/config-reference)；Hermes [Provider 集成](https://hermes-agent.nousresearch.com/docs/integrations/providers/)。WorkBuddy 当前格式来自已安装 Windows 客户端，macOS 的同一路径形态尚待实际客户端核对。

API endpoint 由协议固定为 AIhub：Chat Completions/Responses 使用 `https://api.aihubmax.com/v1`，Anthropic 使用 `https://api.aihubmax.com`。目录不能提供任意 endpoint。GPT 目录目前只有 Chat Completions 公开登记；Responses 未证实，不推断失败，也不自动试调用。真实请求以所选 Key 的分组、权限和额度为准。
