# 本机 helper（给 Agent）

在实际业务工作文件夹运行，路径从已加载 Skill 定位并引用，Windows 原生不切 WSL。统一形式：

```text
uv run --locked --no-dev --project "<setup-api-key Skill 实体目录>" python "<setup-api-key Skill 实体目录>/scripts/setup_api_key.py" <子命令> <参数>
```

先核对 uv >= 0.8。Skill 自带 Python 3.13、锁文件和 Windows/POSIX bootstrap；自有环境缺失自动准备。系统 uv/Node 缺失时按实际报错给安装引导。`UV_PROJECT_ENVIRONMENT` 的相对值按每个 Skill 自己的目录解析；不要把 Setup 已解析的 venv 路径注入 tikin 或 Secret Book 子进程。业务检查在传入的真实 `--cwd` 中执行，不因 `--project` 改变 cwd。

## 只读与开始

所有命令接收 `--host claude-code|codex|workbuddy --cwd "<实际工作文件夹>"`；宿主来自当前会话事实，不能通过目录存在推断。

| 子命令 | 参数与结果 |
| --- | --- |
| `inspect` | `--plugin aihub-studio|tikin-social --plugin-root "<实际实体>"`；必选真实 `--skill <name>` 或 `--plugin-only`；可加 `--no-global-config`。返回真实无值来源报告，不创建任何任务或配置 |
| `start` | 同上，安装未完成可省略 `--plugin-root`；另传 `--operation configure|repair|clear|check`，已有来源才传 `--source manual|secret-book`。`--installation installed|not_installed|disabled|unloaded|unknown` 由原生管理记录提供，默认未知；helper 不把目录当安装证据 |
| `list` | 可按 `--plugin` 过滤；只读当前宿主、运行环境和 cwd 的未完成任务，不自动选择 |
| `status` | `--task <id>`；返回进度，不消费确认，不执行待办 |
| `attach` | `--task <id> --plugin-root "<实体>" --installation <实际状态>`；安装或更新后绑定真实产物，旧计划与确认失效，重新检查 |

`start` 的 `--submission not_submitted|submitted|unknown` 保存原任务提交状态，默认未知。可传 `--business-record "<已存在的业务 JSON 路径>"` 或已知 `--business-task-id`；只保留引用，不复制请求内容或读取记录中的 Secret。无法恢复原请求时仅补询必要内容，不猜测重建。

状态位于运行用户 `~/.config/setup-aihub/tasks/<id>.json`，仅有上下文、选择、路径、字段名、文件/环境校验值、确认指纹及结果元数据。检查报告包含文件修订和环境哈希，不含值；不要将整个环境或原始异常写进记录。状态输出应翻译成用户需要的中文结果，不直接展示整份内部 JSON。

## 手填与清除

1. `start` 后使用 `plan --task <id> --target "<文件>" --fields AIHUB_API_KEY`。tikin 字段可为 `TIKIN_API_KEY` 或经选择的 `TIKIN_BASE_URL`，多个用逗号隔开。`clear` 任务生成删除投影；其他任务准备手填位置。纯检查任务拒绝修改。
2. 将计划中的目标、字段、作用范围、当前/投影来源与共享影响展示给用户。首次共享位置是业务 `.env`；已有来源必须沿用，环境变量不能用低层文件遮蔽。tikin 必须说明 Key 与地址是否仍对应；删除地址可能回到默认服务。
3. 用户已授权当前摘要后，调用 `apply --task <id> --confirm <当前计划指纹>`。不要把“继续”、任务编号或旧计划当成新授权。helper 再读声明、加载器、来源和文件修订，任何变化均停止，不覆盖并发修改。
4. `prepare` 只准备注释字段，不接收 Key，不替换既有值。告诉用户实际路径；Windows 可由 Agent 协助用本机编辑器打开，macOS/Linux 使用实际可用编辑器。让用户去掉对应示例行的 `#` 并填写值，不要求回贴文件。已有字段直接在原行修改。
5. 用户完成手填后 `continue --task <id>` 重新读取；手填造成的变化是预期的，不复用旧计划重写文件。清除由 helper 在同一次调用后复查，操作成功可能导致必填项缺失，按结果解释。

