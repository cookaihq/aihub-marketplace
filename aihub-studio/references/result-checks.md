# 结果检查与错误反馈

这是 **AIhub Studio 的结果内容检查**：核对成品是否满足用户需求。五个 Skill 的新任务都使用本流程。`delivered` 只代表文件交付成功；`result_check.status` 单独表示需求检查结果。检查模块只调用理解接口，不调用生成接口，也不因为内容不符、检查失败或文件被修改而重新生成。

## 配置

以下均可省略，与当前 Skill 的 Key 使用相同读取层级，列表取最高非空层的完整值：

| 配置 | 默认值 | 行为 |
| --- | --- | --- |
| `AIHUB_RESULT_CHECK_ENABLED` | `1` | `0` 关闭语义检查；原有文件格式与可解析性检查继续运行。只接受 `0`/`1`。 |
| `AIHUB_RESULT_CHECK_PROVIDER` | `auto` | `auto` 由 Skill 先检查宿主实际媒体能力，能力不足才调用 AIhub；`host` 只用宿主；`aihub` 直接用 AIhub。 |
| `AIHUB_RESULT_CHECK_MODELS` | `gemini-4-hydrogen` | 逗号分隔精确 ID。提交前按当前 LLM 注册表的可见性和媒体能力选择首个适用项，提交后不自动换检查模型。 |
| `AIHUB_ERROR_REPORT_THRESHOLD` | `3` | 兼容旧配置，仍校验正整数；不再延迟首错报告与当前结果说明。 |
| `AIHUB_SUPPORT_URL` | 无 | 当前服务管理员的 HTTP(S) 支持入口，不含账号、密码、查询参数或片段。 |

理解主任务模型与结果检查模型分别配置；`AIHUB_UNDERSTANDING_MODELS` 不覆盖 `AIHUB_RESULT_CHECK_MODELS`。

`config-check` 返回这些字段的实际来源和格式错误；`doctor` 同时返回生效的检查与反馈设置。仍只有 `AIHUB_API_KEY` 必填。Jev 未接入，也不需要 TypeSafe 凭证。

## 保存需求和生成后的检查

1. 新任务 JSON 的 `original_request` 保存用户原文；`review_requirements` 可把它拆成具体项，每项为 `{"id":"subject","text":"只有一只橘猫","priority":"required"}`，偏好用 `preference`。程序始终增加完整原文检查项，不能只检查 Agent 自行选择的一小部分要求。用户批准改变需求时，`requirement_revisions` 按时间保存 `{"request":"修改后的完整需求","user_confirmation":"用户同意修改的原话"}`；只记录真实同意，不能为了让结果通过而修改原任务记录。
2. `run/continue` 下载成功后在 `run.json` 旁创建 `review.json`，保存原文、当前需求、检查项、产物 SHA-256、实际尺寸/时长/音轨、可提取的文本。程序先检查可测条件；有明确不符合直接报告 `mismatched`，不再消耗模型额度确认已知差异。时长允许最多 0.05 秒的容器时间舍入误差；宽高比数值误差须小于 0.01，明确像素尺寸严格相等。未定义数值规则的质量等要求由逐项媒体检查说明证据。
3. `auto/host` 通常返回 `pending`。Agent 使用当前会话实际可用的图片、音频、视频和文档工具打开产物，并核对编辑参考图、原录音或原 PDF。只有真正观察的范围才能写为完整。CLI 无法发现宿主工具，不能把 `pending` 当作检查完成。
4. 宿主能检查时，将真实观察写为下节 JSON，通过 `review-submit` 提交。宿主缺少必要能力且配置为 `auto` 时执行 `review --provider aihub`；若为 `host`，提交 `{"unavailable_reason":"缺少哪种实际读取能力"}`，不伪造观察结果。
5. `aihub` 路径先查 `/e/v1/configs/llm_generations_models`，再上传产物本身，通过 `/e/v1/llm/generations` 读取媒体和需求。`llm-custom` 请求将检查与严格 JSON 指令放在 `messages` 的 `system` 消息，用户消息携带需求、原媒体和现有输出文本；已测得的媒体时长随素材 ID 传入。模型应核对现有结果并报告差异，不重新转写或改写产物。该过程会把结果与原需求发送给 AIhub，并额外消耗额度。单次检查对全部产物共提交一次理解请求；上传请求另外记录，一般原始媒体输入使用生成任务保存的 URL；自动转写使用保存并绑定哈希的完整原录音快照，小文件上传快照，超过 20 MiB 时报告无法外部检查。
6. Agent 读取结果与逐项证据，同时交付文件和检查结论，按下节说明功能、实际状态和覆盖范围。检查开启时，每次结束检查后，无论通过、不符、证据不足或无法检查，都向用户说明 `user_notice` 中的关闭方式与影响，不能只留在 JSON 或文件里。`disabled` 不重复关闭提示。

## 向用户解释本次检查

把功能归属、检查结论和关闭方式放在一起，用当前任务的普通语言说明。程序摘要提供线索，实际检查项、模型和覆盖以本次记录及真实观察为准。

