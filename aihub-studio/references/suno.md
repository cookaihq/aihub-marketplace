# Suno 创作场景与参数

默认模型为 `suno-v6`；`suno-v6-wild`、`suno-v6-mini` 可由用户明确指定或配置。当前合同来源：[AIhub Suno](https://docs.aihubmax.com/openapi/zh/suno-music-generation.json)。请求统一提交到 `/e/v1/audios/generations`，旧 `suno-v4` 目录不能替代新合同。

| 场景 | operation | prompt 映射 | 固定意图 |
| --- | --- | --- | --- |
| 按描述生成歌曲 | `music-description` | `prompt`，最多 3000 字符 | description，人声 |
| 已有歌词谱曲演唱 | `music-lyrics` | `lyrics`，最多 5000 字符 | custom，人声 |
| 纯音乐／背景配乐 | `music-instrumental` | `style`，最多 1000 字符 | custom，纯音乐 |

输入必须非空白。歌词保持用户原文，不代写后冒充原文；用户允许改写时才使用 `requirements.rewrite_lyrics=true`。`requirements` 不能与场景的 mode / is_instrumental 冲突，也不能重复提供 prompt / lyrics；纯音乐的 style 来自 prompt。不接受未映射的参考素材。

```json
{
  "operation": "music-lyrics",
  "original_request": "请用这份歌词生成一首温暖的民谣，保留原词",
  "prompt": "[Verse]\n远方的灯还亮着\n[Chorus]\n我们沿着河流回家",
  "requirements": {
    "style": "warm acoustic folk",
    "title": "沿着河流",
    "rewrite_lyrics": false,
    "duration": 60
  }
}
```

`duration` 是可选的 10–360 整数秒目标，省略不补时长，实际曲长可能不同。`title` 最多 80 字符。`vocal_gender` 仅适用人声，接受 Male / Female / m / f，提交时归一化为 m / f；不保证绝对遵循。`style_weight` 和 `weirdness_constraint` 必须为 0–1 有限数，显式 0 保留，不主动注入。`style_variation` 可选 off / normal / high / extra / max；这些是偏好，不是音质保证。`negative_prompt` 为排除偏好文本。

`rewrite_lyrics` 仅 custom 人声可传；description 和纯音乐连 false 也不接收。`max_mode` 仅 custom 可传，description 连 false 也不接收；true 的任务价格为标准两倍，不自动开启。Suno Mini 的 description 不接受显式 duration / title / style / vocal_gender / style_weight，包括 null、0 和空值；须由用户调整请求，不能删去要求后提交。

`output_format` 可选 mp3 / m4a / wav，省略由服务使用 mp3。不对返回音频做静默格式转换。一次任务可返回一首或两首独立音轨，分别保存与交付；每项的 audio_url / url 是同一音轨的别名。曲名、歌词、用量和原始任务结果按实际返回保存；计费按实际成功音轨及账户分组倍率结算。链接保存期限由服务存储决定，完成后及时下载，不承诺固定有效期。

已有任务只查询、恢复和补下载，不为补齐第二首或下载失败重新生成。使用 `plan` 检查场景与参数，按原有任务／付费授权流程执行 `run`，不另加确认门。
