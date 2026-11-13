"""ElevenLabs presets use the caller's AIhub credentials and existing service lifetime."""
import json
import subprocess
from urllib.parse import urlsplit
from skill_ui.contracts import UIError

SAMPLE_ORIGINS = ('https://storage.googleapis.com', 'https://api.us.elevenlabs.io')


def sample_url(value):
    try:
        url = urlsplit(value)
        if (url.scheme == 'https' and not url.username and not url.password and not url.fragment
                and url.port in (None, 443) and 'https://' + (url.hostname or '') in SAMPLE_ORIGINS):
            return value
    except (ValueError, TypeError):
        pass
    return ''


def load(configuration):
    try:
        result = subprocess.run(['node', str(configuration.package / 'scripts/voice-library.mjs')],
            input=json.dumps({'project': str(configuration.project), 'global_enabled': configuration.options['global_enabled'],
                              'provider': 'elevenlabs'}),
            cwd=configuration.project, env=configuration.environment, capture_output=True, text=True,
            encoding='utf-8', timeout=35)
        data = json.loads(result.stdout)
        if data.get('error'):
            raise UIError('voice_library', data['message'], 502)
        if result.returncode or not isinstance(data.get('voices'), list):
            raise ValueError()
        for voice in data['voices']:
            voice['sample_audio'] = sample_url(voice.get('sample_audio'))
        return data
    except (OSError, ValueError, subprocess.SubprocessError):
        raise UIError('voice_library', 'ElevenLabs 预置音色库暂时无法读取，请重试；已保存的音色和收藏保留。', 502) from None
