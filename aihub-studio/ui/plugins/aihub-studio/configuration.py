from importlib import import_module


def fields(field):
    fields = [
        field("AIHUB_API_KEY", "AIhub API Key", "服务连接", sensitive=True, required=True,
              help="用于调用 AIhub 多媒体创作与理解服务。",
              clear_help="移除本页标明文件中的显式值；可能回退到下一层配置。缺少密钥时下次任务需先补齐。"),
    ]
    for skill in ("image", "video", "audio", "music", "understanding"):
        module = import_module(__package__ + '.skills.aihub-' + skill + '.configuration')
        fields.extend(module.fields(field))
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
    return fields
