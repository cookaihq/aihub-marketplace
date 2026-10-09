import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { isAbsolute, join } from 'node:path';
import type { AddressInfo } from 'node:net';
import { AihubmaxClient } from '../src/apiClient.js';
import { bindDiagnosticRecord, collectRequestErrors, existingFeedback, feedback, observeTerminalTask } from '../src/diagnostics.js';
import { redactEvidence } from '../src/diagnosticEvidence.js';
import type { LoadedConfig } from '../src/config.js';
import { startRun, continueRun } from '../src/runs.js';

const config = (baseUrl: string): LoadedConfig => ({ skill: 'aihub-image', apiKey: 'synthetic-api-secret', baseUrl,
  sources: { AIHUB_API_KEY: 'environment', AIHUB_BASE_URL: 'environment' } });

test('terminal observation without transport evidence does not invent HTTP 200', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-http-evidence-'));
  try {
    const result = await collectRequestErrors(async events => {
      await observeTerminalTask({ id: 'synthetic-task', status: 'failed', error: { code: 'service_unavailable' } });
      return feedback(config('https://example.invalid'), { status: 'remote_failed', record: join(root, 'task.json') }, events);
    });
    const saved = JSON.parse(await readFile(String(result!.diagnostic), 'utf8'));
    assert.equal(saved.events[0].http_status, null, 'HTTP status must be unknown unless observed at the transport boundary');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('first rejected request creates an absolute Markdown report with actual request and response evidence', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-first-error-'));
  const server = createServer((_req, res) => {
    res.writeHead(422, { 'content-type': 'application/json', 'x-request-id': 'synthetic-request-id' });
    res.end(JSON.stringify({ error: { code: 'new_provider_error', message: 'precise synthetic detail', upstream_status: 503 } }));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const cfg = config(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
    const result = await collectRequestErrors(async events => {
      await assert.rejects(new AihubmaxClient(cfg).submitGeneration('/v1/images/generations', {
        model: 'gpt-image-2.5-flare', prompt: 'synthetic private prompt', size: '1024x1024',
      }));
      return feedback(cfg, { status: 'preflight_failed', run_record: join(root, 'run.json') }, events);
    });
    assert.equal(result!.upstream_error_count, 1);
    assert.equal(result!.show_notice, true);
    assert.ok(isAbsolute(String(result!.error_report)));
    const report = await readFile(String(result!.error_report), 'utf8');
    for (const evidence of ['synthetic private prompt', 'new_provider_error', 'precise synthetic detail', 'synthetic-request-id', '422', '/v1/images/generations']) {
      assert.ok(report.includes(evidence), `missing evidence: ${evidence}`);
    }
    assert.ok(!report.includes(cfg.apiKey));
    const draft = await readFile(String(result!.issue_draft), 'utf8');
    assert.ok(!draft.includes('synthetic private prompt'));
    assert.ok(!draft.includes('synthetic-request-id'));
  } finally {
    server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));
    await rm(root, { recursive: true, force: true });
  }
});

test('accepted submission survives a new invocation; query HTTP and provider evidence stay distinct', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-cross-turn-'));
  let requests = 0;
  const server = createServer((req, res) => {
    requests++;
    res.writeHead(req.method === 'POST' ? 202 : 201, { 'content-type': 'application/json', 'x-request-id': 'gateway-query' });
    res.end(JSON.stringify(req.method === 'POST' ? { id: 'task-across-turns', status: 'pending' }
      : { id: 'task-across-turns', status: 'failed', error: { code: 'new_vendor_code', message: 'vendor detail',
        upstream: { http_status: 502, request_id: 'vendor-request', provider: 'returned-provider', retry_count: 2 } } }));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const cfg = config(`http://127.0.0.1:${(server.address() as AddressInfo).port}`), record = join(root, 'run.json');
  try {
    await collectRequestErrors(async () => {
      await bindDiagnosticRecord(cfg, record, { original_request: 'user original words', inputs: { images: ['https://assets.invalid/ref.png?Signature=signed-secret'] } }, true);
      await new AihubmaxClient(cfg).submitGeneration('/v1/images/generations', { model: 'synthetic-model', prompt: 'actual submitted prompt' });
    });
    const query = () => collectRequestErrors(async events => {
      await bindDiagnosticRecord(cfg, record);
      await new AihubmaxClient(cfg).getTask('task-across-turns');
      return feedback(cfg, { status: 'remote_failed', run_record: record }, events);
    });
    const first = await query(), again = await query();
    assert.equal(first!.error_report, again!.error_report);
    assert.equal(again!.upstream_error_count, 1);
    const saved = JSON.parse(await readFile(String(first!.diagnostic), 'utf8'));
    assert.equal(saved.events[0].http_status, 201);
    assert.equal(saved.events[0].http_status_source, 'client_response');
    assert.equal(saved.events[0].upstream[0].value.http_status, 502);
    assert.equal(saved.exchanges[0].response.http_status, 202);
    const report = await readFile(String(first!.error_report), 'utf8');
    for (const text of ['user original words', 'actual submitted prompt', 'new_vendor_code', 'returned-provider']) assert.ok(report.includes(text));
    assert.ok(!report.includes('signed-secret'));
    const recovered = await feedback(cfg, { status: 'delivered', record }, []);
    assert.equal(recovered!.show_notice, true);
    assert.equal(recovered!.upstream_error_count, 1);
    assert.equal(requests, 3);
  } finally { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); await rm(root, { recursive: true, force: true }); }
});

test('first failed attempt is saved before retry; a report write error cannot replay a POST', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-live-report-'));
  let calls = 0, firstSaved = false;
  const server = createServer(async (req, res) => {
    calls++;
    if (calls === 2) firstSaved = (await readFile(join(root, 'error-report.md'), 'utf8')).includes('503');
    res.writeHead(req.method === 'POST' || calls === 1 ? 503 : 200, { 'content-type': 'application/json', 'retry-after': '0' });
    res.end(JSON.stringify(req.method === 'POST' || calls === 1 ? { error: { code: 'service_unavailable' } } : { data: [] }));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const cfg = config(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
  try {
    await collectRequestErrors(async events => {
      await bindDiagnosticRecord(cfg, join(root, 'run.json'));
      await new AihubmaxClient(cfg).listLiveModels();
      assert.equal(events.length, 1);
      assert.equal(firstSaved, true);
    });
    const broken = join(root, 'broken');
    await mkdir(join(broken, 'diagnostic.json'), { recursive: true });
    await collectRequestErrors(async () => {
      await bindDiagnosticRecord(cfg, join(broken, 'run.json'));
      await assert.rejects(new AihubmaxClient(cfg).submitGeneration('/v1/images/generations', { prompt: 'do not replay' }),
        (error: unknown) => (error as { status: number; ambiguous: boolean }).status === 503 && (error as { ambiguous: boolean }).ambiguous);
    });
    assert.equal(calls, 3);
  } finally { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); await rm(root, { recursive: true, force: true }); }
});

test('legacy fixed HTTP 200 is migrated as unknown without fabricating lost evidence', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-legacy-report-'));
  try {
    await writeFile(join(root, 'diagnostic.json'), JSON.stringify({ schema_version: 1, kind: 'aihub-diagnostic',
      events: [{ id: 'task-old', at: '2026-10-09T08:14:11Z', stage: 'remote_execution', http_status: 200, code: 'service_unavailable', ambiguous: false }] }));
    const result = await feedback(config('https://example.invalid'), { status: 'remote_failed', record: join(root, 'task.json') }, []);
    const saved = JSON.parse(await readFile(String(result!.diagnostic), 'utf8'));
    assert.equal(saved.events[0].http_status, null);
    assert.equal(saved.events[0].http_status_source, 'legacy_unverified');
    assert.equal(saved.exchanges.length, 0);
    assert.match(await readFile(String(result!.error_report), 'utf8'), /固定填充值/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('redaction preserves unknown error detail but removes nested credentials, signed URLs and large binary', () => {
  const value = redactEvidence({ unknown: { detail: 'keep this evidence', api_key: 'nested-key', Authorization: 'Bearer extra-auth',
    accessToken: 'camel-access-secret', refreshToken: 'camel-refresh-secret',
    cookie: 'session=private', asset: 'https://u:p@assets.invalid/ref.png?X-Amz-Signature=signed-secret',
    text: 'configured-secret token text', data: 'a'.repeat(5000) } }, ['configured-secret']);
  const text = JSON.stringify(value);
  for (const secret of ['nested-key', 'extra-auth', 'camel-access-secret', 'camel-refresh-secret', 'session=private', 'u:p', 'signed-secret', 'configured-secret', 'a'.repeat(1024)]) assert.ok(!text.includes(secret));
  assert.ok(text.includes('keep this evidence'));
  assert.ok(text.includes('OMITTED'));
});

test('a later report update failure retains only links to existing artifacts', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-report-fallback-'));
  const output = { status: 'remote_failed', record: join(root, 'task.json') };
  try {
    const original = await collectRequestErrors(async events => {
      await observeTerminalTask({ id: 'synthetic', status: 'failed' });
      return feedback(config('https://example.invalid'), output, events);
    });
    await rm(String(original!.diagnostic));
    await mkdir(String(original!.diagnostic)); // An unavailable diagnostic prevents this update.
    await assert.rejects(feedback(config('https://example.invalid'), output, []));
    const fallback = await existingFeedback(output);
    assert.equal(fallback!.error_report, original!.error_report);
    assert.equal(fallback!.issue_draft, original!.issue_draft);
    assert.equal(fallback!.diagnostic, undefined, 'a directory must not be linked as a readable report');
    assert.match(String(fallback!.user_notice), /更新失败/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('all six Skill workflows and native music retain original inputs and one report on terminal failure', async t => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-all-error-routes-'));
  const cases: Array<{ skill: LoadedConfig['skill']; operation: string; model: string; inputs?: unknown }> = [
    { skill: 'aihub-image', operation: 'image-generate', model: 'gpt-image-2.5-flare' },
    { skill: 'aihub-video', operation: 'video-text', model: 'seedance-2.5-text-to-video' },
    { skill: 'aihub-audio', operation: 'audio-transcribe', model: 'paraformer-v2', inputs: { audios: ['https://fixtures.invalid/voice.wav'] } },
    { skill: 'aihub-music', operation: 'music-async', model: 'lyria-3-pro' },
    { skill: 'aihub-understanding', operation: 'understanding', model: 'gemini-3.1-pro-preview', inputs: { images: ['https://fixtures.invalid/reference.png?sign=private-signature'] } },
    { skill: 'aihub-document', operation: 'document', model: 'doc2x-v3', inputs: { files: ['https://fixtures.invalid/file.pdf'] } },
    { skill: 'aihub-music', operation: 'music-native', model: 'lyria-3-pro-preview' },
  ];
  let posts = 0;
  const server = createServer((req, res) => {
    const json = (body: unknown, status = 200) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (req.method === 'GET') return json({ data: cases.map(item => ({ id: item.model, capabilities: ['vision'] })) });
    posts++;
    if (req.url?.startsWith('/v1beta/')) return json({ error: { code: 'service_unavailable' } }, 422);
    return json({ id: 'synthetic-task-' + posts, status: 'failed', error: { code: 'service_unavailable' } }, 202);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    for (const item of cases) await t.test(item.operation, async () => {
      const cfg = { ...config(`http://127.0.0.1:${(server.address() as AddressInfo).port}`), skill: item.skill };
      const request = { operation: item.operation, model: item.model, original_request: 'original synthetic ' + item.operation,
        ...(['document', 'audio-transcribe'].includes(item.operation) ? {} : { prompt: 'submitted synthetic prompt' }),
        ...(item.operation === 'document' ? { requirements: { page_count: 1 } } : {}),
        ...(item.inputs ? { inputs: item.inputs } : {}) };
      const first = await collectRequestErrors(async events => {
        const output = await startRun(cfg, request, root, 0);
        return { output, report: await feedback(cfg, output, events) };
      });
      assert.ok(first.report, JSON.stringify(first.output));
      assert.equal(first.report.upstream_error_count, 1);
      const saved = JSON.parse(await readFile(String(first.report.diagnostic), 'utf8'));
      assert.equal(saved.context.original_request, request.original_request);
      assert.equal(saved.context.skill, item.skill);
      assert.ok(saved.exchanges.some((e: { method: string }) => e.method === 'POST'));
      const again = await collectRequestErrors(async events => {
        const output = await continueRun(cfg, String(first.output.run_record), 0);
        return feedback(cfg, output, events);
      });
      assert.equal(again!.error_report, first.report.error_report);
      assert.equal(again!.upstream_error_count, 1);
      assert.equal(again!.show_notice, true);
    });
    assert.equal(posts, cases.length, 'report feedback and continuation must not resubmit terminal tasks');
  } finally { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); await rm(root, { recursive: true, force: true }); }
});
