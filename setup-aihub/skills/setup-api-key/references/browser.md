# 本机网页入口

配置、主动更换/修复和业务缺 Key 使用同一入口。清除、仅本轮使用、明确选择编辑文件及原有委托恢复仍按主 Skill 的对应分支处理。

## 启动

先读取主 Skill，核对当前宿主安装和真实业务目录；Tikin 2.x 网页配置需要 setup-api-key Skill / Setup Plugin 3.0.0，AIhub 网页入口自 2.3.0 提供。本版业务支持范围见[业务契约](consumers.md)，Tikin 1.x 先升级。完整 Plugin 的目录必须来自当前宿主已核实的实体。不得把未发布源码说成已安装版，也不使用另一宿主的缓存冒充当前安装。

从原业务 cwd 运行（路径换成绝对路径，参数值仅含无密钥元数据）：

```text
uv run --frozen --no-dev --project "<setup-api-key实体>" python "<setup-api-key实体>/scripts/setup_ui.py" start --host <claude-code|codex|workbuddy> --cwd "<原业务cwd>" --aihub-root "<AIhub Plugin实体>" --plugin aihub-studio --skill <真实caller> --submission <not_submitted|submitted|unknown> --open
```

tikin 使用 `--tikin-root "<Tikin Plugin实体>" --plugin tikin-social`。没有 caller 省略 `--skill`；只给已核实已安装的根，可以同时传两个根在页面选择服务。`--no-global-config` 与业务检查一致。已有 Setup 任务使用 `--task <编号>` 继承真实 caller、来源、安装和提交状态；已委托到独立 Secret Book 的任务先核对旧任务状态，不启动第二次保存。已有来源选择传 `--source manual|secret-book`，已有范围选择传 `--scope project|global`；原业务记录传 `--business-record` / `--business-task-id`，不传业务正文或凭证。

运行环境由 Skill 的 uv.lock 固定；Windows 同样通过 uv，不依赖 bash。宿主默认沙箱若拒绝运行目录写入或本机端口绑定，保留默认沙箱，通过宿主原生命令审批为**这一次启动命令**申请所需权限；不要换路径绕过拒绝，不要求全局关闭沙箱。审批不可用时报告未启动，不能编造链接。

输出中的 `link_markdown` **作为可点击链接直接给用户**，说明在运行此 Agent 的同一电脑打开、60 分钟空闲失效。不要只说已转交 Setup。远程 Agent 无本机浏览器时说明运行环境，可沿用用户选择的本机文件编辑。

## 完成与恢复

保留启动结果的 session。本人操作网页后，或回复“继续”时运行：

```text
uv run --frozen --no-dev --project "<setup-api-key实体>" python "<setup-api-key实体>/scripts/setup_ui.py" status --host <实际宿主> --cwd "<原业务cwd>" --session <session>
```

`status` 不访问凭证值。`done/check_result` 时根据 task_id 用原 helper `status` / `recheck` 核对实际状态，读取并执行[默认设置检查](default-settings.md)，然后依原业务提交状态接续。无值报告只证明本机读取；不把它称为线上鉴权通过，不用计费请求验 Key。已提交先查原结果，未知先核对，不重发。

`uncertain` 必须先在网页“核对实际结果”，不重放保存。刷新保留非敏感选择；进程重启后手填值与旧确认失效，需要本人重填、重新预览。失效或已停止时用相同命令 `start --session <session>` 取新链接；新一轮不得消费旧确认。不要轮询续命。

取消清除未保存的输入，保留已经保存的配置。“结束配置”或 `stop --host ... --cwd ... --session ...` 停止服务。元数据在实际用户 `~/.config/setup-aihub/ui/` 与 `tasks/`，运行日志只含状态和错误码。

## Secret Book 读取

随包 `vendor/secret_book/UPSTREAM.json` 固定 Secret Book 2.7.0 的 MIT 源码提交与 SHA256，每次加载核验；这是依赖快照，不是独立 Skill 安装或新发布的共享库。网页复用原身份、可见性、字段映射契约。

现有 Lark CLI 可用时复用；缺失时仅准备用户目录中的 `@larksuite/cli@1.0.82`。页面选择账号并核对实际 app_id/open_id；只有本人点击授权才发起最小只读 scope 的飞书登录。没有应用配置时由 Agent 读取当前 Lark CLI 配置指引协助本人配置，不自动借用其他应用凭证。

旧连接出现身份变更时恢复原账号或预览改绑同一连接。项目/环境配置、损坏格式和缺少的字段必须修复原来源。连接保存结果不明时先重查连接列表与原文件；不自动新增另一个连接或重放旧确认。远端建表、写字段、补 ID、改记录不属于本入口。
