"""Read only task catalog. Only explicit projects, new task metadata and registered files are indexed."""
import csv
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import subprocess

from skill_ui.contracts import Resource, UIError

MAX_RECORD_BYTES = 8 * 1024 * 1024
TEXT_PREVIEW_BYTES = 160 * 1024


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_RECORD_BYTES + 1)
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError('record too large')
    return json.loads(raw)


def identifier(*values):
    return hashlib.sha256('\0'.join(map(str, values)).encode()).hexdigest()[:24]


def canonical(path):
    return os.path.normcase(str(Path(path).resolve()))


def kind_for(path, mime=''):
    suffix = Path(path).suffix.lower()
    if suffix in ('.csv', '.tsv'):
        return 'table'
    if suffix in ('.md', '.txt', '.pdf', '.docx', '.rtf'):
        return 'document'
    mime = mimetypes.guess_type(str(path))[0] or mime
    return next((kind for kind in ('image', 'video', 'audio') if mime.startswith(kind + '/')), 'file')


class Catalog:
    def __init__(self, project, plugin, extra_tasks=()):
        self.project, self.plugin = Path(project).resolve(strict=True), plugin
        self.extra_tasks = tuple(Path(path).resolve(strict=True) for path in extra_tasks)
        self.tasks, self.items, self.conversations, self.resources = [], [], [], {}
        self.hash_checks = {}
        self.refresh()

    def project_context(self):
        def git(*args):
            try:
                result = subprocess.run(['git', '-C', str(self.project), *args], capture_output=True, text=True,
                                        timeout=3, creationflags=0x08000000 if os.name == 'nt' else 0)
                return result.stdout.strip() if result.returncode == 0 else ''
            except (OSError, subprocess.TimeoutExpired):
                return ''
        branch = git('symbolic-ref', '--quiet', '--short', 'HEAD')
        commit = '' if branch else git('rev-parse', '--short', 'HEAD')
        return {'name': self.project.name, 'path': str(self.project), 'branch': branch or (f'分离 HEAD · {commit}' if commit else '非 Git 项目')}

    def _record(self, root, path):
        file = (root / path).resolve()
        if not file.is_relative_to(root):
            raise ValueError('operational records must stay in the task directory')
        return read_json(file)

    def _business(self, root, metadata):
        outputs, states, supporting, models = [], [], [], []
        for entry in metadata['records']:
            if entry.get('purpose') == 'supporting':
                continue
            try:
                record = self._record(root, entry['path'])
                kind = entry['kind']
                if kind == 'aihub-run':
                    states.append(record.get('status', 'pending'))
                    for attempt in record.get('attempts', []):
                        if attempt.get('model'):
                            models.append(attempt['model'])
                        if attempt.get('audio_record'):
                            audio = self._record(root, attempt['audio_record'])
                            if audio.get('status') == 'delivered':
                                outputs.extend(audio.get('files', []))
                            continue  # Source audio and fragments are supporting records, not a full transcript.
                        if attempt.get('task_record'):
                            outputs.extend(self._record(root, attempt['task_record']).get('files', []))
                        else:
                            outputs.extend((attempt.get('result') or {}).get('files', []))
                elif kind == 'aihub-job':
                    outputs.extend(record.get('files', []))
                    sub = record.get('submission') or {}
                    remote = sub.get('task') or {}
                    status = ('delivered' if remote.get('status') == 'completed' and record.get('files') and not record.get('failed')
                              else 'remote_failed' if remote.get('status') == 'failed'
                              else 'partial' if record.get('files') else sub.get('state', 'pending'))
                    states.append(status)
                    if record.get('model'):
                        models.append(record['model'])
                elif kind == 'aihub-native-music':
                    outputs.extend(record.get('files', []))
                    states.append(record.get('status', 'pending'))
                    models.append(record.get('model', ''))
                elif kind == 'tikin-run':
                    outputs.extend(record.get('outputs', []))
                    states.append(record.get('status', 'pending'))
                elif kind == 'tikin-download':
                    outputs.extend({'path': item['file'], 'bytes': item['bytes'], 'sha256': item.get('sha256')}
                                   for item in record.get('streams', []) if item.get('complete_transfer_verified'))
                    states.append('download-complete' if record.get('status') == 'complete' else record.get('status', 'pending'))
                supporting.append({'title': Path(entry['path']).name, 'text': '执行记录已保留，用于由 Agent 查询或恢复任务。'})
            except (OSError, ValueError, KeyError, TypeError):
                supporting.append({'title': Path(str(entry.get('path', '执行记录'))).name, 'text': '记录无法读取或格式不受支持。请由 Agent 核对；不要为补记录重复发起业务请求。'})
                states.append('record-error')
        for name in ('error-report.md', 'diagnostic.json'):
            if (root / name).is_file():
                supporting.append({'title': name, 'text': '本地诊断资料，不计入最终成果。请由原执行 Agent 在任务目录中核对。'})
        return outputs, states, supporting, models

    def _output(self, task, root, value):
        raw = value.get('path')
        if not isinstance(raw, str) or not raw:
            return None
        path = (root / raw).resolve()
        if path.name == 'task-info.json' or path.suffix == '.part':
            return None
        key = identifier(task['id'], canonical(path))
        mime = mimetypes.guess_type(str(path))[0] or value.get('mime_type') or 'application/octet-stream'
        item = {'id': key, 'task_id': task['id'], 'task': task['title'], 'title': value.get('title') or path.name,
                'kind': kind_for(path, mime), 'summary': '', 'status': '文件缺失', 'metadata': {'任务': task['title'], '文件名': path.name},
                '_path': path, '_mime': mime, '_expected_bytes': value.get('bytes'), '_sha256': value.get('sha256')}
        try:
            info = path.stat()
            if not path.is_file():
                return item
            if value.get('bytes') is not None and info.st_size != value['bytes']:
                item['status'] = '文件已变更'
                return item
            signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            expected = value.get('sha256')
            if expected and (info.st_size <= 2 * 1024 * 1024 or (str(path), signature, expected) in self.hash_checks):
                if not self._matches(path, signature, expected):
                    item['status'] = '文件已变更'
                    return item
            item.update(status='可用', resource=key)
            item['summary'] = f'{path.suffix.removeprefix(".").upper() or "文件"} · {info.st_size:,} 字节'
            item['metadata']['大小'] = f'{info.st_size:,} 字节'
            self.resources[key] = (path, mime, path.name, signature, expected)
        except OSError:
            pass
        return item

    def _matches(self, path, signature, expected):
        key = (str(path), signature, expected)
        if key not in self.hash_checks:
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                info = os.fstat(stream.fileno())
            self.hash_checks[key] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == signature and actual == expected
        return self.hash_checks[key]

    def refresh(self):
        if len(self.hash_checks) > 4096:
            self.hash_checks.clear()
        root = self.project / 'data' / self.plugin
        roots = [path.parent for path in root.glob('*/task-info.json')] if root.is_dir() else []
        roots.extend(self.extra_tasks)
        tasks, items, conversations, self.resources = {}, {}, {}, {}
        for directory in dict.fromkeys(path.resolve() for path in roots):
            if directory not in self.extra_tasks and not directory.is_relative_to(root.resolve()):
                continue
            try:
                metadata = read_json(directory / 'task-info.json')
                if metadata.get('plugin') != self.plugin or canonical(metadata.get('project_root', '')) != canonical(self.project):
                    continue
                if metadata.get('schema_version') != 1 or not isinstance(metadata.get('task_id'), str):
                    raise ValueError('unsupported task schema')
                if any(not isinstance(metadata.get(key), list) for key in ('records', 'participants', 'registered_outputs')):
                    raise ValueError('invalid task metadata')
                task_id = metadata['task_id']
                if task_id in tasks:
                    continue
                creator = metadata.get('creator') or {}
                task = {'id': task_id, 'title': metadata.get('title') or directory.name, 'skill': metadata.get('skill') or '',
                        'host': creator.get('host') or '未知执行工具', 'agent_name': creator.get('agent_name') or creator.get('agent_id') or '未记录',
                        'agent_role': creator.get('agent_role') or '未记录', 'agent_model': creator.get('agent_model'),
                        'folder': directory.name, 'directory': str(directory), 'created_at': metadata.get('created_at') or '',
                        'updated_at': metadata.get('updated_at') or '', 'participants': [], 'message': ''}
                files, statuses, supporting, models = self._business(directory, metadata)
                task['supporting'], task['generation_model'] = supporting, ', '.join(dict.fromkeys(filter(None, models)))
                for file in [*files, *metadata['registered_outputs']]:
                    if isinstance(file, dict):
                        item = self._output(task, directory, file)
                        if item:
                            items[item['id']] = item
                task_files = [item for item in items.values() if item['task_id'] == task_id]
                delivered = metadata.get('delivery')
                if isinstance(delivered, dict):
                    task['status'] = delivered.get('status', 'pending')
                    task['message'] = delivered.get('reason', '')
                elif self.plugin == 'aihub-studio' and 'delivered' in statuses:
                    task['status'] = 'completed'
                elif task_files:
                    task['status'] = 'partial'
                    task['message'] = '已有成果；任务的整体交付尚未完成。'
                elif statuses and all(status in ('failed', 'remote_failed', 'not_submitted', 'no_compatible_model', 'attempt_limit') for status in statuses):
                    task['status'] = 'failed'
                else:
                    task['status'] = 'pending'
                    task['message'] = '任务信息已保存，等待 Agent 查询、继续或完成交付。'
                type_counts = {}
                for item in task_files:
                    label = Path(item['title']).suffix.removeprefix('.').upper() if item['kind'] == 'file' else item['kind']
                    type_counts[label or 'file'] = type_counts.get(label or 'file', 0) + 1
                task['output_count'], task['unavailable_count'], task['type_counts'] = len(task_files), sum(i['status'] != '可用' for i in task_files), type_counts
                # Prefer different formats; remaining spaces show additional available results.
                covers, formats = [], set()
                for item in task_files:
                    fmt = Path(item['title']).suffix.lower() or item['kind']
                    if fmt not in formats and len(covers) < 3:
                        covers.append(item['id']); formats.add(fmt)
                for item in task_files:
                    if len(covers) >= 3:
                        break
                    if item['id'] not in covers:
                        covers.append(item['id'])
                task['thumbnail_ids'] = covers[:3]
                for actor in metadata['participants']:
                    if not actor.get('conversation_id') or not actor.get('host'):
                        continue
                    child = actor.get('relationship') == 'child' and actor.get('parent_conversation_id')
                    group = actor['parent_conversation_id'] if child else actor['conversation_id']
                    key = identifier(actor['host'], group)
                    relation = '创建' if actor.get('relation') == 'created' else '继续'
                    if not any(p['conversation_id'] == key for p in task['participants']):
                        task['participants'].append({'conversation_id': key, 'relation': relation})
                    session = conversations.setdefault(key, {'id': key, 'title': None, 'host': actor['host'], 'short_id': group[-6:],
                                                            'updated_at': '', 'task_ids': [], 'fork_of': actor.get('parent_conversation_id') if actor.get('relationship') == 'fork' else None})
                    if not child and actor.get('conversation_title'):
                        session['title'] = actor['conversation_title']
                    session['updated_at'] = max(session['updated_at'], actor.get('last_at') or task['updated_at'])
                    if task_id not in session['task_ids']:
                        session['task_ids'].append(task_id)
                tasks[task_id] = task
            except (OSError, ValueError, KeyError, TypeError):
                task_id = identifier('unreadable', directory)
                tasks[task_id] = {'id': task_id, 'title': directory.name, 'skill': '', 'host': '未读取', 'agent_name': '未记录', 'agent_role': '未记录',
                                 'folder': directory.name, 'directory': str(directory), 'created_at': '', 'updated_at': '', 'status': 'failed',
                                 'participants': [], 'supporting': [], 'output_count': 0, 'unavailable_count': 0, 'type_counts': {}, 'thumbnail_ids': [],
                                 'message': '任务基本信息无法读取或格式不受支持，未改写记录。'}
        unlinked = [task['id'] for task in tasks.values() if not task['participants']]
        if unlinked:
            conversations['unlinked'] = {'id': 'unlinked', 'title': '未关联会话', 'host': '', 'short_id': '', 'updated_at': '', 'task_ids': unlinked}
        self.tasks = sorted(tasks.values(), key=lambda task: task['updated_at'], reverse=True)
        self.items = sorted(items.values(), key=lambda item: next((i for i, t in enumerate(self.tasks) if t['id'] == item['task_id']), len(self.tasks)))
        self.conversations = sorted(conversations.values(), key=lambda session: session['updated_at'], reverse=True)

    def public_item(self, item, full=False):
        result = {key: value for key, value in item.items() if not key.startswith('_')}
        kind, path = item['kind'], item['_path']
        if item['status'] != '可用':
            result['preview'] = {'type': 'text', 'text': f'{item["status"]}。记录仍保留，请由原执行 Agent 核对。'}
        elif kind in ('image', 'video', 'audio'):
            result['preview'] = {'type': kind, 'resource': item['id']}
        elif path.suffix.lower() in ('.md', '.txt', '.json', '.csv', '.tsv'):
            try:
                self.resource(item['id'])
                with path.open('rb') as stream:
                    raw = stream.read((TEXT_PREVIEW_BYTES if full else 2048) + 1)
                limit = TEXT_PREVIEW_BYTES if full else 2048
                text = raw[:limit].decode('utf-8-sig', errors='replace')
                if path.suffix.lower() in ('.csv', '.tsv'):
                    rows = list(csv.reader(io.StringIO(text), delimiter='\t' if path.suffix.lower() == '.tsv' else ','))[:(101 if full else 4)]
                    result['preview'] = {'type': 'table', 'columns': rows[0][:30] if rows else [], 'rows': [row[:30] for row in rows[1:]]}
                else:
                    result['preview'] = {'type': 'markdown' if path.suffix.lower() == '.md' else 'text', 'text': text}
                if len(raw) > limit or kind == 'table':
                    result['preview_note'] = '预览仅展示部分内容，下载可取得完整文件。'
            except (OSError, UIError):
                result.pop('resource', None)
                result['status'] = '文件无法读取或已变更'
                result['preview'] = {'type': 'text', 'text': '文件无法读取或已变更，请刷新后核对。'}
        else:
            result['preview'] = {'type': 'text', 'text': f'{path.suffix.upper().removeprefix(".") or "文件"} 格式，可下载后使用对应应用打开。'}
        return result

    def snapshot(self, query=None):
        query = query or {}
        mode = query.get('browse', 'tasks')
        folder, selected_file = query.get('folder'), query.get('id')
        tasks = self.tasks
        sessions = [session for session in self.conversations if query.get('sessionq', '').lower() in ((session.get('title') or '未命名会话') + ' ' + session['host']).lower()]
        selected = next((s for s in self.conversations if s['id'] == query.get('conversation')), None)
        if not selected and sessions and mode == 'conversations' and query.get('mobile') != '1':
            selected = sessions[0]
        if mode == 'conversations':
            tasks = [t for t in tasks if selected and t['id'] in selected['task_ids']]
        else:
            tasks = [t for t in tasks if query.get('taskq', '').lower() in ' '.join((t['title'], t['skill'], t['host'])).lower()
                     and (not query.get('status') or query['status'] == t['status'])]
        def paged(values, key, size):
            try:
                page = max(1, min(int(query.get(key, 1)), max(1, (len(values) + size - 1) // size)))
            except (TypeError, ValueError):
                page = 1
            return values[(page-1)*size:page*size], {'page': page, 'size': size, 'total': len(values)}
        shown_tasks, task_paging = paged(tasks, 'conversationpage' if mode == 'conversations' else 'taskpage', 6)
        shown_sessions, session_paging = paged(sessions, 'sessionpage', 20)
        if selected and selected not in shown_sessions:
            shown_sessions = [selected, *shown_sessions]
        if folder:
            shown_tasks = [task for task in self.tasks if task['id'] == folder]
        type_key, text_key = ('ftype', 'fq') if folder else ('type', 'q')
        files = [item for item in self.items if (not folder or item['task_id'] == folder)
                 and (not query.get(type_key) or query[type_key] == item['kind'])
                 and (folder or not query.get('filetask') or item['task_id'] == query['filetask'])
                 and query.get(text_key, '').lower() in (item['title'] + ' ' + item['task']).lower()]
        # Detail navigation from a task follows all its files; global detail follows its filtered collection.
        siblings = [i for i in self.items if i['task_id'] == folder] if folder else files
        navigation = None
        if selected_file:
            index = next((i for i, item in enumerate(siblings) if item['id'] == selected_file), -1)
            if index >= 0:
                shown_tasks = [task for task in self.tasks if task['id'] == siblings[index]['task_id']]
                navigation = {'previous': siblings[index-1]['id'] if index else None,
                              'next': siblings[index+1]['id'] if index+1 < len(siblings) else None,
                              'index': index+1, 'total': len(siblings)}
                shown_files = siblings[max(0, index-8):index+9]
                file_paging = {'page': 1, 'size': 24, 'total': len(files)}
            else:
                shown_files, file_paging = [], {'page': 1, 'size': 24, 'total': len(files)}
        elif folder or mode == 'files':
            shown_files, file_paging = paged(files, 'filepage', 24)
        else:
            covers = {id for task in shown_tasks for id in task['thumbnail_ids']}
            shown_files = [item for item in self.items if item['id'] in covers]
            file_paging = {'page': 1, 'size': 24, 'total': len(files)}
        if folder or selected_file:
            related = {p['conversation_id'] for task in shown_tasks for p in task['participants']}
            shown_sessions += [session for session in self.conversations if session['id'] in related and session not in shown_sessions]
        public_sessions = [{**{k: v for k, v in session.items() if k != 'task_ids'}, 'task_count': len(session['task_ids'])} for session in shown_sessions]
        task_options = [task for task in self.tasks if query.get('filetaskq', '').lower() in task['title'].lower()][:20]
        chosen_task = next((task for task in self.tasks if task['id'] == query.get('filetask')), None)
        if chosen_task and chosen_task not in task_options:
            task_options.append(chosen_task)
        return {'tasks': shown_tasks, 'items': [self.public_item(i, i['id'] == selected_file) for i in shown_files],
                'task_options': [{key: task[key] for key in ('id', 'title', 'created_at')} for task in task_options],
                'conversations': public_sessions, 'project_context': self.project_context(),
                'totals': {'tasks': len(self.tasks), 'files': len(self.items)},
                'paging': {'tasks': task_paging, 'files': file_paging, 'sessions': session_paging},
                'selected_conversation': selected['id'] if selected else None, 'navigation': navigation,
                'available_types': list(dict.fromkeys(i['kind'] for i in self.items if not folder or i['task_id'] == folder))}

    def resource(self, id):
        entry = self.resources.get(id)
        if not entry:
            raise UIError('resource', '此文件不在当前项目的成果清单中。', 404)
        path, mime, name, signature, expected = entry
        try:
            info = path.stat()
            if path.resolve() != path or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != signature:
                raise UIError('changed', '文件已变化，请刷新后重新核对。', 409)
            if expected and not self._matches(path, signature, expected):
                raise UIError('changed', '文件与登记内容不一致，请刷新并由 Agent 核对。', 409)
        except OSError:
            raise UIError('missing', '文件已移动或不存在。', 404) from None
        return Resource(path, mime, name)
