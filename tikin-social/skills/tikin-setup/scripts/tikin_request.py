"""Shared JSON request transport for all tikin Skills. No business request is sent by report code."""
import hashlib
import json
import math
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import tomllib
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from request_reporting import SECRET_KEY, atomic_write, existing_feedback, feedback, now, record_lock, redact, upstream_fields

MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT = 30
MAX_RETRY_AFTER = 60
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
READ_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def result_data(value, key):
    """Keep full business results and usable media URLs; report limits apply only to evidence."""
    if isinstance(value, dict):
        cursors = {'pagination_token', 'continuation_token', 'next_token', 'next_page_token'}
        return {name: '[REDACTED]' if SECRET_KEY.search(name) and name not in cursors else result_data(item, key)
                for name, item in value.items()}
    if isinstance(value, list):
        return [result_data(item, key) for item in value]
    return value.replace(key, '[REDACTED]') if isinstance(value, str) else value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials or replay a POST to another location.


def retry_delay(headers, attempt):
    raw = headers.get('retry-after')
    try:
        seconds = float(raw)
    except (ValueError, TypeError):
        try:
            from email.utils import parsedate_to_datetime
            seconds = parsedate_to_datetime(raw).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            seconds = float('nan')
    return min(max(0, seconds), MAX_RETRY_AFTER) if math.isfinite(seconds) else 2 ** (attempt - 1)


def business_error(body):
    if not isinstance(body, dict):
        return None, None
    task = body.get('data') if isinstance(body.get('data'), dict) else body
    if task.get('status') in ('failed', 'error'):
        return task.get('error') or {'code': 'unknown_error'}, task.get('id') or task.get('task_id')
    if body.get('error'):
        return body['error'], None
    code = body.get('code')
    success_codes = (None, 0, '0', 'ok', 'success')
    code_ok = code in success_codes or (str(code).isdigit() and 200 <= int(code) < 300)
    if body.get('success') is False or not code_ok:
        return {'code': code, 'message': body.get('message') or body.get('msg')}, None
    return None, None


