# YouTube V3: from metadata to saved streams

Use this workflow for `POST /api/v1/youtube/web_v2/get_video_streams_v3` after the
selected service supports that candidate operation and the user supplies an authorized
HTTP proxy with a stable public exit. The metadata API and actual file download are
separate steps. HTTP 200 metadata can be charged even if sampling or downloading fails.
This candidate has controlled HTTP/proxy evidence; real proxy/media and supported-host
acceptance are still pending. Do not infer live availability from the bundled index.

## Obtain metadata once

Preserve the user's existing proxy address, credentials and sticky-session identifier.
An actual US residential exit is the usual starting point, but the video's allowed
region determines the choice. Country and session labels alone do not prove a stable
exit. Do not buy a proxy, change it, or fall back to direct downloading automatically.

Write a private request file outside the installation. URL-encode reserved characters
inside proxy credentials; never put the proxy password in chat, command arguments or
query parameters. Use the current discovery schema for the exact request:

```json
{
  "original_request": "<original download request>",
  "method": "POST",
  "path": "/api/v1/youtube/web_v2/get_video_streams_v3",
  "body": {
    "video_id": "<11-character video ID>",
    "proxy_url": "http://USERNAME:ENCODED_PASSWORD@proxy.example:1000",
    "itags": ["137", "140"],
    "verify_download": true
  }
}
```

Send it through the existing `tikin-config request` entry with the real calling Skill
and original task record. In regression, that same request must use the existing
`--regression-approval` and shared ledger; every metadata attempt retains its original
cost reservation. The downloader cannot create or repeat a metadata request.

Save the complete successful CLI JSON output to a private `metadata-response.json`,
including `status`, `http_status`, `request_sha256`, `client_base_url`, `record` and
`response`. Do not save only `response.data` or rebuild a response with a different
proxy. Retain the exact signed URLs, per-stream `download_headers`, Unix `expires_at`,
verification fields and `proxy_exit_ip`. The CLI masks input proxy credentials while
preserving usable returned media URLs and headers; keep the full response private.

## Download the selected streams

Provide an explicitly chosen exit-check URL that returns JSON `{"ip":"<public IP>"}`
over HTTP or HTTPS. It is accessed through the same proxy. There is no default external
IP service. The exit-check request receives neither media headers nor API credentials.

```text
uv run --frozen --project "<installed tikin-setup directory>" python "<installed tikin-setup directory>/scripts/tikin-config" --skill tikin-youtube download --request-file "<absolute request.json>" --response-file "<absolute metadata-response.json>" --output-dir "<absolute media directory>" --exit-check-url "<explicit JSON IP-check URL>"
```

This command uses the pinned Python runtime on each supported OS. It does not need an
API key, read global business configuration or send a Tikin request. It always uses the
original HTTP proxy, including for HTTPS CONNECT, and ignores environment proxy bypass
settings. TLS certificate checks remain enabled. All redirects are refused, so proxy
credentials and target-specific headers cannot be forwarded to a redirected target.
Returned range, proxy-authentication or other transport-control headers are refused
instead of silently changing a partial request into a claimed full download.

Before and after each stream, the helper checks the proxy's observed exit against the
metadata. Each stream has a 300-second deadline, further bounded by its URL expiry;
the invocation has at most 300 seconds per selected stream in total, including checks.
There are no automatic download retries. It verifies the complete byte count against
Content-Length and returned `content_length` when present, checks a media MIME type and
container evidence, and computes a local SHA-256. A missing verifiable full length,
HTML/JSON disguised as media, a truncated transfer, expiry, changed exit, failed sample
verification or missing requested stream prevents completion. MP4/M4A box boundaries
are checked; WebM/Ogg/MP3 use container signatures plus the complete transfer count.
This does not decode every frame or independently authenticate the provider's content.

When `verify_download` was requested, the returned requested/all-stream/per-stream
verification flags must be true. A false flag always blocks downloading. Null sampling
flags when sampling was not requested allow the separate complete-transfer checks;
sampling alone never establishes a complete local file.

## Results and continuation

`status: complete` and `complete_transfer_verified: true` mean every selected stream
passed the checks and exists locally. Report each file, size and hash. The default
selection has separate video and audio streams; both must complete before reporting
the download complete. `merge_performed: false` and `decode_verified: false` remain
explicit. If the user wants one audiovisual file, perform and verify an authorized
local merge separately; two downloaded streams are not an already merged video.

`status: partial` retains finished files, a `download.json` record, and any `.part`
file. A killed process also leaves that durable partial marker. Rerun the same command
with the same inputs to verify and reuse completed files and retry unfinished streams
within their original expiry. Unfinished bytes stay in `partial_files`; a new exclusive
file is used for that stream, without overwriting the partial. Local edits to a completed
file cause a refusal. Concurrent invocations of the same record are locked locally.
The helper never refreshes expired metadata, changes proxy/session, or resets a Tikin
regression allowance. A new paid metadata request needs the existing authorization and
remaining budget, not an automatic recovery loop.

`status: blocked` gives a stable `reason` before the affected download can proceed.
Valid integer or HTTP-date `Retry-After` values from the proxy/media boundary use the
shared request parser and persist their full `not_before` time. A new process returns
`status: cooldown` before any exit/media request until that time; changing processes
does not shorten the server's wait. No automatic retry or long blocking sleep is added.
Report `metadata_success`, download status and any retained record/file paths separately.
Do not claim a failed download was free. Exit/media traffic is proxy traffic, not a
zero-priced Tikin query and not a way to bypass the single metadata-request ledger.
