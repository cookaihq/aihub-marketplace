# 默认 Skill 检查与提醒

## 何时执行

每次会话首次使用本 Plugin 的任意 Skill 时执行一次；后续 Skill 转交、分页、恢复和再次调用不重复询问。用户明确要求检查、重新开启提醒或设为默认时仍处理该请求。检查是当前任务的附带步骤，优先继续原任务；可以在交付结果后附上选择，或使用宿主的异步提问能力。用户未回答不写文件，不阻塞业务操作。

当前任务禁用全局配置时直接跳过本流程，不读取或写入任何提醒偏好或宿主全局规则。未知 Agent、规则不可读、辅助程序不可用或设置损坏时报告检查未完成，继续原任务；不把未知误判成缺少默认规则，不覆盖损坏文件，不为修复检查而运行独立 WorkBuddy/CodeBuddy CLI。

## 读取当前 Agent 和偏好

从当前会话确认 Agent 是 `codex`、`claude-code`、`workbuddy` 或 `hermes`，然后直接执行下面的只读 `check`。程序在内部读取规定的配置目录变量，返回实际目录；不要先扫描 home、其他 Agent 的目录或凭证文件，也不要运行 `env` / `printenv`、打印全部进程环境或读取业务 `.env`。检查不需要凭证。已有明确的非默认宿主配置目录时用 `--config-dir` 传入绝对路径。

读取结果后，按当前宿主上下文核对 `config_dir`。远程、容器和 WSL 使用实际执行环境，不能套用另一台机器的路径。WorkBuddy 配置目录变量冲突时，程序会停止此项检查；只核对这两个目录值和当前宿主配置，不扩大读取范围。仍无法确定时报告未知，继续主任务。

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" default-skills \
  --skill <当前五个 Skill 之一> --agent <当前Agent>
