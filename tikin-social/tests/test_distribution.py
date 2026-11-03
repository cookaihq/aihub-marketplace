"""Inspect real Plugin and whole-suite Skills-only installations through the CLI."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tikin-distribution-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, 'TIKIN_API_KEY': 'synthetic-install-key',
                    'TIKIN_BASE_URL': 'http://127.0.0.1:1',
                    'UV_PROJECT_ENVIRONMENT': str(ROOT / 'skills/tikin-setup/.venv')}

    def copy(self, plugin):
        target = self.root / ('plugin' if plugin else 'skills-only')
        source = ROOT if plugin else ROOT / 'skills'
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('.venv', '__pycache__', '.git'))
        return target / 'skills' if plugin else target

    def status(self, skills):
        command = ['uv', 'run', '--frozen', '--project', str(skills / 'tikin-setup'),
                   'python', str(skills / 'tikin-setup/scripts/tikin-config'),
                   '--skill', 'tikin-douyin', '--no-global-config', 'status']
        result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_both_distributions_identify_the_same_complete_suite_and_index(self):
        native = self.status(self.copy(True))
        standalone = self.status(self.copy(False))
        for result in (native, standalone):
            installed = result['installation']
            self.assertEqual(installed['status'], 'verified')
            self.assertEqual(installed['index_sha256'], '285a879c2e134a7925a9985feac4f4897d806e59c53062e98076b3fb8ae2bbb7')
            self.assertEqual(installed['skill_count'], 17)
            self.assertEqual(result['key_source'], 'environment')
            self.assertNotIn('synthetic-install-key', json.dumps(result))
        self.assertEqual(native['installation']['suite_sha256'], standalone['installation']['suite_sha256'])
        self.assertEqual(native['installation']['plugin_version'], standalone['installation']['plugin_version'])
        self.assertEqual(native['installation']['form'], 'plugin')
        self.assertEqual(standalone['installation']['form'], 'skills-only')

    def test_incomplete_native_package_is_not_reported_as_verified(self):
        skills = self.copy(True)
        (skills.parent / '.codebuddy-plugin/plugin.json').unlink()
        self.assertEqual(self.status(skills)['installation']['status'], 'modified')

    def test_changed_or_missing_skill_is_identified_without_changing_user_files(self):
        skills = self.copy(False)
        changed = skills / 'tikin-douyin/SKILL.md'
        changed.write_text(changed.read_text() + '\nMy local note.\n')
        config = skills / 'tikin-setup/.env'
        config.write_text('TIKIN_API_KEY=retained-local-key\n')
        (skills / 'tikin-youtube/SKILL.md').unlink()
        result = self.status(skills)['installation']
        self.assertEqual(result['status'], 'modified')
        self.assertEqual(result['changed_files'], ['tikin-douyin/SKILL.md', 'tikin-youtube/SKILL.md'])
        self.assertIn('My local note.', changed.read_text())
        self.assertEqual(config.read_text(), 'TIKIN_API_KEY=retained-local-key\n')
        self.assertNotIn('retained-local-key', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
