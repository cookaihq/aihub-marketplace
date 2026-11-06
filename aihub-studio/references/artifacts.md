# 任务保存、成果登记与产物页面

首次新建、继续或交付本 Plugin 任务前读取本页。从真实业务项目目录执行命令；Plugin 安装目录只保存程序。

## 任务与身份

新任务默认保存到 `data/aihub-studio/YYYYMMDDHHmmss-任务摘要-run-8hex/`。用 `--task-name "抖音评论分析"` 提供简短用途，省略时采用对应 Skill 的默认用途。名称不含原始长提示词、账号、链接或凭证。

程序在业务提交前创建最外层的 `task-info.json`，其中记录项目、Skill、创建者、参与者和成果引用。`run.json` 或 `task.json` 继续承担原业务恢复；模型尝试、转写分片和下载继承外层任务。继续时使用返回的记录；用户明确要求新生成才另建。跨 Plugin 分别建任务，以可靠会话身份关联。

宿主可靠提供身份时，传 `--context-file "<项目内的执行上下文 JSON>"`，创建、继续和成果登记均沿用它。允许字段为：

```json
{"host":"Codex","conversation_id":"实际会话ID","conversation_title":"实际会话标题","agent_id":"实际Agent实例ID","agent_role":"实际角色","agent_model":"实际Agent模型"}
```

值必须来自当前宿主事实；未知字段省略。`host` 只用 `Codex`、`Claude Code`、`WorkBuddy` 或 `Hermes`；Agent 模型不是业务生成模型。真实子 Agent 可提供 `parent_conversation_id` 和 `relationship: "child"`，fork 用 `"fork"`。没有可靠父子关系就省略。Codex 可自动读取 `CODEX_THREAD_ID`，Hermes 可自动读取 `HERMES_SESSION_ID`；同时存在两类会话变量时不猜宿主，须提供可靠的显式 host；仅有 Claude 兼容环境变量不足以判断宿主。缺身份不阻塞任务，页面归入“未关联会话”；不扫描聊天历史、不补猜 ID。上下文文件不包含聊天正文、请求内容或密钥，不登记为成果。

## 文件和交付

程序生成的最终文件默认放在任务根的 `files/` 并自动关联。Agent 额外整理的 Markdown 报告、CSV、JSON 保存后，通过本地命令登记；默认也放在 `files/`。用户明确指定外置文件位置时保留该位置。用 UTF-8 JSON 数组文件列出真实绝对路径：

```json
["<任务绝对目录>/files/analysis.md","<任务绝对目录>/files/data.csv"]
```

Windows 使用随包 `scripts/aihub.ps1`；其他环境使用同参数的 `node scripts/aihub.mjs`：

```powershell
& "<Plugin实体>/scripts/aihub.ps1" artifact-register --skill aihub-understanding --record "<原run.json或task.json>" --files-file "<成果路径数组.json>" --delivery completed --reason "分析报告及数据已保存并检查" --context-file "<执行上下文.json>"
```

登记不需要 Key、不联网，重复登记同一路径保持同一成果身份。`--delivery` 可为 `completed`、`partial`、`failed`，同时说明完成或停止原因；只有文件登记时可省略交付参数。程序已报告完整交付时不必再制造一份完成凭据。原业务状态、内容检查和文件是否仍可用是不同信息。

最终分析结论默认保存 Markdown，保留证据和实际限制；未完成分析只登记已有部分。诊断、请求记录、源素材和转写分片是辅助资料，不当作最终成果。文件登记失败时保留已生成文件与原记录，修复本地登记；不要为补记录重新生成。

## 打开页面

使用完整 Plugin 自带的固定 Python 环境，无需安装开发 UI Skill：

```text
uv run --frozen --project "<Plugin实体>" python "<Plugin实体>/scripts/ui.py" start --project "<实际项目>" --page artifacts
```

`status`、`stop` 使用同一组项目与页面参数；任务整目录显式放在默认根外时，启动加 `--task-dir "<外置任务根>"`，可重复。页面只读取当前项目的新规范任务，不扫描旧 `data/aihub/`、不迁移历史、不补登记。

WorkBuddy 必须用宿主原生后台工具启动，并给 `start` 增加 `--keep-running`；输出 URL 后后台任务保持到页面停止。具体工具参数见[配置入口](credential-setup.md)。先在独立工具调用核对 `status` 后再交付链接。

向用户给出启动结果中的可点击链接，并在附近写明 **📱 跨设备访问需要 FRP / Tailscale；未核实时说明当前配置状态未核实。** 默认只供本机访问。配置与产物服务独立，闲置 60 分钟结束；产物可勾选本次常驻，停止/重启后恢复默认计时。

页面提供“按任务 / 按会话 / 按文件”，显示当前项目实际 Git 分支。任务卡片最多显示 3 个不同格式的缩略图，图片和视频使用封面。点击文件夹先看本任务文件，再打开详情。会话桌面左侧选择会话、右侧查看任务；手机逐层返回。页面只负责查看与下载，不执行重试或删除。
