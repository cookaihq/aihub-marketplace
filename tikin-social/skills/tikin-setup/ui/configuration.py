"""Configuration adapter backed by the two Plugins' original loaders."""
from copy import deepcopy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

from skill_ui.contracts import UIError
from skill_ui.storage import active
from definitions import definitions
from persistence import Transaction, read, digest

ASSIGNMENT = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$')


def dotenv(raw, updates):
    raw = raw or b''
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        raise UIError('encoding', '配置文件必须是 UTF-8。', 422) from None
    if any(c in text for c in ('\0', '\ufeff', '\u2028', '\u2029', '\x85')) or '\r' in text.replace('\r\n', ''):
        raise UIError('format', '配置文件包含不受支持的换行或控制字符。', 422)
    newline = '\r\n' if '\r\n' in text else '\n'
    output = []
    for line in text.splitlines(keepends=True):
        match = ASSIGNMENT.fullmatch(line.rstrip('\r\n'))
        if match:
            key, value = match.groups()
            if value[:1] in ('"', "'") and (len(value) < 2 or value[-1] != value[0]):
                raise UIError('format', '现有配置包含跨行值，请先修复文件。', 422)
            if key in updates:
                continue  # Remove every occurrence, matching each loader's last-key semantics.
        output.append(line)
    for key, value in updates.items():
        if value is None:
            continue
        if output and not output[-1].endswith('\n'):
            output.append(newline)
        # Both original parsers remove exactly one outer quote pair; no shell evaluation.
        output.append(key + '="' + value + '"' + newline)
    return (b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + ''.join(output).encode('utf-8')


class Configuration:
    def __init__(self, package, project, options, environment=None):
        self.package, self.project, self.options = Path(package), Path(project), options
        self.plugin = options['plugin']
        self.environment = environment
        self.definitions = definitions(self.plugin)
        self.secret = secrets.token_bytes(32)
        self.transaction = Transaction(self.project / 'tmp' / (self.plugin + '-config-transactions'), owner_path=self.project)

    def _load(self, overrides=None):
        payload = dict(self.options, project=str(self.project), overrides=overrides or {})
        command = (['node', str(self.package / 'scripts/ui-config.mjs')] if self.plugin == 'aihub-studio'
                   else [sys.executable, str(self.package / 'scripts/ui-config.py')])
        try:
            result = subprocess.run(command, input=json.dumps(payload), text=True, encoding='utf-8',
                                    capture_output=True, cwd=self.project, env=self.environment, timeout=20)
            data = json.loads(result.stdout)
            if result.returncode or data.get('error'):
                raise ValueError()
        except (OSError, ValueError, subprocess.SubprocessError):
            raise UIError('configuration', '无法读取配置。请检查配置文件格式、调用 Skill 和 Agent 身份。', 422) from None
        return data

    def _state(self, overrides=None):
        data = self._load(overrides)
        shared = data['shared']
        loads = [shared, *data.get('models', {}).values()]
        if any(p['reason'] == 'unreadable' for load in loads for p in load['inspection']['problems']):
            raise UIError('configuration', '某个配置文件不可读取，请修复权限或文件后重新载入。', 422)
        paths = {layer['path']: layer['revision'] for load in loads for layer in load['inspection']['layers']}
        settings_path = data.get('settings_path')
        if settings_path:
            raw = (overrides[settings_path].encode('utf-8') if overrides and settings_path in overrides
                   else read(settings_path))
            paths[settings_path] = digest(raw)
        fields = []
        for definition in self.definitions:
            field = deepcopy(definition)
            key = field['id']
            readonly = False
            if key.startswith('routing.') or key == 'default_skill_reminders':
                target = settings_path or str(Path.home() / '.config' / self.plugin / 'settings.json')
                settings = data.get('settings', {})
                if key.startswith('routing.'):
                    routing = settings.get('routing', {})
                    if key == 'routing.default':
                        value, explicit = routing.get('default', 'auto'), 'default' in routing
                    else:
                        platform = key.rsplit('.', 1)[-1]
                        value = routing.get('platforms', {}).get(platform, 'inherit')
                        explicit = platform in routing.get('platforms', {})
                else:
                    reminder = data.get('reminder', {})
                    entry = next((e for e in settings.get('default_skill_reminders', {}).get('agents', [])
                                  if e['agent'] == self.options.get('agent') and e['config_dir'] == reminder.get('config_dir')), None)
                    value, explicit = (entry['enabled'], True) if entry else (True, False)
                    readonly = not bool(reminder)
                readonly = readonly or not self.options['global_enabled']
                scope = '个人全局偏好'
                if readonly:
                    field['help'] += ' 当前未启用全局配置或未指定 Agent，仅展示默认值。'
            else:
                load = data.get('models', {}).get(key, shared)
                source = load['sources'].get(key, load.get('selectionSources', {}).get(key, 'missing'))
                raw = load['values'].get(key)
                explicit = source not in ('missing', 'built-in default')
                value = raw if raw is not None else field.get('default', '')
                if field['type'] == 'boolean' and raw is not None:
                    value = raw.strip() == '1'
                elif field['type'] == 'list' and raw is not None:
                    value = [part.strip() for part in raw.split(',')]
                elif field['type'] == 'number' and raw is not None:
                    try:
                        value = int(raw)
                    except ValueError:
                        value = None
                        field['help'] += ' 当前值不是正整数，请修复。'
                if source == 'environment':
                    target, scope, readonly = '进程环境变量', '当前进程（只读）', True
                    field['help'] += ' 请修改启动 Agent 或服务时注入的环境变量，再重启本页。'
                elif explicit:
                    target = source
                    scope = '当前项目' if Path(source).is_relative_to(self.project) else '个人全局配置'
                elif self.options.get('save_scope') == 'project' or not self.options['global_enabled']:
                    target, scope = str(self.project / '.env.local'), '当前项目'
                else:
                    target, scope = str(Path(data['settings_path']).with_name('.env')), '个人全局配置'
                if not readonly and target not in paths:
                    raise UIError('target', '保存目标不在原加载器的读取范围内。', 422)
                field.setdefault('clear_help', '移除标明文件中的显式值；之后使用下一层配置或内置默认值。')
            field.update(value=value, explicit=explicit, readonly=readonly, path=target, scope=scope)
            fields.append(field)
        # Includes every consulted layer, preferences, caller and all effective values.
        fingerprint = {'data': data, 'paths': paths, 'options': self.options,
                       'environment': {f['id']: (self.environment if self.environment is not None else os.environ).get(f['id']) for f in self.definitions if f['id'].isupper()}}
        revision = hmac.new(self.secret, json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode(), hashlib.sha256).hexdigest()
        task = self.options.get('task') or {'id': self.plugin + '-configuration', 'binding': str(self.project),
            'continuation': '请在项目 ' + str(self.project) + ' 中重新检查 ' + self.plugin + ' 配置，并继续此前已授权的任务。'}
        snapshot = {'revision': revision, 'fields': fields, 'validation': '本地格式、原加载器回读与必需项检查；未验证在线鉴权',
                    'note': '修改已有值会写回当前生效文件；新值按下方标明范围保存。保存后由 Agent 继续原任务。', 'task': task}
        return snapshot, data, paths

    def snapshot(self):
        self.transaction.recover()
        return self._state()[0]

    def _validate(self, field, value):
        kind = field['type']
        valid = {'text': isinstance(value, str), 'select': value in field.get('choices', []),
                 'number': type(value) is int and 1 <= value <= 9007199254740991 if type(value) is int else False,
                 'boolean': type(value) is bool, 'list': isinstance(value, list)}.get(kind, False)
        if not valid:
            raise UIError('validation', field['label'] + '的值无效。', 422)
        strings = value if isinstance(value, list) else [value] if isinstance(value, str) else []
        if any(not isinstance(v, str) or any(c in v for c in '\r\n\0\u2028\u2029\x85') or '••••••' in v for v in strings):
            raise UIError('validation', field['label'] + '包含不支持的字符。', 422)
        if kind == 'list' and (len(value) > 50 or any(not v or re.search(r'[\s,]', v) for v in value) or len(set(value)) != len(value)):
            raise UIError('validation', field['label'] + '须为不重复的模型 ID。', 422)
        if field['id'] == 'AIHUB_SUPPORT_URL' and value:
            try:
                url = urlsplit(value)
                if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
                    raise ValueError()
                _ = url.port
            except ValueError:
                raise UIError('validation', '支持页面地址须为不含凭证、查询参数和片段的 HTTP(S) 地址。', 422) from None
        if field.get('required') and (not value or isinstance(value, str) and not value.strip()):
            raise UIError('validation', '请填写 ' + field['label'] + '，或使用“清除”。', 422)

    def save(self, changes, revision):
        if not isinstance(changes, dict) or not changes:
            raise UIError('changes', '没有待保存的修改。')
        self.transaction.recover()
        current, data, paths = self._state()
        if current['revision'] != revision:
            raise UIError('conflict', '配置已被其他操作修改。草稿仍保留，请重新载入后核对。', 409)
        fields = {f['id']: f for f in current['fields']}
        updates, settings = {}, deepcopy(data.get('settings', {}))
        settings_changed = False
        for key, change in changes.items():
            field = fields.get(key)
            if not field or field['readonly']:
                raise UIError('readonly', '变更包含未知或只读字段。', 422)
            if not isinstance(change, dict) or change.get('op') not in ('set', 'unset'):
                raise UIError('changes', '变更格式无效。')
            value = change.get('value') if change['op'] == 'set' else None
            if change['op'] == 'set':
                self._validate(field, value)
            if key.startswith('routing.'):
                settings_changed = True
                routing = settings.setdefault('routing', {'default': 'auto', 'platforms': {}})
                if key == 'routing.default':
                    routing['default'] = value or 'auto'
                else:
                    platforms = routing.setdefault('platforms', {})
                    platform = key.rsplit('.', 1)[-1]
                    if value in (None, 'inherit'):
                        platforms.pop(platform, None)
                    else:
                        platforms[platform] = value
            elif key == 'default_skill_reminders':
                settings_changed = True
                reminder = data['reminder']
                preferences = settings.setdefault(key, {'version': 1, 'agents': []})
                preferences['agents'] = [e for e in preferences['agents'] if (e['agent'], e['config_dir']) !=
                                         (self.options['agent'], reminder['config_dir'])]
                if value is not None:
                    preferences['agents'].append({'agent': self.options['agent'], 'config_dir': reminder['config_dir'], 'enabled': value})
            else:
                if type(value) is bool:
                    value = '1' if value else '0'
                elif isinstance(value, list):
                    value = ','.join(value)
                elif value is not None:
                    value = str(value)
                updates.setdefault(field['path'], {})[key] = value
        modifications = {}
        for path, values in updates.items():
            before = read(path)
            if digest(before) != paths[path]:
                raise UIError('conflict', '配置文件已变化，请重新载入。', 409)
            modifications[path] = (before, dotenv(before, values))
        if settings_changed:
            path = data['settings_path']
            before = read(path)
            if digest(before) != paths[path]:
                raise UIError('conflict', '偏好文件已变化，请重新载入。', 409)
            modifications[path] = (before, (json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode())
        overrides = {path: after.decode('utf-8') for path, (_, after) in modifications.items()}
        candidate, projected, _ = self._state(overrides)
        values = {f['id']: f['value'] for f in candidate['fields']}
        for field in candidate['fields']:
            key = field['id']
            if field.get('required') and not values[key] and changes.get(key, {}).get('op') != 'unset':
                raise UIError('validation', '请补齐 ' + field['label'] + '。', 422)
            if key in changes and changes[key]['op'] == 'set' and not active(field, values):
                raise UIError('validation', field['label'] + '当前不适用，请核对关联设置。', 422)
            if active(field, values) and not (values[key] is None and not field['explicit']) and not (field.get('required') and not values[key] and changes.get(key, {}).get('op') == 'unset'):
                self._validate(field, values[key])
        for load in [projected['shared'], *projected.get('models', {}).values()]:
            if any(p['reason'] not in ('missing',) for p in load['inspection']['problems']):
                raise UIError('validation', '修改后的配置未通过原加载器校验；未保存任何字段。', 422)
        expected_fields = {f['id']: f['value'] for f in candidate['fields']}
        def verify(written):
            fresh = self._state()[0]
            if not written and fresh['revision'] != revision:
                raise UIError('conflict', '保存前配置已变化，请重新载入。', 409)
            if written and {f['id']: f['value'] for f in fresh['fields']} != expected_fields:
                raise UIError('conflict', '回读结果与预期不一致，已尝试回滚。请重新载入。', 409)
            return fresh
        return self.transaction.apply(modifications, verify)
