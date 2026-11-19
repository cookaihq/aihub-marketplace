"""Shared field drafts, directory projection and original multi-file transaction."""
from pathlib import Path

from configuration import Configuration
from persistence import read
from skill_ui.contracts import UIError
from skill_ui.scopes import ScopePlanner, annotate_snapshot
from skill_ui.directories import selector_edits, retarget_request, check_directory_revision, planning_snapshot
from skill_ui.storage import active
from skill_ui.batches import dependencies


class ScopedConfiguration(Configuration):
    def _state(self, overrides=None):
        snapshot, data, paths = super()._state(overrides)
        for layer in snapshot['layers']:
            if layer['id'] != 'process':
                layer['exists'] = paths.get(layer['path']) is not None
        for field in snapshot['fields']:
            key = field['id']
            field['config_key'] = ('$.default_skill_reminders.agents[agent,config_dir].enabled'
                if key == 'default_skill_reminders' else '$.' + '.'.join(field['settings_path'])
                if field.get('settings_path') else key)
        snapshot['presentation'] = {'title': 'Tikin 设置', 'description': '按项编辑设置，展开项目或全局可查看配置文件。',
                                    'focus': ['TIKIN_API_KEY', 'routing.default']}
        if self.options.get('save_scope') == 'project':
            snapshot['presentation']['initial_target'] = snapshot['default_targets']['project']
        annotate_snapshot(snapshot, self.secret, lambda f, value: value is None or
            isinstance(value, str) and not value.strip() or
            isinstance(value, list) and not value and f.get('encoding') != 'json')
        return snapshot, data, paths

    @staticmethod
    def _destination(layer, before, after):
        path = Path(layer['path'])
        scope = layer['scope']
        if scope not in ('project', 'global') or before[scope] == after[scope]:
            return path
        root = Path(before[scope])
        if path.is_relative_to(root):
            return Path(after[scope]) / path.relative_to(root)
        # Ordinary Skill fallback exits the chain when the global root is set.
        return Path(after[scope]) / '.env'

    def _candidate(self, request, revision, *, saving=False):
        current, _, _ = self._state()
        if current['revision'] != revision:
            raise UIError('conflict', '配置已变化。草稿仍保留，请重新载入后核对。', 409)
        anchors = {}
        for target, selectors in selector_edits(current, request).items():
            _, edits = self._file_candidate(selectors, revision, target)
            anchors.update(edits)
        anchor_overrides = {path: after.decode('utf-8') for path, (_, after) in anchors.items()}
        if not anchors:
            return ScopePlanner(current, self.secret, lambda files: self._project(files, revision)).plan(request, revision)

        prospective, _, _ = self._state(anchor_overrides)
        baseline_revision = prospective['revision']
        check_directory_revision(request, baseline_revision, saving=saving)
        normalized, unchanged = retarget_request(current, prospective, request,
            lambda field, layer: self._layer_id(str(self._destination(layer, current['directories'], prospective['directories']))))
        candidate, modifications = ScopePlanner(planning_snapshot(current, prospective), self.secret,
            lambda files: self._project(files, baseline_revision, anchor_overrides, anchors)).plan(normalized, baseline_revision)
        candidate['unchanged_fields'].extend(unchanged)
        candidate['directory_revision'] = baseline_revision
        return candidate, modifications

    def _project(self, files, revision, overrides=None, anchors=None):
        modifications, changed = dict(anchors or {}), set()
        for target, changes in files.items():
            _, edits = self._file_candidate(changes, revision, target, overrides)
            for path, (_, after) in edits.items():
                before = modifications[path][0] if path in modifications else read(path)
                modifications[path] = before, after
            changed.update(changes)
        candidate, projected, _ = self._state({path: after.decode('utf-8')
            for path, (_, after) in modifications.items()})
        errors = []
        graph = dependencies(candidate)
        related, pending = set(changed), set(changed)
        while pending:
            key = pending.pop()
            additions = graph[key] - related
            related.update(additions)
            pending.update(additions)
        values = {field['id']: field['effective']['value'] for field in candidate['fields']}
        for field in candidate['fields']:
            key = field['id']
            if key not in related:
                continue
            if field['effective']['status'] in ('error', 'invalid'):
                errors.append(field['effective'].get('message', field['label'] + '无法读取或格式无效。'))
            if field.get('required') and field['effective']['empty']:
                errors.append('修改后没有可用的 ' + field['label'] + '，请先配置回退值。')
            if any(changes.get(key, {}).get('op') == 'set' for changes in files.values()) and not active(field, values):
                errors.append(field['label'] + '当前不适用，请核对关联设置。')
        for load in [projected['shared'], *projected.get('models', {}).values()]:
            if any(problem['reason'] != 'missing' and problem.get('key') in related for problem in load['inspection']['problems']):
                errors.append('修改后的配置未通过原加载器校验；请修复配置后保存。')
        candidate['validation_errors'] = sorted(set(errors))
        candidate['directory_targets'] = {key: next(layer['path'] for layer in candidate['layers'] if layer['id'] == target)
            for target, changes in files.items() for key in changes}
        return candidate, modifications

    def preview(self, changes, revision):
        return self._candidate(changes, revision)[0]
