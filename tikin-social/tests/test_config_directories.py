"""Directory selection through the shipped CLI, using synthetic home and project."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SETUP = Path(__file__).resolve().parents[1] / 'skills/tikin-setup'
PYTHON = SETUP / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
TMP = Path(os.environ.get('SKILL_UI_TEST_TMP', Path.cwd() / 'tmp' / 'config-directory-tests')).resolve()
TMP.mkdir(parents=True, exist_ok=True)


class ConfigDirectories(unittest.TestCase):
    def test_new_roots_replace_old_business_sources_and_settings(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temporary:
            project = Path(temporary)
            user, global_root, project_root = (project / name for name in ('user', '配置 global', '配置 project'))
            anchor = user / '.config/tikin-social'
            ordinary = user / '.config/tikin-douyin'
            for path in (user, global_root, project_root, anchor, ordinary):
                path.mkdir(parents=True, exist_ok=True)
            (anchor / '.env').write_text(f'TIKIN_GLOBAL_CONFIG_DIR="{global_root}"\nTIKIN_API_KEY=old-global\n', encoding='utf-8')
            (project / '.env.local.tikin-social').write_text(f'TIKIN_PROJECT_CONFIG_DIR="{project_root}"\nTIKIN_API_KEY=old-project\n', encoding='utf-8')
            (ordinary / '.env').write_text('TIKIN_API_KEY=ordinary\n', encoding='utf-8')
            environment = {k: v for k, v in os.environ.items() if not k.startswith(('TIKIN_', 'AIHUB_'))}
            environment.update(HOME=str(user), USERPROFILE=str(user))

            def status(*args):
                result = subprocess.run([str(PYTHON), str(SETUP / 'scripts/tikin-config'), '--skill', 'tikin-douyin', *args, 'status'],
                                        cwd=project, env=environment, capture_output=True, text=True, encoding='utf-8', check=True)
                return json.loads(result.stdout)

            self.assertFalse(status()['key_configured'])
            (global_root / '.env').write_text('TIKIN_API_KEY=new-global\n', encoding='utf-8')
            (global_root / 'settings.json').write_text('{"routing":{"default":"confirm","platforms":{}}}', encoding='utf-8')
            self.assertEqual(status()['key_source'], str(global_root / '.env'))
            self.assertEqual(status()['settings']['routing']['default'], 'confirm')
            (project_root / '.env.tikin-social').write_text('TIKIN_API_KEY=new-project\n', encoding='utf-8')
            self.assertEqual(status()['key_source'], str(project_root / '.env.tikin-social'))
            self.assertEqual(status('--no-global-config')['key_source'], str(project_root / '.env.tikin-social'))
            self.assertEqual(status()['cwd'], str(project))

    def test_fixed_selector_anchors_environment_disabled_global_and_unreadable_files(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temporary:
            project = Path(temporary).resolve()
            user, selected, injected = (project / name for name in ('user', 'selected', 'injected'))
            anchor = user / '.config/tikin-social/.env'
            anchor.parent.mkdir(parents=True)
            selected.mkdir(); injected.mkdir()
            environment = {k: v for k, v in os.environ.items() if not k.startswith(('TIKIN_', 'AIHUB_'))}
            environment.update(HOME=str(user), USERPROFILE=str(user))
            def inspect(*args):
                result = subprocess.run([str(PYTHON), str(SETUP / 'scripts/tikin-config'), '--skill', 'tikin-douyin', *args, 'config-check'],
                    cwd=project, env=environment, capture_output=True, text=True, encoding='utf-8')
                self.assertIn(result.returncode, (0, 3), result.stderr)
                return json.loads(result.stdout)
            anchor.write_text('TIKIN_GLOBAL_CONFIG_DIR=relative\nTIKIN_API_KEY=old\n', encoding='utf-8')
            self.assertTrue(any(p['reason'] == 'expected_absolute_config_directory' for p in inspect()['problems']))
            anchor.write_text(f'TIKIN_GLOBAL_CONFIG_DIR="{selected}"\n', encoding='utf-8')
            (selected / '.env').write_text('TIKIN_API_KEY=selected\nTIKIN_GLOBAL_CONFIG_DIR=/ignored-recursive\n', encoding='utf-8')
            self.assertEqual(inspect()['fields']['TIKIN_API_KEY']['source'], str(selected / '.env'))
            self.assertEqual(inspect()['directories']['global'], str(selected))
            skill_root = selected / 'tikin-douyin'
            skill_root.mkdir()
            (skill_root / '.env.local').write_text('TIKIN_API_KEY=skill-selected\n', encoding='utf-8')
            self.assertEqual(inspect()['fields']['TIKIN_API_KEY']['source'], str(skill_root / '.env.local'))
            (injected / '.env').write_text('TIKIN_API_KEY=process-root\n', encoding='utf-8')
            environment['TIKIN_GLOBAL_CONFIG_DIR'] = str(injected)
            self.assertEqual(inspect()['fields']['TIKIN_API_KEY']['source'], str(injected / '.env'))
            disabled = inspect('--no-global-config')
            self.assertFalse(any(str(user) in row['path'] or str(injected) in row['path'] for row in disabled['layers']))
            environment.pop('TIKIN_GLOBAL_CONFIG_DIR')
            anchor.unlink(); anchor.mkdir()
            self.assertTrue(any(p['reason'] == 'unreadable' for p in inspect()['problems']))
            self.assertFalse(any(p['reason'] == 'unreadable' for p in inspect('--no-global-config')['problems']))
