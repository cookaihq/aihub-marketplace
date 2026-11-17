# 大文件转写与恢复

`audio-transcribe` 的 `inputs.audios` 接受本地路径和 HTTP(S) URL；路径相对执行 CLI 时的工作文件夹解析，run 保存绝对路径。将原文件直接交给 `plan/run`，由程序在确定实际候选后处理，不由 Agent 固定时长切片。TTS 和其他任务的输入契约不变。

指定 `scribe-v2` / `scribe-v3` 时先读并遵守 [ElevenLabs 合同](elevenlabs.md#scribe-转写)，使用一个完整输入；以下分段、转换和合并流程仅适用于 Paraformer。

```json
{
  "operation": "audio-transcribe",
  "original_request": "完整转写录音，保留时间戳并区分说话人。",
  "inputs": { "audios": ["D:/录音/访谈.wav"] },
  "requirements": { "diarization": { "enabled": true } }
}
```

## 实际候选的约束

| 候选 | 模型文件限制 | 参数差异 |
| --- | --- | --- |
| `paraformer-v2`（默认） | 单文件 2 GB、12 小时；支持的容器见 `plan.candidates[].transcription.formats` | `channel_id`、`diarization`、`language_hints`、`recognition` |
| `paraformer-8k-v2` | 同一接口的文件限制；8 kHz、中文 | 不接受 `language_hints`；需要时重采样为 8 kHz，保留声道编号 |

来源：[AIhub Paraformer OpenAPI](https://docs.aihubmax.com/openapi/zh/paraformer-v2.json)，2026-10-28 核对。`cohere-transcribe` 尚无已核实的自动处理映射，本流程明确拒绝；Scribe 按上述独立合同处理，不能借用 Paraformer 的限制。

本地发送使用既有 `/e/v1/files/upload/base64` 适配器，**20 MiB 是客户端上传上限**，不是所有模型的服务端限制。URL 能整段提交时直接传原 URL，不套用本地上传上限。程序先下载 URL 快照以测量并保留原音频；网络失败在提交前停止，可继续读取。URL 内容应在整个任务期间保持不变。

`plan` 不联网，展示精确候选的契约；`run` 探测音频并给出实际分段。候选切换时重新检查模型约束、采样率、格式、大小与时长，复用已保存源快照，不用新配置或修改后的原文件替换录音。用户指定模型仍固定，既有 fallback 策略继续生效。

## 音频处理

需要 PATH 中可真实执行的 FFmpeg 和 ffprobe，不下载本机模型或权重。程序保存源快照，探测实际容器、时长、采样率与声道。整段满足模型及当前上传通道时直接处理；需转换或分段时输出保留声道的 PCM WAV。

生成的分片按大小和时长上限的 90% 规划，再实测字节数、时长及连续覆盖。预计边界前最多 60 秒的真实波形按 20 毫秒计算每声道短时能量，优先选较长停顿；没有合适停顿时选低能量点，边界两侧各保留 0.4 秒重叠。波形不保证语义句末。多音频流文件先报告需要明确拆出音轨，不静默丢弃其他流。

每个源最多 8 GiB，需预留源快照和 PCM 分片的空间。下载有总时间预算；每个源分段处理预算 30 分钟、最多 10,000 片，耗尽在付费转写前停止。分析内存随边界窗口和声道数增长，不随录音总长度增长。整段直接传输只需不超硬上限，生成分片才应用余量。

## 记录与恢复

`run_record` 是统一恢复入口。`audio-sources/sources.json` 和源快照保存在 run 目录下；`attempt-N/transcription.json` 保存当前模型契约、源与分片哈希、边界、上传结果及各片段 `task.json`。原始结构化结果保留在对应片段任务目录。

每段上传前落盘意图，禁用服务端自动清理其他素材。`upload_unknown` 或中断遗留的 `uploading` 不自动重新上传。每段生成前落盘任务记录；`submission_unknown` 不重复付费。查询/下载失败只恢复原任务，已完成片段不再次提交。`--wait-seconds` 是本轮共享等待预算；用同一个 `continue --record ...` 继续。

| 状态 | 处理 |
| --- | --- |
| `preprocessing_failed` | 修复工具、磁盘、格式、声道或源文件问题后继续原 run |
| `submitted` / `waiting` / `query_failed` / `download_failed` / `partial` | `continue` 恢复已有片段任务 |
| `upload_unknown` / `submission_unknown` | 保留记录，核对远端是否接受；没有可靠证据前不重发，不另建 run 绕过 |
| `upload_rejected` | 上传明确被拒，停止计划，先处理实际拒绝原因 |
| `merge_failed` | 保留原结果和任务编号，修复结果读取/时间戳问题后继续，不重新转写 |
| `transcription_failed` | 已有其他片段成功，本片段终止失败；停止并保留部分结果，不重付成功片段来替换整次候选 |

尚无成功片段且原策略允许的明确模型错误，才能进入下一候选。源变化、查询/下载错误、上传不明、合并或语义检查失败均不触发替换模型。

## 合并与检查

交付 `merged/transcript.txt` 和 `merged/transcript.json`，按源文件顺序合并所有结果。全局时间轴把前序源文件时长及片段起点加到返回的毫秒时间戳上，合并文件统一使用秒；原结果保留原单位。未返回时间戳的文本明确标记，不伪造时间。服务端全文与逐句列表不一致时保留完整全文、独立的 `sentences` 时间戳和 `text_alignment=unverified`，不把不完整的句子列表当成全文，也不宣称这些时间戳已对齐全文。

重叠先按实际重叠区间、文字和时间去重；没有可用词时间时仅消除边界精确重复，不能全篇删同句。无法可靠匹配时保留两侧并提示复核，删除记录在 `duplicates`。说话人标识包含源、片段、声道；`speaker_alignment=fragment-local` 表示同号 speaker 不能证明跨片段为同一个人。

结果检查读取完整源快照及产物。转写成功、分片覆盖校验或抽听均不代表全量语义检查通过。`review.sources` 给出原录音路径、哈希和时长；完整覆盖要求实际听过的完整时间区间及 `audio_checked`。AIhub 检查上传器仍有 20 MiB 上限，完整原录音超过时报告 `unavailable`，由宿主检查并披露观察范围。

## 已交付转写更换检查凭证

用户明确选择新凭证继续检查时，先在原业务工作目录通过正常加载器确认当前凭证来源，不显示或复制 Key。使用同一个 `run.json` 执行下列公开流程；不编辑任何身份字段，不创建新转写。原 Key 可以不可得，但原 run、转写记录、已结束的 `review.json`、完整源快照和全部输出必须仍在原位置且可验证。

```powershell
$aihubPlugin = '<实际 Studio 6.6.0 或兼容新版的完整安装目录>'
$asrRecord = '<原 run.json 的完整路径>'
& "$aihubPlugin/scripts/aihub.ps1" review-recover --skill aihub-audio --record $asrRecord --reason '用户已明确选择当前凭证继续检查已交付转写'
if ($LASTEXITCODE -ne 0) { throw '恢复未获准；保留记录，先处理返回原因。' }
```

成功返回 `review_recovery_ready`。这一步离线核验并追加 `review-recovery.json`：记录时间、原因、原 ASR 身份与当前检查身份的不可逆标识、run/plan 绑定，以及源、输出和转写记录的哈希；不保存 Key，不替换原 `credential_id`。受阻尝试也追加原因与已读取的身份。审计文件属于私密本地记录，不能直接公开分享。

用户已明确要求新检查且前次确定结束后，再执行：

```powershell
& "$aihubPlugin/scripts/aihub.ps1" review --skill aihub-audio --record $asrRecord --recheck --provider aihub --wait-seconds 30
```

该步骤可能上传源录音并产生新的检查费用。旧检查原样保存为 `review-history-*.json`，新检查单独绑定当前凭证；`checking` 时省略 `--recheck`，用 `review` 继续同一检查。结果仍可能为 `mismatched`、`inconclusive` 或 `unavailable`，不得改写转写来制造通过。只读历史结论时不传 `--recheck`。

随后 `continue --skill aihub-audio --record ...` 在每次读取时验证恢复授权和原文件，仅返回已交付的本地 ASR 与适用的检查状态；它不会让新凭证查询、下载或重发旧 ASR，也不接受 ASR 的 `--confirm`。`resume/task` 等远端恢复仍要求原身份。缺失或变化的文件、服务/Skill 不符、ASR 未完成、检查 pending/checking、上传或提交不明均阻断换凭证；这些状态须先按原协议处理。

上层工具还须接受所装 Studio 的版本与本地转写契约；本入口不会自动修改调用方的版本门或业务账本。完整约束见[结果检查恢复](result-checks.md#已交付转写的检查凭证恢复)。
