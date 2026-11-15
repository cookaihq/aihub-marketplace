"""ElevenLabs presets use the caller's AIhub credentials and existing service lifetime."""
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from skill_ui.contracts import UIError
from skill_ui.storage import atomic_json, file_lock, private_directory

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


def _request(configuration, operation=None, expected_identity=None):
    try:
        result = subprocess.run(['node', str(configuration.package / 'scripts/voice-library.mjs')],
            input=json.dumps({'project': str(configuration.project), 'global_enabled': configuration.options['global_enabled'],
                              'provider': 'elevenlabs', 'operation': operation, 'expected_identity': expected_identity}),
            cwd=configuration.project, env=configuration.environment, capture_output=True, text=True,
            encoding='utf-8', timeout=35)
        data = json.loads(result.stdout)
        if data.get('error'):
            raise UIError(data['error'], data['message'], 409 if data['error'] == 'conflict' else 502)
        if result.returncode:
            raise ValueError()
        if operation == 'cache-identity':
            if not re.fullmatch(r'[a-f0-9]{64}', data.get('identity', '')) or not isinstance(data.get('home_directory'), str):
                raise ValueError()
            return data
        if not isinstance(data.get('voices'), list):
            raise ValueError()
        for voice in data['voices']:
            voice['sample_audio'] = sample_url(voice.get('sample_audio'))
        return data
    except (OSError, ValueError, subprocess.SubprocessError):
        raise UIError('voice_library', 'ElevenLabs 预置音色库暂时无法读取，请重试；已保存的音色和收藏保留。', 502) from None


def load(configuration, refresh=False):
    identity = _request(configuration, 'cache-identity')
    directory = Path(identity['home_directory']) / '.config/aihub-studio/cache/voice-library'
    path = directory / (identity['identity'] + '.json')
    private_directory(directory, owner_path=configuration.project)
    with file_lock(path.with_suffix('.lock'), protect_git=True, owner_path=configuration.project):
        if not refresh:
            try:
                cached = json.loads(path.read_text(encoding='utf-8'))
                if (cached.get('identity') == identity['identity'] and isinstance(cached.get('voices'), list)
                        and isinstance(cached.get('saved_at'), (int, float))):
                    for voice in cached['voices']:
                        voice['sample_audio'] = sample_url(voice.get('sample_audio'))
                    return {'voices': cached['voices'], 'saved_at': cached['saved_at']}
            except (FileNotFoundError, ValueError, TypeError):
                pass
        # Download first. Failure leaves the last successful cache intact.
        data = _request(configuration, expected_identity=identity['identity'])
        if _request(configuration, 'cache-identity')['identity'] != identity['identity']:
            raise UIError('conflict', '音色库账号已改变，请重新载入。', 409)
        data['saved_at'] = time.time() * 1000
        atomic_json(path, dict(data, identity=identity['identity']), protect_git=True, owner_path=configuration.project)
        return data
