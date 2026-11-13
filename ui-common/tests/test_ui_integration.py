"""Real loader and persistence regression coverage; no business network calls."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MARKET = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MARKET / 'aihub-studio/shared'), str(MARKET / 'ui-common')]
from configuration import Configuration
from persistence import Transaction, digest, replace
from catalog import Catalog
from skill_ui.contracts import UIError, public_config


class Integration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ['TEMP'], prefix='marketplace-ui-')
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {key: '' for key in os.environ if key.startswith(('AIHUB_', 'TIKIN_'))})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def adapter(self, plugin):
        package = MARKET / ('aihub-studio' if plugin == 'aihub-studio' else 'tikin-social/skills/tikin-setup')
        return Configuration(package, self.project, {'plugin': plugin, 'global_enabled': False, 'save_scope': 'project', 'agent': 'codex'})

    @unittest.skipUnless(os.name == 'nt', 'Windows project-owner ACL')
    def test_project_owner_can_read_files_written_with_a_different_execution_sid(self):
        import private_platform
        self.git('init', '--quiet')
        target = self.project / 'private' / 'setting.env'
        parent_acl = private_platform._dacl_bytes(private_platform._read_security(self.project))
        # Simulate an execution identity distinct from the real project owner;
        # set/read the actual DACL, then read the result as the project owner.
        with patch.object(private_platform, '_current_sid', return_value='S-1-5-18'):
            transaction = Transaction(self.project / 'txn', owner_path=self.project)
            transaction.apply({str(target): (None, b'synthetic-value')}, lambda saved: None)
            private_platform.verify_private_permissions(target, owner_path=self.project)
        self.assertEqual(target.read_bytes(), b'synthetic-value')
        self.assertEqual(private_platform._dacl_bytes(private_platform._read_security(self.project)), parent_acl)

    def fields(self, snapshot):
        return {f['id']: f for f in snapshot['fields']}

    def target(self, path):
        return Configuration._layer_id(str(path))

    def global_adapter(self, plugin, **options):
        user = self.project / 'synthetic-user'
        user.mkdir(exist_ok=True)
        environment = dict(os.environ, HOME=str(user), USERPROFILE=str(user))
        environment.pop('UV_PROJECT_ENVIRONMENT', None)
        package = MARKET / ('aihub-studio' if plugin == 'aihub-studio' else 'tikin-social/skills/tikin-setup')
        return Configuration(package, self.project, {'plugin': plugin, 'global_enabled': True,
                             'save_scope': 'global', 'agent': 'codex', 'config_dir': str(user / 'agent'), **options}, environment), user

    def test_missing_key_starts_and_real_loader_reads_saved_value(self):
        for plugin, key in [('aihub-studio', 'AIHUB_API_KEY'), ('tikin-social', 'TIKIN_API_KEY')]:
            with self.subTest(plugin=plugin):
                adapter = self.adapter(plugin)
                initial = adapter.snapshot()
                self.assertFalse(self.fields(public_config(initial))[key]['effective']['configured'])
                saved = adapter.save({key: {'op': 'set', 'value': 'synthetic-only-value'}},
                                     initial['revision'], self.target(self.project / '.env.local'))
                self.assertEqual(self.fields(saved)[key]['effective']['value'], 'synthetic-only-value')
                self.assertNotIn('synthetic-only-value', json.dumps(public_config(saved)))
                self.assertFalse(adapter.transaction.journal.exists())

    def test_elevenlabs_selection_and_favorites_save_together_in_the_chosen_scope(self):
        voice, favorites = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID', 'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS'
        adapter, user = self.global_adapter('aihub-studio', skill='aihub-audio')
        target = user / '.config/aihub-studio/.env'
        target.parent.mkdir(parents=True)
        target.write_text('AIHUB_API_KEY=synthetic\nUNRELATED=preserve\n', encoding='utf-8')
        initial = adapter.snapshot()
        self.assertNotIn('AIHUB_DOCUMENT_MODELS', self.fields(initial))
        saved = adapter.save({voice: {'op': 'set', 'value': 'voice-global'},
                              favorites: {'op': 'set', 'value': ['voice-global', 'voice-second']}},
                             initial['revision'], self.target(target))
        self.assertEqual(self.fields(saved)[voice]['effective']['value'], 'voice-global')
        self.assertEqual(self.fields(saved)[favorites]['effective']['value'], ['voice-global', 'voice-second'])
        self.assertIn('UNRELATED=preserve', target.read_text(encoding='utf-8'))
        project = self.project / '.env.local.aihub-studio'
        selected = adapter.save({voice: {'op': 'set', 'value': 'voice-project'},
                                 favorites: {'op': 'set', 'value': []}},
                                saved['revision'], self.target(project))
        fields = self.fields(selected)
        self.assertEqual(fields[voice]['effective']['value'], 'voice-project')
        self.assertEqual(fields[favorites]['effective']['value'], [])
        self.assertEqual(fields[favorites]['effective']['source'], self.target(project))
        self.assertIn('voice-global', target.read_text(encoding='utf-8'))
        self.assertIn('[]', project.read_text(encoding='utf-8'))
        before = project.read_bytes()
        with self.assertRaises(UIError):
            adapter.save({voice: {'op': 'set', 'value': 'stale'}}, saved['revision'], self.target(project))
        self.assertEqual(project.read_bytes(), before)
        isolated = Configuration(adapter.package, self.project, {**adapter.options, 'global_enabled': False}, adapter.environment)
        isolated_fields = self.fields(isolated.snapshot())
        self.assertEqual(isolated_fields[voice]['effective']['value'], 'voice-project')
        self.assertEqual(isolated_fields[favorites]['effective']['value'], [])
        self.assertNotIn(self.target(target), isolated_fields[favorites]['targets'])

    def test_speech_sources_are_audio_specific_from_every_caller(self):
        key = 'AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID'
        adapter, user = self.global_adapter('aihub-studio', skill='aihub-image')
        plugin = user / '.config/aihub-studio'
        audio = plugin / 'aihub-audio/.env'
        image = plugin / 'aihub-image/.env'
        for path, value in ((audio, 'audio-voice'), (image, 'image-voice')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key + '=' + value + '\nAIHUB_API_KEY=fixture\n')
        for caller in ('aihub-image', 'aihub-audio', 'aihub-video', 'aihub-music', 'aihub-understanding', None):
            adapter.options['skill'] = caller
            fields = self.fields(adapter.snapshot())
            self.assertEqual(len(fields), 19)
            self.assertEqual(fields[key]['effective']['value'], 'audio-voice')
            self.assertEqual(fields[key]['effective']['source'], self.target(audio))
            self.assertNotIn(self.target(image), fields[key]['targets'])
        adapter.options['skill'] = 'aihub-audio'
        path = self.project / '.env.local.aihub-studio'
        saved = adapter.save({key: {'op':'set', 'value':'custom-voice'}}, adapter.snapshot()['revision'], self.target(path))
        self.assertEqual(self.fields(saved)[key]['effective']['value'], 'custom-voice')
        cleared = adapter.save({key: {'op':'unset'}}, saved['revision'], self.target(path))
        self.assertEqual(self.fields(cleared)[key]['effective']['value'], 'audio-voice')

    def test_speech_favorites_preserve_settings_and_coordinate_node_writer(self):
        from importlib import import_module
        key = 'audio.minimax_speech.favorite_voice_ids'
        adapter, user = self.global_adapter('aihub-studio')
        plugin = user / '.config/aihub-studio'
        plugin.mkdir(parents=True)
        (plugin / '.env').write_text('AIHUB_API_KEY=fixture\n')
        path = plugin / 'settings.json'
        original = {'custom': {'keep': True}, 'audio': {'other': 42},
                    'default_skill_reminders': {'version':1, 'agents':[]}}
        path.write_text(json.dumps(original))
        initial = adapter.snapshot()
        values = ['Chinese (Mandarin)_Warm_Girl'] + ['voice-' + str(i) for i in range(75)]
        changes = {key:{'op':'set','value':values}}
        adapter.preview(changes, initial['revision'], self.target(path))
        self.assertEqual(json.loads(path.read_text()), original)
        lock = Path(str(path) + '.default-skills.lock')
        lock.write_text('another writer')
        with self.assertRaises(UIError) as error:
            adapter.save(changes, initial['revision'], self.target(path))
        self.assertEqual(error.exception.code, 'busy')
        self.assertEqual(lock.read_text(), 'another writer')
        self.assertEqual(json.loads(path.read_text()), original)
        lock.unlink()
        saved = adapter.save(changes, initial['revision'], self.target(path))
        self.assertEqual(self.fields(saved)[key]['effective']['value'], values)
        data = json.loads(path.read_text())
        self.assertEqual(data['custom'], original['custom'])
        self.assertEqual(data['audio']['other'], 42)
        self.assertEqual(data['default_skill_reminders'], original['default_skill_reminders'])
        script = "import {agentDefaults} from './dist/agentDefaults.js'; agentDefaults({agent:'codex',action:'dismiss'});"
        with import_module('plugins.aihub-studio.persistence').settings_lock(path, self.project):
            result = subprocess.run(['node','--input-type=module','-e',script], cwd=adapter.package,
                                    env=adapter.environment, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(path.read_text()), data)
        subprocess.run(['node','--input-type=module','-e',script], cwd=adapter.package,
                       env=adapter.environment, capture_output=True, check=True)
        self.assertEqual(json.loads(path.read_text())['audio'], data['audio'])
        updated = adapter.snapshot()
        cleared = adapter.save({key:{'op':'unset'}}, updated['revision'], self.target(path))
        self.assertEqual(self.fields(cleared)[key]['effective']['value'], [])
        self.assertFalse(json.loads(path.read_text())['default_skill_reminders']['agents'][0]['enabled'])
        disabled = self.fields(self.adapter('aihub-studio').snapshot())[key]
        self.assertTrue(disabled['readonly'])
        self.assertEqual(disabled['targets'], [])

    def test_invalid_favorite_schema_cannot_be_overwritten(self):
        adapter, user = self.global_adapter('aihub-studio')
        folder = user / '.config/aihub-studio'
        folder.mkdir(parents=True)
        path = folder / 'settings.json'
        original = '{"audio":{"minimax_speech":{"favorite_voice_ids":["a","a"]}}}'
        path.write_text(original)
        with self.assertRaises(UIError):
            adapter.snapshot()
        self.assertEqual(path.read_text(), original)

    def git(self, *args, check=True):
        return subprocess.run(['git', '-C', str(self.project), *args], check=check,
                              capture_output=True)

    def test_first_save_in_git_repo_prepares_protection_without_preview_writes(self):
        self.git('init', '--quiet')
        ignore = self.project / '.gitignore'
        original = b'# existing rules\r\nkeep-this-pattern'
        ignore.write_bytes(original)
        for plugin, key in [('aihub-studio', 'AIHUB_API_KEY'), ('tikin-social', 'TIKIN_API_KEY')]:
            with self.subTest(plugin=plugin):
                adapter = self.adapter(plugin)
                path = self.project / ('.env.local.' + plugin)
                initial = adapter.snapshot()
                before_ignore = ignore.read_bytes()
                changes = {key: {'op': 'set', 'value': 'synthetic-first-save'}}
                adapter.preview(changes, initial['revision'], self.target(path))
                self.assertEqual(ignore.read_bytes(), before_ignore)
                self.assertFalse(path.exists())
                self.assertFalse(adapter.transaction.directory.exists())
                saved = adapter.save(changes, initial['revision'], self.target(path))
                self.assertEqual(self.fields(saved)[key]['effective']['value'], 'synthetic-first-save')
                for protected in (path, Path(str(path) + '.ui.lock'),
                                  Path(str(path) + '.ui-1234567890abcdef.tmp'),
                                  adapter.transaction.journal, adapter.transaction.directory / 'transaction.lock'):
                    self.git('check-ignore', '--quiet', '--', str(protected))
                after_ignore = ignore.read_bytes()
                adapter.save({key: {'op': 'set', 'value': 'synthetic-second-save'}},
                             saved['revision'], self.target(path))
                self.assertEqual(ignore.read_bytes(), after_ignore)
                self.assertTrue(after_ignore.startswith(original + b'\r\n'))
                self.assertNotIn('synthetic-first-save', json.dumps(public_config(saved)))
                self.assertFalse(adapter.transaction.journal.exists())
        self.assertEqual(self.git('check-ignore', '--quiet', '--', '.env.local.unrelated', check=False).returncode, 1)

    def test_global_save_in_git_project_also_protects_recovery_files(self):
        self.git('init', '--quiet')
        adapter, user = self.global_adapter('tikin-social')
        path = user / '.config/tikin-social/.env'
        saved = adapter.save({'TIKIN_API_KEY': {'op': 'set', 'value': 'synthetic-global'}},
                             adapter.snapshot()['revision'], self.target(path))
        self.assertEqual(self.fields(saved)['TIKIN_API_KEY']['effective']['value'], 'synthetic-global')
        self.git('check-ignore', '--quiet', '--', str(adapter.transaction.journal))
        self.git('check-ignore', '--quiet', '--', str(path))

    def test_automatic_ignore_handles_nested_negations_and_literal_names(self):
        self.git('init', '--quiet')
        (self.project / '.gitignore').write_text('*.env\n')
        folder = self.project / 'nested [project]'
        folder.mkdir()
        ignore = folder / '.gitignore'
        ignore.write_bytes(b'# preserve me\n!*.env\n')
        path = folder / 'private [key]*?.env'
        if os.name == 'nt':
            path = folder / 'private [key].env'
        replace(path, b'synthetic', None)
        self.assertTrue(ignore.read_bytes().startswith(b'# preserve me\n!*.env\n'))
        self.git('check-ignore', '--quiet', '--', str(path))
        self.assertEqual(self.git('check-ignore', '--quiet', '--', str(folder / 'public.env'), check=False).returncode, 1)

    def test_tracked_config_is_not_overwritten_or_removed_from_index(self):
        self.git('init', '--quiet')
        path = self.project / '.env.local.tikin-social'
        path.write_bytes(b'TIKIN_API_KEY=synthetic-tracked\n')
        self.git('add', '--', path.name)
        before_index = self.git('ls-files', '--stage').stdout
        adapter = self.adapter('tikin-social')
        with self.assertRaises(UIError) as error:
            adapter.save({'TIKIN_API_KEY': {'op': 'set', 'value': 'synthetic-new'}},
                         adapter.snapshot()['revision'], self.target(path))
        self.assertEqual(error.exception.code, 'tracked')
        self.assertEqual(path.read_bytes(), b'TIKIN_API_KEY=synthetic-tracked\n')
        self.assertEqual(self.git('ls-files', '--stage').stdout, before_index)
        self.assertFalse(adapter.transaction.journal.exists())

    def test_unwritable_ignore_preserves_config_and_retry_succeeds(self):
        self.git('init', '--quiet')
        adapter = self.adapter('tikin-social')
        path = self.project / '.env.local.tikin-social'
        initial = adapter.snapshot()
        changes = {'TIKIN_API_KEY': {'op': 'set', 'value': 'synthetic-retry'}}
        with patch('persistence._add_ignore', side_effect=PermissionError('synthetic-denied')):
            with self.assertRaises(UIError) as error:
                adapter.save(changes, initial['revision'], self.target(path))
        self.assertEqual(error.exception.code, 'git')
        self.assertFalse(path.exists())
        saved = adapter.save(changes, initial['revision'], self.target(path))
        self.assertEqual(self.fields(saved)['TIKIN_API_KEY']['effective']['value'], 'synthetic-retry')

    def test_explicit_file_save_preserves_unknowns_and_other_file(self):
        local = self.project / '.env.local'
        local.write_text('# keep me\nOTHER=value\nAIHUB_API_KEY=old\nAIHUB_API_KEY=last\n', encoding='utf-8')
        model = self.project / '.env.aihub-studio'
        model.write_text('AIHUB_IMAGE_MODELS=old-model\n', encoding='utf-8')
        adapter = self.adapter('aihub-studio')
        initial = adapter.snapshot()
        fields = self.fields(initial)
        self.assertEqual(fields['AIHUB_IMAGE_MODELS']['effective']['source'], self.target(model))
        changes = {'AIHUB_API_KEY': {'op': 'set', 'value': 'literal-$(keep)'},
                   'AIHUB_IMAGE_MODELS': {'op': 'set', 'value': ['new-model', 'second-model']}}
        preview = adapter.preview(changes, initial['revision'], self.target(local))
        self.assertEqual(fields['AIHUB_IMAGE_MODELS']['effective'], self.fields(preview)['AIHUB_IMAGE_MODELS']['effective'])
        self.assertIn('last', local.read_text())
        saved = adapter.save(changes, initial['revision'], self.target(local))
        raw = local.read_text()
        self.assertIn('# keep me\nOTHER=value\n', raw)
        self.assertEqual(raw.count('AIHUB_API_KEY='), 1)
        self.assertEqual(model.read_text(), 'AIHUB_IMAGE_MODELS=old-model\n')
        self.assertEqual(self.fields(saved)['AIHUB_IMAGE_MODELS']['effective']['value'], ['old-model'])
        adapter.save({'AIHUB_IMAGE_MODELS': {'op': 'unset'}}, saved['revision'], self.target(model))
        self.assertEqual(self.fields(adapter.snapshot())['AIHUB_IMAGE_MODELS']['effective']['value'], ['new-model', 'second-model'])

    def test_global_settings_and_key_save_separately(self):
        for plugin in ('aihub-studio', 'tikin-social'):
            adapter, user = self.global_adapter(plugin)
            snapshot = adapter.snapshot()
            key = 'AIHUB_API_KEY' if plugin == 'aihub-studio' else 'TIKIN_API_KEY'
            target = self.target(user / '.config' / plugin / '.env')
            self.assertIn(target, self.fields(snapshot)[key]['targets'])
            with self.assertRaises(UIError):
                adapter.save({key: {'op': 'set', 'value': 'synthetic-global-value'},
                              'default_skill_reminders': {'op': 'set', 'value': False}}, snapshot['revision'], target)
            saved = adapter.save({key: {'op': 'set', 'value': 'synthetic-global-value'}}, snapshot['revision'], target)
            changes = {'default_skill_reminders': {'op': 'set', 'value': False}}
            if plugin == 'tikin-social':
                changes['routing.default'] = {'op': 'set', 'value': 'confirm'}
            result = adapter.save(changes, saved['revision'], self.target(user / '.config' / plugin / 'settings.json'))
            values = {f['id']: f['effective']['value'] for f in result['fields']}
            self.assertFalse(values['default_skill_reminders'])
            self.assertEqual(values[key], 'synthetic-global-value')
            if plugin == 'tikin-social':
                self.assertEqual(values['routing.default'], 'confirm')
                cleared = adapter.save({'routing.default': {'op': 'unset'}}, result['revision'],
                                       self.target(user / '.config' / plugin / 'settings.json'))
                self.assertEqual(self.fields(cleared)['routing.default']['effective']['value'], 'auto')

    def test_project_only_key_global_inheritance_empty_and_false(self):
        adapter, user = self.global_adapter('aihub-studio', skill='aihub-image')
        folder = user / '.config/aihub-studio'
        folder.mkdir(parents=True)
        global_file = folder / '.env'
        global_file.write_text('AIHUB_API_KEY=synthetic-global-secret\nAIHUB_IMAGE_MODELS=global-model\nAIHUB_RESULT_CHECK_ENABLED=0\nAIHUB_MODEL_FALLBACK_POLICY=off\n')
        local = self.project / '.env.local'
        local.write_text('AIHUB_API_KEY=synthetic-project-secret\n')
        initial = adapter.snapshot()
        fields = self.fields(initial)
        self.assertEqual(fields['AIHUB_API_KEY']['effective']['source'], self.target(local))
        self.assertEqual(fields['AIHUB_IMAGE_MODELS']['effective']['source'], self.target(global_file))
        self.assertIs(fields['AIHUB_RESULT_CHECK_ENABLED']['effective']['value'], False)
        before = {p: p.read_bytes() for p in [local, global_file]}
        for change in [{'op': 'unset'}, {'op': 'set', 'value': ''}]:
            preview = adapter.preview({'AIHUB_API_KEY': change}, initial['revision'], self.target(local))
            self.assertEqual(self.fields(preview)['AIHUB_API_KEY']['effective']['source'], self.target(global_file))
            self.assertEqual(self.fields(preview)['AIHUB_API_KEY']['effective']['value'], 'synthetic-global-secret')
            public = json.dumps(public_config(preview))
            self.assertNotIn('synthetic-global-secret', public)
            self.assertNotIn('synthetic-project-secret', public)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        low = adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'synthetic-new-global'}},
                           initial['revision'], self.target(global_file))
        self.assertEqual(self.fields(low)['AIHUB_API_KEY']['effective']['value'], 'synthetic-project-secret')
        cleared = adapter.save({'AIHUB_API_KEY': {'op': 'unset'}}, low['revision'], self.target(local))
        self.assertEqual(self.fields(cleared)['AIHUB_API_KEY']['effective']['value'], 'synthetic-new-global')

    def test_all_actual_layers_and_caller_isolation(self):
        for plugin, skill, key in [('aihub-studio', 'aihub-image', 'AIHUB_API_KEY'),
                                   ('tikin-social', 'tikin-douyin', 'TIKIN_API_KEY')]:
            adapter, user = self.global_adapter(plugin, skill=skill)
            folder = user / '.config' / plugin
            ordered = [self.project / ('.env.local.' + plugin), self.project / ('.env.' + plugin),
                       self.project / '.env.local', self.project / '.env',
                       folder / skill / '.env.local', folder / skill / '.env',
                       folder / '.env.local', folder / '.env', user / '.config' / skill / '.env']
            for index, path in enumerate(ordered):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(key + '=synthetic-layer-' + str(index) + '\n')
            for index, path in enumerate(ordered):
                snapshot = adapter.snapshot()
                field = self.fields(snapshot)[key]
                rows = [row for row in field['rows'] if row['status'] != 'skipped']
                row_by_id = {row['layer']: row for row in rows}
                actual = [layer['id'] for layer in snapshot['layers'] if layer['id'] in row_by_id and layer['scope'] != 'process']
                self.assertEqual(actual, [self.target(p) for p in ordered])
                self.assertEqual(field['effective']['value'], 'synthetic-layer-' + str(index))
                path.write_text(key + '=\n')
            self.assertEqual(self.fields(adapter.snapshot())[key]['effective']['status'], 'missing')
            adapter.options['skill'] = None
            snapshot = adapter.snapshot()
            self.assertNotIn(self.target(ordered[-1]), self.fields(snapshot)[key]['targets'])

    def test_plugin_project_targets_retired_sources_and_save_round_trip(self):
        for plugin, skill, key in [('aihub-studio', 'aihub-image', 'AIHUB_API_KEY'),
                                   ('tikin-social', 'tikin-douyin', 'TIKIN_API_KEY')]:
            with self.subTest(plugin=plugin):
                adapter, user = self.global_adapter(plugin, skill=skill)
                local = self.project / ('.env.local.' + plugin)
                plain = self.project / ('.env.' + plugin)
                retired = [self.project / ('.env.' + skill), user / '.config' / plugin / ('.env.' + skill)]
                for path in retired:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(key + '=retired-secret\n')
                initial = adapter.snapshot()
                self.assertEqual(initial['default_targets']['project'], self.target(local))
                self.assertEqual(self.fields(initial)[key]['effective']['status'], 'missing')
                for path in retired:
                    self.assertNotIn(self.target(path), [layer['id'] for layer in initial['layers']])
                    with self.assertRaises(UIError):
                        adapter.preview({key: {'op': 'set', 'value': 'new'}}, initial['revision'], self.target(path))
                self.assertNotIn(self.target(plain), self.fields(initial)[key]['targets'])
                changes = {key: {'op': 'set', 'value': 'synthetic-plugin-key'}}
                preview = adapter.preview(changes, initial['revision'], self.target(local))
                self.assertFalse(local.exists())
                self.assertEqual(self.fields(preview)[key]['effective']['source'], self.target(local))
                saved = adapter.save(changes, initial['revision'], self.target(local))
                self.assertNotIn('synthetic-plugin-key', json.dumps(public_config(saved)))
                # The plain Plugin source can repair an existing secret and edit nonsecrets.
                plain.write_text(key + '=synthetic-plain-key\n')
                saved = adapter.save({key: {'op': 'set', 'value': 'synthetic-repaired'}},
                                     adapter.snapshot()['revision'], self.target(plain))
                self.assertEqual(self.fields(saved)[key]['effective']['source'], self.target(local))
                for caller in (None, skill):
                    adapter.options['skill'] = caller
                    self.assertEqual(self.fields(adapter.snapshot())[key]['effective']['source'], self.target(local))
                cleared = adapter.save({key: {'op': 'unset'}}, adapter.snapshot()['revision'], self.target(local))
                self.assertEqual(self.fields(cleared)[key]['effective']['value'], 'synthetic-repaired')
                self.assertEqual(self.fields(cleared)[key]['effective']['source'], self.target(plain))
                self.assertTrue(all('retired-secret' in p.read_text() for p in retired))

    def test_validation_revision_conflict_and_target_whitelist(self):
        file = self.project / '.env.local'
        original = 'AIHUB_API_KEY=synthetic-before\n'
        file.write_text(original)
        adapter = self.adapter('aihub-studio')
        initial = adapter.snapshot()
        with self.assertRaises(UIError):
            adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'replacement'},
                          'AIHUB_IMAGE_MODELS': {'op': 'set', 'value': ['bad model']}},
                         initial['revision'], self.target(file))
        with self.assertRaises(UIError):
            adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'replacement'}},
                         initial['revision'], '../../outside')
        self.assertEqual(file.read_text(), original)
        (self.project / '.env').write_text('UNKNOWN=added\n')
        for method in (adapter.save, adapter.preview):
            with self.assertRaises(UIError) as error:
                method({'AIHUB_API_KEY': {'op': 'set', 'value': 'replacement'}}, initial['revision'], self.target(file))
            self.assertEqual(error.exception.code, 'conflict')
        self.assertEqual(file.read_text(), original)

    def test_environment_winner_allows_editing_lower_file_but_never_environment(self):
        (self.project / '.env.local').write_text('AIHUB_API_KEY=first\n')
        adapter = self.adapter('aihub-studio')
        with patch.dict(os.environ, {'AIHUB_API_KEY': 'synthetic-environment'}):
            snapshot = adapter.snapshot()
            self.assertEqual(self.fields(snapshot)['AIHUB_API_KEY']['effective']['source'], 'process')
            self.assertNotIn('process', self.fields(snapshot)['AIHUB_API_KEY']['targets'])
            saved = adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'lower-file'}},
                                 snapshot['revision'], self.target(self.project / '.env.local'))
            self.assertEqual(self.fields(saved)['AIHUB_API_KEY']['effective']['value'], 'synthetic-environment')
            with self.assertRaises(UIError):
                adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'cannot-save'}}, saved['revision'], 'process')

    def test_unreadable_file_and_disabled_globals(self):
        broken = self.project / '.env'
        broken.mkdir()
        adapter = self.adapter('aihub-studio')
        snapshot = adapter.snapshot()
        self.assertEqual(self.fields(snapshot)['AIHUB_API_KEY']['effective']['status'], 'error')
        self.assertTrue(snapshot['validation_errors'])
        self.assertFalse(any(layer['enabled'] and layer['scope'] == 'global' for layer in snapshot['layers']))
        preview = adapter.preview({'AIHUB_API_KEY': {'op': 'set', 'value': 'valid-but-unreadable-layer'}},
                                  snapshot['revision'], self.target(self.project / '.env.local'))
        self.assertTrue(preview['validation_errors'])
        with self.assertRaises(UIError):
            adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'valid-but-unreadable-layer'}},
                         snapshot['revision'], self.target(self.project / '.env.local'))

    def test_partial_write_rolls_back_and_interrupted_transaction_recovers(self):
        first, second = self.project / 'one.env', self.project / 'two.env'
        first.write_bytes(b'one')
        second.write_bytes(b'two')
        transaction = Transaction(self.project / 'txn')
        def fail_after_write(written):
            if written:
                raise RuntimeError('synthetic failure')
        with self.assertRaises(RuntimeError):
            transaction.apply({str(first): (b'one', b'changed-one'), str(second): (b'two', b'changed-two')}, fail_after_write)
        self.assertEqual((first.read_bytes(), second.read_bytes()), (b'one', b'two'))
        replace(first, b'interrupted', digest(b'one'))
        journal = {'version': 1, 'committed': False, 'entries': [
            {'path': str(first), 'before': base64.b64encode(b'one').decode(), 'after': digest(b'interrupted')}]}
        replace(transaction.journal, json.dumps(journal).encode(), None)
        Transaction(transaction.directory).recover()
        self.assertEqual(first.read_bytes(), b'one')
        self.assertFalse(transaction.journal.exists())

    def test_recovery_never_overwrites_an_external_edit(self):
        path = self.project / 'setting.env'
        path.write_bytes(b'external')
        transaction = Transaction(self.project / 'txn')
        journal = {'version': 1, 'entries': [{'path': str(path), 'before': base64.b64encode(b'old').decode(), 'after': digest(b'ours')}]}
        replace(transaction.journal, json.dumps(journal).encode(), None)
        with self.assertRaises(UIError):
            transaction.recover()
        self.assertEqual(path.read_bytes(), b'external')
        self.assertTrue(transaction.journal.exists())

    def test_catalog_project_filter_pagination_sessions_and_resource_boundary(self):
        root = self.project / 'data/tikin-social'
        for number in range(26):
            task = root / f'20261106143025-任务{number}-run-{number:08x}'
            task.mkdir(parents=True)
            file = task / 'report.md'
            file.write_text('# report\n', encoding='utf-8')
            metadata = {'schema_version': 1, 'plugin': 'tikin-social', 'project_root': str(self.project), 'task_id': str(number),
                        'title': '任务' + str(number), 'records': [], 'created_at': str(number), 'updated_at': str(number),
                        'registered_outputs': [{'path': 'report.md', 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}],
                        'participants': [{'host': 'codex', 'conversation_id': str(number), 'relation': 'created'}],
                        'delivery': {'status': 'completed', 'reason': '报告完成'}}
            if number == 25:
                metadata['project_root'] = str(self.project / 'different')
            (task / 'task-info.json').write_text(json.dumps(metadata))
        catalog = Catalog(self.project, 'tikin-social')
        page = catalog.snapshot()
        self.assertEqual(page['totals'], {'tasks': 25, 'files': 25})
        self.assertEqual(len(page['tasks']), 6)
        self.assertEqual(len(catalog.snapshot({'browse': 'files'})['items']), 24)
        detail = catalog.snapshot({'folder': '0'})
        self.assertIn(detail['tasks'][0]['participants'][0]['conversation_id'], [s['id'] for s in detail['conversations']])
        resource = detail['items'][0]['resource']
        self.assertTrue(catalog.resource(resource).content.is_file())
        with self.assertRaises(UIError):
            catalog.resource('../../.env')
        catalog.resource(resource).content.write_text('# edited\n')
        with self.assertRaises(UIError):
            catalog.resource(resource)
        catalog.refresh()
        changed = catalog.snapshot({'folder': '0'})['items'][0]
        self.assertEqual(changed['status'], '文件已变更')
        self.assertNotIn('resource', changed)


if __name__ == '__main__':
    unittest.main()
