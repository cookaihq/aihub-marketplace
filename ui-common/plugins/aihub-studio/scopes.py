"""Studio's field scopes project through its original loader and file transaction."""
from configuration import Configuration
from skill_ui.contracts import UIError
from skill_ui.scopes import ScopePlanner, annotate_snapshot
from skill_ui.storage import active


class StudioConfiguration(Configuration):
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
            if field['type'] == 'select':
                field['choice_labels'] = {'auto': '自动选择', 'confirm': '切换前确认', 'off': '关闭',
                    'preflight_only': '仅预检', 'host': '当前 Agent', 'aihub': 'AIhub 服务模型'}
        focus = ['AIHUB_API_KEY']
        caller = self.options.get('skill')
        model = 'AIHUB_' + caller.removeprefix('aihub-').upper() + '_MODELS' if caller else ''
        if model:
            focus.append(model)
        if caller == 'aihub-audio':
            focus.extend(['AIHUB_ELEVENLABS_DEFAULT_VOICE_ID', 'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS'])
        focus.append('AIHUB_RESULT_CHECK_ENABLED')
        snapshot['presentation'] = {'title': 'AIhub 设置', 'description': '展开项目或全局设置，查看详情或切换生效位置。',
                                    'focus': focus}
        if self.options.get('save_scope') == 'project':
            snapshot['presentation']['initial_target'] = snapshot['default_targets']['project']
        snapshot['validation'] = '本地格式与原加载器回读；未验证在线鉴权。'
        snapshot['note'] = '切换位置会清理遮蔽目标的高层同项设置；已保存的清理不会因撤销草稿恢复。'
        annotate_snapshot(snapshot, self.secret, lambda f, value: value is None or
            isinstance(value, str) and not value.strip() or
            isinstance(value, list) and not value and f.get('encoding') != 'json')
        return snapshot, data, paths

    def _candidate(self, changes, revision, target=None):
        current, _, _ = self._state()
        return ScopePlanner(current, self.secret, lambda files: self._project(files, revision)).plan(changes, revision)

    def _project(self, files, revision):
        modifications, changed = {}, set()
        for target, changes in files.items():
            # The original adapter owns allowlists, encoding, private paths and
            # type checks. Only the complete projection supplies dependencies.
            _, edits = super()._candidate(changes, revision, target)
            if modifications.keys() & edits.keys():
                raise UIError('target', '同一文件不能重复指定。', 422)
            modifications.update(edits)
            changed.update(changes)
        candidate, projected, _ = self._state({path: after.decode('utf-8')
            for path, (_, after) in modifications.items()})
        errors = list(candidate['validation_errors'])
        values = {field['id']: field['effective']['value'] for field in candidate['fields']}
        for field in candidate['fields']:
            key = field['id']
            if key not in changed:
                continue
            if field.get('required') and field['effective']['empty']:
                errors.append('修改后没有可用的 ' + field['label'] + '，请先配置回退值。')
            if any(changes.get(key, {}).get('op') == 'set' for changes in files.values()) and not active(field, values):
                errors.append(field['label'] + '当前不适用，请核对关联设置。')
        for load in [projected['shared'], *projected.get('models', {}).values()]:
            if any(problem['reason'] != 'missing' for problem in load['inspection']['problems']):
                errors.append('修改后的配置未通过原加载器校验；请修复配置后保存。')
        candidate['validation_errors'] = sorted(set(errors))
        return candidate, modifications

    def preview(self, changes, revision):
        return self._candidate(changes, revision)[0]

    def save(self, changes, revision):
        return super().save(changes, revision, None)
