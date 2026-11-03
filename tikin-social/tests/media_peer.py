"""Controlled API, media and HTTP proxy processes for the public download tests."""
import base64
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import select
import socket
import ssl
import struct
import sys
import threading
import time
from urllib.parse import urlsplit


def box(kind, data=b''):
    return struct.pack('>I', len(data) + 8) + kind + data


MEDIA = box(b'ftyp', b'isom\0\0\0\0isom') + box(b'moov') + box(b'mdat', b'\0' * 131072)


def main():
    root = Path(sys.argv[1])
    ports = {}
    lock = threading.Lock()
    exit_checks = 0

    def config():
        return json.loads((root / 'config.json').read_text())

    def log(value):
        with lock, (root / 'calls.jsonl').open('a') as handle:
            handle.write(json.dumps(value) + '\n')

    class Origin(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, payload, headers=None):
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            body = json.loads(raw)
            cfg = config()
            log({'peer': 'api', 'path': self.path})
            scheme = 'https' if cfg.get('tls') else 'http'
            port = ports[scheme]
            streams = [{'itag': itag, 'url': f'{scheme}://127.0.0.1:{port}/media/{itag}?sig=synthetic-signature',
                        'download_headers': {'X-Media-Required': 'fixture-header', 'Cookie': 'synthetic-media-cookie'},
                        'expires_at': time.time() + cfg.get('expires_in', 120),
                        'verified': cfg.get('verified', True),
                        'verification': {'ok': cfg.get('verified', True), 'scope': 'sampled_ranges',
                                         'full_file_verified': False},
                        'content_length': len(b'<html>access denied</html>') if itag == '140' and cfg.get('mode') == 'html' else len(MEDIA)}
                       for itag in body.get('itags', ['137', '140'])]
            data = {'video_id': body['video_id'], 'same_proxy_required': True,
                    'proxy_exit_ip': '203.0.113.10', 'proxy_exit_verified': True,
                    'download_verification_requested': body.get('verify_download', False),
                    'all_selected_streams_verified': cfg.get('verified', True), 'streams': streams}
            self.reply(200, json.dumps({'code': 200, 'data': data}).encode(), {'Content-Type': 'application/json'})

        def do_GET(self):
            nonlocal exit_checks
            cfg = config()
            log({'peer': 'origin', 'path': self.path, 'headers': dict(self.headers)})
            if self.path == '/exit':
                ips = cfg.get('exit_ips', ['203.0.113.10'])
                ip = ips[min(exit_checks, len(ips) - 1)]
                exit_checks += 1
                self.reply(200, json.dumps({'ip': ip}).encode(), {'Content-Type': 'application/json'})
                return
            if self.headers.get('X-Media-Required') != 'fixture-header':
                self.reply(403, b'headers missing')
                return
            mode = cfg.get('mode', 'ok') if self.path.startswith('/media/140') else cfg.get('video_mode', 'ok')
            if mode == 'limited':
                self.reply(429, b'', {'Retry-After': cfg.get('retry_after', '120')})
                return
            if mode == 'redirect':
                self.reply(302, b'', {'Location': f'http://127.0.0.1:{ports["http"]}/leak'})
                return
            payload = b'<html>access denied</html>' if mode == 'html' else MEDIA
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4' if '/137' in self.path else 'audio/mp4')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            if mode == 'partial':
                self.wfile.write(payload[:16384])
                self.wfile.flush()
                self.close_connection = True
                return
            if mode in ('slow', 'interrupt'):
                self.wfile.write(payload[:16384])
                self.wfile.flush()
                time.sleep(2 if mode == 'slow' else 15)
                payload = payload[16384:]
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            log({'peer': 'proxy', 'method': self.command, 'path': self.path,
                 'auth': self.headers.get('Proxy-Authorization')})
            expected = 'Basic ' + base64.b64encode(b'fixture-user:proxy:p@ss').decode()
            if self.headers.get('Proxy-Authorization') != expected:
                self.send_error(407)
                return False
            if config().get('proxy_failure'):
                self.send_error(502)
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            target = urlsplit(self.path)
            assert target.hostname == '127.0.0.1' and target.port in ports.values()
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=20)
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in ('proxy-authorization', 'proxy-connection')}
            connection.request('GET', target.path + ('?' + target.query if target.query else ''), headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in ('server', 'date'):
                    self.send_header(key, value)
            self.end_headers()
            try:
                while chunk := response.read1(8192):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()

        def do_CONNECT(self):
            if not self.allowed():
                return
            host, port = self.path.rsplit(':', 1)
            assert host == '127.0.0.1' and int(port) == ports['https']
            with socket.create_connection((host, int(port)), timeout=20) as upstream:
                self.send_response(200)
                self.end_headers()
                sockets = [self.connection, upstream]
                until = time.monotonic() + 20
                while time.monotonic() < until:
                    ready, _, _ = select.select(sockets, [], [], 1)
                    for source in ready:
                        try:
                            data = source.recv(65536)
                            if not data:
                                return
                            (upstream if source is self.connection else self.connection).sendall(data)
                        except OSError:
                            return

    servers = [ThreadingHTTPServer(('127.0.0.1', 0), Origin) for _ in range(2)]
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(root / 'cert.pem', root / 'key.pem')
    servers[1].socket = tls.wrap_socket(servers[1].socket, server_side=True)
    servers.append(ThreadingHTTPServer(('127.0.0.1', 0), Proxy))
    ports.update(zip(('http', 'https', 'proxy'), (server.server_port for server in servers)))
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    (root / 'ports.json').write_text(json.dumps(ports))
    threading.Event().wait()


if __name__ == '__main__':
    main()
