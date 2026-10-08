# tikin 凭证检查与 Setup 衔接

纯凭证请求及业务真实缺项进入本流程，不执行完整 `tikin-setup` 的更新、路由、提醒、Key 创建或线上验证。正常业务配置可读时直接继续原任务。

从实际已安装 `tikin-setup` 定位 helper，始终保留业务 cwd、真实 caller 和关闭全局的语义：

```text
uv run --locked --no-dev --project "<tikin-setup实体>" python "<tikin-setup实体>/scripts/tikin-config" --skill <真实业务Skill> config-check
```

没有 caller 使用 `--plugin-only`，不沿用默认 `tikin-setup`。身份/`--no-global-config` 放在子命令前。`config-check` 通过真实加载器输出无值 `secret-book.config-inspection/v1`，退出 `3` 表示配置问题；不调用 API，不创建路由文件，也不依赖 POSIX shell 或媒体工具。Windows 使用本 Skill `Scripts/python.exe`，macOS/Linux 使用 `bin/python`；不同于仍需 POSIX 适配的媒体/API shell 示例。

[credentials.json](credentials.json) 声明必填敏感 `TIKIN_API_KEY` 与关联可选 `TIKIN_BASE_URL`，默认地址 `https://console.tikin.net`。常规首配不强制填地址；现有非默认地址时核对 Key 属于同一服务。加载器按字段独立取首个非空值，声明关联组不授权拼配不同服务。

## 转交与最小回退

当前宿主可调用兼容的 `setup-aihub` 时，读取并实际进入其流程。传递 `tikin-social` 身份/版本/实体、真实 caller、cwd、全局开关、声明/无值报告、有效的来源/范围选择、原任务记录引用和提交状态。Setup 仅运行本 helper 配置检查，不调用整个 `tikin-setup`，不再相互转交。

Setup 不可用时如实说明并保留原任务；提供安装或最小本机配置，不阻断已配置业务：

> 请安装完整 setup-aihub Plugin：优先从 https://github.com/cookaihq/aihub-marketplace.git 获取，网络故障时同版本回退 https://cnb.cool/zhidateam/tannt/aihub-marketplace.git，安装后继续 tikin 凭证配置。

核对当前源码所需版本已经发布再安装；不要把未发布的开发能力说成已可取得。WorkBuddy 走当前原生“专家·技能·连接器 → 技能 → 套件”，不能另起 `codebuddy/cbc`/内嵌 CLI（包括 help/list）、调用未公开 RPC 或手写注册表。

回退沿用来源选择，未定时提供 **自行填写本机文件／从 Secret Book 选择配置并保存**。手填不依赖 Secret Book。首次共享已确定为 `~/.config/tikin-social/.env`，已有项目/Skill 范围沿用；错误修复实际来源，环境变量先找注入位置。展示完整路径、字段、范围、替换项与覆盖后按用户授权保存；项目文件须未跟踪且被忽略。用户本机填写，完整 Key 不进入聊天、argv、记录或备份。`set-key` 会初始化路由且只写共享文件，不能用于此通用修复流程。

选择 Secret Book 后，进入当前公开使用者流程：本人身份连接已有表，远端只读；候选、映射、目标及写入确认由它完成。缺列/ID/权限不自动建表或修复远端，不借管理员身份。声明和原生报告用于兼容 `configure/configure-status`；2.4.0 不足以证明新角色要求，所需能力未核实时提供兼容版本、手填或暂缓。确认未安装时提供安装并继续/手填/暂缓，独立官方源为 https://github.com/cookaihq/secret-book，网络故障同版本回退 https://cnb.cool/zhidateam/tannt/secret-book.git，不当作 Marketplace。

Secret Book 的共享空 caller 需要已发布 2.5.1 或更新版本，真实 caller 仍兼容 2.5.0；保持原始报告，不虚构或更换 caller。按实际安装包的 `references/roles.md` 创建或恢复 `consumer` 任务，业务命令带公开 workflow 参数，确认使用 `workflow status` 的最新任务 token。2.5.1、2.5.2、2.5.4 已有配置契约联调，两个服务已通过 2.5.2 本人真实表到临时项目的保存、恢复和本机复查；客户端加载、线上鉴权与业务完成仍分别报告。

两条路径保存后均重新运行真实 `config-check`，报告本机结果与生效来源。仅用户要求且非计费接口已有依据时提供线上鉴权；不因已有 `validate` 命令便主动调用。网络、限流、余额、权限与鉴权拒绝分别解释；401/403 需核对账号/服务授权，不能直接断言 Key 文本错误。

原业务未提交且请求及原授权有效才交回执行；已提交先查已有结果，未知先核对。配置修复不重发。后续业务只读自己的文件，Secret Book 表轮换不自动同步；临时、不落盘要求按安全进程注入处理。

## 清除前的只读投影

在 `config-check` 后加 `--delete-from "<已知来源文件>" --delete-fields TIKIN_API_KEY`，可经选择使用 `TIKIN_BASE_URL` 或两者（逗号分隔）。返回 `config-deletion-preview/v1`，分别包含 `before/after`；不改磁盘、不把整个文件忽略。先展示低层暴露/高层覆盖/默认值，再按具体授权清除指定字段。删除地址后需核对保留的 Key 与最终服务对应；清除本机不等于远端撤销。
