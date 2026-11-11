DEFAULT_VOICE = 'AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID'
FAVORITES = 'audio.minimax_speech.favorite_voice_ids'


def fields(field):
    return [
        field(DEFAULT_VOICE, 'MiniMax Speech 默认音色', '语音合成', default='',
              max_length=512, trimmed=True, value_pattern=r'[^\x00-\x1f\x7f-\x9f\u2028\u2029]+',
              help='用于 Speech 2.8 HD / Turbo。任务已指定音色时优先使用任务设置；留空不预设音色。',
              clear_help='移除此文件中的默认音色，按来源优先级继续回退；不会修改已经开始的任务。'),
        field(FAVORITES, 'MiniMax Speech 收藏音色', '语音合成', 'list', default=[],
              settings_path=['audio', 'minimax_speech', 'favorite_voice_ids'],
              max_items=2000, max_length=512, trimmed=True,
              value_pattern=r'[^\x00-\x1f\x7f-\x9f\u2028\u2029]+', item_label='音色 ID',
              help='个人全局候选音色，跨项目与 Agent 共用；收藏不会自动改变默认音色。',
              clear_help='清空收藏列表，不修改默认音色或既有任务。'),
    ]
