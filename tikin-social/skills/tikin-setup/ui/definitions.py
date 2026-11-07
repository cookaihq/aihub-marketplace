def field(key, label, group, kind="text", **options):
    return dict(id=key, label=label, group=group, type=kind,
                effect="下次业务调用读取；本页不发起业务请求。", **options)


def definitions(plugin):
    if plugin == "aihub-studio":
        fields = [
            field("AIHUB_API_KEY", "AIhub API Key", "服务连接", sensitive=True, required=True,
                  help="用于调用 AIhub 创作与文档服务。",
                  clear_help="移除本页标明文件中的显式值；可能回退到下一层配置。缺少密钥时下次任务需先补齐。"),
        ]
        for kind, label in [("IMAGE", "图片"), ("VIDEO", "视频"), ("AUDIO", "音频"),
                            ("MUSIC", "音乐"), ("UNDERSTANDING", "多模态理解"), ("DOCUMENT", "文档")]:
            fields.append(field("AIHUB_" + kind + "_MODELS", label + "模型顺序", "各 Skill 模型", "list", default=[],
                                help="只影响对应 Skill；留空沿用按任务选择模型的现有行为，填写准确模型 ID。"))
        fields += [
            field("AIHUB_MODEL_FALLBACK_POLICY", "模型切换策略", "模型切换", "select", default="auto",
                  choices=["auto", "confirm", "off", "preflight_only"],
                  help="auto 自动切换；confirm 切换前确认；off 关闭；preflight_only 仅预检。"),
            field("AIHUB_MODEL_MAX_ATTEMPTS", "最多尝试模型数", "模型切换", "number", default=None, advanced=True,
                  help="包含首个模型；不设置时采用适用候选数。请填写正整数。"),
            field("AIHUB_RESULT_CHECK_ENABLED", "检查最终结果", "结果检查", "boolean", default=True,
                  help="生成后核对原需求与实际产物。"),
            field("AIHUB_RESULT_CHECK_PROVIDER", "检查方式", "结果检查", "select", default="auto",
                  choices=["auto", "host", "aihub"], depends_on={"AIHUB_RESULT_CHECK_ENABLED": True},
                  help="auto 自动选择；host 当前 Agent；aihub 使用服务模型。"),
            field("AIHUB_RESULT_CHECK_MODELS", "检查模型顺序", "结果检查", "list", default=["gemini-3.8-flash"],
                  depends_on={"AIHUB_RESULT_CHECK_ENABLED": True}, advanced=True,
                  help="检查需调用 AIhub 时按顺序选择；不改变已有业务授权。"),
            field("AIHUB_ERROR_REPORT_THRESHOLD", "连续失败报告阈值", "排障", "number", default=3, advanced=True,
                  help="现有错误报告触发阈值，至少为 1。"),
            field("AIHUB_SUPPORT_URL", "支持页面地址", "排障", default="", advanced=True,
                  help="可选 HTTP(S) 地址，不含账号、密码、查询参数或片段。"),
        ]
    else:
        fields = [
            field("TIKIN_API_KEY", "Tikin API Key", "服务连接", sensitive=True, required=True,
                  help="用于访问 Tikin 社交媒体数据服务。"),
            field("routing.default", "默认调用方式", "平台调用", "select", default="auto", choices=["auto", "confirm"],
                  help="auto 按当前任务直接调用；confirm 按现有 Tikin 路由规则先确认。此字段为 settings.json 必需结构，移除设置会重置为 auto。"),
        ]
        for platform, label in [("douyin", "抖音"), ("instagram", "Instagram"), ("threads", "Threads"),
                                ("tiktok", "TikTok"), ("twitter", "X / Twitter"),
                                ("xiaohongshu", "小红书"), ("youtube", "YouTube")]:
            fields.append(field("routing.platforms." + platform, label, "平台单独设置", "select", default="inherit",
                                choices=["inherit", "auto", "confirm"], advanced=True,
                                help="inherit 跟随默认调用方式；auto / confirm 只覆盖此平台。",
                                clear_help="清除后跟随默认调用方式。"))
    fields.append(field("default_skill_reminders", "提醒设为默认 Skill", "使用偏好", "boolean", default=True,
                        advanced=True, help="只修改当前 Agent 的提醒偏好，不改写宿主规则，也不代表已设为默认。"))
    return fields
