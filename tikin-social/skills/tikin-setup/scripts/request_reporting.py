"""Private local evidence. Loaded only through the pinned tikin-config runtime."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

SECRET_KEY = re.compile(r'authorization|cookie|api[_.-]?key|password|secret|credential|accessToken|refreshToken|idToken|sessionId|(?:^|[_-])(?:auth|token|signature|sign|sig|session|jwt)(?:$|[_-])|^x-amz-|^x-goog-', re.I)


def secret_values(value, sensitive=False):
    """Also mask known input secrets if a service echoes them in another field."""
    if isinstance(value, str):
        return [value] if sensitive and value else []
    if isinstance(value, dict):
        values = []
        for name, item in value.items():
            values.extend(secret_values(item, sensitive or bool(SECRET_KEY.search(name))))
            if name.lower() == 'proxy_url' and isinstance(item, str):
                values.append(item)
                try:
                    password = urlsplit(item).password
                    if password:
                        values.extend([password, unquote(password)])
                except ValueError:
                    pass  # The complete malformed input is still masked.
        return values
    if isinstance(value, list):
        return [secret for item in value for secret in secret_values(item, sensitive)]
    return []


def redact(value, secrets=(), key='', depth=0):
    if SECRET_KEY.search(key):
        return '[REDACTED]'
    if depth > 20:
        return '[OMITTED: nesting limit]'
    if isinstance(value, str):
        text = value
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'data:[^\s;,]+;base64,[a-zA-Z0-9+/=\s]+', '[OMITTED: base64 data]', text)
        text = re.sub(r'\b(?:Bearer|Basic)\s+[^\s,;"\'<>]+', '[REDACTED authorization]', text, flags=re.I)
        text = re.sub(r'((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization|cookie|password|secret|signature)\s*[=:]\s*)(?:"[^"]*"|\x27[^\x27]*\x27|[^\s,;]+)', r'\1[REDACTED]', text, flags=re.I)

        def clean_url(match):
            try:
                url = urlsplit(match.group())
                host = url.netloc.rsplit('@', 1)[-1]
                query = urlencode([(name, '[REDACTED]') for name, _ in parse_qsl(url.query, keep_blank_values=True)])
                return urlunsplit((url.scheme, host, url.path, query, '[REDACTED]' if url.fragment else ''))
            except ValueError:
                return '[REDACTED malformed URL]'

        text = re.sub(r'https?://[^\s"\'<>]+', clean_url, text, flags=re.I)
        if (re.search(r'base64|file_data|inline_data', key, re.I) or len(text) > 1024) and re.fullmatch(r'[A-Za-z0-9+/=\r\n]+', text):
            return f'[OMITTED: binary/base64, {len(value)} characters]'
        return text if len(text) <= 32768 else text[:32768] + f'\n[OMITTED: {len(text) - 32768} characters]'
    if isinstance(value, (bytes, bytearray)):
        return f'[OMITTED: binary, {len(value)} bytes]'
    if isinstance(value, list):
        return [redact(item, secrets, depth=depth + 1) for item in value[:200]] + ([f'[OMITTED: {len(value) - 200} items]'] if len(value) > 200 else [])
    if isinstance(value, dict):
        result = {name: redact(item, secrets, str(name), depth + 1) for name, item in list(value.items())[:300]}
        if len(value) > 300:
            result['_omitted_fields'] = len(value) - 300
        return result
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def restrict_private(path: Path) -> None:
    # Native DACL API avoids starting PowerShell for every task-state write.
    from private_platform import private_permissions
    private_permissions(path, owner_path=Path.cwd())


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    temporary = Path(name)
    try:
        # Empty file is restricted before writing any private text.
        restrict_private(temporary)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            fd = None
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if fd is not None:
            os.close(fd)
        temporary.unlink(missing_ok=True)


@contextmanager
def record_lock(path):
    """OS releases the lock when an interrupted process exits; no stale PID guessing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a+b') as stream:
        stream.seek(0)
        if sys.platform == 'win32':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == 'win32':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def upstream_fields(body, path='response.body', depth=0):
    if not isinstance(body, dict) or depth > 8:
        return []
    found = []
    for key, value in body.items():
        source = path + '.' + key
        if re.search(r'upstream|provider|trace[_-]?id|request[_-]?id|route|retries|retry_count|timeout_stage', key, re.I):
            found.append({'source': source, 'value': value})
        else:
            found.extend(upstream_fields(value, source, depth + 1))
    return found


