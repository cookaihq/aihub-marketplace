# 任务保存、最终分析与产物页面

首次新建、继续或交付 Tikin 业务任务前读取本页。离线接口发现、配置和安装本身不创建成果任务。

## 同一个任务

从实际业务项目执行 `tikin-config request`，新任务提供 `--task-name "抖音评论分析"`，默认根为 `data/tikin-social/`。程序独占创建 `YYYYMMDDHHmmss-任务摘要-run-8hex/`，在首次请求前保存 `task-info.json`。`run.json` 继续管理请求、分页和恢复。同一用户任务的翻页、异步查询与后续操作复用返回的 `--record`，不因进程或会话改变另建任务。新的独立需求另建；AIhub Studio 任务独立，以会话关联。

宿主可靠提供身份时，创建、继续、下载和本地登记均传 `--context-file "<执行上下文.json>"`：

```json
{"host":"WorkBuddy","conversation_id":"实际会话ID","conversation_title":"实际标题","agent_id":"实际Agent实例ID","agent_role":"实际角色","agent_model":"实际Agent模型"}
```

`host` 只用 `Codex`、`Claude Code`、`WorkBuddy` 或 `Hermes`；未知值省略，不用标题或项目推断 ID，不扫描聊天历史。Codex 可以自动读取 `CODEX_THREAD_ID`，Hermes 可以自动读取 `HERMES_SESSION_ID`；同时存在两类会话变量时须明确当前 host。已知子 Agent 可加可靠的 `parent_conversation_id`、`relationship: "child"`；fork 用 `"fork"`，独立显示。缺身份照常执行，页面归入“未关联会话”。上下文只含身份，不放聊天正文或密钥；首次创建者保留，真实继续者追加。

## 数据与最终报告

成功请求的完整 JSON 保存到 `files/response-<指纹>.json` 并自动关联，不能用诊断中的截断响应代替。相同请求身份的最新成功响应保存在同一位置；分页使用不同请求指纹。程序下载的媒体默认在关联任务的 `files/`，明确传入 `--output-dir` 时保留选定位置。

完成评论、账号、竞品、趋势、标签或舆情分析后，将最终结论另存为 `files/analysis.md`；包括数据来源、样本量、关键发现及分页停止原因。完整数据导出为 CSV/JSON。仅检索或下载任务按实际交付文件，不为凑报告制造分析。未完成时保留已有文件，说明部分结果。

Agent 保存的报告、表格、普通下载工具取得的媒体需要本地登记。用户明确指定外置文件时直接引用，不强制搬移。先写 UTF-8 JSON 数组：

```json
["<任务绝对目录>/files/analysis.md","<任务绝对目录>/files/comments.csv"]
```

再在原项目目录执行，caller 采用实际 Skill：

```text
uv run --frozen --project "<tikin-setup实体>" python "<tikin-setup实体>/scripts/tikin-config" --skill tikin-comments-analysis artifact-register --record "<原run.json>" --files-file "<成果路径数组.json>" --delivery completed --reason "样本分析及报告已完成" --context-file "<执行上下文.json>"
```

`--delivery` 可为 `completed`、`partial` 或 `failed`，必须提供实际完成/停止原因。没有新增文件时省略 `--files-file`，仍可登记整体交付状态。一次请求成功、进程退出或一个文件存在都不代表整项分析完成；真实续行会使旧交付凭据失效，需要在本轮结束时重登记。登记不读取 Key、不联网、不会重发业务；重复登记同一路径保持成果身份。运行记录、诊断、源素材及 `.part` 不计最终成果。登记失败保留原数据，只修复本地登记。

## 打开产物或配置

```text
uv run --frozen --project "<tikin-setup实体>" python "<tikin-setup实体>/scripts/ui.py" start --project "<实际项目>" --page artifacts
```

`status`、`stop` 沿用相同参数。任务整目录放在默认根外时显式加 `--task-dir "<任务根>"`，可重复；不扫描磁盘其他位置或历史任务。页面显示实际项目分支，提供按任务、按会话、按文件三种查看方式；任务卡片最多横排 3 个不同格式的缩略图，图片/视频使用封面。任务文件夹先下钻到成果，再进入详情。手机支持逐层返回。

Markdown 详情支持标题、列表、强调、代码块、表格和引用式图片。附图按已登记文档所在目录解析，支持中文、空格和 URL 编码路径，无需逐张登记，也不增加成果数量。复制保留 Markdown 文本；下载取得原文件，不自动打包附图。正文预览最多 160 KiB，超出时提示下载完整文件。

图片限文档目录及子目录内的 PNG、JPEG、GIF、WebP，每张最多 20 MiB，并核对文件签名。越界及指向目录外的符号链接、SVG、远程图片不加载；缺失或变更显示提示，刷新重新核对。原始 HTML 显示为文本，HTTP(S) 链接可以主动打开，其他本地文档不会因链接自动开放。现有文档和任务记录保持原位。

WorkBuddy 用宿主 `Bash` 工具的 `run_in_background: true` 执行 `start`，加 `--keep-running`。入口立即输出 URL 并保持后台任务到页面停止；用 `TaskOutput` 取结果，在独立调用中检查 `status` 后交付链接。普通短调用可能回收整个子进程树；不要绕开宿主控制。结束先执行相同参数的 `stop`，后台入口自行退出。

给出启动结果的可点击链接，附近必须说明 **📱 跨设备访问需要 FRP / Tailscale；当前配置状态未核实时明确说明。** 默认本机访问、闲置 60 分钟结束；产物可勾选本次常驻。配置页独立启动，使用 `--page configuration`，入口细则见[配置流程](credential-setup.md)。
