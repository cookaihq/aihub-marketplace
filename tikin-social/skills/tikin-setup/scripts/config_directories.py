"""Read directory selectors only from their fixed anchors, before business files."""
import hashlib
import os
from pathlib import Path
import re

DIRECTORY_KEYS = ('TIKIN_GLOBAL_CONFIG_DIR', 'TIKIN_PROJECT_CONFIG_DIR')


def resolve_directories(global_enabled=True, file_overrides=None):
    project = Path.cwd()
    default_global = Path.home() / '.config/tikin-social'
    anchors = dict(zip(DIRECTORY_KEYS, (str(default_global / '.env'), str(project / '.env.local.tikin-social'))))
    result = dict(global_=str(default_global), project=str(project), default_global=str(default_global),
                  default_project=str(project), custom_global=False, anchors=anchors, values={}, sources={},
                  layers=[{'path': 'environment', 'values': {}}], problems=[])
    for key, scope in zip(DIRECTORY_KEYS, ('global_', 'project')):
        if scope == 'global_' and not global_enabled:
            continue
        path = anchors[key]
        row = {'path': path, 'revision': None, 'values': {}}
        try:
            override = (file_overrides or {}).get(path, ...)
            if override is None:
                raise FileNotFoundError()
            raw = Path(path).read_bytes() if override is ... else override.encode('utf-8')
            row['revision'] = hashlib.sha256(raw).hexdigest()
            for line in raw.decode('utf-8-sig').splitlines():
                match = re.fullmatch(r'\s*' + key + r'\s*=\s*(.*?)\s*', line)
                if match:
                    value = match[1]
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    row['values'][key] = value
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            row['error'] = 'unreadable'
            result['problems'].append({'source': path, 'reason': 'unreadable'})
        result['layers'].append(row)
        injected = os.environ.get(key, '')
        result['layers'][0]['values'][key] = injected
        value = injected if injected.strip() else row['values'].get(key, '')
        if not value.strip():
            continue
        source = 'environment' if injected.strip() else path
        result['values'][key], result['sources'][key] = value, source
        if not Path(value.strip()).is_absolute() or re.search(r'[\x00-\x1f\x7f\u0085\u2028\u2029]', value):
            result['problems'].append({'key': key, 'source': source, 'reason': 'expected_absolute_config_directory'})
            continue
        result[scope] = os.path.abspath(value.strip())
        if scope == 'global_':
            result['custom_global'] = True
    result['global'] = result.pop('global_')
    return result


def global_config_directory():
    result = resolve_directories()
    if result['problems']:
        raise ValueError('Cannot read configuration directory settings; run config-check.')
    return Path(result['global'])
