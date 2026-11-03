"""Download existing stream results; this module never sends a Tikin API request."""
import base64
from contextlib import contextmanager
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import struct
import threading
import time
from typing import Any, Iterator
from urllib.parse import SplitResult, unquote, urlsplit
import uuid

from request_reporting import atomic_write, record_lock, restrict_private
from tikin_request import request_fingerprint, retry_after

STREAMS_PATH = '/api/v1/youtube/web_v2/get_video_streams_v3'
MAX_STREAM_SECONDS = 300


class DownloadError(Exception):
    """Fixed, credential-free reason plus the shared transport's cooldown evidence."""
    def __init__(self, reason: str, not_before: float | None = None, http_status: int | None = None) -> None:
        super().__init__(reason)
        self.not_before = not_before
        self.http_status = http_status


def require(condition: Any, reason: str) -> None:
    if not condition:
        raise DownloadError(reason)


def parsed_url(value: Any, proxy: bool = False) -> SplitResult:
    if not isinstance(value, str) or re.search(r'[\s\x00-\x1f\x7f]', value):
        raise DownloadError('invalid_url')
    parsed = urlsplit(value)
    require(parsed.scheme in (('http',) if proxy else ('http', 'https')) and parsed.hostname and not parsed.fragment,
            'invalid_proxy' if proxy else 'invalid_url')
    if proxy:
        require(parsed.port and not parsed.query and parsed.path in ('', '/'), 'invalid_proxy')
    else:
        require(parsed.username is None and parsed.password is None, 'url_credentials_not_allowed')
        _ = parsed.port  # Validate a malformed port before opening a connection.
    return parsed


def seconds_left(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'download_deadline_exceeded')
    return remaining


class Proxy:
    def __init__(self, value: str):
        self.address = parsed_url(value, proxy=True)
        self.auth = None
        if self.address.username is not None:
            credentials = unquote(self.address.username) + ':' + unquote(self.address.password or '')
            self.auth = 'Basic ' + base64.b64encode(credentials.encode()).decode()

    @contextmanager
    def open(self, url: str, headers: dict[str, str], deadline: float) -> Iterator[http.client.HTTPResponse]:
        target = parsed_url(url)
        timeout = min(30, seconds_left(deadline))
        assert self.address.hostname is not None and target.hostname is not None
        request_headers = dict(headers)
        connection: http.client.HTTPConnection
        if target.scheme == 'https':
            connection = http.client.HTTPSConnection(self.address.hostname, self.address.port,
                                                     timeout=timeout, context=ssl.create_default_context())
            tunnel_headers = {'Proxy-Authorization': self.auth} if self.auth else {}
            connection.set_tunnel(target.hostname, target.port or 443, headers=tunnel_headers)
            request_target = target.path or '/'
            if target.query:
                request_target += '?' + target.query
        else:
            connection = http.client.HTTPConnection(self.address.hostname, self.address.port, timeout=timeout)
            request_target = url  # Preserve signed path/query bytes exactly.
            if self.auth:
                request_headers['Proxy-Authorization'] = self.auth

        active_socket = None

        def interrupt() -> None:
            sock = active_socket or connection.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()

        timer = threading.Timer(seconds_left(deadline), interrupt)
        timer.daemon = True
        timer.start()
        response = None
        try:
            connection.request('GET', request_target, headers=request_headers)
            active_socket = connection.sock
            seconds_left(deadline)
            response = connection.getresponse()
            if response.status != 200:
                delay = retry_after({'retry-after': response.getheader('Retry-After')})
                raise DownloadError('redirect_refused' if 300 <= response.status < 400 else 'media_http_failure',
                                    time.time() + delay if delay is not None else None, response.status)
            yield response
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()


