# Plugin 配置中心入口

读取主 Skill，核对真实宿主、已选 Plugin 实体、caller、业务 cwd 和提交状态。`setup_ui.py` 保存 Setup 任务关联，然后委托该 Plugin 自带的配置中心。业务包必须包含 `scripts/ui.py`：Studio 位于 Plugin 根，Tikin 位于 `skills/tikin-setup/`。没有该入口时更新对应完整 Plugin；不使用另一宿主缓存冒充已安装版本。

```text
uv run --frozen --project "<setup-api-key实体>" python "<setup-api-key实体>/scripts/setup_ui.py" start --host <claude-code|codex|workbuddy|hermes> --cwd "<原业务cwd>" --aihub-root "<AIhub Plugin实体>" --plugin aihub-studio --skill <真实caller> --submission <not_submitted|submitted|unknown> --open
```

Tikin 改用 `--tikin-root "<Tikin Plugin实体>" --plugin tikin-social`。没有 caller 省略 `--skill`；同时传两根时必须先明确 `--plugin`。`--no-global-config` 与业务一致，已有范围传 `--scope project|global`，已有业务引用传 `--business-record` / `--business-task-id`。不传 Key 或业务正文。

WorkBuddy 用原生 `Bash` 工具的 `run_in_background: true` 执行，并给 `start` 增加 `--keep-running`。入口先输出任务绑定和 URL，再保持后台任务；通过 `TaskOutput` 取得结果，在独立工具调用核对 `status` 后交付链接。结束时同参数 `stop`，后台入口自行退出；不使用脱离宿主控制的启动方式。

已有任务传 `--task <编号>`（`--session` 为同一编号的别名）；恢复原 caller、scope、业务绑定和提交状态，不能把新请求混到旧任务。配置来源由业务加载器决定；无 Secret Book 分支。用户直接填写 Key，查看来源与变更摘要，一次保存。服务地址不在页面展示。

交付返回的可点击 URL，说明本机访问及闲置 60 分钟到期；附近必须有 **📱 跨设备访问需要 FRP / Tailscale，当前配置状态未核实时明确说明。** 不自动创建隧道。

本人保存后，或回复继续时：

```text
uv run --frozen --project "<setup-api-key实体>" python "<setup-api-key实体>/scripts/setup_ui.py" status --host <实际宿主> --cwd "<原业务cwd>" --task <编号>
uv run --frozen --project "<setup-api-key实体>" python "<setup-api-key实体>/scripts/setup_api_key.py" continue --host <实际宿主> --cwd "<原业务cwd>" --task <编号>
```

页面 `status` 只读服务状态和无值回执；helper `continue` 通过原加载器复查并记录完成。核对 task 与 binding，随后执行[默认设置检查](default-settings.md)。本机回读不等于在线鉴权；已提交先查询，未知先核对，不重发。

服务到期/停止后用相同任务 `start` 获取新链接。手填草稿不在服务重启后恢复。`stop` 使用相同 host、cwd 和 task；停止页面不会删除已保存配置或原业务成果。Setup 的任务元数据在运行用户 `~/.config/setup-aihub/tasks/`；页面运行文件由业务 Plugin 管理在项目 `tmp/<plugin>-ui/`，日志轮转且不含凭证和完整授权链接。
