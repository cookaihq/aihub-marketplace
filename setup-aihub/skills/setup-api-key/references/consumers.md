# 业务消费者契约

只接入以下两项。适配器核对三份 Plugin manifest、凭证声明和真实来源报告，调用业务运行时；不能把任意市场条目或环境变量加入管理范围。

| Plugin | 本次本地兼容基线 | 字段与入口 |
| --- | --- | --- |
| `aihub-studio` | 1.2.0 | `references/credentials.json` 仅声明必填敏感字段 `AIHUB_API_KEY`；`node "<plugin>/scripts/aihub.mjs" config-check --skill <真实业务Skill> --credentials-only` |
| `tikin-social` | 1.2.0 | `skills/tikin-setup/references/credentials.json`；`uv run --locked --no-dev --project "<tikin-setup>" python "<tikin-setup>/scripts/tikin-config" --skill <真实业务Skill> config-check` |

两个入口没有 caller 时都使用 `--plugin-only`，与 `--skill` 互斥。tikin 身份和全局开关放在 `config-check` 前，AIhub 放在后面。`--no-global-config` 关闭两类全局目录。AIhub 的 `--credentials-only` 不检查业务模型设置/媒体工具，不能从它成功推断其他配置正确。

Windows 原生 AIhub 使用 `& "<plugin>/scripts/aihub.ps1" config-check ...`；Setup 的适配器自动调用这一入口。它检查 Node 版本并固定路径解析选项，保持默认沙箱及真实 cwd/caller。上表的直接 Node 形式用于 macOS / Linux，不能在 Windows 配置回退中绕过随包入口。

删除投影在同一 `config-check` 增加 `--delete-from "<已知来源路径>" --delete-fields <逗号分隔字段>`，两边返回 `config-deletion-preview/v1`，内含真实 `before` 和投影 `after`。文件字节不变，修订哈希仍指向真实文件。投影不能作为已生效检查交给 Secret Book。

AIhub 首配只处理 Key，默认服务为 `https://api.aihubmax.com`；不增加 `AIHUB_BASE_URL` 可选配置。有旧地址覆盖时由业务诊断核对，不借配置任务改写。tikin Key 必填，`TIKIN_BASE_URL` 可选且默认 `https://console.tikin.net`，两项在声明中关联。加载器按字段独立读取，关联声明不意味着强制填地址或允许把不同服务的 Key 与地址拼配。删除/更换任一项后，说明另一个字段的来源并核对服务对应关系。

报告 `secret-book.config-inspection/v1` 包含 consumer、真实 caller 或 null、cwd、global_enabled、layers/revision、字段存在性/来源/问题和环境哈希。缺项返回 `3`；运行失败、超时、输出损坏、未知 schema 各自处理。未知字段/原始异常不进入用户回复或任务记录。Setup 自身不生成一份配置优先级。

共享首次保存分别为运行用户 `~/.config/aihub-studio/.env` 和 `~/.config/tikin-social/.env`；已有原来源优先。完整路径与读取顺序见 [Plugin README](../../../README.md#配置位置与生效顺序)。同用户、同环境的三个宿主及不同 Plugin 版本可能共享这些文件。

## 用户没有 Key

沿用业务随包文档已给出的服务入口。tikin 控制台为 <https://console.tikin.net>，让用户在自己的账号界面找到既有 API Key；具体控件按当时可见界面核对，不猜路径。AIhub 可从 <https://docs.aihubmax.com> 的官方说明找到其服务入口；若当前公开文档不能确认密钥页面，明确请用户向服务管理员取得已有 Key 或准确控制台链接。首版不代为开户、创建或撤销 Key，也不请求用户把 Key 发到聊天。

## 线上鉴权

当前没有登记已核实非计费的鉴权能力。即使业务代码存在模型列表或 `/api/usage/token/`，仍不能据此认定免费。用户要求时说明此限制；取得正式接口依据、确认真实目标与脱敏输出后才能接入。不得向默认地址试发自定义服务的 Key，不调用图片生成、模型对话或数据业务探测 Key。
