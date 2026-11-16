"""Real loaders and file transactions; every file is synthetic and task-local."""
from importlib import import_module
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MARKET = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MARKET / 'aihub-studio/shared'), str(MARKET / 'ui-common')]
from scoped_configuration import ScopedConfiguration
from skill_ui.contracts import UIError, public_config

TMP = Path(os.environ.get('SKILL_UI_TEST_TMP', Path.cwd() / 'tmp' / 'ui-directory-tests')).resolve()
TMP.mkdir(parents=True, exist_ok=True)


class DirectorySaving(unittest.TestCase):
    def approve(self, adapter, request, revision):
        request.pop('directory_revision', None)
        preview = adapter.preview(request, revision)
        request['directory_revision'] = preview['directory_revision']
        return preview

    def adapter(self, project, plugin, **options):
        prefix = 'AIHUB' if plugin == 'aihub-studio' else 'TIKIN'
        user = project / 'user'
        user.mkdir(exist_ok=True)
        old = user / '.config' / plugin / '.env'
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(prefix + '_API_KEY=original-synthetic-key\nUNRELATED=keep\n', encoding='utf-8')
        environment = {k: v for k, v in os.environ.items() if not k.startswith(('AIHUB_', 'TIKIN_'))}
        environment.update(HOME=str(user), USERPROFILE=str(user))
        package = MARKET / ('aihub-studio' if prefix == 'AIHUB' else 'tikin-social/skills/tikin-setup')
        cls = import_module('plugins.aihub-studio.scopes').StudioConfiguration if prefix == 'AIHUB' else ScopedConfiguration
        adapter = cls(package, project, dict(plugin=plugin, global_enabled=True, save_scope='global',
            agent='codex', config_dir=str(user / 'agent'), **options), environment)
        return adapter, prefix, old

    def test_directory_and_business_edits_use_new_roots_without_copying_other_fields(self):
        for plugin, prefix in [('aihub-studio', 'AIHUB'), ('tikin-social', 'TIKIN')]:
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory(dir=TMP) as temporary:
                project = Path(temporary).resolve()
                user, global_root, local_root = [project / name for name in ('user', '新 global', '新 project')]
                user.mkdir()
                old = user / '.config' / plugin / '.env'
                old.parent.mkdir(parents=True)
                old.write_text(prefix + '_API_KEY=old-synthetic-key\nUNRELATED=keep\n', encoding='utf-8')
                project_anchor = project / ('.env.local.' + plugin)
                project_anchor.write_text('UNRELATED=project-keep\n', encoding='utf-8')
                environment = {k: v for k, v in os.environ.items() if not k.startswith(('AIHUB_', 'TIKIN_'))}
                environment.update(HOME=str(user), USERPROFILE=str(user))
                package = MARKET / ('aihub-studio' if prefix == 'AIHUB' else 'tikin-social/skills/tikin-setup')
                cls = import_module('plugins.aihub-studio.scopes').StudioConfiguration if prefix == 'AIHUB' else ScopedConfiguration
                adapter = cls(package, project, dict(plugin=plugin, global_enabled=True, save_scope='global', agent='codex', config_dir=str(user / 'agent')), environment)
                initial = adapter.snapshot()
                target = adapter._layer_id(str(old))
                local_target = adapter._layer_id(str(project_anchor))
                preference = 'audio.minimax_speech.favorite_voice_ids' if prefix == 'AIHUB' else 'routing.default'
                preference_value = ['fixture-voice'] if prefix == 'AIHUB' else 'confirm'
                settings = old.parent / 'settings.json'
                request = {'files': {
                    target: {prefix + '_GLOBAL_CONFIG_DIR': {'op': 'set', 'value': str(global_root)},
                             prefix + '_API_KEY': {'op': 'set', 'value': 'new-synthetic-key'}},
                    local_target: {prefix + '_PROJECT_CONFIG_DIR': {'op': 'set', 'value': str(local_root)}},
                    adapter._layer_id(str(settings)): {preference: {'op': 'set', 'value': preference_value}}}}
                preview = self.approve(adapter, request, initial['revision'])
                self.assertEqual(preview['validation_errors'], [])
                self.assertFalse(global_root.exists(), 'preview must not create the new root')
                self.assertIn('old-synthetic-key', old.read_text(encoding='utf-8'))
                saved = adapter.save(request, initial['revision'])
                fields = {f['id']: f for f in saved['fields']}
                self.assertEqual(fields[prefix + '_API_KEY']['effective']['source'], adapter._layer_id(str(global_root / '.env')))
                self.assertEqual(fields[preference]['effective']['value'], preference_value)
                self.assertEqual((global_root / '.env').read_text(encoding='utf-8'), prefix + '_API_KEY="new-synthetic-key"\n')
                self.assertIn('old-synthetic-key', old.read_text(encoding='utf-8'))
                self.assertIn('UNRELATED=keep', old.read_text(encoding='utf-8'))
                self.assertFalse(settings.exists(), 'old settings file must not be created')
                self.assertTrue((global_root / 'settings.json').exists())
                self.assertFalse((local_root / ('.env.local.' + plugin)).exists(), 'unchanged project business config must not be copied')
                self.assertEqual(adapter.snapshot()['revision'], saved['revision'])

    def test_directory_only_and_reset_use_actual_sources_without_copying(self):
        for plugin in ('aihub-studio', 'tikin-social'):
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory(dir=TMP) as temporary:
                project = Path(temporary).resolve()
                adapter, prefix, old = self.adapter(project, plugin)
                new = project / 'selected global'
                state = adapter.snapshot()
                request = {'files': {adapter._layer_id(str(old)): {
                    prefix + '_GLOBAL_CONFIG_DIR': {'op': 'set', 'value': str(new)}}}}
                self.approve(adapter, request, state['revision'])
                saved = adapter.save(request, state['revision'])
                self.assertFalse(new.exists(), 'directory-only save must not create a business file')
                fields = {f['id']: f for f in saved['fields']}
                self.assertEqual(fields[prefix + '_API_KEY']['effective']['status'], 'missing')
                self.assertNotIn(adapter._layer_id(str(old)), fields[prefix + '_API_KEY']['targets'])
                self.assertEqual(fields[prefix + '_GLOBAL_CONFIG_DIR']['targets'], [adapter._layer_id(str(old))])
                reset = {'files': {adapter._layer_id(str(old)): {prefix + '_GLOBAL_CONFIG_DIR': {'op': 'unset'}}}}
                preview = self.approve(adapter, reset, saved['revision'])
                self.assertEqual(next(f for f in preview['fields'] if f['id'] == prefix + '_API_KEY')['effective']['value'], 'original-synthetic-key')
                restored = adapter.save(reset, saved['revision'])
                self.assertEqual(restored['revision'], adapter.snapshot()['revision'])
                self.assertNotIn(prefix + '_GLOBAL_CONFIG_DIR', old.read_text(encoding='utf-8'))
                self.assertIn('UNRELATED=keep', old.read_text(encoding='utf-8'))

    def test_new_root_source_race_and_write_failure_preserve_anchors(self):
        for plugin in ('aihub-studio', 'tikin-social'):
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory(dir=TMP) as temporary:
                project = Path(temporary).resolve()
                adapter, prefix, old = self.adapter(project, plugin)
                new = project / 'selected global'
                new.mkdir()
                before = old.read_bytes()
                request = {'files': {adapter._layer_id(str(old)): {
                    prefix + '_GLOBAL_CONFIG_DIR': {'op': 'set', 'value': str(new)},
                    prefix + '_API_KEY': {'op': 'set', 'value': 'new-synthetic'}}}}
                state = adapter.snapshot()
                self.approve(adapter, request, state['revision'])
                original_apply = adapter.transaction.apply
                external = new / '.env.local'
                def race(changes, verify):
                    external.write_text(prefix + '_API_KEY=external-synthetic\n', encoding='utf-8')
                    return original_apply(changes, verify)
                with patch.object(adapter.transaction, 'apply', race), self.assertRaises(UIError) as error:
                    adapter.save(request, state['revision'])
                self.assertEqual(error.exception.code, 'conflict')
                self.assertEqual(before, old.read_bytes())
                self.assertIn('external-synthetic', external.read_text(encoding='utf-8'))
                external.unlink()
                self.approve(adapter, request, state['revision'])
                import persistence
                original_replace = persistence.replace
                def fail_new(path, content, expected, owner_path=None):
                    if Path(path) == new / '.env':
                        raise OSError('synthetic write failure')
                    return original_replace(path, content, expected, owner_path)
                with patch.object(persistence, 'replace', fail_new), self.assertRaises(OSError):
                    adapter.save(request, adapter.snapshot()['revision'])
                self.assertEqual(before, old.read_bytes())
                self.assertFalse((new / '.env').exists())
                self.assertFalse(adapter.transaction.journal.exists())

    def test_preview_binds_new_root_sources_until_save(self):
        for plugin in ('aihub-studio', 'tikin-social'):
            with self.subTest(plugin=plugin), tempfile.TemporaryDirectory(dir=TMP) as temporary:
                project = Path(temporary).resolve()
                adapter, prefix, old = self.adapter(project, plugin)
                new = project / 'selected global'
                state = adapter.snapshot()
                before = old.read_bytes()
                request = {'files': {adapter._layer_id(str(old)): {
                    prefix + '_GLOBAL_CONFIG_DIR': {'op': 'set', 'value': str(new)},
                    prefix + '_API_KEY': {'op': 'set', 'value': 'new-synthetic'}}}}
                with self.assertRaises(UIError) as missing:
                    adapter.save(request, state['revision'])
                self.assertEqual(missing.exception.code, 'conflict')
                self.approve(adapter, request, state['revision'])
                new.mkdir()
                external = new / '.env.local'
                external.write_text(prefix + '_API_KEY=external-synthetic\n', encoding='utf-8')
                self.assertEqual(state['revision'], adapter.snapshot()['revision'])
                with self.assertRaises(UIError) as changed:
                    adapter.save(request, state['revision'])
                self.assertEqual(changed.exception.code, 'conflict')
                self.assertEqual(old.read_bytes(), before)
                self.assertFalse((new / '.env').exists())
                self.approve(adapter, request, state['revision'])
                adapter.save(request, state['revision'])
                self.assertIn('external-synthetic', external.read_text(encoding='utf-8'))

    def test_directory_switch_uses_original_input_or_explicit_target_choice(self):
        for plugin in ('aihub-studio', 'tikin-social'):
            for mode in ('input', 'existing', 'edited'):
                with self.subTest(plugin=plugin, mode=mode), tempfile.TemporaryDirectory(dir=TMP) as temporary:
                    project = Path(temporary).resolve()
                    adapter, prefix, old = self.adapter(project, plugin)
                    state = adapter.snapshot()
                    before = old.read_bytes()
                    new = project / 'selected project'
                    new.mkdir()
                    destination = new / ('.env.local.' + plugin)
                    destination.write_text(prefix + '_API_KEY=candidate-synthetic\nUNRELATED=preserve\n', encoding='utf-8')
                    anchor = project / ('.env.local.' + plugin)
                    target = adapter._layer_id(str(anchor))
                    key = prefix + '_API_KEY'
                    request = {'files': {target: {prefix + '_PROJECT_CONFIG_DIR': {'op': 'set', 'value': str(new)}}},
                        'switches': {key: {'target': target, 'mode': 'existing' if mode == 'existing' else 'input'}}}
                    if mode == 'edited':
                        request['files'][adapter._layer_id(str(old))] = {key: {'op': 'set', 'value': 'edited-synthetic'}}
                    preview = self.approve(adapter, request, state['revision'])
                    plan = preview['scope_plans'][key]
                    if mode == 'edited':
                        self.assertEqual(plan['state'], 'choice')
                        request['switches'][key].update(choice='input', choice_token=plan['choice_token'])
                    else:
                        self.assertFalse(plan['input_changed'])
                        self.assertEqual(preview['validation_errors'], [])
                    saved = adapter.save(request, state['revision'])
                    expected = {'input': 'original-synthetic-key', 'existing': 'candidate-synthetic', 'edited': 'edited-synthetic'}[mode]
                    field = next(f for f in saved['fields'] if f['id'] == key)
                    self.assertEqual(field['effective']['value'], expected)
                    self.assertEqual(field['effective']['source'], adapter._layer_id(str(destination)))
                    self.assertIn('UNRELATED=preserve', destination.read_text(encoding='utf-8'))
                    self.assertEqual(old.read_bytes(), before)

    def test_invalid_directory_and_malformed_switch_do_not_write(self):
        with tempfile.TemporaryDirectory(dir=TMP) as temporary:
            project = Path(temporary).resolve()
            adapter, prefix, old = self.adapter(project, 'tikin-social')
            state = adapter.snapshot()
            request = {'files': {adapter._layer_id(str(old)): {
                prefix + '_GLOBAL_CONFIG_DIR': {'op': 'set', 'value': '../relative'}}}}
            before = old.read_bytes()
            with self.assertRaises(UIError):
                adapter.save(request, state['revision'])
            request['files'][adapter._layer_id(str(old))][prefix + '_GLOBAL_CONFIG_DIR']['value'] = str(project / 'new')
            request['switches'] = {prefix + '_API_KEY': None}
            with self.assertRaises(UIError):
                adapter.preview(request, state['revision'])
            self.assertEqual(before, old.read_bytes())