```

`AIHUB_PLUGIN_DIR` 为当前 Skill 所属的实际完整 Plugin 目录。

`--action` 省略时为 `check`。命令只做本地检查，不需要 API key、不联网、不写规则。`status=dismissed` 时不提醒；`review_required` 表示需要下面的语义核对，不表示缺少规则。`session_loaded=not_verified` 不能改口说已经生效。检查不会创建 settings.json。

## 核对规则是否已经生效

1. 读取当前会话实际适用的全局与项目规则。辅助程序返回候选文件、选定的全局主文件、真实路径以及建议规则。它不解析自然语言、imports 或全部项目覆盖，最终结论由当前 Agent 阅读实际规则后作出。
2. Codex 核对实际配置目录的首个非空 `AGENTS.override.md` / `AGENTS.md`，再沿项目加载链检查覆盖、配置的 fallback 文件和上下文预算。Claude Code 核对 `CLAUDE.md`、`rules/`、imports、项目/本地规则及托管策略。WorkBuddy 核对当前配置目录的 `CODEBUDDY.md`、`rules/` 和项目 `CODEBUDDY.md` / `AGENTS.md` / `.codebuddy/`，并核对版本与启用条件。Hermes 核对当前 Profile 的 `SOUL.md`，并核对项目上下文：`.hermes.md` / `HERMES.md` 优先，其次是 Git 根到 cwd 的 `AGENTS.override.md` / `AGENTS.md` / `agents.md` 链，再次是 cwd 的 `CLAUDE.md` 等。候选路径不是实际加载证明。
3. 判断现有文字是否已经明确表达本 Plugin 的相关任务默认使用其具体 Skills，并实际按其 AIHub 流程执行，包含复合任务中的适用子任务。语义等效的手写规则也算，不要求相同标记或逐字一致；仅出现 Plugin 名、安装说明、示例或被禁用/覆盖的规则都不算已生效。已有旧版默认规则时按其实际文字说明已覆盖范围和新版差异，不把缺少新版措辞当作完全未设置，也不在本次业务任务中重复要求设为默认；用户明确要求升级规则时直接更新，完成后展示实际内容及差异。
4. 有等效规则且当前任务适用时不询问。只在项目生效时说明范围，不重复追加项目规则；如需跨项目默认，提供全局设置选择。有相反规则、部分覆盖、重复规则块或无法确认加载时解释具体文件与冲突，不自动覆盖。
5. 确认没有适用默认规则、提醒开启且本会话尚未提示时，在原任务结果之后提供下面的固定菜单。说明本次 Plugin、当前 Agent、全局作用范围及实际发现的共享文件影响；选择“设为默认”即授权设置这些对象。同一会话同一 Plugin 最多提示一次，沿用用户已作出的跳过、关闭提醒或本轮不要询问的选择。

### 默认设置菜单

1. **设为默认 (推荐)**
2. **本次跳过**
3. **不再提醒**

第一项固定为推荐项，保持上述顺序；使用宿主选项工具时采用相同文案和顺序。选择后直接设置，完成后展示完整内容和位置。未答复或界面预选均不构成设置授权。

## 用户选择之后

- **设为默认**：读取 [完整建议规则](default-skills-rule.md)，核对实际目标文件和已说明的影响范围，直接执行设置，不再要求预览确认。说明规则要求通过 AIHub 实际执行适用任务及复合子任务；需要其他执行通道时沿用用户对本任务的明确选择或授权。普通对话、代码、搜索、图表、截图和通用 Office 创作不强行路由，确定性辅助处理与按 Skill 流程进行的宿主结果检查继续使用适用工具。使用宿主实际加载的全局入口；全局文件不存在时确认该宿主会读取此入口再创建。检查 symlink，同一实体只编辑一次并保留链接；多个 Agent 共享实体时，沿用菜单中已说明且用户选择的共同影响；新发现超出该范围的影响时仅暂停受影响项并说明原因。
- 用户选择“设为默认”后，重新读取目标及相关覆盖规则，写入一个带 Plugin 标记的规则块。已有等效规则就不写；已有本 Plugin 块且用户要求更新时只更新该块，不追加第二份。保留其他内容、手工规则和 symlink，不写安装缓存路径或业务密钥。文件发生变化时重新检查；范围及选择仍有效就继续，出现实际冲突或超出授权范围时说明具体问题。跨轮恢复先核对实际文件，已完成项只核验；沿用可核实的选择继续未完成项，不重复询问。缺少选择记录时先恢复对应菜单，不能从“提醒已关闭”或旧版的预览请求推断设置授权。
- 回读文件核对内容，并在结果回复中展示实际写入的完整规则、文件位置和影响范围；已有等效规则时展示核实到的内容。规则通常在新会话加载；当前 Agent 通过实际规则查看入口或新会话验证后才能说已生效。在验证前报告“已写入，待宿主加载验证”。规则中的 Skill 名是稳定逻辑名，调用时使用当前 Skill 列表中的实际完整标识；不为所有宿主拼造同一种前缀语法。未安装或能力不匹配时说明原因，不承诺一定调用。
- **本次跳过 / 未答复**：不保存任何偏好，本会话不重复询问，下次会话仍可检查。
- **不再提醒**：得到此选择后执行上面的同一命令并加 `--action dismiss`；它只保存关闭提醒，绝不写入默认规则。回读输出确认 `reminder_enabled=false`。
- **重新开启提醒**：用户明确要求时加 `--action enable`，确认 `reminder_enabled=true`，再核对规则。关闭/开启提醒不删除或改变已写入的默认规则；取消默认优先级需要用户另行要求，再检查实际规则后修改。

## 提醒偏好的保存范围

唯一来源是运行用户的 `~/.config/aihub-studio/settings.json`，不从环境变量、项目 `.env*`、普通 Skill 配置、旧 Plugin 别名或安装目录读取这个偏好。文件使用 `default_skill_reminders.version=1`，其 `agents` 列表每条包含 `agent`、解析 symlink 后的实际 `config_dir` 和布尔 `enabled`；无记录时默认开启。

同一用户、同一 Plugin、同一 Agent 配置目录的全部 Skill 与后续版本共用一条记录；不同 Agent 或配置目录分别保存，另一个 Plugin 独立。设置程序保留未知字段和其他 Agent 的记录；tikin 的已有 `routing` 同样保留。读取无副作用；保存使用文件锁、并发变更检查及原子替换，遇到损坏或未知格式不覆盖。残留锁只在查明没有程序正在保存后才能移除。更新 Plugin 不删除个人设置。

macOS/Linux 按实际运行用户的 home 定位；Windows 原生用实际运行时用户目录，WSL 使用 Linux 用户目录，不跨环境读取。AIhub 的 Node 程序和 tikin 的共享 Python 请求、配置及端点搜索入口支持原生 Windows 路径；脚本检查与各宿主业务验收分别记录。`--no-global-config` 会跳过本项读取，并拒绝保存；不要绕过它打开 settings.json。

## Hermes 入口与 Profile

使用当前 Hermes local backend 的实际 cwd 和进程环境；从 `skill_view("<plugin>:<skill>")` 返回的路径定位完整 Plugin。启用后的 Skill 进入当前版本的 `skills_list` 和可用技能索引；显式加载与自然触发分别核对。安装与更新见同包 README。缺业务 Key 时复用本 Plugin 配置中心，保留真实 caller、cwd 和原任务提交状态。

提醒按实际 `HERMES_HOME`（或明确的 `--config-dir`）隔离，规则目标是其中的 `SOUL.md`；macOS/Linux 默认 `~/.hermes`，当前 Windows 默认 `%LOCALAPPDATA%/hermes`，默认目录还遵循 `HERMES_DATA_DIR_SUFFIX`。自定义/非默认 Profile 必须传当前实际目录，不从默认目录猜测；不要将 Hermes 全局规则写入 `~/.hermes/AGENTS.md`。保留 SOUL 原有人格与其他规则，只追加获授权的 Plugin 块；当前 Profile 的范围不等于全部 Profile。业务 Key 仍使用运行用户的 `.config/<plugin>/` 分层，与 Profile 的提醒和配置任务分开。

## 宿主依据

- Codex：[AGENTS.md 规则加载](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。
- Claude Code：[memory 与规则](https://code.claude.com/docs/en/memory)。
- WorkBuddy：核对本机桌面运行时 `SkillExtensionLoader.parseSkillFile` 和 `MemoryLoader.loadUserMemories`；Skill 逻辑名来自 frontmatter，描述包含 Plugin 来源，全局规则为实际配置目录内的 `CODEBUDDY.md`。其他版本仍需核对真实加载，不把安装卡片或静态文件存在当成会话验收。

- Hermes：[Plugin Skills](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/)、当前安装的 `hermes_constants.py`、`agent/prompt_builder.py`。核对实际版本和当前 Profile；文件保存与新会话加载分别验收。
