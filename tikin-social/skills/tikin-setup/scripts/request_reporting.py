"""Private local evidence. Loaded only through the pinned tikin-config runtime."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEY = re.compile(r'authorization|cookie|api[_.-]?key|password|secret|credential|accessToken|refreshToken|idToken|sessionId|(?:^|[_-])(?:auth|token|signature|sign|sig|session|jwt)(?:$|[_-])|^x-amz-|^x-goog-', re.I)


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


def restrict_private(path):
    if os.name != 'nt':
        os.chmod(path, 0o600)
        return
    script = r'''
$ErrorActionPreference = 'Stop'
$path = $env:TIKIN_PRIVATE_FILE_PATH
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetOwner($user)
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @($user, $system)) {
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
  $acl.AddAccessRule($rule)
}
[System.IO.File]::SetAccessControl($path, $acl)
$actual = [System.IO.File]::GetAccessControl($path)
$rules = @($actual.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne 2) { exit 2 }
foreach ($rule in $rules) {
  if ($rule.IsInherited -or $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl' -or
      $rule.IdentityReference.Value -notin @($user.Value, 'S-1-5-18')) { exit 2 }
}
'''
    environment = dict(os.environ, TIKIN_PRIVATE_FILE_PATH=str(path))
    environment.pop('PSModulePath', None)
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                            env=environment, capture_output=True, timeout=10, creationflags=0x08000000)
    if result.returncode:
        raise OSError('Could not restrict private report permissions; no private content written')


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    finally:
        if fd is not None:
            os.close(fd)
        temporary.unlink(missing_ok=True)


@contextmanager
def record_lock(path):
    """OS releases the lock when an interrupted process exits; no stale PID guessing."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(str(path) + '.lock', 'a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
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


def link(path):
    text = str(path).replace('\\', '/')
    label = text.replace('[', r'\[').replace(']', r'\]')
    return '[' + label + '](<' + text.replace('%', '%25').replace('#', '%23').replace('?', '%3F').replace('<', '%3C').replace('>', '%3E') + '>)'


def json_block(value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    fence = '`' * max([3] + [len(match) + 1 for match in re.findall(r'`+', text)])
    return fence + 'json\n' + text + '\n' + fence


def existing_feedback(record):
    """Link only real files when updating an earlier report failed."""
    names = {'error_report': 'error-report.md', 'diagnostic': 'diagnostic.json', 'issue_draft': 'issue-draft.md', 'record': record.name}
    artifacts = {}
    for key, name in names.items():
        try:
            if (record.parent / name).is_file():
                artifacts[key] = str(record.parent / name)
        except OSError:
            pass
    links = [link(path) for path in artifacts.values()]
    return {**artifacts, 'show_notice': True, 'artifact_links': links,
            'user_notice': '本轮报告更新失败；以下已有文件可能未包含最新结果：\n\n' + '\n\n'.join(links)} if links else None


def feedback(record, state):
    if not state['events']:
        return None
    directory = record.parent
    diagnostic, report, draft = (directory / name for name in ('diagnostic.json', 'error-report.md', 'issue-draft.md'))
    links = [link(path) for path in (report, diagnostic, draft, record)]
    summary = {key: state.get(key) for key in ('plugin', 'plugin_version', 'skill', 'created_at', 'updated_at', 'status', 'original_request')}
    summary.update(model=None, model_switches=None, internal_retries=None)
    content = '# tikin Social 本地请求与错误汇总\n\n'
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
    return {'upstream_error_count': len(state['events']), 'show_notice': True,
            'error_report': str(report), 'diagnostic': str(diagnostic), 'issue_draft': str(draft),
            'artifact_links': links, 'user_notice': '本地错误汇总：\n\n' + '\n\n'.join(links)}
