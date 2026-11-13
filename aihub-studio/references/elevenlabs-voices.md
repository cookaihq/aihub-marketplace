# ElevenLabs 预置音色库

用于获取预置音色、筛选、试听、选择和收藏。获取目录使用 AIhub `GET /e/v1/configs/elevenlabs-preset-voice-id`，复用音频 Skill 的配置链和 Key；文档说明目录查询不扣 quota。清单不是模型／账户权限白名单，仍需在业务提交时核对可用性。

先按[统一配置中心](credential-setup.md)中的实际启动命令打开完整配置页面，caller 保持 `aihub-audio`，项目使用用户业务目录。点击“ElevenLabs 默认音色”中的“打开音色库”；需要直接定位时，在启动返回的 URL 中添加查询参数 `voice-library=elevenlabs`，保留原有授权 fragment。实际返回可点击的 HTTP 页面链接，不能只给 HTML 源文件或声称页面已打开。

页面可按名称／ID 搜索，按语言、性别、分类筛选，试听已有样音并收藏；多语言音色可从任一语言筛选到。试听不生成新语音。样音不可用时允许继续选择与收藏，明确提示；目录暂时不可读时保留已保存值和收藏。

用户选择“当前项目”或“全局（所有项目）”，页面显示实际目标文件。点击“保存并使用”将所选默认音色和收藏列表在同一目标文件原子保存并通过原加载器回读；只修改这两项。单独“保存收藏”只保存收藏。保存冲突或失败保留选择供重试，不能报告成功；仅选中、关闭页面或到期不会保存。

默认项目目标为 `.env.local.aihub-studio`，默认全局目标为 `~/.config/aihub-studio/.env`。`AIHUB_ELEVENLABS_DEFAULT_VOICE_ID` 供 Eleven Speech 使用，任务显式音色优先；对话逐段指定，收藏不自动分配角色或轮换。收藏以 `AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS` 的 JSON 数组保存，项目整体覆盖全局，`[]` 可明确覆盖为空。关闭全局配置时仅提供项目保存。高优先级来源继续生效，保存到其他位置不会抹除它，页面提示实际来源。

页面空闲 60 分钟到期，按 `scripts/ui.py start|status|stop --page configuration` 核对并重开同一项目的实例。保留统一配置中心的其他设置入口。交付链接时按 UI 生命周期规则提供实际期限、当前／新会话重开请求，以及 FRP / Tailscale 跨设备提示；不默认开隧道。
