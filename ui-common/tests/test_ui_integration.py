"""Real loader and persistence regression coverage; no business network calls."""
import base64
import hashlib
import json
import os
from pathlib import Path
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

    def test_missing_key_starts_and_real_loader_reads_saved_value(self):
        for plugin, key in [('aihub-studio', 'AIHUB_API_KEY'), ('tikin-social', 'TIKIN_API_KEY')]:
            with self.subTest(plugin=plugin):
                adapter = self.adapter(plugin)
                initial = adapter.snapshot()
                self.assertFalse(next(f for f in public_config(initial)['fields'] if f['id'] == key)['configured'])
                saved = adapter.save({key: {'op': 'set', 'value': 'synthetic-only-value'}}, initial['revision'])
                self.assertEqual(next(f for f in saved['fields'] if f['id'] == key)['value'], 'synthetic-only-value')
                self.assertNotIn('synthetic-only-value', json.dumps(public_config(saved)))
                self.assertFalse(adapter.transaction.journal.exists())

    def test_actual_skill_source_and_multiple_files_preserve_unknowns(self):
        (self.project / '.env.local').write_text('# keep me\nOTHER=value\nAIHUB_API_KEY=old\nAIHUB_API_KEY=last\n', encoding='utf-8')
        model = self.project / '.env.aihub-image'
        model.write_text('AIHUB_IMAGE_MODELS=old-model\n', encoding='utf-8')
        adapter = self.adapter('aihub-studio')
        initial = adapter.snapshot()
        fields = {f['id']: f for f in initial['fields']}
        self.assertEqual(Path(fields['AIHUB_IMAGE_MODELS']['path']), model)
        adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'literal-$(keep)-`keep`'},
                      'AIHUB_IMAGE_MODELS': {'op': 'set', 'value': ['new-model', 'second-model']}}, initial['revision'])
        raw = (self.project / '.env.local').read_text()
        self.assertIn('# keep me\nOTHER=value\n', raw)
        self.assertEqual(raw.count('AIHUB_API_KEY='), 1)
        self.assertIn('new-model,second-model', model.read_text())

    def test_real_global_settings_and_key_share_one_transaction(self):
        user = self.project / 'synthetic-user'
        user.mkdir()
        environment = dict(os.environ, HOME=str(user), USERPROFILE=str(user))
        environment.pop('UV_PROJECT_ENVIRONMENT', None)
        for plugin in ('aihub-studio', 'tikin-social'):
            package = MARKET / ('aihub-studio' if plugin == 'aihub-studio' else 'tikin-social/skills/tikin-setup')
            adapter = Configuration(package, self.project, {'plugin': plugin, 'global_enabled': True,
                                    'save_scope': 'global', 'agent': 'codex', 'config_dir': str(user / 'agent')}, environment)
            snapshot = adapter.snapshot()
            key = 'AIHUB_API_KEY' if plugin == 'aihub-studio' else 'TIKIN_API_KEY'
            self.assertEqual(Path(snapshot['fields'][0]['path']), user / '.config' / plugin / '.env')
            changes = {key: {'op': 'set', 'value': 'synthetic-global-value'}, 'default_skill_reminders': {'op': 'set', 'value': False}}
            if plugin == 'tikin-social':
                changes['routing.default'] = {'op': 'set', 'value': 'confirm'}
            result = adapter.save(changes, snapshot['revision'])
            values = {f['id']: f['value'] for f in result['fields']}
            self.assertFalse(values['default_skill_reminders'])
            self.assertEqual(values[key], 'synthetic-global-value')
            if plugin == 'tikin-social':
                self.assertEqual(values['routing.default'], 'confirm')

    def test_validation_and_revision_conflict_do_not_partially_save(self):
        file = self.project / '.env.local'
        original = 'AIHUB_API_KEY=synthetic-before\n'
        file.write_text(original)
        adapter = self.adapter('aihub-studio')
        initial = adapter.snapshot()
        with self.assertRaises(UIError):
            adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'replacement'},
                          'AIHUB_IMAGE_MODELS': {'op': 'set', 'value': ['bad model']}}, initial['revision'])
        self.assertEqual(file.read_text(), original)
        (self.project / '.env').write_text('UNKNOWN=added\n')
        with self.assertRaises(UIError) as error:
            adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'replacement'}}, initial['revision'])
        self.assertEqual(error.exception.code, 'conflict')
        self.assertEqual(file.read_text(), original)

    def test_clear_uses_original_loader_fallback_and_environment_is_readonly(self):
        (self.project / '.env.local').write_text('AIHUB_API_KEY=first\n')
        (self.project / '.env').write_text('AIHUB_API_KEY=fallback\n')
        adapter = self.adapter('aihub-studio')
        initial = adapter.snapshot()
        saved = adapter.save({'AIHUB_API_KEY': {'op': 'unset'}}, initial['revision'])
        self.assertEqual(saved['fields'][0]['value'], 'fallback')
        with patch.dict(os.environ, {'AIHUB_API_KEY': 'synthetic-environment'}):
            snapshot = adapter.snapshot()
            self.assertTrue(snapshot['fields'][0]['readonly'])
            with self.assertRaises(UIError):
                adapter.save({'AIHUB_API_KEY': {'op': 'set', 'value': 'cannot-save'}}, snapshot['revision'])

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
