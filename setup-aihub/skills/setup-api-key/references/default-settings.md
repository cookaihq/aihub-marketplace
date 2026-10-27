# Plugin默认设置检查

密钥 `configure/repair` 成功后必须执行本流程，再结束 Setup 的结果回复。检查范围是开发者清单内**所有在当前宿主已安装的 Plugin 或独立 Skill**，不限于本次配置密钥的对象；不安装未安装项目。保留已完成的密钥结果，检查失败、未答复或跨轮等待不阻塞原业务任务。

## 读取清单与确认安装

按 [helper](helper.md) 的统一入口运行 `defaults --action catalog --host <实际宿主> --cwd <业务目录>`，读取随完整 Plugin 分发的 [指定清单](../../../references/default-settings-targets.json)。本清单与凭证适配器列表用途不同，不能用正在配置的 `--plugin` 缩减检查范围。清单缺失、损坏或版本未知时报告“Plugin默认设置检查未完成”，保留密钥成功结果，不改用硬编码列表。

- `kind=plugin` 的 `name` 对照当前宿主原生 Plugin 安装记录及实际 manifest；`kind=skill` 对照当前宿主独立 Skill 安装/发现记录及 frontmatter。核对 `source_repository` 与真实来源，同名异源不代用。GitHub/CNB 同源关系按已核实的安装说明判断。
- 按 [宿主入口](hosts.md) 取得所有条目的安装证据。确认未安装的记为 `not_installed`；已安装但禁用或本会话未加载仍在检查范围，分别记 `disabled/unloaded`，不会因检查而启用。记录不可取得为 `unknown`，不是未安装。只在开发源码目录发现文件不是安装证明。
- 对每个已安装对象，从其**实际安装根目录**解析清单中的 `setup_guide/rule_template`；读取其流程，执行离线默认检查，再由当前 Agent 阅读实际适用的全局和项目规则，判断语义等效、覆盖、冲突及作用范围。检查对象为 Plugin 时按其流程检查全部默认 Skills；独立 Skill 按该 Skill 的流程检查。
- 目前 AIhub 的离线入口使用目标安装中已核实的 `aihub-image` 作为该管理命令的 Skill 标识；tikin 使用 `tikin-setup`。它们只是现有默认设置入口需要的标识，不改变凭证任务的真实 caller，不运行生成、数据查询、`doctor` 或完整 `tikin-setup`。Windows AIhub 使用同包 `scripts/aihub.ps1`。新增对象须提供自己的流程与规则文件，不能猜测其命令。
- 当前任务关闭全局读取时，沿用 `global_disabled` 跳过整项，不读取全局规则或提醒偏好。其余情况复用目标对象自己的提醒读取与保存入口，不建立第二份提醒配置。关闭提醒仅抑制询问，仍可报告检查到的默认状态。

未知宿主、缺运行时/参考文件、规则不可读、无法核实覆盖或加载，均如实记录。`review_required` 只是需要语义核对；仅出现名称、安装说明或默认规则标记不足以认定已设置。已有等效规则不重复询问，旧规则按已覆盖范围报告，不借本流程升级。Secret Book 的 `agent-rule` 检查不替代本流程。

## 保存检查结果与显示选项

用当前完成的凭证任务编号，运行 `defaults --action record --task <id> --input <报告.json>`（另带实际 `--host/--cwd`）。JSON 只含以下字段；为清单中的每一项填写一行，包括未安装或未知项，避免漏检。输入文件按当前项目临时文件规范保存，不放凭证或完整规则文件原文。

```json
{
  "targets": [
    {
      "id": "plugin:aihub-studio",
      "installation": "installed",
      "evidence": "当前宿主原生安装入口返回的实际来源、版本、作用域与位置",
      "root": "/实际/aihub-studio",
      "status": "missing",
      "reason": "已阅读全局及项目规则，未发现适用默认规则",
      "config_dir": "/当前宿主实际配置目录",
      "global_rule_file": "/当前宿主实际全局规则入口",
      "rule_files": ["/已检查的全局规则入口", "/已检查的项目规则入口"],
      "session_loaded": "not_verified",
      "reminder_enabled": true,
      "already_prompted": false
    }
  ]
}
```

这是单行格式示例；实际报告必须包含整个清单。`installation` 为 `installed/disabled/unloaded/not_installed/unknown/source_conflict`；`status` 为 `missing/configured_global/configured_project/conflict/unknown/skipped`。未知/跳过行可省略路径字段，其余行必须提供真实路径。`rule_files` 包含实际读取的 imports、项目覆盖和不存在但可能新增的加载入口；helper 保存路径及内容指纹，不复制原文。`evidence/reason` 仅含无值证据。加载仅在本客户端核实后填 `verified`，其余为 `not_verified`。

`already_prompted` 根据同一会话的实际提示记录填写；用户此前选择跳过、本轮不要询问时也为 true。多服务配置完成后只汇总一次，其他任务按实际已提示状态收尾。helper 返回冻结的 `eligible`，只有已安装、`missing`、提醒开启且尚未提示的项目进入选项。

