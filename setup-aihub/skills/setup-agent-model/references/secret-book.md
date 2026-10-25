# Secret Book 原生配置公开契约

需要 **Secret Book >= 2.7.0** 和完整 **Setup AIHub >= 2.1.0**。核对实际 Skill 实体、版本与当前宿主；这些版本未发布时不能拿旧版冒充。先沿用用户的使用者角色和既有表/身份，只读远端。安装、登录或本人授权缺失时保存 Setup 任务，按 Secret Book 自身流程处理；用户选择手填则不查表。

业务声明为 [credentials.json](credentials.json)：`AIHUB_API_KEY` 是必填敏感值，映射到已选原生字段。该名字用于表中映射，不意味着写到 dotenv。Setup 先完成目标/配置项/模型/默认选择，然后：

```text
handoff --task <Setup任务> --host <实际宿主> --cwd <原目录> --output <公开无值报告JSON>
```

以同一 cwd 将返回的 `requirements/report` 交给 Secret Book，读其 `references/consumer-setup.md` 原生配置分支。由它核对候选记录、实际 key 映射、用户身份及一次保存摘要。原生报告不接受 `--scope/--skill-only`，目标文件已经明确；这些 dotenv 参数不能重定向写入。

Secret Book `configure` 首次输出确认摘要，确认后通过固定的 `native-bridge` 协议调用同包格式适配器。允许的协议只有 `secret-book.native-configuration/v1`，禁止传任意命令或 `run` 包装写文件绕过检查。值仅经 stdin 进入子进程。`native-bridge` 是供已获授权写入器调用的内部 IPC，本身不替 Agent 获取用户同意；一般 Agent 使用 `plan/apply` 或 Secret Book configure。

写后读取 Secret Book 公开输出中的 `native_receipt`，保存为无值 JSON，然后：

```text
accept-secret-book --task <Setup任务> --host <实际宿主> --cwd <原目录> --receipt <公开receipt.json> --reference <Secret Book公开workflow编号>
```

Setup 独立回读目标文件、校验计划字段与写入版本；不再次保存，不重复相同确认。只有两个阶段都通过才说本机保存完成，仍需分别核对客户端加载与真实调用。

恢复只能使用双方公开入口：Setup `status/list/recheck`；Secret Book `workflow status` 获取本任务 pending，`configure-status --requirements <声明>` 获取公开 history/receipt。禁止读写另一方私有状态文件。SB 写入结果不明先 `configure-reconcile --requirements <声明> --inspection <原报告>`（同一 cwd、consumer workflow），不查远端、不重发写入；仅存在 Key 不能证明预期替换。根据现状重新规划和确认，旧 token 不复用。

取消 Setup 不回滚已完成的 Secret Book 保存；身份、源记录值、映射、代码或目标变化会使原确认失效。表中轮换也不会自动同步，后续客户端直接读取自己的原生配置。
