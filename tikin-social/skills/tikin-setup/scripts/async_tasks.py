"""Persist caption and LinkedIn workflows without a separate request transport."""
import time
import hashlib
from dataclasses import dataclass
from typing import Any
from catalog import CAPTION_CREATE, CAPTION_RESULT, LINKEDIN_CREATES, LINKEDIN_STATUS, LINKEDIN_RESULT

MAX_QUERIES = 10
MAX_POLL_SECONDS = 60
WAITING = {'processing', 'queued', 'active', 'pending', 'running'}


@dataclass(frozen=True)
class Workflow:
    key: str
    id_field: str
    creates: frozenset[str]
    queries: frozenset[str]
    result: str
    interval: int


CAPTION = Workflow('caption', 'job_id', frozenset({CAPTION_CREATE}), frozenset({CAPTION_RESULT}), CAPTION_RESULT, 2)
LINKEDIN = Workflow('linkedin', 'task_id', LINKEDIN_CREATES, frozenset({LINKEDIN_STATUS, LINKEDIN_RESULT}), LINKEDIN_RESULT, 1)


def workflow(path: str) -> Workflow | None:
    return next((item for item in (CAPTION, LINKEDIN) if path in item.creates | item.queries), None)


def failed_records(path: str, body: Any) -> list[dict[str, Any]]:
    if path != LINKEDIN_RESULT or not isinstance(body, dict):
        return []
    data = body.get('data', body)
    records = data.get('records') if isinstance(data, dict) else None
    return [item for item in records if isinstance(item, dict) and (item.get('error') or item.get('error_code'))] if isinstance(records, list) else []


def before_send(state: dict[str, Any], path: str, query: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    flow = workflow(path)
    if flow is None:
        return None
    created = state.get(flow.key + '_creations', {}).get(fingerprint)
    if path in flow.creates and created:
        return {'status': 'task_exists', 'task': created}
    if path in flow.queries:
        job_id = query.get(flow.id_field)
        if not isinstance(job_id, str) or not job_id:
            raise ValueError(f'{flow.key} queries require the existing {flow.id_field}')
        progress = state.get(flow.key + '_polls', {}).get(hashlib.sha256(job_id.encode()).hexdigest())
        if progress and (progress['attempts'] >= MAX_QUERIES or time.time() >= progress['deadline']):
            return {'status': 'poll_budget_exhausted', 'task': {flow.id_field: job_id},
                    'poll_attempts': progress['attempts'], 'poll_deadline': progress['deadline']}
    return None


def reserve_query(state: dict[str, Any], path: str, query: dict[str, Any]) -> None:
    flow = workflow(path)
    if flow is None or path not in flow.queries:
        return
    key = hashlib.sha256(query[flow.id_field].encode()).hexdigest()
    progress = state.setdefault(flow.key + '_polls', {}).setdefault(key,
        {'attempts': 0, 'deadline': time.time() + MAX_POLL_SECONDS})
    progress['attempts'] += 1
    state['not_before'] = max(state.get('not_before', 0), time.time() + flow.interval)


def start_poll(state: dict[str, Any], path: str, query: dict[str, Any]) -> float | None:
    """Start the durable wall-clock budget before any proof, cooldown or query."""
    flow = workflow(path)
    if flow is None or path not in flow.queries:
        return None
    key = hashlib.sha256(query[flow.id_field].encode()).hexdigest()
    progress = state.setdefault(flow.key + '_polls', {}).setdefault(key,
        {'attempts': 0, 'deadline': time.time() + MAX_POLL_SECONDS})
    return float(progress['deadline'])


def valid_query_response(path: str, query: dict[str, Any], body: Any) -> bool:
    flow = workflow(path)
    if flow is None or path not in flow.queries:
        return True
    data = body.get('data', body) if isinstance(body, dict) else None
    return isinstance(data, dict) and data.get(flow.id_field) == query.get(flow.id_field)


def observe(state: dict[str, Any], path: str, fingerprint: str, body: Any) -> dict[str, Any] | None:
    flow = workflow(path)
    if flow is None or not isinstance(body, dict):
        return None
    nested = body.get('data')
    data = nested if isinstance(nested, dict) else body
    status, job_id = data.get('status'), data.get(flow.id_field)
    if not isinstance(job_id, str) or not job_id:
        return None  # A synchronous caption response does not prove an asynchronous workflow.
    complete = (path == LINKEDIN_RESULT and data.get('ready') is True
                and isinstance(data.get('records'), list)) if flow == LINKEDIN else (
                    status in ('ready', 'completed') and bool(data.get('content') or data.get('captions')))
    complete = complete and state['status'] == 'ok'
    task = {flow.id_field: job_id, 'status': status, 'query_path': flow.result, 'complete': complete}
    if path in flow.creates:
        state.setdefault(flow.key + '_creations', {})[fingerprint] = task
    else:
        for fingerprint, created in state.get(flow.key + '_creations', {}).items():
            if created.get(flow.id_field) == job_id:
                state[flow.key + '_creations'][fingerprint] = task
    waiting = (not complete and status not in ('failed', 'error')) if flow == LINKEDIN else (
        status in WAITING or (status == 'ready' and not complete))
    if waiting:
        if state['status'] == 'ok':
            state['status'] = 'waiting'
        state['not_before'] = max(state.get('not_before', 0), time.time() + flow.interval)
    return task