最后回复先报告密钥文件、字段、实际来源与本机检查，再报告未执行线上鉴权/业务调用等实际状态；其后必须使用标题 **Plugin默认设置检查**。逐项展示所有已安装对象及“尚未设为默认／已配置全局默认规则／仅当前项目／存在冲突／检查未完成”，必要时附文件、作用范围及加载核验状态。未安装条目不提供设置选项；无法确认安装的另说明原因。没有指定且已安装的对象时明确说明；不能写“全部已设为默认”。

存在 `eligible` 时点名本次选项作用于哪些项目，写明：**“你可以回复下面的选项文字，或直接回复数字：”**，然后按固定顺序展示：

1. **设为默认**：逐项使用清单返回的 `default_message`，再说明“如果你明确指定其他工具，就按你的要求执行。”
2. **本次跳过**：暂时不设置，以后仍可提醒。
3. **不再提醒**：以后不再询问是否将上述项目设为默认。

补充“选择 1 后，我会先展示完整规则、目标文件及影响范围，经你确认后写入。”同一菜单作用于本次列出的全部待设置项；用户指定子集时先重新列出对应选择，不扩大授权。文案中的 `{agent}` 只由实际宿主决定：`codex → ChatGPT/Codex`、`claude-code → Claude Code`、`workbuddy → WorkBuddy`；展示名称不扩大到其他 Agent 的规则文件。

没有待设置项时只报告结果，不显示空菜单。helper 任务号保留用于跨轮恢复；业务配置已成功，不让用户误以为还必须设默认才能使用密钥。

## 数字回复、预览与恢复

后续只收到 `1/2/3` 或选项文字时，先读本 Skill，按 `status` 或同宿主/cwd 的 `list` 找到 `default_settings` 待办，再读取 `defaults --action status --task <id>`。未知进度 schema 保留原文件并报告不能恢复，不覆盖或消费选择。多个待办或当前对话另有数字菜单时补充确认对应项目，不猜最新项。再次核对原安装、实际宿主配置目录和提醒状态；发生变化先重做检查，保留原凭证结果。`record` 会撤销旧选择/确认，不能带着旧确认覆盖新范围。

调用 `defaults --action choose --task <id> --choice <数字或文字>` 记录用户选择；用户明确只选部分项目时加 `--targets <eligible中的ID,ID>`，先点名所选项目，其余项目本次不设置：

- **2**：关闭本次待办；不保存长期提醒偏好，本会话不重复提示。
- **3**：按每个选中对象的现有入口执行 `dismiss`，使用本次核对的宿主及真实配置目录。分别回读提醒关闭结果，再 `finish`；失败项单列，成功项不重放。只关闭 `selected` 中的项目，保留已有规则和其他对象/Agent 的设置。
- **1**：先核对原生检查返回的 `global_rule_file`、实际加载入口、symlink 及共享影响，写入范围是当前 Agent 的全局规则。用 `defaults --action preview --task <id> --input <预览参数.json>`，参数为 `{"shared_with":["实际共享该文件的 Agent 名称"]}`，无共享时空数组。输出中逐项包含完整规则、目标文件、作用范围与确认指纹；必须在用户可见回复中展示，不只给文件链接或摘要。同一实体文件的多个规则合并展示，并计划一次编辑。

得到对该完整预览的明确确认后，使用 `defaults --action verify --task <id> --confirm <当前指纹>` 校验。这个命令不替 Agent 获取用户同意，也不写文件；它核对清单、模板及全部已审阅规则的修订。随后按各目标 `setup_guide` 编辑当前规则实体，保留其他内容、链接及换行；同一实体只编辑一次。`1`、任务号、指纹存在或“继续”本身不等于确认完整规则。

`verify` 之后中断时先回读实际文件，已写入项只核验，未写入项不自动重放；重新规划所需剩余步骤。规则、模板、安装来源或真实配置目录变化后重新检查与预览，不消费旧确认。规则冲突和手工内容按目标流程处理，不静默覆盖。

写入或关闭提醒后，`defaults --action finish --task <id> --input <结果.json>`：

```json
{"outcomes":[{"id":"plugin:aihub-studio","status":"written","session_loaded":"not_verified","evidence":"实际规则路径及回读结果；当前会话加载尚未核实"}]}
```

覆盖全部 `selected`；写规则使用 `written/failed`，关闭提醒使用 `dismissed/failed`。写规则由 helper 再核对模板全文确实存在及 symlink 未换指向；提醒结果以目标原生入口回读为证据。报告“已写入，待宿主加载验证”，实际客户端核验后才报告已加载。失败不撤销密钥成功、不回滚其他已完成项目。

## 开发者维护清单

指定清单是唯一检查对象来源。`kind/name` 组成稳定 ID，名称与分发实体一致；`source_repository` 是已核实的来源仓，支持已有说明中核实的镜像。`setup_guide/rule_template` 是目标安装根内的相对路径；模板继续由目标项目维护，Setup 不复制完整规则。`default_message` 使用具体任务示例及 `{agent}`。新增独立 Skill 使用 `kind=skill` 并核实独立安装根；Plugin 内的 Skill 由其所属 Plugin 条目覆盖，避免重复设置同一组规则。

增加/移除对象时同步验证安装识别、流程路径、三个宿主中的实际行为与展示；未知清单版本、重复身份或越界路径必须报错。用户安装状态、检查结论和提醒偏好不写回此文件。各目标的旧提醒配置及确认行为保持其原规则，本次不增加旧格式、旧别名或兼容分支。
