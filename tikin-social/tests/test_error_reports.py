"""Exercise the distributed request command against synthetic local HTTP responses."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/tikin-setup/scripts/tikin-config'
sys.path.insert(0, str(SCRIPT.parent))
import tikin_request


class ErrorReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tikin-errors-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.status = 422
        self.payload = {'error': {'code': 'provider_new_code', 'message': 'synthetic private detail',
                                  'upstream_status': 503, 'trace_id': 'private-trace'}}
        self.calls = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.calls.append(self.path)
                self.send_response(owner.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Request-ID', 'private-request')
                self.send_header('Set-Cookie', 'secret-cookie=do-not-save')
                self.end_headers()
                self.wfile.write(json.dumps(owner.payload).encode())

            do_POST = do_GET

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.env = {**os.environ, 'TIKIN_API_KEY': 'synthetic-key-do-not-save',
                    'TIKIN_BASE_URL': f'http://127.0.0.1:{self.server.server_port}'}

    def request(self, record=None, method='GET'):
        request = self.root / 'request.json'
        request.write_text(json.dumps({'original_request': 'synthetic private user requirement',
                                      'method': method, 'path': '/api/v1/tiktok/test',
                                      'query': {'keyword': 'private query', 'blank': '', 'api_key': 'nested-secret'}}), encoding='utf-8')
        cmd = [sys.executable, str(SCRIPT), '--skill', 'tikin-tiktok', '--no-global-config',
               'request', '--request-file', str(request)]
        if record:
            cmd += ['--record', str(record)]
        result = subprocess.run(cmd, cwd=self.root, env=self.env, text=True, encoding='utf-8',
                                capture_output=True, timeout=40)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return json.loads(result.stdout)

    def test_first_error_has_actual_request_response_and_private_public_split(self):
        output = self.request()
        self.assertEqual(len(self.calls), 1)
        feedback = output['feedback']
        report = Path(feedback['error_report'])
        self.assertTrue(report.is_absolute())
        text = report.read_text(encoding='utf-8')
        for evidence in ['synthetic private user requirement', 'private query', 'provider_new_code',
                         'private-trace', 'private-request', '422', '503']:
            self.assertIn(evidence, text)
        for secret in ['synthetic-key-do-not-save', 'nested-secret', 'secret-cookie=do-not-save']:
            self.assertNotIn(secret, text)
        diagnostic = json.loads(Path(feedback['diagnostic']).read_text(encoding='utf-8'))
        self.assertEqual(diagnostic['exchanges'][0]['request']['query']['blank'], [''])
        draft = Path(feedback['issue_draft']).read_text(encoding='utf-8')
        for private in ['private query', 'private-trace', 'private-request', 'synthetic private user requirement']:
            self.assertNotIn(private, draft)
        self.assertTrue(all(str(Path(p)).replace('\\', '/') in '\n'.join(feedback['artifact_links'])
                            for p in [feedback['error_report'], feedback['diagnostic'], feedback['issue_draft']]))

    def test_terminal_failure_is_deduplicated_across_processes_and_recovery_keeps_links(self):
        self.status = 200
        self.payload = {'id': 'synthetic-task', 'status': 'failed', 'error': {'code': 'service_unavailable'}}
        first = self.request()
        again = self.request(first['record'])
        self.assertEqual(again['feedback']['upstream_error_count'], 1)
        self.assertEqual(first['feedback']['error_report'], again['feedback']['error_report'])
        self.payload = {'id': 'synthetic-task', 'status': 'completed', 'data': {'items': []}}
        recovered = self.request(first['record'])
        self.assertEqual(recovered['status'], 'ok')
        self.assertEqual(recovered['feedback']['error_report'], first['feedback']['error_report'])
        self.assertEqual(len(self.calls), 3)

    def test_uncertain_write_is_not_replayed_even_after_a_successful_query(self):
        self.status = 503
        first = self.request(method='POST')
        self.assertEqual(first['status'], 'submission_unknown')
        self.assertEqual(len(self.calls), 1)
        self.status, self.payload = 200, {'code': 200, 'data': []}
        queried = self.request(first['record'])
        self.assertEqual(queried['status'], 'ok')
        repeated = self.request(first['record'], method='POST')
        self.assertEqual(repeated['status'], 'submission_unknown')
        self.assertEqual(len(self.calls), 2)

    def test_report_write_failure_preserves_the_actual_result_without_resending(self):
        request = self.root / 'write.json'
        request.write_text(json.dumps({'original_request': 'synthetic batch', 'method': 'POST',
                                       'path': '/api/v1/batch', 'body': ['one']}), encoding='utf-8')
        self.status = 503
        with patch.object(tikin_request, 'feedback', side_effect=OSError('synthetic report failure')):
            result = tikin_request.execute(self.env, 'tikin-tiktok', request, output_dir=self.root)
        self.assertEqual(result['status'], 'submission_unknown')
        self.assertEqual(result['http_status'], 503)
        self.assertIn('feedback_warning', result)
        self.assertEqual(len(self.calls), 1)
        again = tikin_request.execute(self.env, 'tikin-tiktok', request, result['record'])
        self.assertEqual(again['status'], 'submission_unknown')
        self.assertEqual(len(self.calls), 1)

    def test_success_keeps_full_results_media_urls_and_pagination_tokens(self):
        self.status = 200
        self.payload = {'data': list(range(501)), 'pagination_token': 'next-page',
                        'media_url': 'https://media.invalid/file?sign=usable-signature',
                        'accessToken': 'must-not-return'}
        result = self.request()
        self.assertEqual(len(result['response']['data']), 501)
        self.assertEqual(result['response']['pagination_token'], 'next-page')
        self.assertEqual(result['response']['media_url'], self.payload['media_url'])
        self.assertNotIn('must-not-return', json.dumps(result))

    def test_later_save_failure_still_links_the_previous_real_report(self):
        first = self.request()
        with patch.object(tikin_request, 'feedback', side_effect=OSError('synthetic later save failure')):
            again = tikin_request.execute(self.env, 'tikin-tiktok', self.root / 'request.json', first['record'])
        self.assertEqual(again['status'], 'failed')
        self.assertIn('feedback_warning', again)
        self.assertEqual(again['feedback']['error_report'], first['feedback']['error_report'])
        self.assertTrue(Path(again['feedback']['error_report']).is_file())
        self.assertEqual(len(self.calls), 2)

    def test_transient_reads_save_first_error_before_retry(self):
        request = self.root / 'read.json'
        request.write_text(json.dumps({'original_request': 'synthetic read', 'path': '/api/v1/read'}), encoding='utf-8')
        self.status = 503
        def recover(_):
            reports = list(self.root.glob('tikin-run-*/error-report.md'))
            self.assertEqual(len(reports), 1)
            self.assertIn('503', reports[0].read_text(encoding='utf-8'))
            self.status, self.payload = 200, {'data': []}
        with patch.object(tikin_request.time, 'sleep', side_effect=recover):
            result = tikin_request.execute(self.env, 'tikin-tiktok', request, output_dir=self.root)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['feedback']['upstream_error_count'], 1)
        self.assertEqual(len(self.calls), 2)

    def test_nonfinite_retry_after_is_bounded(self):
        for value in ['Infinity', 'NaN', '-Infinity', 'nonsense']:
            self.assertEqual(tikin_request.retry_delay({'retry-after': value}, 1), 1)
        self.assertEqual(tikin_request.retry_delay({'retry-after': '3600'}, 1), 60)


if __name__ == '__main__':
    unittest.main()
