"""Persist caption workflow state without creating tasks or making network calls."""
import time
import hashlib
from typing import Any
from catalog import CAPTION_CREATE, CAPTION_RESULT

MAX_QUERIES = 10
MAX_POLL_SECONDS = 60
POLL_INTERVAL = 2
WAITING = {'processing', 'queued', 'active', 'pending', 'running'}


def before_send(state: dict[str, Any], path: str, query: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    created = state.get('caption_creations', {}).get(fingerprint)
    if path == CAPTION_CREATE and created:
        return {'status': 'task_exists', 'task': created}
    if path == CAPTION_RESULT:
        job_id = query.get('job_id')
        if not isinstance(job_id, str) or not job_id:
            raise ValueError('caption result queries require the existing job_id')
        progress = state.get('caption_polls', {}).get(hashlib.sha256(job_id.encode()).hexdigest())
        if progress and (progress['attempts'] >= MAX_QUERIES or time.time() >= progress['deadline']):
            return {'status': 'poll_budget_exhausted', 'task': {'job_id': job_id},
                    'poll_attempts': progress['attempts'], 'poll_deadline': progress['deadline']}
    return None


def reserve_query(state: dict[str, Any], path: str, query: dict[str, Any]) -> None:
    if path != CAPTION_RESULT:
        return
    key = hashlib.sha256(query['job_id'].encode()).hexdigest()
    progress = state.setdefault('caption_polls', {}).setdefault(key,
        {'attempts': 0, 'deadline': time.time() + MAX_POLL_SECONDS})
    progress['attempts'] += 1


def observe(state: dict[str, Any], path: str, fingerprint: str, body: Any) -> dict[str, Any] | None:
    if path not in (CAPTION_CREATE, CAPTION_RESULT) or not isinstance(body, dict):
        return None
    nested = body.get('data')
    data = nested if isinstance(nested, dict) else body
    status, job_id = data.get('status'), data.get('job_id')
    if not isinstance(job_id, str) or not job_id:
        return None  # A synchronous caption response does not prove an asynchronous workflow.
    task = {'job_id': job_id, 'status': status, 'query_path': CAPTION_RESULT}
    if path == CAPTION_CREATE:
        state.setdefault('caption_creations', {})[fingerprint] = task
    else:
        for fingerprint, created in state.get('caption_creations', {}).items():
            if created.get('job_id') == job_id:
                state['caption_creations'][fingerprint] = task
    waiting = status in WAITING or (status == 'ready' and not (data.get('content') or data.get('captions')))
    if waiting:
        if state['status'] == 'ok':
            state['status'] = 'waiting'
        state['not_before'] = max(state.get('not_before', 0), time.time() + POLL_INTERVAL)
    return task