- **检查了什么。** 分清文件格式／可解析性检查、Agent 实际观察、外部 AIhub 模型复核；分别说明已完成项与未完成项。依据 `program_checks`、`report.findings`、`report.coverage` 解释结果；配置为 `auto`、存在音轨、提交了视频或返回 `matched`，都不能代替读取实际证据。抽帧只能支持所见帧，字幕和元数据不能证明连续画面、配音连贯或音画同步。
- **实际模型和状态。** 外部模型从 `external.model` 及 `external.result` 取得。仅选出候选、素材上传中或请求明确被拒时写“计划使用……，尚未成功提交”；有已受理任务时才写实际检查模型。提交结果不明时明确说明。未选出模型时写“尚未选出，未提交检查”，可另列 `model_selection.configured_models` 为配置候选；不能把默认值写成已调用。宿主检查或程序已发现差异时说明未调用外部检查模型。
- **关闭方式及影响。** 例如：“AIhub Studio 的结果内容检查用于核对成品是否满足你的要求。本次……。你可以说‘仅本次关闭 AIhub 结果检查’，或明确要求在当前项目、某个 Skill 或五个 AIhub Skill 中长期关闭。关闭后仍检查文件格式和可解析性，额外的内容需求检查关闭。”沿用用户已选范围，未明确的长期范围不自行扩展。使用外部 AIhub 模型会发送原需求和成品并额外消耗额度，在解释检查方式或用户选择时说明；沿用现有授权，不新加逐次付费确认。

已受理的 `external.result.model` 与计划的 `external.model` 不同时，优先说明服务实际返回的型号，另列计划值；`feedback.context.planned_model` 保留这一区别。服务没有返回实际型号时，按已提交记录说明已知范围，不凭默认值补写。

结合任务选择真实适用的检查项，不把下表当作已完成清单：

| 任务 | 可说明的内容检查项 |
| --- | --- |
| 图片生成／编辑 | 主体、文字、构图，以及参考图中要求保留的部分 |
| 视频 | 画面内容、配音是否连贯、字幕是否正确及与画面／声音同步；披露未观看／未听取的时段 |
| 语音／转写 | 朗读内容、顺序、发音或转写与原录音是否对应；披露未听取的片段 |
| 音乐 | 用户要求的人声／纯音乐、歌词、风格和结构；只有实际听过的范围才有听审结论 |
| 素材理解 | 回答是否受原素材支持、是否遗漏要求，实际读取的页、画面或音视频时段 |

检查失败时同时说明已有文件可用性、失败步骤、具体错误、检查覆盖和恢复办法，遵守 [调用异常反馈与本地报告](error-reports.md)。`stage`、`failure`、`external.result` 和 `feedback.context` 保留这些线索；错误中的具体 `message` 需读取并解释与本次任务有关的部分，不把整个原始响应贴给用户。模型清单筛选的 `listed` 和 `missing_capabilities` 只表示本次查询结果与媒体能力声明，不证明 Key 的模型调用授权。

```bash
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" review --skill "${AIHUB_CALLER}" \
  --record "/任务目录/data/aihub-studio/20261106143025-任务摘要-run-a1b2c3d4/run.json"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" review-submit --skill "${AIHUB_CALLER}" \
  --record "/任务目录/data/aihub-studio/20261106143025-任务摘要-run-a1b2c3d4/run.json" \
  --review-file "/任务目录/实际检查报告.json" --review-token "<review 返回的 token>"
node "${AIHUB_PLUGIN_DIR}/scripts/aihub.mjs" review --skill "${AIHUB_CALLER}" \
  --record "/任务目录/data/aihub-studio/20261106143025-任务摘要-run-a1b2c3d4/run.json" --provider aihub --wait-seconds 30
```

图片报告示例，仅在实际观察后填写；全部检查项都必须出现：

```json
{
  "findings": [{
    "requirement_id": "original-request",
    "verdict": "matched",
    "evidence": [{"asset_id": "artifact-1", "observation": "主体只有一只橘猫，围巾为红色", "location": "图片中央"}]
  }],
  "coverage": [{"asset_id": "artifact-1", "complete": true, "note": "已查看整张图片"}]
}
```

额外需求 ID 为 `user-<id>`。证据引用 `review` 返回的产物/原素材 ID，不能编造 ID。每个被声明完整检查的素材都应有具体证据。音频/视频 coverage 还需 `time_ranges: [[0,5]]` 和实际检查音轨后的 `audio_checked: true`；抽帧不能写成连续完整观察，未观察片段必须披露，覆盖不足保持 `inconclusive`。不能仅靠 prompt、文件名或生成模型自述作证据。

| 检查状态 | 对用户的含义 |
| --- | --- |
| `matched` | 所有检查项符合，已报告完整素材覆盖；仍是 AI 判断，不是绝对正确性保证。 |
| `mismatched` | 程序或实际媒体证据发现差异，说明具体要求和实际结果，由用户决定是否修改或重做。 |
| `inconclusive` | 覆盖、证据或报告格式不足，无法判断所有要求是否满足。 |
| `unavailable` | 无法读取实际产物、模型不可用、检查请求失败等；交付已有文件并说明原因。 |
| `disabled` | 用户关闭语义检查，只报告实际执行的文件检查。 |
| `pending` / `checking` | 等待宿主报告 / 远端检查尚未结束，继续原检查流程。 |

