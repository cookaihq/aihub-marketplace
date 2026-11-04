"""Public CLI -> controlled HTTP proxy -> media, without Tikin business services."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/tikin-setup/scripts/tikin-config'


class ProxyDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tikin-media-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cfg = {}
        self.configure()
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
                        '-keyout', str(self.root / 'key.pem'), '-out', str(self.root / 'cert.pem')],
                       capture_output=True, check=True, timeout=10)
        self.peer = subprocess.Popen([sys.executable, str(Path(__file__).with_name('media_peer.py')), str(self.root)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_peer)
        until = time.monotonic() + 5
        while not (self.root / 'ports.json').exists() and self.peer.poll() is None and time.monotonic() < until:
            time.sleep(0.02)
        self.assertTrue((self.root / 'ports.json').exists(), 'controlled peer did not start')
        self.ports = json.loads((self.root / 'ports.json').read_text())
        self.base = f'http://127.0.0.1:{self.ports["http"]}'
        self.env = {**os.environ, 'TIKIN_API_KEY': 'synthetic-media-key', 'TIKIN_BASE_URL': self.base,
                    'SSL_CERT_FILE': str(self.root / 'cert.pem'), 'NO_PROXY': '*'}
        self.request_file = self.root / 'request.json'
        self.response_file = self.root / 'response.json'
        self.output = self.root / 'downloads'

    def stop_peer(self):
        if self.peer.poll() is None:
            self.peer.terminate()
        self.peer.wait(timeout=5)

    def configure(self, **kwargs):
        self.cfg.update(kwargs)
        (self.root / 'config.json').write_text(json.dumps(self.cfg))

    def metadata(self, verify=True):
        self.request_file.write_text(json.dumps({'method': 'POST', 'path': '/api/v1/youtube/web_v2/get_video_streams_v3',
            'original_request': 'download both controlled streams',
            'body': {'video_id': 'abcdefghijk', 'proxy_url': f'http://fixture-user:proxy%3Ap%40ss@127.0.0.1:{self.ports["proxy"]}',
                     'itags': ['137', '140'], 'verify_download': verify}}))
        result = subprocess.run([sys.executable, str(SCRIPT), '--no-global-config', 'request',
                                 '--request-file', str(self.request_file), '--task-name', 'download-streams'], env=self.env, cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.response_file.write_text(result.stdout)
        return json.loads(result.stdout)

    def command(self):
        return [sys.executable, str(SCRIPT), '--no-global-config', 'download',
                '--request-file', str(self.request_file), '--response-file', str(self.response_file),
                '--output-dir', str(self.output), '--exit-check-url', self.base + '/exit']

    def download(self):
        result = subprocess.run(self.command(), env=self.env, cwd=self.root, capture_output=True, text=True, timeout=12)
        self.assertTrue(result.stdout.strip(), result.stderr)
        self.assertNotIn('proxy:p@ss', result.stdout + result.stderr)
        self.assertNotIn('synthetic-signature', result.stdout + result.stderr)
        return json.loads(result.stdout)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]

    def test_both_streams_are_downloaded_through_same_authenticated_proxy(self):
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['streams']), 2)
        for item in result['streams']:
            self.assertTrue(item['complete_transfer_verified'])
            self.assertEqual(Path(item['file']).stat().st_size, item['bytes'])
        origin = [row for row in self.calls() if row['peer'] == 'origin']
        self.assertEqual(sum(row['path'].startswith('/media/') for row in origin), 2)
        self.assertTrue(all(not row['headers'].get('Proxy-Authorization') for row in origin))
        self.assertTrue(all(not row['headers'].get('Cookie') for row in origin if row['path'] == '/exit'))
        self.assertEqual(sum(row['peer'] == 'api' for row in self.calls()), 1)

    def test_https_connect_keeps_proxy_credentials_out_of_the_origin(self):
        self.configure(tls=True)
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(sum(row['peer'] == 'proxy' and row['method'] == 'CONNECT' for row in self.calls()), 2)
        self.assertTrue(all(not row['headers'].get('Proxy-Authorization') for row in self.calls() if row['peer'] == 'origin'))

    def test_a_different_proxy_cannot_be_substituted_into_the_original_request(self):
        self.metadata()
        request = json.loads(self.request_file.read_text())
        request['body']['proxy_url'] = 'http://other:secret@127.0.0.1:1'
        self.request_file.write_text(json.dumps(request))
        result = self.download()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'request_fingerprint_mismatch')
        self.assertFalse(any(row['peer'] == 'proxy' for row in self.calls()))

    def test_false_metadata_verification_does_not_download(self):
        self.configure(verified=False)
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'metadata_verification_failed')
        self.assertTrue(result['metadata_success'])
        self.assertFalse(any(row['peer'] == 'proxy' for row in self.calls()))

    def test_changed_exit_stops_before_the_second_stream_and_keeps_the_first(self):
        self.configure(exit_ips=['203.0.113.10', '203.0.113.10', '203.0.113.11'])
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['reason'], 'proxy_exit_changed')
        self.assertTrue(result['streams'][0]['complete_transfer_verified'])
        self.assertTrue(Path(result['streams'][0]['file']).is_file())
        self.assertFalse(any('/media/140' in row['path'] for row in self.calls()))

    def test_partial_download_is_preserved_and_resume_reuses_the_finished_stream(self):
        self.configure(mode='partial')
        self.metadata()
        first = self.download()
        self.assertEqual(first['status'], 'partial')
        partial = Path(first['streams'][1]['file'])
        partial_bytes = partial.read_bytes()
        self.assertTrue(partial_bytes)
        completed = Path(first['streams'][0]['file'])
        first_stat = completed.stat()
        self.configure(mode='ok')
        self.env.pop('TIKIN_API_KEY')
        self.env.pop('TIKIN_BASE_URL')
        resumed = self.download()
        self.assertEqual(resumed['status'], 'complete')
        self.assertEqual(len(resumed['streams']), 2)
        self.assertEqual(partial.read_bytes(), partial_bytes)
        self.assertEqual(completed.stat().st_mtime_ns, first_stat.st_mtime_ns)
        calls = self.calls()
        self.assertEqual(sum(row['peer'] == 'origin' and '/media/137' in row['path'] for row in calls), 1)
        self.assertEqual(sum(row['peer'] == 'api' for row in calls), 1)

    def test_expired_urls_are_not_sent_to_the_proxy(self):
        self.configure(expires_in=-1)
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'media_url_expired')
        self.assertFalse(any(row['peer'] == 'proxy' for row in self.calls()))

    def test_html_with_media_mime_is_not_a_complete_stream(self):
        self.configure(mode='html')
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['reason'], 'invalid_media_container')
        self.assertFalse(result['complete_transfer_verified'])
        self.assertTrue(Path(result['streams'][1]['file']).is_file())

    def test_redirects_never_forward_media_headers_to_another_target(self):
        self.configure(mode='redirect')
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['reason'], 'redirect_refused')
        self.assertFalse(any('/leak' in row['path'] for row in self.calls()))

    def test_proxy_failure_never_falls_back_to_direct_even_with_no_proxy_star(self):
        self.configure(proxy_failure=True)
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(any(row['peer'] == 'origin' for row in self.calls()))
        self.assertEqual(sum(row['peer'] == 'api' for row in self.calls()), 1)

    def test_stream_cannot_finish_after_its_expiry(self):
        self.configure(mode='slow', expires_in=0.7)
        self.metadata()
        start = time.monotonic()
        result = self.download()
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['complete_transfer_verified'])

    def test_killed_process_leaves_partial_state_and_resumes_without_new_metadata(self):
        self.configure(mode='interrupt')
        self.metadata()
        process = subprocess.Popen(self.command(), env=self.env, cwd=self.root,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            until = time.monotonic() + 5
            partial = None
            while time.monotonic() < until:
                candidates = list(self.output.glob('*/stream-140-*.part'))
                if candidates and candidates[0].stat().st_size:
                    partial = candidates[0]
                    break
                time.sleep(0.02)
            self.assertIsNotNone(partial, 'controlled partial was not written')
        finally:
            process.terminate()
            process.wait(timeout=5)
        saved = json.loads(next(self.output.glob('*/download.json')).read_text())
        self.assertEqual(saved['status'], 'partial')
        content = partial.read_bytes()
        self.configure(mode='ok')
        result = self.download()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(partial.read_bytes(), content)
        self.assertEqual(len(result['streams']), 2)
        self.assertEqual(sum(row['peer'] == 'api' for row in self.calls()), 1)

    def test_completed_files_are_reused_but_never_overwritten_after_local_edits(self):
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'complete')
        count = len(self.calls())
        self.assertEqual(self.download()['status'], 'complete')
        self.assertEqual(len(self.calls()), count)
        file = Path(result['streams'][0]['file'])
        file.write_bytes(b'local modification')
        changed = self.download()
        self.assertEqual(changed['status'], 'blocked')
        self.assertEqual(changed['reason'], 'existing_media_changed')
        self.assertEqual(file.read_bytes(), b'local modification')
        self.assertEqual(len(self.calls()), count)

    def test_exit_change_after_receiving_bytes_keeps_them_partial(self):
        self.configure(exit_ips=['203.0.113.10', '203.0.113.11'])
        self.metadata()
        result = self.download()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['reason'], 'proxy_exit_changed')
        self.assertFalse(result['streams'][0]['complete_transfer_verified'])
        self.assertGreater(Path(result['streams'][0]['file']).stat().st_size, 0)
        self.assertFalse(any('/media/140' in row['path'] for row in self.calls()))

    def test_missing_sampling_can_be_followed_by_a_complete_download(self):
        self.configure(verified=None)
        self.metadata(verify=False)
        result = self.download()
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['complete_transfer_verified'])

    def test_invalid_metadata_and_unsafe_headers_are_rejected_without_network(self):
        original = self.metadata()
        changes = [({'video_id': 'wrong-video'}, 'video_identity_mismatch'),
                   ({'proxy_exit_verified': False}, 'proxy_verification_missing'),
                   ({'streams': original['response']['data']['streams'][:1]}, 'selected_streams_missing')]
        for fields, reason in changes:
            with self.subTest(reason=reason):
                value = json.loads(json.dumps(original))
                value['response']['data'].update(fields)
                self.response_file.write_text(json.dumps(value))
                result = self.download()
                self.assertEqual(result['reason'], reason)
                self.assertEqual(result['status'], 'blocked')
        original['response']['data']['streams'][0]['download_headers']['Proxy-Authorization'] = 'secret-for-another-proxy'
        self.response_file.write_text(json.dumps(original))
        self.assertEqual(self.download()['reason'], 'unsafe_download_headers')
        self.assertFalse(any(row['peer'] == 'proxy' for row in self.calls()))

    def test_invalid_tls_certificate_is_not_bypassed(self):
        self.configure(tls=True)
        self.metadata()
        self.env.pop('SSL_CERT_FILE')
        result = self.download()
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['complete_transfer_verified'])
        self.assertFalse(any(row['peer'] == 'origin' and '/media/' in row['path'] for row in self.calls()))

    def test_returned_identity_encoding_header_is_preserved(self):
        response = self.metadata()
        for stream in response['response']['data']['streams']:
            stream['download_headers']['accept-encoding'] = 'identity'
        self.response_file.write_text(json.dumps(response))
        self.assertEqual(self.download()['status'], 'complete')
        media = [row for row in self.calls() if row['peer'] == 'origin' and '/media/' in row['path']]
        self.assertTrue(all(row['headers'].get('accept-encoding') == 'identity' for row in media))

    def test_media_retry_after_blocks_network_when_resuming_in_a_new_process(self):
        self.configure(video_mode='limited', retry_after='120')
        self.metadata()
        first = self.download()
        self.assertEqual(first['status'], 'partial')
        count = len(self.calls())
        resumed = self.download()
        self.assertEqual(resumed['status'], 'cooldown')
        self.assertGreater(resumed['retry_after_seconds'], 100)
        self.assertEqual(resumed['last_http_status'], 429)
        self.assertEqual(len(self.calls()), count)


if __name__ == '__main__':
    unittest.main()