def exchange(method, url, headers, body, timeout):
    """Return actual status/body plus a transport error; never guess a provider status."""
    response, status, response_headers = None, None, {}
    started = time.monotonic()
    try:
        request = Request(url, method=method, headers=headers,
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None)
        try:
            response = build_opener(NoRedirect).open(request, timeout=timeout)
        except HTTPError as error:
            response = error
        status = response.code
        response_headers = {key.lower(): value for key, value in response.headers.items()}
        chunks, size = [], 0
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('request deadline exceeded while reading response')
            # urllib's per-read socket timeout is reduced to the remaining wall-clock budget.
            sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
            if sock:
                sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                return status, response_headers, '[OMITTED: response exceeds 32 MiB]', ValueError('response_too_large'), 'response_body'
            chunks.append(chunk)
        text = b''.join(chunks).decode('utf-8', errors='replace')
        try:
            return status, response_headers, json.loads(text), None, None
        except ValueError:
            return status, response_headers, text, ValueError('invalid_json_response'), None
    except (URLError, OSError, TimeoutError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        phase = ('response_body' if status is not None else 'request_before_response_headers') if isinstance(reason, (TimeoutError, socket.timeout)) else None
        return status, response_headers, None, reason, phase
    finally:
        if response:
            response.close()


def execute(values, skill, request_file, record_input=None, output_dir='data/tikin'):
    key, base = values.get('TIKIN_API_KEY'), values['TIKIN_BASE_URL'].rstrip('/')
    if not key:
        raise ValueError('missing TIKIN_API_KEY; run config-check')
    spec = json.loads(Path(request_file).read_text(encoding='utf-8-sig'))
    if not isinstance(spec, dict) or set(spec) - {'method', 'path', 'query', 'body', 'original_request', 'timeout_seconds', 'reference_materials'}:
        raise ValueError('request-file has unknown fields or is not an object')
    if not isinstance(spec.get('original_request'), str) or not spec['original_request'].strip():
        raise ValueError('original_request must preserve the user request')
    method, path = str(spec.get('method', 'GET')).upper(), spec.get('path')
    if method not in {'GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE'}:
        raise ValueError('unsupported HTTP method')
    if not isinstance(path, str) or not path.startswith('/api/') or path.startswith('//') or urlsplit(path).fragment:
        raise ValueError('path must be a relative /api/... path from endpoint discovery')
    query = spec.get('query', {})
    if not isinstance(query, dict):
        raise ValueError('query must be an object')
    timeout = spec.get('timeout_seconds', DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError('timeout_seconds must be finite and between 0 and 300')
    url = base + path
    if query:
        url += ('&' if '?' in path else '?') + urlencode(query, doseq=True)
    body = spec.get('body')
    headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    record = Path(record_input).resolve() if record_input else Path(output_dir).resolve() / ('tikin-run-' + str(uuid.uuid4())) / 'run.json'
    setup_root = Path(__file__).resolve().parents[1]
    plugin_root = setup_root.parent.parent
    manifest_path = plugin_root / '.claude-plugin/plugin.json'
    installation = plugin_root if manifest_path.is_file() else setup_root
    if record.is_relative_to(installation):
        raise ValueError('reports must be outside the Plugin installation')
    # Skills-only installs still carry the pinned project version, but no Plugin manifest.
    version = (json.loads(manifest_path.read_text(encoding='utf-8'))['version'] if manifest_path.is_file()
               else tomllib.loads((setup_root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version'])
    binding = hashlib.sha256((base + '\0' + key).encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps([method, url, body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with record_lock(record):
        if record_input:
            state = json.loads(record.read_text(encoding='utf-8'))
            if state.get('kind') != 'tikin-run' or state.get('binding') != binding or state.get('skill') != skill:
                raise ValueError('record belongs to another Skill, service or credential')
            if method not in READ_METHODS and fingerprint in state.get('pending_writes', [state.get('pending_write')]):
                output = {'status': 'submission_unknown', 'record': str(record),
                          'error': 'Previous write outcome is unknown; do not replay automatically'}
                try:
                    output['feedback'] = feedback(record, state)
                except (OSError, ValueError, subprocess.SubprocessError):
                    output['feedback_warning'] = '无法保存错误报告；先前写入结果仍然未知，不要因此重新提交。'
                    output['feedback'] = existing_feedback(record)
                return output
        else:
            state = {'schema_version': 1, 'kind': 'tikin-run', 'plugin': 'tikin-social', 'plugin_version': version,
                     'skill': skill, 'binding': binding, 'created_at': now(), 'updated_at': now(),
                     'original_request': redact(spec['original_request'], [key]), 'status': 'ready', 'events': [], 'exchanges': []}

        def save():
            state['updated_at'] = now()
            atomic_write(record, json.dumps(state, ensure_ascii=False, indent=2) + '\n')

        pending = set(state.get('pending_writes', [state.get('pending_write')])) - {None}
        state.pop('pending_write', None)
        if method not in READ_METHODS:
            pending.add(fingerprint)
        state['pending_writes'] = sorted(pending)
        save()  # A write needs its recovery record before transmission.
        warning = None
        latest_feedback = None
        result_body, status = None, None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            start, at = time.monotonic(), now()
            status, response_headers, result_body, error, timeout_stage = exchange(method, url, headers, body, timeout)
            elapsed_ms = round((time.monotonic() - start) * 1000)
            business, task_id = business_error(result_body)
            task_body = result_body.get('data', result_body) if isinstance(result_body, dict) else None
            if not isinstance(task_body, dict):
                task_body = result_body
            remote_failed = isinstance(task_body, dict) and task_body.get('status') in ('failed', 'error')
            failed = error is not None or status is None or not 200 <= status < 300 or business is not None
            not_sent = status is None and isinstance(error, (socket.gaierror, ConnectionRefusedError))
            ambiguous = method not in READ_METHODS and not not_sent and (error is not None or status == 429 or (status is not None and status >= 500))
            deterministic = status is not None and 400 <= status < 500 and status != 429
            transient = not deterministic and not isinstance(error, ssl.SSLCertVerificationError) and (
                status == 429 or (status is not None and status >= 500) or isinstance(error, OSError))
            retry = transient and attempt < MAX_ATTEMPTS and (method in READ_METHODS or not_sent)
            delay = retry_delay(response_headers, attempt) if retry else None
            query_pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
            evidence = redact({'id': str(uuid.uuid4()), 'at': at, 'method': method, 'url': url,
                               'elapsed_ms': elapsed_ms, 'attempt': attempt, 'max_attempts': MAX_ATTEMPTS,
                               'retry_policy': 'idempotent' if method in READ_METHODS else 'non-idempotent',
                               'retry_scheduled': retry, 'retry_delay_ms': delay * 1000 if delay is not None else None,
                               'timeout_ms': timeout * 1000, 'timeout_stage': timeout_stage,
                               'request': {'headers': headers, 'body': body,
                                           'query': {name: [value for key_name, value in query_pairs if key_name == name] for name, _ in query_pairs},
                                           'original_request': spec['original_request'], 'reference_materials': spec.get('reference_materials')},
                               'response': {'http_status': status, 'headers': response_headers, 'body': result_body}}, [key])
            state['exchanges'].append(evidence)
            state['status'] = 'submission_unknown' if ambiguous else 'remote_failed' if remote_failed else 'failed' if failed else 'ok'
            # A later GET or another write must not erase an earlier uncertain submission.
            if method not in READ_METHODS and not ambiguous and not retry:
                pending.discard(fingerprint)
                state['pending_writes'] = sorted(pending)
            if failed:
                detail = business if isinstance(business, dict) else {'message': business}
                event = redact({'id': 'task-' + hashlib.sha256(str(task_id).encode()).hexdigest() if task_id else evidence['id'],
                                'at': at, 'stage': 'remote_execution' if remote_failed else 'request',
                                'http_status': status, 'http_status_source': 'client_response' if status else 'not_received',
                                'task_id': task_id, 'task_status': task_body.get('status') if remote_failed else None,
                                'request_id': response_headers.get('x-request-id'), 'ambiguous': ambiguous,
                                'code': detail.get('code'), 'message': detail.get('message') or (str(error) if error else None),
                                'exchange_id': evidence['id'], 'upstream': upstream_fields(result_body)}, [key])
                prior = next((item for item in state['events'] if item['id'] == event['id']), None)
                if prior:
                    event['at'] = prior['at']
                    prior.update(event)
                else:
                    state['events'].append(event)
            try:
                save()
                latest_feedback = feedback(record, state)
            except (OSError, ValueError, subprocess.SubprocessError):
                warning = '无法保存最新错误报告；保留原任务结果与任务 ID，不要因此重新提交。'
                latest_feedback = existing_feedback(record)
            if not retry:
                break
            sys.stderr.write(f'[tikin] attempt {attempt}/{MAX_ATTEMPTS} failed; retrying in {delay}s\n')
            time.sleep(delay)
        output = {'schema_version': 1, 'status': state['status'], 'record': str(record),
                  'http_status': status, 'response': redact(result_body, [key]) if failed else result_data(result_body, key)}
        if latest_feedback:
            output['feedback'] = latest_feedback
        if warning:
            output['feedback_warning'] = warning
        return output
