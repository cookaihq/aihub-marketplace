"""Shipped configuration HTTP API -> original resolver and transaction, synthetic roots only."""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, ProxyHandler, HTTPCookieProcessor, build_opener
from urllib.error import HTTPError

MARKET = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MARKET / 'aihub-studio/shared'), str(MARKET / 'aihub-studio/ui')]
from adapter import build
from skill_ui import server


class FieldScopes(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ['TEMP'], prefix='studio-scopes-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        self.user = self.project / 'user'
        self.user.mkdir()
        options = dict(plugin='aihub-studio', skill='aihub-audio', agent='codex',
                       global_enabled=True, save_scope='global', config_dir=str(self.user / 'agent'))
        environment = dict(os.environ, HOME=str(self.user), USERPROFILE=str(self.user),
                           AIHUB_UI_OPTIONS=json.dumps(options))
        for key in list(environment):
            if key.startswith(('AIHUB_', 'TIKIN_')) and key != 'AIHUB_UI_OPTIONS':
                environment.pop(key)
        isolated = patch.dict(os.environ, environment, clear=True)
        isolated.start()
        self.addCleanup(isolated.stop)
        self.adapter = build(self.project)
        (self.project / 'runtime').mkdir()
        self.app = server.Server(self.adapter, self.project, 'configuration', self.project / 'runtime')
        thread = threading.Thread(target=self.app.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.app.shutdown(), self.app.server_close(), thread.join(timeout=5)))
        self.client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        self.csrf = self.request('/api/session', {'token': self.app.token})['csrf']

    def request(self, route, body=None):
        headers = {'Origin': self.app.origin, 'Content-Type': 'application/json'}
        if getattr(self, 'csrf', None):
            headers['X-CSRF-Token'] = self.csrf
        with self.client.open(Request(self.app.origin + route,
                data=None if body is None else json.dumps(body).encode(), headers=headers), timeout=30) as response:
            self.assertIn('no-store', response.headers['Cache-Control'])
            return json.load(response)

    def snapshot(self):
        return self.request('/api/state')['config']

    def target(self, snapshot, path):
        return next(layer['id'] for layer in snapshot['layers'] if layer['path'] == str(path))

    def field(self, snapshot, key):
        return next(field for field in snapshot['fields'] if field['id'] == key)

    def test_switch_uses_real_loader_and_cleans_all_higher_sources_atomically(self):
        key = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID'
        project = self.project / '.env.local.aihub-studio'
        shared = self.project / '.env.local'
        global_file = self.user / '.config/aihub-studio/.env'
        global_file.parent.mkdir(parents=True)
        project.write_text(key + '=project-voice\nUNRELATED=keep\n')
        shared.write_text(key + '=shared-voice\n')
        global_file.write_text(key + '=global-voice\n')
        initial = self.snapshot()
        self.assertEqual(initial.get('configuration_protocol'), 'field-scopes-v1')
        target = self.target(initial, global_file)
        changes = {'files': {}, 'switches': {key: {'target': target, 'mode': 'existing'}}}
        preview = self.request('/api/preview', {'changes': changes, 'revision': initial['revision']})['config']
        self.assertEqual(preview['scope_plans'][key]['state'], 'ready')
        self.assertIn('project-voice', project.read_text())
        saved = self.request('/api/save', {'changes': changes, 'revision': initial['revision']})['config']
        self.assertEqual(self.field(saved, key)['effective']['value'], 'global-voice')
        self.assertEqual(self.field(saved, key)['effective']['source'], target)
        self.assertEqual(project.read_text(), 'UNRELATED=keep\n')
        self.assertEqual(shared.read_text(), '')
        reread = self.snapshot()
        self.assertEqual(self.field(reread, key)['effective']['source'], target)
        # A client recovering a lost save response can recognize this exact
        # completed projection without resubmitting the destructive switch.
        self.assertEqual(self.field(preview, key)['edit_revision'], self.field(reread, key)['edit_revision'])
        self.assertFalse(self.adapter.configuration.transaction.journal.exists())

    def test_voice_cache_survives_reload_and_failed_refresh_and_isolates_credentials(self):
        # Replace only the external transport, keeping the shipped pipe, resolver,
        # catalogue normalization and on-disk cache in the exercised path.
        fixture = self.project / 'network.mjs'
        calls, failure = self.project / 'calls.jsonl', self.project / 'fail'
        fixture.write_text("import {appendFileSync,existsSync,readFileSync} from 'node:fs';\n"
            "globalThis.fetch=async url=>{appendFileSync(" + json.dumps(str(calls)) + ",String(url)+'\\n');"
            "const offset=Number(new URL(url).searchParams.get('offset')),mode=existsSync(" + json.dumps(str(failure)) + ")?readFileSync(" + json.dumps(str(failure)) + ",'utf8'):'';"
            "if(offset&&mode==='auth')return new Response('{}',{status:401});"
            "if(offset&&mode==='json')return new Response('{');"
            "const total=mode==='empty'?0:offset&&mode==='changed'?202:201,headers={'X-Total-Count':String(total),'X-Limit':'100','X-Offset':String(offset),'X-Next-Offset':offset+100<total?String(offset+100):''};"
            "if(offset&&mode==='headers')delete headers['X-Next-Offset'];"
            "const rows=Array.from({length:Math.min(100,total-offset)},(_,i)=>({voice_id:'fixture-voice-'+(offset+i),name:mode==='updated'?'Updated':'Fixture',languages:['zh','en'],category:['narration'],metadata:{index:offset+i,keep:false}}));"
            "return new Response(JSON.stringify(rows),{headers});};\n")
        with patch.dict(os.environ, {'NODE_OPTIONS': '--import=' + fixture.as_uri()}):
            credential = self.project / '.env.local.aihub-studio'
            credential.write_text('AIHUB_API_KEY=synthetic-account-A\n')
            first = self.request('/api/elevenlabs-voices')
            self.assertIsInstance(first.get('saved_at'), (int, float))
            self.assertEqual(len(first['voices']), 201)
            self.assertEqual(first['voices'][0]['voice_id'], 'fixture-voice-0')
            self.assertEqual(first['voices'][-1]['voice_id'], 'fixture-voice-200')
            self.assertEqual(first['voices'][-1]['metadata'], {'index': 200, 'keep': False})
            self.assertEqual([int(url.split('offset=')[1]) for url in calls.read_text().splitlines()], [0, 100, 200])
            cache = self.user / '.config/aihub-studio/cache/voice-library'
            path, = cache.glob('*.json')
            previous = path.read_bytes()
            second = self.request('/api/elevenlabs-voices')
            self.assertEqual(second['saved_at'], first['saved_at'])
            self.assertEqual(len(calls.read_text().splitlines()), 3)
            for mode in ('auth', 'json', 'headers', 'changed'):
                failure.write_text(mode)
                with self.assertRaises(HTTPError) as error:
                    self.request('/api/elevenlabs-voices/refresh', {})
                self.assertEqual(error.exception.code, 502)
                self.assertEqual(path.read_bytes(), previous)
                self.assertEqual(self.request('/api/elevenlabs-voices')['saved_at'], first['saved_at'])
            failure.write_text('updated')
            updated = self.request('/api/elevenlabs-voices/refresh', {})
            self.assertEqual(updated['voices'][0]['voice_name'], 'Updated')
            self.assertGreater(updated['saved_at'], first['saved_at'])
            self.assertEqual(json.loads(path.read_bytes())['voices'], updated['voices'])
            failure.write_text('empty')
            empty = self.request('/api/elevenlabs-voices/refresh', {})
            self.assertEqual(empty['voices'], [])
            self.assertEqual(json.loads(path.read_bytes())['voices'], [])
            failure.unlink()
            credential.write_text('AIHUB_API_KEY=synthetic-account-B\n')
            other = self.request('/api/elevenlabs-voices')
            self.assertGreater(other['saved_at'], first['saved_at'])
            self.assertEqual(len(calls.read_text().splitlines()), 18)
            self.assertEqual(credential.read_text(), 'AIHUB_API_KEY=synthetic-account-B\n')

    def test_directory_rejects_an_account_change_between_identity_and_download(self):
        fixture = self.project / 'network.mjs'
        credential = self.project / '.env.local.aihub-studio'
        credential.write_text('AIHUB_API_KEY=synthetic-account-A\n')
        # The transport response changes the configured account during download.
        # A successful response still belongs only to the key actually requested.
        fixture.write_text("import {writeFileSync} from 'node:fs';\n"
            "globalThis.fetch=async()=>{writeFileSync(" + json.dumps(str(credential)) +
            ",'AIHUB_API_KEY=synthetic-account-B\\n');return new Response(JSON.stringify(["
            "{voice_id:'account-A-voice',name:'Account A'}]),{headers:{'X-Total-Count':'1','X-Limit':'100','X-Offset':'0','X-Next-Offset':''}});};\n")
        with patch.dict(os.environ, {'NODE_OPTIONS': '--import=' + fixture.as_uri()}):
            with self.assertRaises(HTTPError) as error:
                self.request('/api/elevenlabs-voices')
            self.assertEqual(error.exception.code, 409)
        cache = self.user / '.config/aihub-studio/cache/voice-library'
        self.assertFalse(list(cache.glob('*.json')))

    def test_choice_is_bound_to_input_and_revision_and_public_values_stay_masked(self):
        key = 'AIHUB_API_KEY'
        project = self.project / '.env.local.aihub-studio'
        global_file = self.user / '.config/aihub-studio/.env'
        global_file.parent.mkdir(parents=True)
        project.write_text(key + '=synthetic-project-A\n')
        global_file.write_text(key + '=synthetic-global-B\n')
        initial = self.snapshot()
        source, target = self.target(initial, project), self.target(initial, global_file)
        changes = {'files': {source: {key: {'op': 'set', 'value': 'synthetic-entered-C'}}},
            'switches': {key: {'target': target, 'mode': 'input'}}}
        preview = self.request('/api/preview', {'changes': changes, 'revision': initial['revision']})['config']
        plan = preview['scope_plans'][key]
        self.assertEqual(plan['state'], 'choice')
        for value in ('synthetic-project-A', 'synthetic-global-B', 'synthetic-entered-C'):
            self.assertNotIn(value, json.dumps(preview))
        changes['switches'][key].update(choice='input', choice_token=plan['choice_token'])
        changes['files'][source][key]['value'] = 'synthetic-entered-D'
        with self.assertRaises(HTTPError) as error:
            self.request('/api/save', {'changes': changes, 'revision': initial['revision']})
        self.assertEqual(error.exception.code, 422)
        self.assertIn('synthetic-project-A', project.read_text())
        preview = self.request('/api/preview', {'changes': changes, 'revision': initial['revision']})['config']
        changes['switches'][key]['choice_token'] = preview['scope_plans'][key]['choice_token']
        checked = self.request('/api/preview', {'changes': changes, 'revision': initial['revision']})['config']
        self.assertEqual(checked['scope_plans'][key]['state'], 'ready')
        saved = self.request('/api/save', {'changes': changes, 'revision': initial['revision']})['config']
        self.assertEqual(self.field(saved, key)['effective']['source'], target)
        self.assertEqual(project.read_text(), '')
        self.assertIn('synthetic-entered-D', global_file.read_text())
        self.assertEqual(self.field(checked, key)['edit_revision'], self.field(saved, key)['edit_revision'])
        with self.assertRaises(HTTPError) as error:
            self.request('/api/save', {'changes': changes, 'revision': initial['revision']})
        self.assertEqual(error.exception.code, 409)

    def test_subset_dependencies_missing_key_and_required_deletion(self):
        project = self.project / '.env.local.aihub-studio'
        project.write_text('AIHUB_RESULT_CHECK_ENABLED=0\n')
        initial = self.snapshot()
        target = self.target(initial, project)
        def save(edits, snapshot):
            return self.request('/api/save', {'revision': snapshot['revision'],
                'changes': {'files': {target: edits}, 'switches': {}}})['config']
        provider = {'AIHUB_RESULT_CHECK_PROVIDER': {'op': 'set', 'value': 'host'}}
        with self.assertRaises(HTTPError) as error:
            save(provider, initial)
        self.assertEqual(error.exception.code, 422)
        combined = dict(provider, AIHUB_RESULT_CHECK_ENABLED={'op': 'set', 'value': True})
        saved = save(combined, initial)
        self.assertEqual(self.field(saved, 'AIHUB_RESULT_CHECK_PROVIDER')['effective']['value'], 'host')
        self.assertFalse(self.field(saved, 'AIHUB_API_KEY')['effective']['configured'])
        saved = save({'AIHUB_API_KEY': {'op': 'set', 'value': 'synthetic-only-key'}}, saved)
        with self.assertRaises(HTTPError) as error:
            save({'AIHUB_API_KEY': {'op': 'unset'}}, saved)
        self.assertEqual(error.exception.code, 422)
        self.assertIn('synthetic-only-key', project.read_text())

    def test_real_tracked_higher_source_blocks_the_entire_switch(self):
        key = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID'
        project = self.project / '.env.local.aihub-studio'
        shared = self.project / '.env.local'
        global_file = self.user / '.config/aihub-studio/.env'
        global_file.parent.mkdir(parents=True)
        project.write_text(key + '=project-A\n')
        shared.write_text(key + '=project-B\n')
        global_file.write_text(key + '=global-C\n')
        def git(*args):
            return subprocess.run(['git', '-C', str(self.project), *args], capture_output=True, check=True).stdout
        git('init', '--quiet')
        git('add', '--', shared.name)
        index = git('ls-files', '--stage')
        before = {path: path.read_bytes() for path in (project, shared, global_file)}
        initial = self.snapshot()
        changes = {'files': {}, 'switches': {key: {'target': self.target(initial, global_file), 'mode': 'existing'}}}
        with self.assertRaises(HTTPError):
            self.request('/api/save', {'changes': changes, 'revision': initial['revision']})
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertEqual(index, git('ls-files', '--stage'))

    def test_process_override_blocks_switch_and_failed_second_write_rolls_back(self):
        from importlib import import_module
        persistence = import_module('persistence')
        key = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID'
        project = self.project / '.env.local.aihub-studio'
        shared = self.project / '.env.local'
        global_file = self.user / '.config/aihub-studio/.env'
        global_file.parent.mkdir(parents=True)
        project.write_text(key + '=project-A\n')
        shared.write_text(key + '=project-B\n')
        global_file.write_text(key + '=global-C\n')
        before = {path: path.read_bytes() for path in (project, shared, global_file)}
        with patch.dict(os.environ, {key: 'synthetic-process-voice'}):
            initial = self.snapshot()
            changes = {'files': {}, 'switches': {key: {'target': self.target(initial, global_file), 'mode': 'existing'}}}
            preview = self.request('/api/preview', {'changes': changes, 'revision': initial['revision']})['config']
            self.assertEqual(preview['scope_plans'][key]['state'], 'blocked')
            with self.assertRaises(HTTPError):
                self.request('/api/save', {'changes': changes, 'revision': initial['revision']})
        initial = self.snapshot()
        replace = persistence.replace
        failures = []
        def fail_second(path, content, expected, *args, **kwargs):
            if Path(path) == shared and content == b'' and not failures:
                failures.append(True)
                raise PermissionError('synthetic second configuration write failure')
            return replace(path, content, expected, *args, **kwargs)
        with patch.object(persistence, 'replace', side_effect=fail_second):
            with self.assertRaises(HTTPError):
                self.request('/api/save', {'changes': changes, 'revision': initial['revision']})
        self.assertTrue(failures)
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertEqual(self.field(self.snapshot(), key)['effective']['value'], 'project-A')
        self.assertFalse(self.adapter.configuration.transaction.journal.exists())


if __name__ == '__main__':
    unittest.main()
