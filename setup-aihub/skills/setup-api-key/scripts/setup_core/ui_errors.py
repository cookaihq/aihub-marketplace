"""Stable, value-free errors for the local browser boundary."""
from .errors import SetupError
import re

MESSAGES = {
    "invalid_input": "请检查输入。密钥必须是非空的单行文本。",
    "invalid_url": "服务地址必须是 HTTPS 地址，不能包含用户名、密码或查询参数。",
    "input_required": "未保存的输入已清除，请重新填写并预览。",
    "target_changed": "目标文件已变化，请重新检查并预览保存。",
    "sources_changed": "配置来源已变化，旧确认已失效，请重新预览。",
    "confirmation_mismatch": "确认已失效，请重新预览保存。",
    "repair_actual_source": "已有配置需要在实际生效的原文件修复。",
    "repair_environment_at_injection_source": "此字段由进程环境变量覆盖，请让 Agent 修复启动时的注入来源。",
    "target_not_ignored": "目标或原子写入临时文件未被 Git 忽略，请让 Agent 核对忽略规则后重试。",
    "target_tracked": "目标已被 Git 跟踪，不能保存密钥。请让 Agent 处理该来源。",
    "reconcile_before_retry": "上次保存结果待核对，请先检查实际文件；不会重复保存。",
    "secret_book_unavailable": "凭证读取未完成，请检查连接、运行环境或表权限后重试。",
    "secret_book_configuration_invalid": "Secret Book 原配置缺项或格式不兼容，请在原来源修复后重新检查。",
    "lark_missing": "正在准备 Lark CLI。若准备失败，请让 Agent 检查本机 Node/npm 环境。",
    "lark_prepare_failed": "Lark CLI 准备失败，请让 Agent 检查本机安装环境后重试。",
    "lark_unavailable": "Lark CLI 无法运行，请让 Agent 检查当前进程的 PATH 与依赖。",
    "network_budget": "本轮读取超时，进度已保留，可以稍后重新检查。",
    "rate_limited": "服务要求稍后重试，请在所示时间后重新检查。",
    "identity_changed": "当前飞书身份与连接不一致，请恢复原账号或确认改绑原连接。",
    "repair_book_source": "该连接由环境或项目配置提供，请让 Agent 在实际来源修复表与身份的绑定，随后重新检查。",
    "connection_save_unconfirmed": "连接保存未确认。请重新检查连接列表和原文件后继续；不会重放旧保存。",
    "login_required": "需要本人登录，请选择账号并完成飞书授权。",
    "login_expired": "本次授权已到期或短期上下文已丢失，请重新发起授权。",
    "login_pending": "本机尚未确认授权完成，请完成飞书页面授权后重新检查。",
    "record_unavailable": "该记录不可见、编号不唯一或已失效，请重新选择或联系维护者。",
    "missing_keys": "所选字段缺值，请选择其他记录或联系凭证维护者补齐。",
    "related_fields_differ": "所选记录的服务地址与本机不同，请核对地址并明确选择是否一同配置。",
    "table_fields_missing": "已有表缺少必要字段，请联系表管理员处理后重新检查。",
    "no_application": "当前环境没有可用的飞书应用，请让 Agent 配置 Lark CLI 应用后回来检查。",
    "no_services": "尚未提供已安装业务 Plugin 的位置，请让 Agent 核对安装后重新打开。",
    "consumer_upgrade_required": "业务 Plugin 版本过低，请让 Agent 升级到所需版本后继续配置。",
    "incompatible_version": "当前业务 Plugin 版本不在 Setup 支持范围内，请让 Agent 核对可用的 Setup 版本后继续。",
}


def public_error(error):
    reason = error.reason if isinstance(error, SetupError) else "local_operation_failed"
    result = {"error": reason, "message": MESSAGES.get(reason, "本机操作未完成，请让 Agent 按错误编号检查后继续：" + reason)}
    if isinstance(error, SetupError) and reason in ("consumer_upgrade_required", "incompatible_version"):
        details = error.details
        if (details.get("plugin") in ("aihub-studio", "tikin-social")
                and all(isinstance(details.get(key), str) and re.fullmatch(r"\d+\.\d+\.\d+", details[key])
                        for key in ("current_version", "minimum", "maximum_exclusive"))):
            result["message"] = (f"{details['plugin']} 当前版本为 {details['current_version']}；"
                                 f"本版 Setup 支持 >= {details['minimum']}、< {details['maximum_exclusive']}。"
                                 + ("请让 Agent 升级业务 Plugin 后继续配置。" if reason == "consumer_upgrade_required"
                                    else "请让 Agent 核对支持此版本的 Setup，不要降级业务 Plugin。"))
    if isinstance(error, SetupError):
        # Never forward arbitrary exception messages, argv, HTTP bodies or values.
        for key in ("retry_at", "source", "field", "missing_fields", "expected", "observed"):
            if key in error.details:
                result[key] = error.details[key]
    return result
