# ElevenLabs 音色设计与创建

这是 `aihub-audio` 的新音色场景；预置音色查找仍走[预置音色库](elevenlabs-voices.md)。Gateway v0.9.17 已于 2026-11-14 部署两款模型，接口、价格和公开文档均已生效。保留现有 TTS、Dialogue、ASR 默认、个人模型配置和显式选择，不恢复旧 `audio-clone` 或克隆占位配置。

## 流程与费用

必须依次执行 **Design → 展示全部候选供试听 → 用户明确选择 → Create**。用户选择前完成候选交付并等待；不能默认选第一个、自动创建全部候选或把试听当作已创建音色。参考音频只用于音色设计，不承诺专业克隆或精确复刻；仅使用本人或已获授权素材。

| 阶段 | 模型与接口 | 费用和输出 |
| --- | --- | --- |
| Design | `elevenlabs-voice-design`；`POST /e/v1/audios/generations` | USD 0.08 / 1000 个实际响应试听文本的 Unicode 字符，整段计费一次，不乘候选数量；沿用分组倍率。自动文本先预扣 1000 字符，再按实际响应结算 |
| Create | `elevenlabs-voice-create`；同一接口 | 免费，保存用户选中的候选，返回完整音色对象和真正可合成的 `voice_id` |

服务地址固定 `https://api.aihubmax.com`；两阶段均按返回的 task ID 使用 `/e/v1/tasks/{task_id}` 查询。候选 `generated_voice_id` 不能直接用于 TTS。Create 是保存候选，不是再做一次 Design。

## 1. Design 并交付全部候选

从实际业务项目执行，按[任务保存与产物页面](artifacts.md)准备任务与可靠身份。请求示例：

```json
{
  "operation": "audio-voice-design",
  "original_request": "设计自然温暖的中文旁白音色，先试听所有候选，再由我选择保存。",
  "requirements": {
    "voice_description": "自然、温暖、清晰的成年中文旁白声音，适合长篇知识讲解。",
    "auto_generate_text": true
  }
}
```

省略 `model` 时照常尊重个人模型列表，没有列表才选内置 Design。个人列表没有此用途时不自动追加或改写，用户本次明确型号时才填 `model`。用 `plan` 检查，`run --request-file <请求JSON> --output-dir <业务任务根> --wait-seconds 30` 提交，后续 `continue --record <返回的run_record>`；均带 `--skill aihub-audio`，Windows 使用 `scripts/aihub.ps1`，其他环境使用 `node scripts/aihub.mjs`。

`voice_description` 去首尾空白后 20–1000 字符。Design 固定 v3，**不接受 `quality`**。试听文本二选一：`auto_generate_text=true` 时不提供 `text`；手填 `text` 为 100–1000 字符，可省略或关闭 `auto_generate_text`。不使用请求的 `prompt` 字段。

可选 `reference_audio_base64` 为音频文件的**裸 Base64**，不接受 URL 或 Data URI。由确定性程序读取已授权文件编码，不在对话回显完整 Base64；素材可读不代表已授权使用其声音。其他可选参数：`prompt_strength` 0–1、`loudness` -1–1、`guidance_scale` 0–100、`seed` 整数 0–2147483647、`should_enhance` 布尔。未指定不主动填默认，false/0 保留，完整字段可用 `describe` 查询。

完成后读取 `result.voice_design.text` 和**全部** `result.voice_design.previews[]`；每项保留实际候选 ID、原始元数据，并有 `candidate_number` 和下载成功的 `file`。原始 `results[0]`、空对象、空列表、null、0 等保留在结果 JSON 与任务记录，不编造缺失字段、时长或费用。仅解码成功不等于用户已听审。

按返回顺序向用户列出所有候选编号、ID、可点击音频链接和实际试听文本，并打开既有产物页面供播放。任务还生成候选说明 Markdown 和原始结果 JSON。页面按原入口重开，不创建另一套配置或自定义音色列表。有下载失败则继续原 run/task 取文件，不重新 Design。用户尚未试听全部候选或未明确选择时不提交 Create，不伪造选择确认。

## 2. 明确选择后 Create

取得用户明确选择后，保存选择文件。候选数量以真实返回为准，不固定为三个；下方所有 ID 必须替换为本次真实值。`--record` 使用返回的 **`result.record` / `task.json`**，不是 `run_record`。

```json
{
  "design_task_id": "此次Design任务ID",
  "generated_voice_id": "用户明确选中的候选ID",
  "auditioned_generated_voice_ids": ["候选1真实ID", "候选2真实ID", "候选3真实ID"],
  "user_confirmation": "用户试听全部候选后的实际选择原话",
  "voice_name": "温暖中文旁白",
  "voice_description": "自然、温暖、清晰的成年中文旁白声音，适合长篇知识讲解。",
  "labels": {"language": "zh"}
}
```

`voice_name` 非空，`voice_description` 去首尾空白后 20–1000 字符；`labels` 可省略或 null，提供时为字符串键值对象。名称和描述沿用用户要求，重要信息缺失时补充询问，不用占位值提交。

```text
voice-create --skill aihub-audio --record <Design的task.json> --selection-file <selection.json> --wait-seconds 30
voice-create --skill aihub-audio --record <同一个Design的task.json> --wait-seconds 30
```

第一条校验来源任务、服务与凭证、全部本地音频、完整试听名单、所选 ID 和确认，保存选择后提交。通用 `generate` 不允许直接 Create。第二条只恢复已有 Create，不能改候选自动全部创建。选择证据仅在本地保存；上游只收到模型、名称、描述、所选 ID 和可选标签。

本地锁防止同一记录并发重复提交；它不等于跨机器幂等协议。任务指针提交前保存，结果未知时保留 `submission_unknown`，有 task ID 时只查询原任务；无 task ID 则先对账，不重发。远端失败保持失败，不自动换模型、重新 Design 或重发 Create。每个候选只能成功创建一次且可能过期。容量恢复后的新尝试须明确安排并保留旧证据，不手改旧记录伪造未提交。

## 3. 交付并自行保存 ID

只有完成且返回非空 `voice_id` 才报告创建成功。交付完整音色 JSON、保存 ID 提醒 Markdown、真实 `voice_id` 和任务 ID。醒目、逐字提醒：

**生成的 `voice_id` 请自行妥善保存。平台不提供音色列表、音色查询或 ID 找回功能。**

任务查询仍可用，不将其宣传为音色查询或 ID 找回。用户要求后续合成时，显式选 `eleven-v4-text-to-speech-custom-voice` 或 `eleven-v4-text-to-dialogue-custom-voice`，使用创建后的 `voice_id`；不能用候选 ID，不能自动修改默认音色、收藏或模型列表。

2026-11-14 边界：上游容量 30/30，Gateway 本轮 Create 两次失败且零费用；本轮 Create 和新音色 TTS 尚未成功复验。历史直连 Design/Create 和中文 TTS 成功，用户已允许按该逻辑继续适配发布，待容量恢复补测。不能把夹具、历史成功或正式部署写成当前生产 Create/TTS 成功。

权威合同：[Design](https://docs.aihubmax.com/pages/zh/api-manual/audio-series/elevenlabs/elevenlabs-voice-design)、[Create](https://docs.aihubmax.com/pages/zh/api-manual/audio-series/elevenlabs/elevenlabs-voice-create)，及同站 `/openapi/zh/{model}.json`。费用展示以真实 `task.usage` 为准，不把预扣当最终账单。
