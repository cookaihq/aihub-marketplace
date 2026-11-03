"""Public CLI tests with real processes, durable files and controlled HTTP peers."""
import json
import hashlib
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/tikin-setup/scripts/tikin-config'


class ExecutionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tikin-execution-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.responses = [(200, {}, {'data': {'items': []}})]
        self.calls = []
        self.received = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.guard_binding = None
        self.service_binding = None
        self.proof_override = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if owner.guard_binding and self.headers.get('X-Tikin-Regression-Binding') != owner.guard_binding:
                    self.send_response(409)
                    self.end_headers()
                    self.wfile.write(b'{"error":{"code":"wrong_binding"}}')
                    return
                if self.path == '/_tikin/regression-binding':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps(owner.proof_override or {**owner.service_binding, 'binding_sha256': owner.guard_binding}).encode())
                    return
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.calls.append((self.command, self.path, body))
                owner.received.set()
                owner.release.wait(10)
                status, headers, payload = owner.responses[min(len(owner.calls) - 1, len(owner.responses) - 1)]
                self.send_response(status)
                if owner.guard_binding:
                    self.send_header('X-Tikin-Regression-Binding', owner.guard_binding)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                try:
                    self.wfile.write(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_POST = do_GET

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.env = {**os.environ, 'TIKIN_API_KEY': 'synthetic-execution-key', 'TIKIN_BASE_URL': self.base}

    def command(self, spec, record=None, approval=None):
        path = self.root / 'request.json'
        path.write_text(json.dumps({'original_request': 'controlled execution', 'path': '/api/v1/test', **spec}))
        command = [sys.executable, str(SCRIPT), '--skill', 'tikin-rest-api', '--no-global-config',
                   'request', '--request-file', str(path)]
        if record:
            command += ['--record', str(record)]
        if approval:
            command += ['--regression-approval', str(approval)]
        return command

    def request(self, spec, record=None, approval=None):
        run = subprocess.run(self.command(spec, record, approval), env=self.env, cwd=self.root,
                             text=True, capture_output=True, timeout=15)
        self.assertTrue(run.stdout.strip(), run.stderr)
        return json.loads(run.stdout)

    def approval(self, price='0.30', category='paid', side_effects=False):
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        targets = {'schema': 'tikin.regression-binding.v1', 'environment': 'test',
                   'client_base_url': self.base, 'new_api_base': 'http://127.0.0.1:5010',
                   'return_route': 'http://127.0.0.1:5020', 'upstream_base': 'https://upstream.invalid',
                   'upstream_token_sha256': 'b' * 64, 'catalog_sha256': 'c' * 64,
                   'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                   'test_token_sha256': hashlib.sha256(self.env['TIKIN_API_KEY'].encode()).hexdigest()}
        binding = self.root / 'binding.json'
        binding.write_text(json.dumps(targets))
        self.guard_binding = hashlib.sha256(binding.read_bytes()).hexdigest()
        self.service_binding = targets
        proof = self.root / 'target-proof.json'
        proof.write_text(json.dumps({'schema': 'tikin.regression-route-proof.v1', 'binding_sha256': self.guard_binding,
                                     'environment': 'test', 'expires_at': time.time() + 600,
                                     'route_verified': True, 'price_evidence_sha256': 'a' * 64}))
        approval = self.root / 'approval.json'
        ledger = self.root / 'ledger.json'
        limits = {'paid_attempts': 40, 'paid_usd': '0.50', 'zero_attempts': 40, 'local_attempts': 8}
        value = {'schema_version': 1, 'campaign_id': 'synthetic-spec6', 'ledger_path': str(ledger),
                 'binding_path': str(binding), 'binding_sha256': self.guard_binding, 'expires_at': time.time() + 600, 'limits': limits,
                 'proof_path': str(proof), 'proof_sha256': hashlib.sha256(proof.read_bytes()).hexdigest(),
                 'requests': {digest(['GET', self.base + '/api/v1/test', None]):
                              {'category': category, 'price_usd': price, 'max_units': 1, 'upstream_attempts': 1,
                               'side_effects': side_effects, 'price_evidence_sha256': 'a' * 64}}}
        approval.write_text(json.dumps(value))
        ledger.write_text(json.dumps({'schema_version': 1, 'campaign_id': value['campaign_id'],
                                      'ledger_path': str(ledger), 'binding_sha256': self.guard_binding,
                                      'limits': limits, 'approval_sha256s': [hashlib.sha256(approval.read_bytes()).hexdigest()],
                                      'reservations': [], 'not_before': 0}))
        return approval, ledger

    def test_side_effecting_get_keeps_unknown_submission_even_if_relabelled_as_read(self):
        self.responses = [(503, {}, {'error': {'code': 'unavailable'}})]
        first = self.request({'side_effects': True})
        self.assertEqual(first['status'], 'submission_unknown')
        self.responses = [(200, {}, {'data': []})]
        repeated = self.request({'side_effects': False}, first['record'])
        self.assertEqual(repeated['status'], 'submission_unknown')
        self.assertEqual(len(self.calls), 1)

    def test_retry_after_is_not_shortened_and_survives_another_process(self):
        self.responses = [(429, {'Retry-After': '3600'}, {'error': {'code': 'rate_limited'}})]
        spec = {'side_effects': False, 'time_budget_seconds': 1}
        first = self.request(spec)
        self.assertEqual(first['status'], 'cooldown')
        self.assertGreater(first['retry_after_seconds'], 3500)
        self.assertEqual(first['response_headers']['retry-after'], '3600')
        again = self.request(spec, first['record'])
        self.assertEqual(again['status'], 'cooldown')
        self.assertEqual(len(self.calls), 1)

    def test_http_date_retry_after_is_preserved_without_early_send(self):
        date = format_datetime(datetime.now(timezone.utc) + timedelta(minutes=5), usegmt=True)
        self.responses = [(429, {'Retry-After': date}, {'error': {'code': 'rate_limited'}})]
        result = self.request({'side_effects': False, 'time_budget_seconds': 0.1})
        self.assertEqual(result['status'], 'cooldown')
        self.assertGreater(result['retry_after_seconds'], 290)
        self.assertEqual(result['response_headers']['retry-after'], date)
        self.assertEqual(len(self.calls), 1)

    def test_paid_attempt_count_stops_even_when_dollars_remain(self):
        approval, ledger = self.approval(price='0.001')
        state = json.loads(ledger.read_text())
        state['reservations'] = [{'id': 'prior', 'category': 'paid', 'attempts': 40,
                                   'reserved_usd': '0.040', 'request_sha256': 'prior', 'outcome': 'received'}]
        ledger.write_text(json.dumps(state))
        result = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(result['reason'], 'budget_exhausted')
        self.assertEqual(self.calls, [])

    def test_unclassified_get_is_not_assumed_to_be_replay_safe(self):
        self.responses = [(503, {}, {'error': {'code': 'unavailable'}})]
        first = self.request({})
        self.assertEqual(first['status'], 'submission_unknown')
        self.assertEqual(len(self.calls), 1)

    def test_regression_budget_is_shared_across_records_and_processes(self):
        approval, ledger = self.approval()
        first = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(first['status'], 'ok')
        second = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(second['status'], 'regression_blocked')
        self.assertEqual(second['reason'], 'budget_exhausted')
        self.assertEqual(len(self.calls), 1)
        entries = json.loads(ledger.read_text())['reservations']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['reserved_usd'], '0.30')

    def test_regression_rejects_wrong_target_or_identity_before_sending(self):
        approval, _ = self.approval()
        self.env['TIKIN_BASE_URL'] = 'https://console.tikin.net'
        self.assertEqual(self.request({'side_effects': False}, approval=approval)['reason'], 'wrong_target')
        self.env['TIKIN_BASE_URL'] = self.base
        self.env['TIKIN_API_KEY'] = 'another-synthetic-identity'
        self.assertEqual(self.request({'side_effects': False}, approval=approval)['reason'], 'wrong_identity')
        self.assertEqual(self.calls, [])

    def test_missing_ledger_does_not_create_a_new_allowance(self):
        approval, ledger = self.approval()
        ledger.unlink()
        result = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(result['status'], 'local_error')
        self.assertFalse(ledger.exists())
        self.assertEqual(self.calls, [])

    def test_zero_and_local_checks_have_independent_persistent_limits(self):
        for category, cap in [('zero', 40), ('local', 8)]:
            with self.subTest(category=category):
                approval, ledger = self.approval(price='0', category=category)
                a = json.loads(approval.read_text())
                if category == 'local':
                    next(iter(a['requests'].values()))['upstream_forbidden'] = True
                approval.write_text(json.dumps(a))
                state = json.loads(ledger.read_text())
                state['approval_sha256s'] = [hashlib.sha256(approval.read_bytes()).hexdigest()]
                state['reservations'] = [{'id': 'prior', 'category': category, 'attempts': cap,
                                           'reserved_usd': '0', 'request_sha256': 'prior', 'outcome': 'received'}]
                ledger.write_text(json.dumps(state))
                result = self.request({'side_effects': False}, approval=approval)
                self.assertEqual(result['reason'], 'budget_exhausted')
        self.assertEqual(self.calls, [])

    def test_record_cannot_drop_the_regression_binding_on_resume(self):
        approval, _ = self.approval(price='0.001')
        first = self.request({'side_effects': False}, approval=approval)
        result = self.request({'side_effects': False}, first['record'])
        self.assertEqual(result['reason'], 'record_regression_mismatch')
        self.assertEqual(len(self.calls), 1)

    def test_interrupted_send_keeps_reservation_and_blocks_replacement_process(self):
        approval, ledger = self.approval(price='0.001')
        self.release.clear()
        process = subprocess.Popen(self.command({'side_effects': False}, approval=approval),
                                   env=self.env, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(self.received.wait(5))
            state = json.loads(ledger.read_text())
            self.assertEqual(state['reservations'][0]['outcome'], 'reserved')
        finally:
            process.kill()
            process.communicate(timeout=5)
            self.release.set()
        again = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(again['reason'], 'unresolved_attempt')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(json.loads(ledger.read_text())['reservations']), 1)

    def test_concurrent_processes_cannot_double_spend_the_remaining_budget(self):
        approval, ledger = self.approval()
        command = self.command({'side_effects': False}, approval=approval)
        processes = [subprocess.Popen(command, env=self.env, cwd=self.root, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [json.loads(process.communicate(timeout=10)[0]) for process in processes]
        self.assertEqual(sum(result['status'] == 'ok' for result in outputs), 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(json.loads(ledger.read_text())['reservations']), 1)

    def test_unproven_return_is_not_automatically_repeated(self):
        approval, ledger = self.approval(price='0.001')
        self.proof_override = {**self.service_binding, 'return_route': 'http://wrong.invalid', 'binding_sha256': self.guard_binding}
        result = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(result['reason'], 'server_binding_unproven')
        self.assertEqual(self.calls, [])
        self.assertEqual(json.loads(ledger.read_text())['reservations'], [])

    def test_paid_timeout_keeps_cost_and_never_retries_even_for_read(self):
        approval, ledger = self.approval(price='0.001')
        self.release.clear()
        try:
            result = self.request({'side_effects': False, 'timeout_seconds': 0.1}, approval=approval)
        finally:
            self.release.set()
        self.assertEqual(result['status'], 'submission_unknown')
        entries = json.loads(ledger.read_text())['reservations']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['reserved_usd'], '0.001')
        self.assertEqual(entries[0]['outcome'], 'unknown')
        self.assertEqual(len(self.calls), 1)

    def test_every_automatic_retry_reserves_and_stops_at_dollar_limit(self):
        approval, ledger = self.approval(price='0.20')
        self.responses = [(503, {'Retry-After': '0'}, {'error': {'code': 'unavailable'}})]
        result = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(result['reason'], 'budget_exhausted')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(json.loads(ledger.read_text())['reservations']), 2)

    def test_unknown_price_and_expired_proof_never_send(self):
        for price in ['NaN', '-0.1', None]:
            with self.subTest(price=price):
                approval, _ = self.approval(price=price)
                result = self.request({'side_effects': False}, approval=approval)
                self.assertEqual(result['reason'], 'unverified_price')
        approval, ledger = self.approval()
        proof = self.root / 'target-proof.json'
        value = json.loads(proof.read_text())
        value['expires_at'] = time.time() - 1
        proof.write_text(json.dumps(value))
        a = json.loads(approval.read_text())
        a['proof_sha256'] = hashlib.sha256(proof.read_bytes()).hexdigest()
        approval.write_text(json.dumps(a))
        result = self.request({'side_effects': False}, approval=approval)
        self.assertEqual(result['reason'], 'proof_expired_or_unverified')
        self.assertEqual(self.calls, [])

    def test_non_json_error_does_not_leak_supplier_text(self):
        self.responses = [(502, {}, b'<h1>contact supplier.invalid:8123 secret=hidden</h1>')]
        result = self.request({'side_effects': False, 'time_budget_seconds': 0.1})
        self.assertEqual(result['response']['error']['code'], 'invalid_response')
        self.assertNotIn('supplier.invalid', json.dumps(result))

    def test_caption_job_waits_queries_and_reuses_known_creation(self):
        create_path = '/api/v1/youtube/web_v2/get_video_captions'
        query_path = '/api/v1/youtube/web_v2/get_video_captions_result'
        self.responses = [(200, {}, {'code': 200, 'data': {'status': 'processing', 'job_id': 'job-12345', 'captions': []}}),
                          (200, {}, {'data': {'status': 'queued', 'job_id': 'job-12345'}}),
                          (200, {}, {'data': {'status': 'ready', 'job_id': 'job-12345', 'captions': []}}),
                          (200, {}, {'data': {'status': 'completed', 'job_id': 'job-12345', 'content': 'final captions'}})]
        creation = self.request({'path': create_path, 'query': {'video_id': 'synthetic'}, 'side_effects': False})
        self.assertEqual(creation['status'], 'waiting')
        record = creation['record']
        queued = self.request({'path': query_path, 'query': {'job_id': 'job-12345'}}, record)
        self.assertEqual(queued['status'], 'waiting')
        ready = self.request({'path': query_path, 'query': {'job_id': 'job-12345'}}, record)
        self.assertEqual(ready['status'], 'waiting')
        complete = self.request({'path': query_path, 'query': {'job_id': 'job-12345'}}, record)
        self.assertEqual(complete['status'], 'ok')
        self.assertEqual(complete['response']['data']['content'], 'final captions')
        repeated = self.request({'path': create_path, 'query': {'video_id': 'synthetic'}, 'side_effects': False}, record)
        self.assertEqual(repeated['status'], 'task_exists')
        self.assertEqual(repeated['task']['job_id'], 'job-12345')
        self.assertEqual(len(self.calls), 4)

    def test_cookie_body_is_sent_exactly_but_not_saved_in_ordinary_evidence(self):
        self.responses = [(422, {}, {'error': {'code': 'invalid_input'}})]
        cookie = 'sessionid=synthetic-private-cookie; uid=synthetic-user'
        result = self.request({'method': 'POST', 'path': '/api/v1/tiktok/ads/get_location_list', 'body': cookie})
        self.assertEqual(json.loads(self.calls[0][2]), cookie)
        self.assertNotIn(cookie, Path(result['record']).read_text())
        self.assertNotIn(cookie, Path(result['feedback']['error_report']).read_text())

    def test_wire_preserves_object_array_string_empty_body_and_repeated_queries(self):
        examples = [{'nested': {'message': 'value'}, 'number': 2}, ['a', 'b'], 'raw-json-string', None]
        for body in examples:
            spec = {'method': 'POST', 'query': {'item': ['one', 'two'], 'empty': ''}}
            if body is not None:
                spec['body'] = body
            result = self.request(spec)
            self.assertEqual(result['status'], 'ok')
            method, path, sent = self.calls[-1]
            self.assertEqual(method, 'POST')
            self.assertEqual(path, '/api/v1/test?item=one&item=two&empty=')
            self.assertEqual(json.loads(sent) if sent else None, body)

    def test_all_thirteen_migrated_post_requests_reach_the_controlled_boundary(self):
        refs = ROOT / 'skills/tikin-endpoint-discovery/references'
        document = json.loads((refs / 'openapi.json').read_text())
        rows = json.loads((refs / 'request-changes.json').read_text())['method_migrations']
        self.assertEqual(len(rows), 13)
        for row in rows:
            schema = document['paths'][row['path']]['post']['requestBody']['content']['application/json']['schema']
            if '$ref' in schema:
                target = document
                for part in schema['$ref'][2:].split('/'):
                    target = target[part]
                schema = {**target, **{key: value for key, value in schema.items() if key != '$ref'}}
            body = ('sessionid=synthetic-cookie' if schema['type'] == 'string'
                    else {name: 'synthetic-' + name for name in schema.get('required', [])})
            result = self.request({'method': row['new_method'], 'path': row['path'], 'body': body})
            self.assertEqual(result['status'], 'ok')
            method, path, sent = self.calls[-1]
            self.assertEqual((method, path), ('POST', row['path']))
            self.assertEqual(json.loads(sent), body)
        self.assertEqual(len(self.calls), 13)

    def test_caption_query_budget_survives_process_replacement(self):
        path = '/api/v1/youtube/web_v2/get_video_captions_result'
        self.responses = [(200, {}, {'data': {'job_id': 'job-12345', 'status': 'queued'}})]
        record = None
        for _ in range(10):
            result = self.request({'path': path, 'query': {'job_id': 'job-12345'}}, record)
            self.assertEqual(result['status'], 'waiting')
            record = result['record']
        blocked = self.request({'path': path, 'query': {'job_id': 'job-12345'}}, record)
        self.assertEqual(blocked['status'], 'poll_budget_exhausted')
        self.assertEqual(blocked['poll_attempts'], 10)
        self.assertEqual(len(self.calls), 10)

    def test_caption_terminal_failure_preserves_original_job_and_error_record(self):
        self.responses = [(200, {}, {'data': {'job_id': 'job-12345', 'status': 'failed',
                                            'error': {'code': 'caption_failed'}}})]
        result = self.request({'path': '/api/v1/youtube/web_v2/get_video_captions_result', 'query': {'job_id': 'job-12345'}})
        self.assertEqual(result['status'], 'remote_failed')
        self.assertEqual(result['task']['job_id'], 'job-12345')
        self.assertTrue(Path(result['feedback']['error_report']).is_file())
        self.assertEqual(len(self.calls), 1)

    def test_failed_response_hides_internal_details_but_preserves_nested_business_urls(self):
        signed = 'https://media.invalid/file?signature=download-value&token=business-token'
        self.responses = [(502, {}, {'error': {'code': 'service_unavailable',
                            'message': 'Call http://supplier.invalid:8200/support?secret=private for help'},
                            'data': {'media_url': signed, 'token': 'page-cursor', 'message': 'business text'}})]
        result = self.request({'side_effects': False, 'time_budget_seconds': 0.1})
        text = json.dumps(result)
        self.assertNotIn('supplier.invalid', text)
        self.assertNotIn('8200', text)
        self.assertEqual(result['response']['data']['media_url'], signed)
        self.assertEqual(result['response']['data']['token'], 'page-cursor')
        self.assertEqual(result['response']['data']['message'], 'business text')


if __name__ == '__main__':
    unittest.main()
