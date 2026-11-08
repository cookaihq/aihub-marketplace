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

    def _private_project_file(self, path):
        return Path(path) in (self.project / ('.env.local.' + self.plugin), self.project / '.env.local')

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

    @staticmethod
    def _layer_id(path):
        return 'process' if path == 'environment' else 'file_' + hashlib.sha256(path.encode()).hexdigest()[:20]

    def _layer(self, path, home, enabled=True):
        target = Path(path)
        if path == 'environment':
            return dict(id='process', name='进程环境变量', scope='process', scope_label='本次启动注入，只读。',
                        path='进程环境变量', readonly=True, enabled=True, rank=0)
        plugin_root = home / '.config' / self.plugin
        if target.parent == self.project:
            scope, name = 'project', '项目 · ' + target.name
            plugin_file = target.name in ('.env.local.' + self.plugin, '.env.' + self.plugin)
            label = ('仅当前项目的 ' + self.plugin + ' 各 Skill 共用。' if plugin_file
                     else '当前项目中读取同名字段的 Skill 共用。')
            rank = {'.env.local.' + self.plugin: 10, '.env.' + self.plugin: 20,
                    '.env.local': 30, '.env': 40}[target.name]
        else:
            scope, label = 'global', '同一用户的多个项目与 Agent 共用；Skill 专用文件仅影响对应 Skill。'
            name = '全局 · ' + str(target.relative_to(home / '.config')).replace('\\', '/') if target.is_relative_to(home / '.config') else '全局 · ' + target.name
            if target.parent == plugin_root:
                rank = 70 if target.name == '.env.local' else 80
            elif target.parent.parent == plugin_root:
                rank = 50 if target.name == '.env.local' else 60
            else:
                rank = 90
        if target.name == 'settings.json':
            rank = 100
            label = 'Plugin 全局偏好；提醒按当前 Agent 和配置目录绑定，与 dotenv 文件独立保存。'
        return dict(id=self._layer_id(path), name=name, scope=scope, scope_label=label,
                    path=path, readonly=not enabled, enabled=enabled, rank=rank)

    @staticmethod
    def _typed(field, raw):
        if not isinstance(raw, str) or raw == '':
            return raw
        if field['type'] == 'boolean':
            return raw.strip() == '1' if raw.strip() in ('0', '1') else raw
        if field['type'] == 'list':
            return [part.strip() for part in raw.split(',')]
        if field['type'] == 'number':
            return int(raw.strip()) if re.fullmatch(r'\d+', raw.strip()) else raw
        if field['type'] == 'select':
            return raw.strip()
        return raw

    def _state(self, overrides=None):
        data = self._load(overrides)
        shared = data['shared']
        loads = [shared, *data.get('models', {}).values()]
        home = Path(data['home_directory'])
        paths = {layer['path']: layer['revision'] for load in loads for layer in load['inspection']['layers']}
        layers = {self._layer_id(path): self._layer(path, home) for path in ['environment', *paths]}
        settings_path = data.get('settings_path') or str(home / '.config' / self.plugin / 'settings.json')
        settings_id = self._layer_id(settings_path)
        settings_enabled = bool(self.options['global_enabled'])
        layers[settings_id] = self._layer(settings_path, home, settings_enabled)
        if settings_enabled:
            raw = (overrides[settings_path].encode('utf-8') if overrides and settings_path in overrides else read(settings_path))
            paths[settings_path] = digest(raw)
        fields = []
        errors = []
        for definition in self.definitions:
            field = deepcopy(definition)
            key = field['id']
            rows = []
            targets = []
            is_settings = key.startswith('routing.') or key == 'default_skill_reminders'
            if is_settings:
                settings = data.get('settings', {})
                explicit = False
                value = field.get('default')
                if key.startswith('routing.'):
                    routing = settings.get('routing', {})
                    if key == 'routing.default':
                        explicit, value = 'default' in routing, routing.get('default', 'auto')
                    else:
                        platform = key.rsplit('.', 1)[-1]
                        explicit = platform in routing.get('platforms', {})
                        value = routing.get('platforms', {}).get(platform, 'inherit')
                        field['help'] += ' 当前实际调用方式：' + (routing.get('default', 'auto') if value == 'inherit' else value) + '。'
                else:
                    reminder = data.get('reminder', {})
                    entry = next((e for e in settings.get('default_skill_reminders', {}).get('agents', [])
                                  if e['agent'] == self.options.get('agent') and e['config_dir'] == reminder.get('config_dir')), None)
                    explicit, value = (True, entry['enabled']) if entry else (False, True)
                explicit = explicit and paths.get(settings_path) is not None
                readonly = not settings_enabled or (key == 'default_skill_reminders' and not data.get('reminder'))
                field['readonly'] = readonly
                if readonly:
                    field['help'] += ' 本次未启用全局配置或未指定 Agent，此项只读。'
                else:
                    targets = [settings_id]
                for layer in layers.values():
                    applies = layer['id'] == settings_id and settings_enabled
                    rows.append(dict(layer=layer['id'], present=explicit if applies else False,
                                     status=('effective' if explicit else 'missing') if applies else 'skipped',
                                     value=value if applies and explicit else None,
                                     **({} if applies else {'message': '此文件不参与该偏好的读取。'})))
                effective = dict(source=settings_id if explicit else 'default', status='set' if explicit else 'default', value=value)
            else:
                load = data.get('models', {}).get(key, shared)
                source = load['sources'].get(key, load.get('selectionSources', {}).get(key, 'missing'))
                value = self._typed(field, load['values'].get(key, field.get('default', '')))
                explicit = source not in ('missing', 'built-in default')
                effective = dict(source=self._layer_id(source) if explicit else ('default' if 'default' in field else None),
                                 status='set' if explicit else ('default' if 'default' in field else 'missing' if field.get('required') else 'optional'),
                                 value=value)
                layer_values = {self._layer_id(row['path']): row for row in load['layerValues']}
                for layer in layers.values():
                    row = layer_values.get(layer['id'])
                    present = row is not None and key in row['values']
                    raw = row['values'].get(key) if row else None
                    if row is None:
                        status, message = 'skipped', '此文件不参与该项读取（其他 Skill 专用或独立偏好文件）。'
                    elif row.get('error'):
                        status, message = 'error', '文件无法读取；原业务加载器会报错，请修复后重新载入。'
                        effective.update(status='error', message=message)
                        errors.append(message)
                    elif not present:
                        status, message = 'missing', ''
                    elif not str(raw).strip():
                        status, message = 'empty', '空值继续向下回退。'
                    else:
                        status, message = ('effective' if layer['id'] == effective['source'] else 'shadowed'), ''
                    rows.append(dict(layer=layer['id'], present=present, status=status, value=self._typed(field, raw),
                                     **({'message': message} if message else {})))
                    if row is not None and not layer['readonly']:
                        # New project secrets go only to declared local files. Existing
                        # explicit keys may be removed or repaired in their own file.
                        if not field.get('sensitive') or layer['scope'] != 'project' or self._private_project_file(layer['path']) or present:
                            targets.append(layer['id'])
                if effective['status'] != 'error' and value not in (None, ''):
                    try:
                        self._validate(field, value)
                    except UIError as error:
                        effective.update(status='invalid', message=error.message)
                        errors.append(error.message)
                # Keep inherited files editable under a read-only environment winner.
                field['readonly'] = False
            field.update(effective=effective, rows=rows, targets=targets)
            fields.append(field)
        values = {f['id']: f['effective']['value'] for f in fields}
        for field in fields:
            field['active'] = active(field, values)
        # Revision covers all consulted files, actual values, private explicit
        # layers, preferences and caller/options, including the injected process.
        fingerprint = {'data': data, 'paths': paths, 'options': self.options}
        revision = hmac.new(self.secret, json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode(), hashlib.sha256).hexdigest()
        task = self.options.get('task') or {'id': self.plugin + '-configuration', 'binding': str(self.project),
            'continuation': '请在项目 ' + str(self.project) + ' 中重新检查 ' + self.plugin + ' 配置，并继续此前已授权的任务。'}
        defaults = {'project': self._layer_id(str(self.project / ('.env.local.' + self.plugin)))}
        if settings_enabled:
            defaults['global'] = self._layer_id(str(home / '.config' / self.plugin / '.env'))
        snapshot = {'revision': revision, 'layers': sorted(layers.values(), key=lambda layer: (layer['rank'], layer['path'])),
                    'fields': fields, 'default_targets': defaults, 'validation_errors': sorted(set(errors)),
                    'validation': '本地格式、原加载器回读与必需项检查',
                    'note': '按项展示当前生效来源。编辑与保存只作用于所选文件；更高层仍可覆盖它。仅校验本机配置，不验证在线鉴权。' +
                            (' 全局配置本次已关闭。' if not settings_enabled else ''),
                    'task': task}
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

    def _candidate(self, changes, revision, target):
        if not isinstance(changes, dict) or not changes:
            raise UIError('changes', '没有待保存的修改。')
        current, data, paths = self._state()
        if current['revision'] != revision:
            raise UIError('conflict', '配置已被其他操作修改。草稿仍保留，请重新载入后核对。', 409)
        layer = next((layer for layer in current['layers'] if layer['id'] == target), None)
        if not layer or layer['readonly'] or layer['path'] not in paths:
            raise UIError('target', '请选择原加载器允许写入的具体配置文件。', 422)
        fields = {f['id']: f for f in current['fields']}
        updates, settings = {}, deepcopy(data.get('settings', {}))
        settings_changed = False
        for key, change in changes.items():
            field = fields.get(key)
            if not field or target not in field['targets']:
                raise UIError('readonly', '此文件不允许保存所选字段。', 422)
            if not isinstance(change, dict) or change.get('op') not in ('set', 'unset'):
                raise UIError('changes', '变更格式无效。')
            value = change.get('value') if change['op'] == 'set' else None
            if change['op'] == 'set':
                # Empty dotenv values have the loader's fall-through semantics,
                # including numeric/boolean settings. settings.json remains typed.
                if not (key.isupper() and value == ''):
                    self._validate(field, value)
                if field.get('sensitive') and layer['scope'] == 'project' and not self._private_project_file(layer['path']):
                    old = next(row for row in field['rows'] if row['layer'] == target)
                    if value and not old.get('value'):
                        raise UIError('target', '新增项目密钥只能保存到 .env.local.' + self.plugin + ' 或 .env.local；此文件仅允许修复已有密钥或移除设置。', 422)
            if key.startswith('routing.'):
                settings_changed = True
                routing = settings.setdefault('routing', {'default': 'auto', 'platforms': {}})
                if key == 'routing.default':
                    # The real Tikin settings schema requires this member.
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
                updates[key] = value
        path = layer['path']
        before = read(path)
        if digest(before) != paths[path]:
            raise UIError('conflict', '配置文件已变化，请重新载入。', 409)
        after = ((json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode() if settings_changed else dotenv(before, updates))
        candidate, projected, _ = self._state({path: after.decode('utf-8')})
        errors = list(candidate['validation_errors'])
        values = {f['id']: f['effective']['value'] for f in candidate['fields']}
        for field in candidate['fields']:
            key = field['id']
            explicitly_cleared = changes.get(key, {}).get('op') == 'unset' or changes.get(key) == {'op': 'set', 'value': ''}
            if field.get('required') and not values[key] and not explicitly_cleared:
                errors.append('请补齐 ' + field['label'] + '。')
            if key in changes and changes[key]['op'] == 'set' and not active(field, values):
                errors.append(field['label'] + '当前不适用，请核对关联设置。')
        for load in [projected['shared'], *projected.get('models', {}).values()]:
            if any(p['reason'] not in ('missing',) for p in load['inspection']['problems']):
                errors.append('修改后的配置未通过原加载器校验；请修复配置后保存。')
        candidate['validation_errors'] = sorted(set(errors))
        return candidate, {path: (before, after)}

    def preview(self, changes, revision, target):
        # No recovery or persistence here: preview is strictly side-effect free.
        return self._candidate(changes, revision, target)[0]

    def save(self, changes, revision, target):
        self.transaction.recover()
        candidate, modifications = self._candidate(changes, revision, target)
        if candidate['validation_errors']:
            raise UIError('validation', '；'.join(candidate['validation_errors']), 422)
        def verify(written):
            fresh = self._state()[0]
            expected = candidate['revision'] if written else revision
            if fresh['revision'] != expected:
                raise UIError('conflict', '配置已变化或回读与预览不一致；未覆盖外部修改，请重新载入核对。', 409)
            return fresh
        return self.transaction.apply(modifications, verify)
