"""Content identity shared by native Plugin and complete Skills-only installs."""
import hashlib
import json
from pathlib import Path
from typing import Any

IDENTITY_PATH = Path('tikin-setup/references/distribution.json')
IGNORED = {'.venv', '__pycache__', '.git', '.DS_Store'}


def content_files(skills: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for skill in sorted(skills.glob('tikin-*')):
        if not skill.is_dir():
            continue
        for file in sorted(skill.rglob('*')):
            relative = file.relative_to(skills)
            if (relative == IDENTITY_PATH or any(part in IGNORED for part in relative.parts)
                    or file.suffix == '.pyc' or not file.is_file()):
                continue
            # User credentials are never part of a distribution or its content digest.
            if file.name.startswith('.env'):
                continue
            files[relative.as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    return files


def suite_digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inspect(setup: Path) -> dict[str, Any]:
    skills = setup.resolve().parent
    result: dict[str, Any] = {'status': 'unverified', 'setup_path': str(setup.resolve()),
                              'skills_path': str(skills), 'verification': 'local-content'}
    try:
        identity = json.loads((skills / IDENTITY_PATH).read_text(encoding='utf-8'))
        actual = content_files(skills)
        expected = identity['files']
        result.update({key: identity[key] for key in
                       ('plugin_version', 'source', 'tag', 'suite_sha256', 'index_sha256')})
        result['skill_count'] = len(identity['skills'])
        result['skill_versions'] = identity['skills']
        result['changed_files'] = sorted(name for name in expected if actual.get(name) != expected[name])
        result['additional_files'] = sorted(set(actual) - set(expected))
        manifests = [skills.parent / directory / 'plugin.json' for directory in
                     ('.claude-plugin', '.codex-plugin', '.codebuddy-plugin')]
        found = [file for file in manifests if file.is_file()]
        result['form'] = 'plugin' if found else 'skills-only'
        manifest_data = [json.loads(file.read_text(encoding='utf-8')) for file in found]
        manifest_ok = len(found) in (0, 3) and all(
            item.get('version') == identity['plugin_version'] and item.get('name') == 'tikin-social'
            for item in manifest_data)
        result['status'] = ('verified' if manifest_ok and suite_digest(actual) == identity['suite_sha256']
                            and suite_digest(expected) == identity['suite_sha256'] else 'modified')
    except (OSError, ValueError, KeyError, TypeError):
        result['status'] = 'unverified'
    return result
