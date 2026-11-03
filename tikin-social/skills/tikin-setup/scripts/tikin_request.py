"""Shared JSON request transport for all tikin Skills. No business request is sent by report code."""
import hashlib
import json
import math
import re
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import tomllib
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from request_reporting import atomic_write, existing_feedback, feedback, now, record_lock, redact, upstream_fields
from regression import GateError, GUARD_HEADER, Regression

MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT = 30
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
READ_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def result_data(value, key, depth=0):
    """Keep full business results and usable media URLs; report limits apply only to evidence."""
    if isinstance(value, dict):
        credentials = {'authorization', 'cookie', 'set-cookie', 'api_key', 'accessToken', 'refreshToken'}
        return {name: '[REDACTED]' if depth == 0 and name in credentials else result_data(item, key, depth + 1)
                for name, item in value.items()}
    if isinstance(value, list):
        return [result_data(item, key, depth + 1) for item in value]
    return value.replace(key, '[REDACTED]') if isinstance(value, str) else value


def public_result(body, key, failed):
    """Project only recognized error positions; business data and signed URLs stay usable."""
    clean = result_data(body, key)
    if not failed:
        return clean
    if not isinstance(clean, dict):
        return {'error': {'code': 'invalid_response', 'message': 'The service returned an unreadable response.'}}
    task = clean.get('data')
    scopes = [clean]
    if isinstance(task, dict) and task.get('status') in ('failed', 'error'):
        scopes.append(task)
    for scope in scopes:
        if 'error' in scope:
            error = scope['error']
            code = error.get('code') if isinstance(error, dict) else None
            scope['error'] = {'code': code if isinstance(code, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}', code)
                             else 'request_failed', 'message': 'The request failed; see the private local report.'}
        for field in ('message', 'msg', 'detail', 'support'):
            if field in scope:
                scope[field] = 'The request failed; see the private local report.'
    return clean


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials or replay a POST to another location.


def retry_after(headers):
    raw = headers.get('retry-after')
    if not isinstance(raw, str):
        return None
    try:
        if re.fullmatch(r'[0-9]+', raw.strip()):
            seconds = float(raw)
        else:
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(raw)
            if date.tzinfo is None:
                return None
            seconds = date.timestamp() - time.time()
    except (ValueError, TypeError, OverflowError):
        return None
    return max(0, seconds) if math.isfinite(seconds) else None


def retry_delay(headers, attempt):
    seconds = retry_after(headers)
    return seconds if seconds is not None else 2 ** (attempt - 1)


def business_error(body):
    if not isinstance(body, dict):
        return None, None
    nested = body.get('data')
    task = nested if isinstance(nested, dict) else body
    if task.get('status') in ('failed', 'error'):
        return task.get('error') or {'code': 'unknown_error'}, task.get('id') or task.get('task_id')
    if body.get('error'):
        return body['error'], None
    code = body.get('code')
    success_codes = (None, 0, '0', 'ok', 'success')
    code_ok = code in success_codes or (str(code).isdigit() and 200 <= int(str(code)) < 300)
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