Git 中目标及含剩余配置的原子替换临时文件必须未跟踪且实际被忽略。仅忽略精确 `.env.local`、没有覆盖 `.env.local.setup-aihub-*.tmp` 时会拒绝替换；说明具体规则缺口，在用户允许后补所需忽略规则再重做计划，不能先写入或静默换路径。不会自动修改索引。

文件保留 UTF-8/BOM、LF/CRLF 和无关行；不可靠的编码或多行赋值拒绝自动改写。写前验证限制性 Windows DACL/POSIX 权限；拒绝 symlink、junction 和硬链接目标。临时文件权限先于内容写入，完成后清理。锁只能协调本 helper，最终校验与替换间仍存在外部程序竞争窗口；检测到变化或回读失败就核对现状，不承诺跨所有编辑器的事务隔离。

## 选择、委托与恢复

`source --task <id> --source manual|secret-book` 切换用户已决定的来源，丢弃旧的待执行计划。已有明确目标/字段可用 `select --task <id> --target "<文件>" --fields <字段>` 保存选择；这不是写入确认，Secret Book 仍自行核对映射和目标。

`handoff --task <id> --availability missing|unknown|unloaded|incompatible|available`：缺失时给出安装/手填/暂缓三项；可用时还须传 `--secret-book-root "<当前宿主选用的完整 Skill 实体>"`，只读核对其公开元数据后生成 `credentials.json` 路径及原生检查报告。它不安装或执行 Secret Book；宿主加载与运行能力仍由 Agent 核实。所需角色与公开流程见 [Secret Book](secret-book.md)。

只对 `configure/repair` 委托写入。真实 caller 最低 2.5.0，共享模式最低 2.5.1，空 caller 原样保留。位置缺失、版本不兼容或产物元数据不一致分别返回 `secret_book_location_required`、`secret_book_version_incompatible`、`secret_book_artifact_invalid`，不创建已委托状态，仍可转手填或保留任务。`dependency` 记录所选实体路径与版本；测试提交和验证范围另列，不作为宿主安装证据。

委托实际返回后用 `handoff-result --task <id> --status completed|cancelled|pending|failed|unknown`，有公开不透明引用才传 `--reference`。仅传状态/引用，不传 Secret Book 私有状态路径。成功后由业务加载器复查；模拟成功没有实际字段不会完成配置。失败、取消或待操作不由 Setup 重写文件。

实际委托处于 `pending/unknown` 时，禁止切换写入方、重复委托或用本机 `reconcile/cancel` 代替 Secret Book 的公开核对/取消。先由原写入方返回明确结果，再继续 Setup；仅安装状态未知且尚未委托时可以改选手填。后续状态更新未提供新引用会保留原公开引用。已返回完成但本机复查失败时，只重试复查，不让 Secret Book 重复保存。

`continue` 对待确认、待 Secret Book、待安装状态只返回当前待办；不会重放。`reconcile` 对写入中断/结果不明仅报告当前文件与来源，撤销旧执行计划，随后再决定是否需要新计划。`cancel` 关闭任务且保留已经保存的业务配置；用户要求清理进度时，关闭后 `forget` 只移除该任务记录。多服务分别执行，不使用一个全局“当前任务”。

退出 `0` 表示 helper 命令完成，仍须查看嵌套的本机状态；`2` 是需要处理的参数、兼容或安全条件，`1` 是本机运行错误。错误仅输出稳定原因码，不透传可能含值的子进程 stdout/stderr。`sources_changed` 重新检查与规划，`artifact_changed_refresh_required` 核对版本后 `attach`，`reconcile_before_retry` 先核对实际结果。
