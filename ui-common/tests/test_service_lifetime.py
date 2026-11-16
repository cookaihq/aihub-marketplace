"""Exercise the shipped launchers, independent lifetimes and HTTP access boundary."""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlsplit, parse_qs
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPCookieProcessor, build_opener

MARKET = Path(os.environ.get('AIHUB_UI_TEST_MARKET', Path(__file__).resolve().parents[2]))


class ServiceLifetime(unittest.TestCase):
    def test_five_configuration_callers_keep_focus_and_task_context(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TEMP'], prefix='studio-callers-') as folder:
            project = Path(folder)
            package = MARKET / 'aihub-studio'
            user = project / 'user'
            user.mkdir()
            environment = {key: value for key, value in os.environ.items() if not key.startswith(('AIHUB_', 'TIKIN_'))}
            environment.update(HOME=str(user), USERPROFILE=str(user))
            environment.pop('UV_PROJECT_ENVIRONMENT', None)
            for name in ('image', 'video', 'audio', 'music', 'understanding'):
                skill = 'aihub-' + name
                focus = 'AIHUB_API_KEY,AIHUB_' + name.upper() + '_MODELS,AIHUB_RESULT_CHECK_ENABLED'
                command = [sys.executable, str(package / 'scripts/ui.py'), 'start', '--project', folder,
                    '--page', 'configuration', '--agent', 'codex', '--skill', skill, '--fields', focus,
                    '--save-scope', 'project', '--no-global-config', '--task-id', 'synthetic-task',
                    '--task-binding', 'synthetic-binding', '--continuation', '核对原任务后继续']
                def run(action):
                    actual = command.copy()
                    actual[2] = action
                    result = subprocess.run(actual, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=45)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    return json.loads(result.stdout)
                try:
                    started = run('start')
                    url = urlsplit(started['url'])
                    self.assertEqual(parse_qs(url.query)['fields'], [focus])
                    origin = url.scheme + '://' + url.netloc
                    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
                    with client.open(Request(origin + '/api/session', data=json.dumps({'token': url.fragment}).encode(),
                            headers={'Origin': origin, 'Content-Type': 'application/json'}), timeout=10):
                        pass
                    with client.open(origin + '/api/state', timeout=10) as response:
                        state = json.load(response)
                    self.assertEqual(len(state['config']['fields']), 20)
                    self.assertEqual({f['directory_scope'] for f in state['config']['fields'] if f.get('directory_scope')}, {'global', 'project'})
                    self.assertEqual(state['config']['presentation']['initial_target'], state['config']['default_targets']['project'])
                    self.assertFalse(any(layer['enabled'] for layer in state['config']['layers'] if layer['scope'] == 'global'))
                    self.assertEqual(state['config']['task']['binding'], 'synthetic-binding')
                finally:
                    run('stop')

    def test_native_background_launcher_exits_when_its_page_stops(self):
        self.check_background_launcher('workbuddy')

    def test_hermes_background_launcher_exits_when_its_page_stops(self):
        self.check_background_launcher('hermes')

    def check_background_launcher(self, host):
        with tempfile.TemporaryDirectory(dir=os.environ['TEMP'], prefix='attached-ui-') as temporary:
            package = MARKET / 'aihub-studio'
            command = [sys.executable, str(package / 'scripts/ui.py'), 'start', '--project', temporary,
                       '--page', 'artifacts', '--agent', host, '--no-global-config']
            environment = {key: value for key, value in os.environ.items() if not key.startswith(('AIHUB_', 'TIKIN_'))}
            environment.pop('UV_PROJECT_ENVIRONMENT', None)
            process = subprocess.Popen(command + ['--keep-running'], env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            try:
                started = json.loads(process.stdout.readline())
                self.assertEqual(started['status'], 'running')
                self.assertIsNone(process.poll())
                status_command = command.copy()
                status_command[2] = 'status'
                status = subprocess.run(status_command, env=environment, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(status.stdout)['instance'], started['instance'])
            finally:
                stop_command = command.copy()
                stop_command[2] = 'stop'
                subprocess.run(stop_command, env=environment, capture_output=True, check=True, timeout=30)
                self.assertEqual(process.wait(timeout=10), 0)
                process.stdout.close()
                process.stderr.close()

    def test_shipped_services_are_independent_and_restart_without_residency(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TEMP'], prefix='shipped-ui-') as temporary:
            project = Path(temporary)
            environment = {key: value for key, value in os.environ.items() if not key.startswith(('AIHUB_', 'TIKIN_'))}
            environment.pop('UV_PROJECT_ENVIRONMENT', None)
            for plugin in ('aihub-studio', 'tikin-social'):
                with self.subTest(plugin=plugin):
                    package = MARKET / ('aihub-studio' if plugin == 'aihub-studio' else 'tikin-social/skills/tikin-setup')
                    def cli(command, page, seconds=30):
                        result = subprocess.run([sys.executable, str(package / 'scripts/ui.py'), command,
                            '--project', str(project), '--page', page, '--agent', 'codex', '--no-global-config',
                            '--save-scope', 'project', '--idle-seconds', str(seconds)],
                            env=environment, capture_output=True, text=True, encoding='utf-8', timeout=120)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        return json.loads(result.stdout)
                    def connect(started):
                        origin, token = started['url'].split('/#')
                        client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
                        csrf = None
                        def request(path, body=None, headers=None):
                            actual = {'Origin': origin, 'Content-Type': 'application/json'}
                            if csrf:
                                actual['X-CSRF-Token'] = csrf
                            actual.update(headers or {})
                            with client.open(Request(origin + path, data=None if body is None else json.dumps(body).encode(),
                                                     headers=actual), timeout=10) as response:
                                self.assertIn('no-store', response.headers['Cache-Control'])
                                return json.load(response)
                        with self.assertRaises(HTTPError) as error:
                            request('/api/state')
                        self.assertEqual(error.exception.code, 401)
                        csrf = request('/api/session', {'token': token})['csrf']
                        return request
                    try:
                        artifacts = cli('start', 'artifacts')
                        art = connect(artifacts)
                        self.assertEqual(cli('start', 'artifacts')['instance'], artifacts['instance'])
                        first = art('/api/lifetime')['remaining']
                        time.sleep(1.1)
                        self.assertLess(art('/api/lifetime')['remaining'], first)
                        self.assertEqual(art('/api/activity', {})['remaining'], 30)
                        self.assertTrue(art('/api/residency', {'resident': True})['resident'])
                        self.assertTrue(connect(artifacts)('/api/lifetime')['resident'])
                        for path, body, headers, status in [('/health', None, {'Host': 'foreign.invalid'}, 403),
                            ('/api/activity', {}, {'Origin': 'https://foreign.invalid'}, 403),
                            ('/api/activity', {}, {'X-CSRF-Token': 'wrong'}, 403),
                            ('/resources/..%2F..%2F.env.local', None, {}, 404)]:
                            with self.assertRaises(HTTPError) as error:
                                art(path, body, headers)
                            self.assertEqual(error.exception.code, status)
                        configuration = cli('start', 'configuration', 4)
                        config = connect(configuration)
                        self.assertNotEqual(configuration['instance'], artifacts['instance'])
                        with self.assertRaises(HTTPError):
                            config('/api/residency', {'resident': True})
                        deadline = time.monotonic() + 7
                        while time.monotonic() < deadline:
                            try:
                                config('/api/lifetime')
                            except (URLError, TimeoutError, ConnectionError):
                                break
                            time.sleep(.3)
                        self.assertEqual(cli('status', 'configuration')['status'], 'stopped')
                        self.assertTrue(art('/api/lifetime')['resident'])
                        self.assertFalse(art('/api/residency', {'resident': False})['resident'])
                        self.assertGreaterEqual(art('/api/lifetime')['remaining'], 29)
                        cli('stop', 'artifacts')
                        restarted = cli('start', 'artifacts')
                        self.assertNotEqual(restarted['instance'], artifacts['instance'])
                        self.assertFalse(connect(restarted)('/api/lifetime')['resident'])
                    finally:
                        for page in ('configuration', 'artifacts'):
                            cli('stop', page)
                            self.assertEqual(cli('status', page)['status'], 'stopped')
