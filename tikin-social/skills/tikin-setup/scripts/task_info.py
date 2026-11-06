"""Task metadata and local delivery receipts. Never sends or retries a business request."""
from contextlib import contextmanager
from contextvars import ContextVar
import errno
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from request_reporting import atomic_write, now, record_lock, redact

CONTEXT = ContextVar('tikin_artifact_context', default=None)
ACTOR_FIELDS = ('host', 'conversation_id', 'conversation_title', 'agent_id', 'agent_name', 'agent_role',
                'agent_model', 'parent_conversation_id', 'relationship')


def actor_context(value=None, environment=None):
    value, environment = value or {}, os.environ if environment is None else environment
    if not isinstance(value, dict) or set(value) - set(ACTOR_FIELDS):
        raise ValueError('execution context has unknown fields; do not include chat or credentials')
    if any(item is not None and (not isinstance(item, str) or len(item) > 256 or any(ord(c) < 32 for c in item))
           for item in value.values()):
        raise ValueError('invalid execution context value')
    actor = {key: value.get(key) or None for key in ACTOR_FIELDS}
    detected = [name for name, key in (('Codex', 'CODEX_THREAD_ID'), ('Hermes', 'HERMES_SESSION_ID')) if environment.get(key)]
    actor['host'] = actor['host'] or (detected[0] if len(detected) == 1 else None)
    if actor['host'] not in (None, 'Codex', 'Claude Code', 'WorkBuddy', 'Hermes'):
        raise ValueError('unknown execution host')
    keys = {'Codex': ('CODEX_THREAD_ID', 'CODEX_SESSION_ID'), 'Claude Code': ('CLAUDE_SESSION_ID',),
            'WorkBuddy': ('CODEBUDDY_SESSION_ID',), 'Hermes': ('HERMES_SESSION_ID',)}
    actor['conversation_id'] = actor['conversation_id'] or next(
        (environment[key] for key in keys.get(actor['host'], ()) if environment.get(key)), None)
    if actor['relationship'] not in (None, 'child', 'fork'):
        raise ValueError('unknown conversation relationship')
    if bool(actor['parent_conversation_id']) != bool(actor['relationship']) or (actor['relationship'] and not actor['conversation_id']):
        raise ValueError('verified relationship needs both conversation IDs and kind')
    actor['source'] = 'caller-context' if value else 'host-environment' if actor['conversation_id'] else 'unavailable'
    return actor


@contextmanager
def execution_context(context_file=None):
    value = json.loads(Path(context_file).read_text(encoding='utf-8-sig')) if context_file else {}
    token = CONTEXT.set(actor_context(value))
    try:
        yield
    finally:
        CONTEXT.reset(token)


def read(path):
    info = json.loads(Path(path).read_text(encoding='utf-8'))
    if (info.get('schema_version') != 1 or info.get('plugin') != 'tikin-social'
            or not isinstance(info.get('task_id'), str) or not Path(info.get('project_root', '')).is_absolute()
            or not isinstance(info.get('creator'), dict)
            or any(not isinstance(info.get(key), list) for key in ('participants', 'records', 'registered_outputs'))):
        raise ValueError('invalid or unsupported task-info.json; not overwritten')
    return info


def find(record):
    directory = Path(record).resolve()
    if directory.is_file() or directory.suffix == '.json':
        directory = directory.parent
    for parent in (directory, *directory.parents):
        path = parent / 'task-info.json'
        if path.exists():
            read(path)
            return path
    return None


@contextmanager
def metadata_lock(path):
    for attempt in range(76):
        lock = record_lock(path)
        try:
            lock.__enter__()
            break
        except OSError as error:
            if attempt == 75 or error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            time.sleep(.04)
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def write(path, info):
    atomic_write(Path(path), json.dumps(info, ensure_ascii=False, indent=2) + '\n')


