"""Read the frozen, same-source public contract without a network request."""
import json
from pathlib import Path
from typing import Any

REFERENCES = Path(__file__).resolve().parents[2] / 'tikin-endpoint-discovery/references'
CAPTION_CREATE = '/api/v1/youtube/web_v2/get_video_captions'
CAPTION_RESULT = '/api/v1/youtube/web_v2/get_video_captions_result'
LINKEDIN_PREFIX = '/api/v1/linkedin/web_v2/async/'
LINKEDIN_CREATES = frozenset(LINKEDIN_PREFIX + suffix for suffix in (
    'create_company_profile_task', 'create_post_detail_task', 'create_user_profile_task'))
LINKEDIN_STATUS = LINKEDIN_PREFIX + 'get_task_status'
LINKEDIN_RESULT = LINKEDIN_PREFIX + 'get_task_result'


def side_effects(path: str, method: str) -> bool | None:
    if path in LINKEDIN_CREATES or path == CAPTION_CREATE or method not in ('GET', 'HEAD', 'OPTIONS'):
        return True
    if path in (CAPTION_RESULT, LINKEDIN_STATUS, LINKEDIN_RESULT):
        return False
    return None


def read(name: str) -> Any:
    return json.loads((REFERENCES / name).read_text(encoding='utf-8'))


def describe(path: str, method: str) -> dict[str, Any]:
    document = read('openapi.json')
    operation = document['paths'].get(path, {}).get(method.lower())
    if operation is None:
        retired = read('request-changes.json')['retired']
        return {'error': 'operation_not_in_catalog', 'migration': next(
            (row for row in retired if row['operation'] == method + ' ' + path), None)}
    components: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get('$ref')
            if ref and ref not in seen:
                if not ref.startswith('#/components/'):
                    raise ValueError('non-local schema reference')
                seen.add(ref)
                _, _, group, name = ref.split('/', 3)
                name = name.replace('~1', '/').replace('~0', '~')
                target = document['components'][group][name]
                components.setdefault(group, {})[name] = target
                collect(target)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(operation)
    cohorts = read('catalog-cohorts.json')['cohorts']
    cohort = next((name for name, rows in cohorts.items()
                   if any(row['operation'] == method + ' ' + path for row in rows)), None)
    return {'method': method, 'path': path, 'operation': operation, 'components': components,
            'catalog': read('catalog-identity.json'), 'catalog_price': read('catalog-prices.json').get(path),
            'cohort': cohort, 'real_acceptance': 'pending',
            'side_effects': side_effects(path, method)}
