# tikin-social 配置检查与配置中心

保留真实业务 cwd、caller、全局开关和原任务提交状态。已有可读配置直接执行业务；首次缺项、主动配置或有依据的修复才打开页面。配置检查不联网、不执行生成或完整安装流程。

```text
uv run --frozen --project "<tikin-setup实体>" python "<tikin-setup实体>/scripts/tikin-config" --skill <实际业务Skill> config-check
```

无真实 caller 的共享检查使用 `--plugin-only`，不借用其他 Skill。业务禁用全局时检查和页面都传 `--no-global-config`。退出 3 表示缺项/不可读；其他执行错误不等同缺 Key。402/403/429、网络和权限问题分别核对，不直接要求换 Key。

## 实际打开页面

从实际项目目录调用本 Plugin 自带配置中心，无需额外安装 Setup 或开发 UI Skill：

```text
uv run --frozen --project "<tikin-setup实体>" python "<tikin-setup实体>/scripts/ui.py" start --project "<真实业务cwd>" --page configuration --skill <实际业务Skill> --agent <codex|claude-code|workbuddy|hermes>
```

没有 caller 省略 `--skill`。已明确项目保存时加 `--save-scope project`；首次新增默认个人全局。首页展示当前生效配置与逐项来源；编辑时选择项目／全局范围及具体文件。保存范围不改变读取优先级，环境变量只读并在原注入位置修复。API Key 下提供获取控制台链接及“或联系团队负责人分配”；页面不展示服务地址。

WorkBuddy 使用原生 `Bash` 工具 `run_in_background: true`，给 `start` 加 `--keep-running`。通过 `TaskOutput` 取得立即输出的 URL，另一次工具调用检查 `status`，再交付可持续使用的链接。页面停止后后台入口自行退出；不要用普通短调用或脱离宿主控制的方式启动。

用户在页面直接填写 `TIKIN_API_KEY`，先查看项目覆盖／继承全局标签，再在字段抽屉选择文件。保存前查看原加载器计算的结果：移除或空值的回退来源、低层保存后仍被覆盖的提示。点击固定底栏“保存此文件”一次提交；其他文件的草稿保留。密钥不经聊天、argv、日志或进度文件，Agent 不截图已填写的真实 Key。页面调用原加载器校验、检测文件冲突、单文件事务保存并回读；这不等于在线鉴权。

将返回的 URL 作为可点击链接交付，旁边注明 **📱 跨设备访问需要 FRP / Tailscale，当前配置状态未核实时明确说明。** 默认本机访问，实际活动续期 60 分钟；轮询不续期。`status` 和 `stop` 使用相同项目、页面、caller、Agent 和保存范围参数。服务失效后重新 `start`，保留原业务上下文。

## Setup 任务与接续

已在 `setup-aihub:setup-api-key` 中开始的任务沿用其网页入口和任务编号；新 wrapper 打开同一业务配置中心并绑定原任务。先读取该 Skill 的 `references/browser.md`，使用其 `start/status/stop --task <编号>`；不要再启动一个独立保存流程。旧业务包没有 `scripts/ui.py` 时报告需要更新该完整 Plugin，不恢复已退出的配置方式。

保存后运行上面的真实无值检查。Setup 任务再用其 helper `continue` 完成本机复查和原有默认设置检查。返回原业务前核对关联：未提交且内容、原授权仍有效才继续；已提交或状态不明先查询原结果，修复不授权重发。

明确选择本机文件编辑或环境无浏览器时，沿用相同来源规则：新增共享 `~/.config/tikin-social/.env`，明确项目新增 `.env.local`，已有值修复原文件。给出完整本机路径和字段，由用户本机填写；保存前明确目标与影响，保护权限、Git 忽略及无关内容。Setup 可用时复用其 `start → plan → apply → continue` 安全准备。业务配置不提供 Secret Book 入口、备用或委托分支；已经存在的本机配置仍按原顺序读取，不迁移或删除。

仅用户要求清除时，先用原加载器的 `--delete-from` / `--delete-fields` 投影说明会暴露的来源，再清除选定字段。仅本轮使用采用已有安全进程注入，不转成持久保存。来源、本机读取、线上鉴权和真实业务结果分别报告。