def exit_check(proxy: Proxy, url: str, expected: str, deadline: float) -> None:
    with proxy.open(url, {'Accept': 'application/json'}, min(deadline, time.monotonic() + 15)) as response:
        require(response.getheader('Content-Type', '').split(';')[0].strip().lower() == 'application/json',
                'exit_check_not_json')
        payload = response.read(8193)
        require(len(payload) <= 8192, 'exit_check_too_large')
        data = json.loads(payload)
        require(isinstance(data, dict) and isinstance(data.get('ip'), str), 'exit_check_missing_ip')
        require(ipaddress.ip_address(data['ip']) == ipaddress.ip_address(expected), 'proxy_exit_changed')


def headers_for(stream: dict[str, Any]) -> dict[str, str]:
    headers = stream.get('download_headers')
    if not isinstance(headers, dict):
        raise DownloadError('missing_download_headers')
    forbidden = {'host', 'proxy-authorization', 'proxy-connection', 'connection', 'transfer-encoding',
                 'content-length', 'range', 'if-range', 'upgrade', 'te', 'trailer'}
    for key, value in headers.items():
        require(isinstance(key, str) and re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
                and key.lower() not in forbidden and isinstance(value, str)
                and not re.search(r'[\r\n\x00]', value), 'unsafe_download_headers')
        if key.lower() == 'accept-encoding':
            require(value.strip().lower() == 'identity', 'unsafe_download_headers')
    return headers if any(key.lower() == 'accept-encoding' for key in headers) else {**headers, 'Accept-Encoding': 'identity'}


def full_media(path: Path, content_type: str) -> str:
    """Verify container evidence and reject HTML/JSON even with a media MIME type."""
    require(content_type.split(';')[0].strip().lower() in {
        'video/mp4', 'audio/mp4', 'video/webm', 'audio/webm', 'audio/ogg', 'application/ogg',
        'audio/mpeg', 'application/octet-stream'}, 'non_media_content_type')
    with path.open('rb') as handle:
        prefix = handle.read(16)
        if prefix[4:8] == b'ftyp':
            total, offset, kinds = path.stat().st_size, 0, set()
            while offset < total:
                handle.seek(offset)
                header = handle.read(8)
                require(len(header) == 8, 'invalid_media_container')
                size, kind = struct.unpack('>I4s', header)
                header_size = 8
                if size == 1:
                    extended = handle.read(8)
                    require(len(extended) == 8, 'invalid_media_container')
                    size, header_size = struct.unpack('>Q', extended)[0], 16
                if size == 0:
                    size = total - offset
                require(header_size <= size <= total - offset, 'invalid_media_container')
                kinds.add(kind)
                offset += size
            require({b'ftyp', b'moov', b'mdat'} <= kinds, 'invalid_media_container')
            return 'mp4'
        if prefix.startswith(b'\x1aE\xdf\xa3'):
            return 'webm'
        if prefix.startswith(b'OggS'):
            return 'ogg'
        if prefix.startswith(b'ID3') or len(prefix) > 1 and prefix[0] == 0xff and prefix[1] & 0xe0 == 0xe0:
            return 'mp3'
    raise DownloadError('invalid_media_container')


def file_digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def transfer(proxy: Proxy, stream: dict[str, Any], partial: Path, deadline: float) -> tuple[int, str, str]:
    with partial.open('xb') as output:
        restrict_private(partial)
        with proxy.open(stream['url'], headers_for(stream), deadline) as response:
            require(response.getheader('Content-Encoding', 'identity').strip().lower() == 'identity', 'encoded_media_refused')
            require(response.getheader('Content-Range') is None, 'partial_media_response')
            length = response.getheader('Content-Length')
            expected = stream.get('content_length')
            require(length is not None or expected is not None, 'full_length_unproven')
            if length is not None:
                require(re.fullmatch(r'[0-9]+', length), 'invalid_content_length')
            if expected is not None:
                require(not isinstance(expected, bool) and re.fullmatch(r'[0-9]+', str(expected)), 'invalid_content_length')
            size = int(length) if length is not None else int(str(expected))
            require(size > 0 and (expected is None or size == int(expected)), 'media_length_mismatch')
            count, digest = 0, hashlib.sha256()
            while True:
                seconds_left(deadline)
                chunk = response.read1(65536)
                if not chunk:
                    break
                output.write(chunk)
                output.flush()
                count += len(chunk)
                digest.update(chunk)
                require(count <= size, 'media_length_mismatch')
            require(count == size, 'partial_media_transfer')
            seconds_left(deadline)
            output.flush()
            os.fsync(output.fileno())
            content_type = response.getheader('Content-Type', '')
    return count, digest.hexdigest(), full_media(partial, content_type)