def execute(values, skill, request_file, record_input=None, output_dir='data/tikin', regression_approval=None, dry_run=False):
    key, base = values.get('TIKIN_API_KEY'), values['TIKIN_BASE_URL'].rstrip('/')
    if not key:
        raise ValueError('missing TIKIN_API_KEY; run config-check')
    spec = json.loads(Path(request_file).read_text(encoding='utf-8-sig'))
    if not isinstance(spec, dict) or set(spec) - {'method', 'path', 'query', 'body', 'original_request', 'timeout_seconds', 'time_budget_seconds', 'side_effects', 'reference_materials'}:
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
    side_effects = spec.get('side_effects', True)
    if not isinstance(side_effects, bool):
        raise ValueError('side_effects must be a boolean')
    replay_safe = method in READ_METHODS and not side_effects
    time_budget = spec.get('time_budget_seconds', 90)
    if isinstance(time_budget, bool) or not isinstance(time_budget, (int, float)) or not math.isfinite(time_budget) or not 0 < time_budget <= 300:
        raise ValueError('time_budget_seconds must be finite and between 0 and 300')
    deadline = time.monotonic() + time_budget
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
    if dry_run:
        return {'status': 'ok', 'sent': False, 'request_sha256': fingerprint, 'method': method, 'path': path,
                'client_base_url': base, 'test_token_sha256': hashlib.sha256(key.encode()).hexdigest(),
                'side_effects': not replay_safe}
    regression = Regression(regression_approval, base, key, fingerprint, not replay_safe) if regression_approval else None
    regression_ref = regression.reference if regression else None
    if regression:
        headers[GUARD_HEADER] = regression.binding
    with record_lock(record):
        if record_input:
            state = json.loads(record.read_text(encoding='utf-8'))
            if state.get('kind') != 'tikin-run' or state.get('binding') != binding or state.get('skill') != skill:
                raise ValueError('record belongs to another Skill, service or credential')
            if state.get('regression') != regression_ref:
                raise GateError('record_regression_mismatch')
            if fingerprint in state.get('pending_writes', [state.get('pending_write')]):
                output: dict[str, Any] = {'status': 'submission_unknown', 'record': str(record),
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
            state['regression'] = regression_ref

        def save():
            state['updated_at'] = now()
            atomic_write(record, json.dumps(state, ensure_ascii=False, indent=2) + '\n')

        pending = set(state.get('pending_writes', [state.get('pending_write')])) - {None}
        state.pop('pending_write', None)
        remaining_cooldown = state.get('not_before', 0) - time.time()
        if remaining_cooldown > 0:
            if remaining_cooldown >= deadline - time.monotonic():
                return {'status': 'cooldown', 'record': str(record), 'not_before': state['not_before'],
                        'retry_after_seconds': remaining_cooldown, 'feedback': existing_feedback(record)}
            time.sleep(remaining_cooldown)
        attempts = state.setdefault('retry_attempts', {}).get(fingerprint, 0)
        if attempts >= MAX_ATTEMPTS:
            return {'status': 'retry_exhausted', 'record': str(record), 'feedback': existing_feedback(record)}
        state['pending_writes'] = sorted(pending)
        save()
        warning = None
        latest_feedback = None
        result_body, status = None, None
        for attempt in range(attempts + 1, MAX_ATTEMPTS + 1):
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                return {'status': 'time_budget_exhausted', 'record': str(record)}
            reservation = None
            if regression:
                try:
                    proof_status, _, proof_body, proof_error, _ = exchange(
                        'GET', base + '/_tikin/regression-binding', headers, None, min(timeout, remaining_time))
                    if proof_status != 200 or proof_error is not None:
                        raise GateError('server_binding_unproven')
                    regression.verify_server(proof_body)
                    remaining_time = deadline - time.monotonic()
                    if remaining_time <= 0:
                        raise GateError('time_budget_exhausted')
                    reservation = regression.reserve(record)
                except GateError as blocked:
                    return {'status': 'regression_blocked', 'reason': blocked.reason, 'record': str(record),
                            'feedback': existing_feedback(record)}
            if not replay_safe:
                pending.add(fingerprint)
                state['pending_writes'] = sorted(pending)
            state['retry_attempts'][fingerprint] = attempt
            state['status'] = 'in_flight'
            save()
            start, at = time.monotonic(), now()
            status, response_headers, result_body, error, timeout_stage = exchange(method, url, headers, body, min(timeout, remaining_time))
            elapsed_ms = round((time.monotonic() - start) * 1000)
            business, task_id = business_error(result_body)
            task_body = result_body.get('data', result_body) if isinstance(result_body, dict) else None
            if not isinstance(task_body, dict):
                task_body = result_body
            remote_failed = isinstance(task_body, dict) and task_body.get('status') in ('failed', 'error')
            failed = error is not None or status is None or not 200 <= status < 300 or business is not None
            not_sent = status is None and isinstance(error, (socket.gaierror, ConnectionRefusedError))
            ambiguous = not replay_safe and not not_sent and (error is not None or status == 429 or (status is not None and status >= 500))
            if regression and not not_sent and error is not None:
                ambiguous = True
            deterministic = status is not None and 400 <= status < 500 and status != 429
            transient = not deterministic and not isinstance(error, ssl.SSLCertVerificationError) and (
                status == 429 or (status is not None and status >= 500) or isinstance(error, OSError))
            retry = transient and attempt < MAX_ATTEMPTS and (replay_safe or not_sent)
            if regression and ambiguous:
                retry = False
            delay = retry_delay(response_headers, attempt) if retry or 'retry-after' in response_headers else None
            if delay is not None:
                state['not_before'] = time.time() + delay
            if not transient:
                state['retry_attempts'].pop(fingerprint, None)
            query_pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
            evidence = redact({'id': str(uuid.uuid4()), 'at': at, 'method': method, 'url': url,
                               'elapsed_ms': elapsed_ms, 'attempt': attempt, 'max_attempts': MAX_ATTEMPTS,
                               'retry_policy': 'read-only' if replay_safe else 'may-have-side-effects',
                               'retry_scheduled': retry, 'retry_delay_ms': delay * 1000 if delay is not None else None,
                               'timeout_ms': timeout * 1000, 'timeout_stage': timeout_stage,
                               'request': {'headers': headers, 'body': body,
                                           'query': {name: [value for key_name, value in query_pairs if key_name == name] for name, _ in query_pairs},
                                           'original_request': spec['original_request'], 'reference_materials': spec.get('reference_materials')},
                               'response': {'http_status': status, 'headers': response_headers, 'body': result_body}}, [key])
            state['exchanges'].append(evidence)
            state['status'] = 'submission_unknown' if ambiguous else 'remote_failed' if remote_failed else 'failed' if failed else 'ok'
            # A later GET or another write must not erase an earlier uncertain submission.
            if not replay_safe and not ambiguous and not retry:
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
                if regression and reservation:
                    regression.finish(reservation, 'unknown' if ambiguous else 'not_sent' if not_sent else 'received',
                                      status, state.get('not_before', 0))
                latest_feedback = feedback(record, state)
            except (OSError, ValueError, subprocess.SubprocessError):
                warning = '无法保存最新错误报告；保留原任务结果与任务 ID，不要因此重新提交。'
                latest_feedback = existing_feedback(record)
                retry = False  # Never send another attempt without durable evidence.
            if retry and delay >= deadline - time.monotonic():
                state['status'] = 'cooldown'
                save()
                break
            if not retry or delay is None:
                break
            sys.stderr.write(f'[tikin] attempt {attempt}/{MAX_ATTEMPTS} failed; retrying in {delay}s\n')
            time.sleep(delay)
        output = {'schema_version': 1, 'status': state['status'], 'record': str(record),
                  'http_status': status,
                  'response_headers': {'retry-after': response_headers['retry-after']} if retry_after(response_headers) is not None else {},
                  'response': public_result(result_body, key, failed)}
        if state.get('not_before', 0) > time.time():
            output.update(not_before=state['not_before'], retry_after_seconds=state['not_before'] - time.time())
        if latest_feedback:
            output['feedback'] = latest_feedback
        if warning:
            output['feedback_warning'] = warning
        return output
