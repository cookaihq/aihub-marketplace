# Shared requests and local error reports

All tikin business API calls use the bundled `tikin-config request` command, including usage checks, platform queries, search, batch calls, pagination and queries of an existing asynchronous task. It loads the actual caller's configuration, captures the request and response, and saves a local report on the first HTTP, protocol or business error. Keep the existing routing and task authorization choices. Offline endpoint discovery and local configuration inspection do not send requests.

## Execute one operation

Resolve the installed `tikin-setup` directory and the actual calling Skill name. Write a request JSON outside the installation, preserving the user's original words in `original_request`. Copy the endpoint, HTTP method and parameter names from endpoint discovery. `query` becomes URL parameters (array values become repeated parameters); `body` is the exact JSON value to submit, including an object, array, string or explicit `null`. Omit `body` for no request body; `"body": null` sends JSON `null`. Do not put API keys in this file; the helper reads the existing configuration.

```json
{
  "original_request": "读取我给出的这个 TikTok 视频详情",
  "method": "GET",
  "side_effects": false,
  "path": "/api/v1/tiktok/app/v3/fetch_one_video",
  "query": {"aweme_id": "7372484719365098283"}
}
```

The same command works in native Windows PowerShell, macOS and Linux shells; quote each actual path. No POSIX shell or curl is used for API requests:

```text
uv run --frozen --project "<installed tikin-setup directory>" python "<installed tikin-setup directory>/scripts/tikin-config" --skill tikin-tiktok request --request-file "<absolute request.json>" --output-dir "<absolute task output directory>"
```

On follow-up calls for the **same user task**, pass `--record "<absolute run.json returned by the first call>"`. Keep that caller and record for all pages, retries explicitly requested later and task-status queries. Create a new request file with the actual next cursor or query endpoint; `--record` reuses the report, it does not itself replay the previous request. Resume with the same service and credential. An ambiguous POST/PUT/PATCH/DELETE is retained and cannot be replayed automatically using the same record.

`--no-global-config` goes before `request` when this task disables global configuration; it skips both Plugin and ordinary Skill global files. The actual loader retains the existing precedence and does not save credentials. The `run -- <command>` subcommand remains a configuration utility; it does not capture arbitrary child HTTP traffic and is not the business request entrypoint.

Optional request fields: `timeout_seconds` (default 30), `time_budget_seconds`
(default 90 for the entire invocation, including retries and waits), `side_effects`
(default true), and `reference_materials` (necessary source paths, URLs or descriptive
metadata, without binary content). Both time limits must be finite, positive and at
most 300 seconds. Set `side_effects: false` only for a verified read; the HTTP method
alone does not establish that GET is harmless. Task creation, including GET caption
requests that may create a job, uses true. Non-read HTTP methods retain write protection.
Configuration and request validation errors are local errors, not evidence that an
upstream service failed.

## Reliability and results

The helper allows at most 3 attempts in a transient failure sequence for explicitly
verified reads, with 1s/2s fallback backoff and the complete valid numeric/date
`Retry-After`. It never shortens a server cooldown. When the wait exceeds the time
budget it returns `cooldown`, `not_before` and `retry_after_seconds`; continue with
the same record after that time. The attempt count and cooldown survive process
replacement. Deterministic 4xx are not retried. Only DNS failure or connection refusal
proves a write was not sent. HTTP 5xx/429, a timeout or disconnect can leave writes,
including side-effecting GETs, in `submission_unknown`; changing the semantic label
does not clear their replay protection. Report creation never adds requests.
Continue to apply the pagination budget in `tikin-rest-api`; do not create an
unbounded polling loop.

For explicitly approved regression, use [the shared approval and ledger](regression.md)
through this same request entry. Every business attempt, including retries and
resumption, reserves before sending. An ambiguous paid read is also not retried.
This opt-in campaign does not impose its allowance on ordinary user requests.

Read `status`, `http_status` and `response` before claiming success. A 2xx JSON envelope with `error`, `success=false`, a failing business `code`, or an asynchronous `status=failed/error` is a failure. Unknown response shapes require the endpoint's normal verification gate; do not infer success merely from a request ID. Preserve usable returned media URLs for the authorized download, but do not paste their signatures into an error report. Final media downloads use the existing bounded downloader and do not resend the data API request.

`request_sha256` and `client_base_url` identify the exact attempted request; keep the
complete successful output when handing it to [the YouTube V3 downloader](downloads.md).
That downloader only consumes existing metadata and never repeats the API call.

`response_headers.retry-after` exposes a valid server value. Recognized envelope
error messages are replaced with a stable local explanation; non-JSON error pages
are not echoed as public diagnostics. Legal nested business fields, task state and
signed media URLs remain intact. Private reports retain separately sanitized evidence.

Caption and LinkedIn workflows additionally return `waiting`, `task_exists` or
`poll_budget_exhausted` with the existing job. `waiting` and `task_exists` exit
successfully but are not final business data; inspect the structured status.
The same record preserves the bounded query count and deadline, including in-flight
query time. A query response for another task cannot complete the requested task.

## Every user-facing response

When `feedback` exists, copy **every** `feedback.artifact_links` entry into the conversation on first failure, repeated failure/query, recovery and the final response. Each link label must show its **full absolute path** and point at that real saved file. Do not shorten it to a filename, relative path or “same directory”, and do not place links in code fences. `feedback.user_notice` contains ready-to-use Markdown.

Explain the current result and independent error count. Repeated observations of the same terminal task ID update one failure; real failed HTTP attempts count separately. Recovery keeps and updates the same `error-report.md`. The related `diagnostic.json`, `issue-draft.md` and `run.json` also receive full links. A save warning leaves the business result intact; report it, retain the known task/request ID, and never resubmit to recreate a report.

Local reports include original requirements, actual parameters and sanitized request/response JSON. Credentials, Authorization, Cookie and signed URL query values are redacted; binary/Base64 and oversized content have explicit omission markers. `http_status` means the client-to-tikin response, not the supplier's status. API-exposed upstream fields retain their source; missing provider, route, trace, internal timing or retry information is unknown. `service_unavailable` alone does not prove an outage. An administrator can use the local task/request ID to inspect backend logs.

Reports stay local. They can contain private queries and source identifiers. The public Issue draft deliberately excludes private prompts, URLs, paths, raw IDs and responses. Provide its full link for review, and send it only after an explicit user instruction. Never upload the local diagnostic automatically.
