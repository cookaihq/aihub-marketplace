"""Read the authenticated voice catalogue through the original audio configuration chain."""
import json
import subprocess
from urllib.parse import urlsplit

from skill_ui.contracts import UIError

# Hosts in the provider's published preset examples. Audio is fetched by the
# browser without an AIhub authorization header, with no-referrer and its CSP.
SAMPLE_ORIGINS = ('https://filecdn.minimax.chat', 'https://ftres.oss-cn-beijing.aliyuncs.com',
                  'https://ftapp.oss-cn-beijing.aliyuncs.com')


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
            input=json.dumps({'project': str(configuration.project), 'global_enabled': configuration.options['global_enabled']}),
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
        raise UIError('voice_library', '音色库暂时无法读取，请稍后重试；已有设置与收藏保留。', 502) from None