## 恢复和限制

检查 token 同时绑定本次检查、需求版本、检查项和产物哈希；文件变化、报告过期、未知检查项或无证据的“通过”会被拒绝。继续生成任务时会返回保存的检查结论，不会再次提交检查。`checking` 通过 `review` 查询原任务；检查提交结果不明时不得重发。明确要求重新检查且前次已结束时才传 `review --recheck`，旧记录保存为 `review-history-*.json`；它可能产生新的检查费用，不能把该参数加到默认恢复命令中。

AIhub 检查上传实际产物以对应本地哈希，单个产物及转写的完整源录音沿用 20 MiB 上传限制；超过时报告 unavailable，不能偷偷缩小/截断后声称完整检查。当前文档读取支持 ZIP 中的 Markdown、文本、LaTeX 及 DOCX 正文提取，最多 512 个 ZIP 条目、32 MiB 压缩文件、2 MiB 被读取文本。压缩包仅在内存中读取，不解包任意路径到磁盘。正文提取不能证明页面布局、嵌入图片和公式保真，AIhub 文档检查因此不会仅凭正文给出整体 `matched`；宿主可实际打开/渲染后提交相应证据。

旧 `generate/understand/native-music/resume/task` 记录缺少用户原始需求，程序返回 `unavailable` 和关闭提示，不能把旧 prompt 当原始需求补写。五个 Skill 的新任务必须用 `plan/run`。`review.json`、任务记录和报告保留在调用项目任务目录，供跨轮恢复，不写安装目录；由用户决定何时删除。

## 已交付转写的检查凭证恢复

Studio 6.6.0 / Audio 6.5.0 提供 `review-recover --skill aihub-audio --record <原run.json> --reason <用户选择新检查凭证的实际原因>`。只在用户明确授权新凭证检查已交付转写时使用；它离线验证原 run/plan、转写身份与准备绑定、保存的检查以及源/产物哈希，追加私密恢复审计，保留原 ASR 的凭证和全部记录。原 Key 不必仍然可用，也不迁移或保存新 Key。参数中的原因不得包含密钥。

获得 `review_recovery_ready` 后，显式 `review --recheck` 才归档已结束的旧检查并绑定当前凭证创建新检查；未传该参数仍读取已结束的旧结论。新检查中的远端任务只能由它自己的凭证继续，原 ASR 身份不能代为查询。`pending`、`checking`、上传中、待提交或提交结果不明的检查禁止替换；关闭检查不会使其成为可替换状态。文件改变或缺失、服务/Skill 不符、ASR 未交付同样拒绝，保留受阻审计。

获得授权的 `continue` 只读取核验通过的本地 ASR，适用时恢复当前凭证自己的检查；不会查询、下载、确认或重新提交旧 ASR。通用任务的原凭证保护保持有效，不能编辑账本或身份字段代替公开恢复。具体 Windows 命令和上层工具版本要求见[转写恢复步骤](audio-transcription.md#已交付转写更换检查凭证)。

## 用户通过对话关闭或开启

- 用户说“仅本次关闭结果检查”：后续本次 AIhub 命令通过进程环境传 `AIHUB_RESULT_CHECK_ENABLED=0`，不写配置文件；本次恢复命令也沿用。用户说“恢复结果检查”时用 `1`。
- 用户明确要求长期关闭、当前项目关闭或只对一个 Skill 关闭：Agent 运行 `config-check` 找实际来源，按用户已选范围将该字段写成 `0`，保留其它字段。长期共享默认路径是 `~/.config/aihub-studio/.env`；当前项目默认使用 `.env.local.aihub-studio`，普通 `.env.local` 仍可选择。已有更高优先级字段时说明它覆盖什么，并修改用户授权范围内真正生效的位置，不能另写低优先级文件后声称已关闭。写入含 Secret 的文件时继续遵守原有未跟踪/已忽略检查；不展示 Key。
- 用户只说“关闭结果检查”且范围未确定：询问“仅本次、当前项目，还是以后五个 AIhub Skill 都关闭”，沿用已明确的范围，不再次确认。完成后回读 `config-check` / `doctor`，告知作用范围、实际来源和已生效的 `0`。不要要求用户自己手改文件。

关闭检查不会取消已提交的远端检查任务，也不代表费用退还；保留其记录，之后开启可查询原任务。

## 错误反馈

所有五个 Skill 读取并遵守[调用异常反馈与本地报告](error-reports.md)：首错保存，跨轮更新同一报告；向用户先解释当前结果、检查范围、影响和下一步，排障材料按需提供简短入口。客户端 HTTP 与异步状态、上游实际暴露的证据分别说明；旧固定 200 不作为 HTTP 证据。公开草稿与私密本地报告分开，报告保存失败不改变业务结果或重试策略。
