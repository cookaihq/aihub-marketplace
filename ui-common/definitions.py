from importlib import import_module


def field(key, label, group, kind="text", **options):
    return dict(id=key, label=label, group=group, type=kind,
                effect="下次业务调用读取；本页不发起业务请求。", **options)


def definitions(plugin):
    if plugin == "aihub-studio":
        fields = import_module("plugins.aihub-studio.configuration").fields(field)
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
