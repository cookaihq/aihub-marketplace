# 本机 helper（给 Agent）

将 `SkillDir` 解析到完整 Plugin 内本 Skill 实体。保留调用者实际工作目录。Windows PowerShell 与 macOS shell 均使用以下命令形态；先真实执行 `uv --version`，需要 uv >= 0.8。

```text
uv run --frozen --project <SkillDir> python <SkillDir>/scripts/setup_agent_model.py <action> ...
```

helper 自检解释器和真实 import，缺失/损坏的自有环境按锁文件修复。系统 uv 缺失时说明安装入口，不改用系统 Python。Windows uv 访问被拒时先区分可执行文件、缓存与环境权限，保留宿主安全策略。

## 只读检查

```text
catalog
inspect --client <client> --cwd <实际目录>
inspect --client <client> --config <已选原生文件> --cwd <实际目录>
list --host <实际宿主> --cwd <实际目录>
status --task <id> --host <实际宿主> --cwd <实际目录>
```

`client/host` 各自取 `hermes/workbuddy/chatgpt/codex/claude-desktop/claude-code`。`inspect.files[].entries` 只含无值投影，`selector` 和 `identity` 用于精确选择。`file_selection` 是文件内容，不等于运行中选择；`effective_source`、`blocks/notices` 和 `verification` 必须一起解释。既有文件不可读/格式不支持时不能新建另一路径遮盖。

`catalog` 每次检查远端；`--offline` 仅用于已知离线、合成测试或用户要求的离线任务，正常选择不默认跳过检查。

## 计划请求

将非敏感选择写为 UTF-8 JSON。以下示例新建未启用的 Hermes Provider；名称必须来自用户选择。

```json
{
  "client": "hermes",
  "config": "<实际 HERMES_HOME>/config.yaml",
  "selector": "chosen-name",
  "new": true,
  "name": "用户选择的名称",
  "models": ["gpt-6.1-sol"],
  "protocol": "openai-chat-completions",
  "key_mode": "replace"
}
```

编辑已有项设 `new:false`，从刚取得的 `inspect` 复制 `selector/identity`。`default_model` 可省略；明确设置时必须属于 `models`。`key_group` 可记录已知实际分组，不从 Key 内容猜。保留原 Key 使用 `key_mode:preserve` 和来源 `preserve`。

| 目标 | selector / 原生限制 |
| --- | --- |
| Hermes | named provider 名；已有 `model` 配置用 `$model`。named provider 可多选；bare model 仅一个，改变其当前模型/提供者须明确 default |
| WorkBuddy | 已有记录的数组下标及 identity；新建使用未占用的描述性 selector。新增可多选，修改一条仅一个模型，保留重复记录；默认在原生选择器切换 |
| ChatGPT / Codex | Provider ID。profile 是单独的 `*.config.toml` 文件；每份文件只一个模型。所选 ID 与文件当前 model 不同时需明确 `default_model`，不能把未写入 ID 说成已配置 |
| Claude Code | `$settings`，选择用户/项目/本机项目的真实文件。多选写已核实模型别名；默认单独写 `model`，保留管理 allowlist |
| Claude 桌面 | `$configuration`，只编辑实际已有且可识别的原生配置库条目。新建/激活交原生配置库界面；未知包装格式拒绝写入 |

目录未登记所需协议时，先取得该精确 ID 在 AIhub 对应路由的可靠来源。通过 `route_evidence:[{"model":"…","protocol":"…","source":"https://…"}]` 记录，不以无关文档 URL 绕过检查。用户主动要求自定义才提供 `custom_models`，条目使用[目录 schema](catalog.md)且不可覆盖目录已有 ID。

```text
plan --request <非敏感JSON> --source manual|secret-book|preserve --host <实际宿主> --cwd <实际目录>
apply --task <id> --confirm <该任务confirmation_token> --host <实际宿主> --cwd <实际目录>
recheck --task <id> --host <实际宿主> --cwd <实际目录>
cancel --task <id> --host <实际宿主> --cwd <实际目录>
```

计划展示 `changes`（含移除旧模型能力标记）、`secret_fields`、`shared_with` 和来源提示。token 存在不是用户授权；仅在具体摘要已获同意后使用。手填默认本机密码框；`--input terminal` 只适用于用户自己可交互的本地终端。两种方式均不落中间 Key 文件。原生框最长等 5 分钟，宿主执行工具应允许后台会话并保留任务。

`saved` 只表示回读通过。`recheck` 在结果不明或文件版本变化后标为 `needs_review`；仅存在 Key 不足以证明换成预期值。新计划重新检查现状，不自动恢复旧文件。任务在 `~/.config/setup-aihub/agent-model/tasks/`，仅含非敏感选择和摘要；Agent 通过公开 CLI 恢复，不手改状态。

退出码：0 表示命令完成（仍须读 verification），3 是可处理的 `needs_attention`，1 是本机运行失败。错误只含稳定代码，不输出底层可能含 Key 的异常。
