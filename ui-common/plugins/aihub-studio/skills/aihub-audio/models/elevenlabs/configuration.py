DEFAULT_VOICE = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID'
FAVORITES = 'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS'


def fields(field):
    voice_options = dict(max_length=512, trimmed=True,
                         value_pattern=r'[^\x00-\x1f\x7f-\x9f\u2028\u2029]+')
    return [
        field(DEFAULT_VOICE, 'ElevenLabs 默认音色', '语音合成', default='', **voice_options,
              help='从 ElevenLabs 预置音色库筛选、试听并保存。用于单人语音；任务显式指定音色时优先使用任务设置。'),
        field(FAVORITES, 'ElevenLabs 收藏音色', '语音合成', 'list', default=[], encoding='json',
              max_items=2000, item_label='音色 ID', **voice_options,
              help='在用户选择的项目或全局配置中保存。项目列表覆盖全局列表，空列表表示当前范围不收藏音色。'),
    ]