def link(path, label=None):
    text = str(path).replace('\\', '/')
    label = (label or Path(path).name).replace('[', r'\[').replace(']', r'\]')
    return '[' + label + '](<' + text.replace('%', '%25').replace('#', '%23').replace('?', '%3F').replace('<', '%3C').replace('>', '%3E') + '>)'


def json_block(value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    fence = '`' * max([3] + [len(match) + 1 for match in re.findall(r'`+', text)])
    return fence + 'json\n' + text + '\n' + fence


def failure_notice(state):
    """Summarize observed evidence; the Agent adds the user's task impact and partial results."""
    status = state.get('status')
    if status in ('ok', 'waiting', 'task_exists'):
        return ''
    if status == 'regression_blocked':
        return '本地验收授权检查未通过，未继续请求 aihub-tikin。请先核对验收记录。'
    if status == 'submission_unknown':
        return 'aihub-tikin 请求的提交结果尚未确定。请先核对已有任务状态，再继续原任务。'
    latest = next(reversed(state.get('exchanges', [])), {})
    event = next((item for item in reversed(state.get('events', [])) if item.get('exchange_id') == latest.get('id')), {})
    if not event and status in ('cooldown', 'poll_budget_exhausted', 'time_budget_exhausted'):
        return '本轮等待或执行预算已用尽，尚未取得 aihub-tikin 的最终结果。请保留原记录，等待后继续查询。'
    kind = event.get('failure_kind')
    reason, action = {
        'timeout': ('读取 aihub-tikin 响应超时' if event.get('timeout_stage') == 'response_body' else '连接 aihub-tikin 超时',
                    '可以稍后继续原任务，或提供已有内容继续处理。'),
        'connection': ('与 aihub-tikin 的连接中断', '可以稍后继续原任务，或提供已有内容继续处理。'),
        'network': ('连接 aihub-tikin 失败', '请检查网络后继续原任务。'),
        'certificate': ('连接 aihub-tikin 时证书校验失败', '请检查证书或网络配置后继续。'),
        'authentication': ('aihub-tikin 返回鉴权错误', '请检查 API Key 后继续。'),
        'permission': ('aihub-tikin 返回权限错误', '请核对账号和接口权限后继续。'),
        'balance': ('aihub-tikin 返回余额不足错误', '请核对余额后继续。'),
        'parameters': ('aihub-tikin 返回参数错误', '请核对输入和接口要求后继续。'),
        'rate_limited': ('aihub-tikin 暂时限流', '请在冷却结束后继续原记录。'),
        'service': ('aihub-tikin 返回暂时性服务错误', '可以稍后继续原任务，或提供已有内容继续处理。'),
        'remote_task': ('aihub-tikin 返回任务错误', '请先检查已有任务记录及可用内容，再决定下一步。'),
        'response': ('aihub-tikin 未返回可用内容，具体原因尚未确定', '请先检查现有记录，再决定下一步。'),
    }.get(kind, ('aihub-tikin 返回错误' if latest.get('response', {}).get('http_status') is not None
                 else 'aihub-tikin 未返回可用内容，具体原因尚未确定',
                 '请先检查现有记录和输入，再决定下一步。'))
    attempts = latest.get('attempt', 0)
    if attempts > 1:
        reason += f'，已自动尝试 {attempts} 次'
    if status == 'cooldown':
        action = '请在冷却结束后继续原记录。'
    return reason + '，本次请求未完成。' + action


def notice_fields(artifacts, state, stale=False):
    links = [link(path) for path in artifacts.values()]
    target = next((artifacts[name] for name in ('error_report', 'diagnostic', 'record', 'issue_draft') if name in artifacts), None)
    details = link(target, '查看错误详情') if target else None
    notice = failure_notice(state)
    if notice and stale:
        notice += '本地报告未能更新，已有详情可能未包含最新结果。'
    return {'show_notice': bool(notice), 'artifact_links': links, 'details_link': details,
            'user_notice': notice + ('\n\n' + details if notice and details else '')}


def existing_feedback(record, state=None, stale=False):
    """Keep all available evidence, with one user-facing entry into the details."""
    names = {'error_report': 'error-report.md', 'diagnostic': 'diagnostic.json', 'issue_draft': 'issue-draft.md', 'record': record.name}
    artifacts = {}
    for key, name in names.items():
        try:
            if (record.parent / name).is_file():
                artifacts[key] = str(record.parent / name)
        except OSError:
            pass
    if state is None:
        try:
            state = json.loads(record.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            state = {}
    return {**artifacts, **notice_fields(artifacts, state, stale)} if artifacts else None


def feedback(record, state):
    if not state['events']:
        return None
    directory = record.parent
    diagnostic, report, draft = (directory / name for name in ('diagnostic.json', 'error-report.md', 'issue-draft.md'))
    links = [link(path) for path in (report, diagnostic, draft, record)]
    summary = {key: state.get(key) for key in ('plugin', 'plugin_version', 'skill', 'created_at', 'updated_at', 'status', 'original_request')}
    summary.update(model=None, model_switches=None, internal_retries=None)
    content = '# aihub-tikin 本地请求与错误汇总\n\n'
    content += '本文件仅本地保存，包含私密原始需求、实际参数与素材定位信息。凭证已脱敏；不自动发送或创建 Issue。\n\n'
    content += 'HTTP 是客户端实际收到的 tikin 响应；异步状态单独记录。上游 HTTP、错误、request ID、trace ID、路由、供应商和内部重试仅按响应字段及 source 保留；未返回的字段均未知。null 表示未知或不适用。客户端耗时不代表供应商耗时。\n\n'
    content += f"独立错误数：{len(state['events'])}\n\n"
    content += '## 任务\n\n' + json_block(summary) + '\n\n## 错误证据\n\n' + json_block(state['events'])
    content += '\n\n## 实际请求 / 响应 JSON（脱敏）\n\n' + json_block(state['exchanges'])
    content += '\n\nservice_unavailable 本身不能证明上游宕机；服务未暴露的信息需由管理员按任务/请求 ID 查后台日志。\n\n'
    content += '## 关联文件\n\n' + '\n'.join('- ' + item for item in links) + '\n'
    public = '# tikin Social 错误反馈草稿\n\n'
    public += f"Plugin: {state['plugin_version']}\nSkill: {state['skill']}\n任务状态: {state['status']}\n独立错误数: {len(state['events'])}\n\n"
    public += '| # | 阶段 | 客户端 HTTP（不是供应商 HTTP） |\n| --- | --- | --- |\n'
    for index, event in enumerate(state['events'], 1):
        public += f"| {index} | {event['stage']} | {event['http_status'] if event['http_status'] is not None else '未知'} |\n"
    public += '\n请补充不含私密输入的复现步骤，人工检查后提交：https://github.com/cookaihq/aihub-marketplace/issues/new\n不复制本地报告的原始需求、响应、素材链接或定位 ID。本草稿未自动发送。\n'
    atomic_write(diagnostic, json.dumps({key: value for key, value in state.items() if key not in ('binding', 'pending_write', 'pending_writes')}, ensure_ascii=False, indent=2) + '\n')
    atomic_write(draft, public)
    atomic_write(report, content)
    artifacts = {'error_report': str(report), 'diagnostic': str(diagnostic), 'issue_draft': str(draft), 'record': str(record)}
    return {'upstream_error_count': len(state['events']), **artifacts, **notice_fields(artifacts, state)}