def download(request_file: str, response_file: str, output_dir: str, exit_check_url: str) -> dict[str, Any]:
    state: dict[str, Any] | None = None
    record: Path | None = None
    metadata_success = False
    try:
        request = json.loads(Path(request_file).read_text(encoding='utf-8-sig'))
        raw_response = Path(response_file).read_bytes()
        response = json.loads(raw_response)
        require(response.get('status') == 'ok' and type(response.get('http_status')) is int
                and 200 <= response['http_status'] < 300, 'metadata_not_successful')
        require(request.get('method', 'GET').upper() == 'POST' and request.get('path') == STREAMS_PATH
                and not request.get('query') and isinstance(request.get('body'), dict), 'wrong_metadata_request')
        body = request['body']
        base = response.get('client_base_url')
        parsed_url(base)
        fingerprint = request_fingerprint('POST', base.rstrip('/') + STREAMS_PATH, body, True)
        require(response.get('request_sha256') == fingerprint, 'request_fingerprint_mismatch')
        metadata_success = True
        data = response['response']['data']
        require(isinstance(data, dict) and data.get('same_proxy_required') is True
                and data.get('proxy_exit_verified') is True, 'proxy_verification_missing')
        require(isinstance(body.get('video_id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', body['video_id'])
                and data.get('video_id', body['video_id']) == body['video_id'], 'video_identity_mismatch')
        expected_ip = str(ipaddress.ip_address(data['proxy_exit_ip']))
        proxy = Proxy(body['proxy_url'])
        parsed_url(exit_check_url)
        require(data.get('all_selected_streams_verified') is not False, 'metadata_verification_failed')
        requested = body.get('itags', ['137', '140'])
        require(isinstance(requested, list) and 1 <= len(requested) <= 4
                and all(isinstance(itag, str) and re.fullmatch(r'[0-9]{1,8}', itag) for itag in requested)
                and len(set(requested)) == len(requested), 'invalid_selected_streams')
        streams = data.get('streams')
        require(isinstance(streams, list) and all(isinstance(stream, dict) for stream in streams)
                and len(streams) == len(requested) and {stream.get('itag') for stream in streams} == set(requested),
                'selected_streams_missing')
        for stream in streams:
            parsed_url(stream.get('url'))
            headers_for(stream)
            expires = stream.get('expires_at')
            require(type(expires) in (int, float) and math.isfinite(expires), 'expiry_missing')
            verification = stream.get('verification') or {}
            require(isinstance(verification, dict), 'invalid_verification')
            require(stream.get('verified') is not False and verification.get('ok') is not False,
                    'metadata_verification_failed')
            if body.get('verify_download') is True:
                require(data.get('download_verification_requested') is True and data.get('all_selected_streams_verified') is True
                        and stream.get('verified') is True and verification.get('ok') is True,
                        'metadata_verification_missing')
        destination = Path(output_dir).resolve()
        setup_root = Path(__file__).resolve().parents[1]
        plugin_root = setup_root.parent.parent
        installation = plugin_root if (plugin_root / '.claude-plugin/plugin.json').is_file() else setup_root
        require(not destination.is_relative_to(installation), 'output_inside_installation')
        identity = {'request_sha256': fingerprint, 'response_sha256': hashlib.sha256(raw_response).hexdigest(),
                    'proxy_sha256': hashlib.sha256(body['proxy_url'].encode()).hexdigest(),
                    'exit_check_sha256': hashlib.sha256(exit_check_url.encode()).hexdigest()}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        record = destination / ('tikin-download-' + run_id) / 'download.json'
        with record_lock(record):
            if record.exists():
                state = json.loads(record.read_text())
                require(state.get('identity') == identity, 'download_record_mismatch')
            else:
                state = {'schema_version': 1, 'status': 'partial', 'identity': identity,
                         'metadata_success': True, 'streams': [], 'proxy_exit_ip': expected_ip,
                         'metadata_record': response.get('record'), 'selected_itags': requested,
                         'complete_transfer_verified': False, 'decode_verified': False, 'merge_performed': False}

            def save() -> None:
                atomic_write(record, json.dumps(state, ensure_ascii=False, indent=2) + '\n')

            save()
            if state.get('not_before', 0) > time.time():
                return {**state, 'status': 'cooldown', 'record': str(record),
                        'retry_after_seconds': state['not_before'] - time.time()}
            state.pop('not_before', None)
            deadline = time.monotonic() + MAX_STREAM_SECONDS * len(streams)
            for stream in streams:
                itag = stream['itag']
                existing = next((item for item in state['streams'] if item['itag'] == itag
                                 and item.get('complete_transfer_verified')), None)
                if existing:
                    file = Path(existing['file'])
                    require(file.is_file() and file.stat().st_size == existing['bytes']
                            and file_digest(file) == existing['sha256'], 'existing_media_changed')
                    continue
                require(stream['expires_at'] > time.time(), 'media_url_expired')
                stream_deadline = min(deadline, time.monotonic() + MAX_STREAM_SECONDS,
                                      time.monotonic() + stream['expires_at'] - time.time())
                entry = {'itag': itag, 'status': 'partial', 'complete_transfer_verified': False,
                         'file': str(record.parent / ('stream-' + itag + '-' + uuid.uuid4().hex + '.part'))}
                previous = [item for item in state['streams'] if item['itag'] == itag]
                state.setdefault('partial_files', []).extend(previous)
                state['streams'] = [item for item in state['streams'] if item['itag'] != itag] + [entry]
                state['status'] = 'partial'
                state.pop('reason', None)
                save()  # A killed process leaves a durable partial marker and an exclusive file.
                try:
                    exit_check(proxy, exit_check_url, expected_ip, stream_deadline)
                    partial = Path(entry['file'])
                    size, digest, suffix = transfer(proxy, stream, partial, stream_deadline)
                    exit_check(proxy, exit_check_url, expected_ip, stream_deadline)
                    seconds_left(stream_deadline)
                    final = partial.with_suffix('.' + suffix)
                    os.link(partial, final)  # Atomic publication cannot overwrite an existing file.
                    partial.unlink()
                    entry.update(status='complete', complete_transfer_verified=True, file=str(final), bytes=size, sha256=digest)
                    state['last_http_status'] = 200
                    save()
                except (DownloadError, OSError, ValueError, TypeError, KeyError, http.client.HTTPException, KeyboardInterrupt) as error:
                    state['reason'] = str(error) if isinstance(error, DownloadError) else 'transfer_interrupted_or_invalid'
                    if isinstance(error, DownloadError):
                        state['last_http_status'] = error.http_status
                        if error.not_before is not None:
                            state['not_before'] = max(state.get('not_before', 0), error.not_before)
                    if Path(entry['file']).is_file():
                        entry['bytes'] = Path(entry['file']).stat().st_size
                    save()
                    return {**state, 'record': str(record)}
            state.update(status='complete', complete_transfer_verified=True)
            state.pop('reason', None)
            save()
            return {**state, 'record': str(record)}
    except (DownloadError, OSError, ValueError, TypeError, KeyError, AttributeError, http.client.HTTPException) as error:
        reason = str(error) if isinstance(error, DownloadError) else 'invalid_or_unavailable_download_input'
        return {'status': 'blocked', 'reason': reason, 'complete_transfer_verified': False, 'metadata_success': metadata_success,
                **({'record': str(record)} if record else {})}
