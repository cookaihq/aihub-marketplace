"""Real wrapper, HTTP save and recovery through both business configuration loaders."""
from http.cookiejar import CookieJar
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request

import test_setup
from test_setup import MARKET, SKILL


class UITests(unittest.TestCase):
    setUp = test_setup.SetupTests.setUp
    call = test_setup.SetupTests.call

    def ui(self, command, *args, ok=True):
        process = subprocess.run([sys.executable, str(SKILL / 'scripts/setup_ui.py'), command,
                                  '--host', 'codex', '--cwd', str(self.project), *map(str, args)],
                                 env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=60)
        value = json.loads(process.stdout)
        self.assertEqual(process.returncode == 0, ok, value)
        self.assertNotIn(self.marker, process.stdout + process.stderr)
        return value

    def test_real_pages_preserve_task_binding_save_once_and_resume_without_business_calls(self):
        for plugin, root_flag, key, skill in [('aihub-studio', '--aihub-root', 'AIHUB_API_KEY', 'aihub-image'),
                                             ('tikin-social', '--tikin-root', 'TIKIN_API_KEY', 'tikin-douyin')]:
            with self.subTest(plugin=plugin):
                started = self.ui('start', root_flag, MARKET / plugin, '--plugin', plugin, '--skill', skill,
                                  '--no-global-config', '--scope', 'project', '--submission', 'submitted', '--business-task-id', 'existing-task')
                task = started['task']
                try:
                    self.assertEqual(self.ui('start', '--task', task)['instance'], started['instance'])
                    origin, token = started['url'].split('/#')
                    session = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
                    def request(path, body=None, csrf=None, access_origin=None):
                        headers = {'Origin': access_origin or origin, 'Content-Type': 'application/json'}
                        if csrf:
                            headers['X-CSRF-Token'] = csrf
                        req = Request(origin + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
                        with session.open(req, timeout=20) as response:
                            self.assertIn('no-store', response.headers['Cache-Control'])
                            return json.load(response)
                    with self.assertRaises(HTTPError) as rejected:
                        request('/api/state')
                    self.assertEqual(rejected.exception.code, 401)
                    csrf = request('/api/session', {'token': token})['csrf']
                    state = request('/api/state')['config']
                    self.assertEqual(state['task']['id'], task)
                    self.assertEqual(state['task']['binding'], started['binding'])
                    self.assertNotIn('BASE_URL', json.dumps(state))
                    changes = {'changes': {key: {'op': 'set', 'value': self.marker}}, 'revision': state['revision']}
                    with self.assertRaises(HTTPError):
                        request('/api/save', changes, 'invalid')
                    with self.assertRaises(HTTPError):
                        request('/api/save', changes, csrf, 'https://foreign.invalid')
                    saved = request('/api/save', changes, csrf)
                    self.assertNotIn(self.marker, json.dumps(saved))
                    self.assertEqual(saved['receipt']['task']['binding'], started['binding'])
                    status = self.ui('status', '--task', task)
                    self.assertEqual(status['saved']['task']['id'], task)
                    continued = self.call('continue', '--task', task)
                    self.assertEqual(continued['phase'], 'completed')
                    self.assertEqual(continued['result']['business_next_step'], 'query_existing_result')
                    self.assertEqual(continued['context']['caller'], skill)
                    self.assertEqual(continued['business']['task_id'], 'existing-task')
                    self.assertEqual(Path(continued['result']['local']['fields'][key]['source']), self.project / '.env.local')
                    self.assertIn(self.marker, (self.project / '.env.local').read_text())
                    self.assertFalse((self.user / '.config' / plugin / '.env').exists())
                finally:
                    self.ui('stop', '--task', task)
                self.assertEqual(self.ui('status', '--task', task)['status'], 'stopped')

    def test_retired_source_is_rejected_without_creating_a_task(self):
        outcome = self.call('start', '--plugin', 'aihub-studio', '--plugin-root', MARKET / 'aihub-studio',
                            '--plugin-only', '--operation', 'configure', '--source', 'secret-book', ok=False)
        self.assertEqual(outcome['reason'], 'invalid_arguments')
        self.assertFalse((self.user / '.config/setup-aihub/tasks').exists())

    def test_background_wrapper_returns_receipt_before_stop_and_exits_afterward(self):
        for plugin, root_flag in [('aihub-studio', '--aihub-root'), ('tikin-social', '--tikin-root')]:
            with self.subTest(plugin=plugin):
                output = self.project / (plugin + '-launcher.jsonl')
                task = None
                with output.open('w', encoding='utf-8') as log:
                    process = subprocess.Popen([
                        sys.executable, str(SKILL / 'scripts/setup_ui.py'), 'start',
                        '--host', 'workbuddy', '--cwd', str(self.project), root_flag, str(MARKET / plugin),
                        '--plugin', plugin, '--no-global-config', '--scope', 'project', '--keep-running',
                    ], env=self.env, stdout=log, stderr=subprocess.PIPE, text=True, encoding='utf-8')
                    try:
                        deadline = time.monotonic() + 45
                        receipt = ''
                        while time.monotonic() < deadline:
                            receipt = output.read_text(encoding='utf-8')
                            if '\n' in receipt or process.poll() is not None:
                                break
                            time.sleep(.1)
                        self.assertTrue(receipt, 'The wrapper did not promptly return its startup receipt')
                        started = json.loads(receipt)
                        task = started.get('task')
                        self.assertEqual(started['status'], 'running')
                        self.assertIsNone(process.poll())
                        status = self.ui('status', '--host', 'workbuddy', '--task', task)
                        self.assertEqual(status['instance'], started['instance'])
                    finally:
                        if task:
                            self.ui('stop', '--host', 'workbuddy', '--task', task)
                        try:
                            self.assertEqual(process.wait(timeout=10), 0)
                        finally:
                            if process.poll() is None:
                                process.terminate()
                                process.wait(timeout=10)
                            process.stderr.close()
                self.assertEqual(len(output.read_text(encoding='utf-8').splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
