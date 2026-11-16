"""Studio's field scopes project through its original loader and file transaction."""
from scoped_configuration import ScopedConfiguration


class StudioConfiguration(ScopedConfiguration):
    def _state(self, overrides=None):
        snapshot, data, paths = super()._state(overrides)
        for field in snapshot['fields']:
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
        return snapshot, data, paths