def create(record, title, skill, version, secrets=(), kind='tikin-run'):
    path = Path(record).parent / 'task-info.json'
    if path.exists():
        raise ValueError('new task metadata already exists')
    actor = {key: redact(value, secrets) if isinstance(value, str) else value
             for key, value in (CONTEXT.get() or actor_context()).items()}
    at = now()
    info = {'schema_version': 1, 'task_id': str(uuid.uuid4()), 'plugin': 'tikin-social', 'plugin_version': version,
            'skill': skill, 'title': title, 'project_root': str(Path.cwd().resolve()), 'created_at': at, 'updated_at': at,
            'creator': actor, 'participants': [{**actor, 'relation': 'created', 'first_at': at, 'last_at': at}],
            'records': [{'path': Path(record).name, 'kind': kind, 'purpose': 'primary'}],
            'registered_outputs': [], 'delivery': None}
    write(path, info)
    return path


def update(record, change):
    path = find(record)
    if not path:
        return  # Explicit old-record recovery does not backfill metadata.
    with metadata_lock(path):
        info = read(path)
        change(info)
        info['updated_at'] = now()
        write(path, info)


def participate(record, secrets=(), invalidate_delivery=False):
    actor = {key: redact(value, secrets) if isinstance(value, str) else value
             for key, value in (CONTEXT.get() or actor_context()).items()}
    def change(info):
        identity = lambda item: tuple(item.get(key) for key in ('host', 'conversation_id', 'agent_id', 'parent_conversation_id', 'relationship'))
        existing = next((item for item in info['participants'] if identity(item) == identity(actor)), None)
        if existing:
            existing.update({key: value for key, value in actor.items() if value is not None})
            existing['last_at'] = now()
        else:
            info['participants'].append({**actor, 'relation': 'continued', 'first_at': now(), 'last_at': now()})
        if invalidate_delivery:
            info['delivery'] = None
    update(record, change)


def stored_path(root, path):
    path = Path(path).resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def link_record(task, record, kind):
    def change(info):
        path = stored_path(find(task).parent, record)
        if not any(item['path'] == path for item in info['records']):
            info['records'].append({'path': path, 'kind': kind, 'purpose': 'primary'})
    update(task, change)


def register(record, paths=(), delivery=None, reason=''):
    metadata = find(record)
    if not metadata:
        raise ValueError('only new tasks with task-info.json can register outputs')
    if delivery not in (None, 'completed', 'partial', 'failed') or (delivery and not reason.strip()):
        raise ValueError('delivery needs completed/partial/failed and a completion or stopping reason')
    info = read(metadata)
    if Path(info['project_root']).resolve() != Path.cwd().resolve():
        raise ValueError('task belongs to another project; use its original working directory')
    operational = {(metadata.parent / item['path']).resolve() for item in info['records']}
    auxiliary = {'task-info.json', 'run.json', 'task.json', 'download.json', 'diagnostic.json',
                 'error-report.md', 'error-report.json', 'execution-context.json'}
    entries = []
    for value in paths:
        path = Path(value).resolve(strict=True)
        if not path.is_file() or path.name.lower() in auxiliary or path in operational or path.suffix.lower() in ('.part', '.tmp', '.lock'):
            raise ValueError('register final outputs only; execution records and temporary files are supporting material')
        before = path.stat()
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('output changed during registration')
        entries.append({'path': stored_path(metadata.parent, path), 'title': path.name, 'bytes': after.st_size,
                        'sha256': digest, 'registered_at': now()})
    def change(info):
        if Path(info['project_root']).resolve() != Path.cwd().resolve():
            raise ValueError('task belongs to another project; use its original working directory')
        for entry in entries:
            entry['id'] = hashlib.sha256((info['task_id'] + '\0' + entry['path']).encode()).hexdigest()[:24]
            info['registered_outputs'] = [item for item in info['registered_outputs'] if item['path'] != entry['path']] + [entry]
        if delivery:
            info['delivery'] = {'status': delivery, 'at': now(), 'reason': reason.strip()}
    update(record, change)
    participate(record)
    return {'status': 'ok', 'task_info': str(metadata), 'registered': len(entries), 'delivery': delivery}
