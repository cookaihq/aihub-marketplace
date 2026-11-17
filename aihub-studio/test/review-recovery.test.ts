import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, writeFile, readdir, rm } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import type { AddressInfo } from 'node:net';
import { fixtureTransport } from './fixture-transport.js';
import { runCaptured } from '../src/capturedProcess.js';
const oldKey = 'synthetic-original-asr-key', newKey = 'synthetic-new-review-key';

async function fixture(legacyReview = false) {
  const dir = await mkdtemp(join(tmpdir(), 'review-recovery-'));
  const source = join(dir, 'source.wav');
  // Deterministic 1s/16kHz tone; fixture creation also works under native host restrictions.
  const wave = Buffer.alloc(44 + 16000 * 2);
  wave.write('RIFF'); wave.writeUInt32LE(wave.length - 8, 4); wave.write('WAVEfmt ', 8);
  wave.writeUInt32LE(16, 16); wave.writeUInt16LE(1, 20); wave.writeUInt16LE(1, 22);
  wave.writeUInt32LE(16000, 24); wave.writeUInt32LE(32000, 28); wave.writeUInt16LE(2, 32); wave.writeUInt16LE(16, 34);
  wave.write('data', 36); wave.writeUInt32LE(wave.length - 44, 40);
  for (let i = 0; i < 16000; i++) wave.writeInt16LE(Math.round(5000 * Math.sin(2 * Math.PI * 440 * i / 16000)), 44 + 2 * i);
  await writeFile(source, wave);
  const calls: Array<{ path: string; auth: string | undefined }> = [];
  const mode = { review: 'rejected' };
  let base = '';
  const server = createServer(async (req, res) => {
    calls.push({ path: req.url!, auth: req.headers.authorization });
    const json = (v: unknown, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(v)); };
    if (req.url === '/v1/models') return json({ data: [{ id: 'paraformer-v2' }] });
    if (req.url === '/e/v1/configs/llm_generations_models') return json({ data: [{ id: 'gemini-4-hydrogen', capabilities: ['audio'] }] });
    if (req.method === 'POST') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      const body = JSON.parse(raw);
      if (req.url === '/e/v1/files/upload/base64') return json({ id: 'upload', url: `${base}/source.wav`, size: Buffer.from(body.file_data, 'base64').length, filename: 'source.wav', created: 0 });
      if (req.url === '/e/v1/llm/generations') {
        if (mode.review === 'rejected') return json({ error: { code: 'insufficient_user_quota' } }, 403);
        if (mode.review === 'unknown') return json({ error: { code: 'gateway_error' } }, 503);
        const input = JSON.parse(body.messages.find((m: any) => m.role === 'user').content[0].text);
        const assets = [...input.artifacts.map((a: any) => a.id), ...input.inputs_in_content_order.map((a: any) => a.id)];
        const report = { findings: input.requirements.map((r: any) => ({ requirement_id: r.id, verdict: 'mismatched', evidence: assets.map(asset_id => ({ asset_id, observation: 'The synthetic transcript says speech, but the source is a sine tone.', location: '0–1 seconds' })) })),
          coverage: assets.map(asset_id => ({ asset_id, complete: true, note: 'Whole synthetic source and transcript inspected', ...(asset_id.startsWith('source') ? { time_ranges: [[0, 1]], audio_checked: true } : {}) })) };
        return json({ id: 'new-review', model: body.model, status: mode.review === 'pending' ? 'pending' : 'completed', results: [{ text: JSON.stringify(report) }] });
      }
      return json({ id: 'original-asr', model: 'paraformer-v2', status: 'completed', results: [{ transcripts: [{ text: 'fixture speech', sentences: [{ text: 'fixture speech', begin_time: 0, end_time: 1000 }] }] }] });
    }
    return json({ error: 'Unexpected remote read' }, 404);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening'); base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const request = join(dir, 'request.json');
  await writeFile(request, JSON.stringify({ operation: 'audio-transcribe', original_request: 'Transcribe the full recording faithfully.', inputs: { audios: [source] } }));
  const call = async (key: string, ...args: string[]) => {
    const program = process.platform === 'win32' ? 'powershell.exe' : process.execPath;
    const prefix = process.platform === 'win32' ? ['-NoProfile', '-NonInteractive', '-File', resolve('scripts/aihub.ps1')] : [resolve('scripts/aihub.mjs')];
    let stdout = '';
    try { ({ stdout } = await runCaptured(program, [...prefix, ...args, '--skill', 'aihub-audio', '--no-global-config'], { cwd: dir, windowsHide: true, timeout: 60_000,
      env: { ...process.env, ...fixtureTransport(base), AIHUB_API_KEY: key, AIHUB_AUDIO_MODELS: 'paraformer-v2', AIHUB_RESULT_CHECK_ENABLED: '1', AIHUB_RESULT_CHECK_PROVIDER: 'auto', AIHUB_RESULT_CHECK_MODELS: 'gemini-4-hydrogen' } })); }
    catch (error) { stdout = (error as { stdout: string }).stdout; }
    assert.ok(!stdout.includes(oldKey) && !stdout.includes(newKey));
    return JSON.parse(stdout);
  };
  const done = await call(oldKey, 'run', '--request-file', request, '--output-dir', dir);
  assert.equal(done.status, 'delivered');
  const rejected = await call(oldKey, 'review', '--record', done.run_record, '--provider', 'aihub', '--wait-seconds', '0');
  assert.equal(rejected.status, 'unavailable');
  const reviewPath = join(dirname(done.run_record), 'review.json');
  if (legacyReview) {
    // The 6.5.3 on-disk contract predates independent review credentials.
    const oldReview = JSON.parse(await readFile(reviewPath, 'utf8'));
    delete oldReview.credential_id;
    oldReview.token = createHash('sha256').update(JSON.stringify({ id: oldReview.id, plan: oldReview.plan_hash, revision: oldReview.requirement_revision,
      original: oldReview.original_request, current: oldReview.current_request, requirements: oldReview.requirements, sources: oldReview.sources, checks: oldReview.program_checks,
      artifacts: oldReview.artifacts.map((a: any) => ({ id: a.id, path: a.path, sha256: a.sha256, bytes: a.bytes })) })).digest('hex');
    await writeFile(reviewPath, JSON.stringify(oldReview));
  }
  const previousReview = JSON.parse(await readFile(reviewPath, 'utf8'));
  const snapshot = await readFile(done.run_record, 'utf8');
  return { dir, done, calls, mode, call, snapshot, previousReview, recover: (key = newKey) => call(key, 'review-recover', '--record', done.run_record, '--reason', 'User explicitly selected a new credential for review.'),
    close: async () => { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); await rm(dir, { recursive: true, force: true }); } };
}

test('public recovery authorizes only delivered local ASR reads and a new review, preserving original identity and history', async () => {
  const f = await fixture(true);
  try {
    const denied = await f.call(newKey, 'review', '--record', f.done.run_record);
    assert.equal(denied.status, 'recovery_failed'); assert.match(denied.error, /credential/);
    const before = f.calls.length;
    const recovered = await f.recover();
    assert.equal(recovered.status, 'review_recovery_ready', JSON.stringify(recovered));
    assert.equal(f.calls.length, before, 'authorizing recovery must stay offline');
    assert.equal(await readFile(f.done.run_record, 'utf8'), f.snapshot);
    assert.equal((await f.call(newKey, 'continue', '--record', f.done.run_record, '--confirm', 'synthetic-token')).status, 'recovery_failed');
    assert.equal(f.calls.length, before, 'local review consent cannot approve ASR');
    f.mode.review = 'complete';
    const checked = await f.call(newKey, 'review', '--record', f.done.run_record, '--provider', 'aihub', '--recheck', '--wait-seconds', '0');
    assert.equal(checked.status, 'mismatched', JSON.stringify(checked));
    const count = f.calls.length;
    const continued = await f.call(newKey, 'continue', '--record', f.done.run_record, '--wait-seconds', '0');
    assert.equal(continued.status, 'delivered'); assert.equal(continued.result_check.status, 'mismatched');
    assert.equal(f.calls.length, count, 'delivered continue must not query or download old remote tasks');
    assert.equal(await readFile(f.done.run_record, 'utf8'), f.snapshot);
    assert.equal(f.calls.filter(c => c.path === '/e/v1/audios/generations').length, 1);
    const history = (await readdir(dirname(f.done.run_record))).find(n => n.startsWith('review-history-'));
    assert.ok(history);
    assert.deepEqual(JSON.parse(await readFile(join(dirname(f.done.run_record), history), 'utf8')), f.previousReview);
    assert.equal(f.previousReview.credential_id, undefined, 'legacy review identity stays implicit in the original ASR');
    const other = await f.call('synthetic-unapproved-key', 'continue', '--record', f.done.run_record);
    assert.equal(other.status, 'recovery_failed');
    const originalRun = JSON.parse(f.snapshot);
    const originalAudio = JSON.parse(await readFile(originalRun.attempts.at(-1).audio_record, 'utf8'));
    const remoteBefore = f.calls.length;
    const child = await f.call(newKey, 'resume', '--record', originalAudio.parts[0].task_record, '--wait-seconds', '0');
    assert.equal(child.status, 'recovery_failed');
    assert.equal(f.calls.length, remoteBefore, 'review authorization cannot query or download an original child task');
    f.mode.review = 'pending';
    const pending = await f.call(newKey, 'review', '--record', f.done.run_record, '--provider', 'aihub', '--recheck', '--wait-seconds', '0');
    assert.equal(pending.status, 'checking');
    const pendingCalls = f.calls.length;
    assert.equal((await f.call(oldKey, 'review', '--record', f.done.run_record, '--wait-seconds', '0')).status, 'recovery_failed');
    assert.equal((await f.call(newKey, 'review', '--record', f.done.run_record, '--recheck')).status, 'recovery_failed');
    assert.equal((await f.recover('synthetic-third-review-key')).status, 'recovery_failed');
    assert.equal(f.calls.length, pendingCalls, 'neither old credentials nor another new key may replace an active review');
    assert.equal(await readFile(f.done.run_record, 'utf8'), f.snapshot);
  } finally { await f.close(); }
});

test('changed or missing output, unfinished review and unknown submission cannot be authorized or replayed', async () => {
  const f = await fixture();
  try {
    const reviewPath = f.done.result_check.review_record;
    const saved = await readFile(reviewPath, 'utf8');
    for (const change of ['pending', 'checking', 'preparing', 'ready', 'unknown']) {
      const review = JSON.parse(saved);
      if (change === 'pending' || change === 'checking') review.status = change;
      else {
        review.external.state = change === 'preparing' || change === 'ready' ? change : 'submitted';
        review.external.result = { status: change === 'unknown' ? 'submission_unknown' : 'delivered' };
      }
      await writeFile(reviewPath, JSON.stringify(review));
      assert.equal((await f.recover()).status, 'recovery_failed', change);
    }
    await writeFile(reviewPath, saved);
    for (const change of ['service', 'skill', 'active']) {
      const run = JSON.parse(f.snapshot);
      if (change === 'service') run.service_url = 'https://another.invalid';
      if (change === 'skill') run.skill = 'aihub-image';
      if (change === 'active') run.status = 'waiting';
      await writeFile(f.done.run_record, JSON.stringify(run));
      assert.equal((await f.recover()).status, 'recovery_failed', change);
    }
    await writeFile(f.done.run_record, f.snapshot);
    const audioPath = JSON.parse(f.snapshot).attempts.at(-1).audio_record;
    const audioSnapshot = await readFile(audioPath, 'utf8');
    for (const field of ['binding', 'preparation_hash']) {
      const changed = JSON.parse(audioSnapshot);
      changed[field] = 'modified-before-recovery';
      await writeFile(audioPath, JSON.stringify(changed));
      assert.equal((await f.recover()).status, 'recovery_failed', field);
    }
    await writeFile(audioPath, audioSnapshot);
    const output = f.done.files[0].path, original = await readFile(output);
    await writeFile(output, 'changed output');
    assert.equal((await f.recover()).status, 'recovery_failed');
    await rm(output);
    assert.equal((await f.recover()).status, 'recovery_failed');
    await writeFile(output, original);
    assert.equal((await f.recover()).status, 'review_recovery_ready');
    const audit = JSON.parse(await readFile(join(dirname(f.done.run_record), 'review-recovery.json'), 'utf8'));
    assert.ok(audit.events.some((e: any) => e.outcome === 'blocked'));
    assert.equal(audit.events.at(-1).outcome, 'authorized');
    assert.ok(audit.events.every((e: any) => e.original_credential_id && e.credential_id && e.run_id));
    await writeFile(output, 'changed after authorization');
    assert.equal((await f.call(newKey, 'continue', '--record', f.done.run_record)).status, 'recovery_failed');
    await writeFile(output, original);
    const source = JSON.parse(audioSnapshot).sources[0].path;
    await writeFile(source, 'changed source after authorization');
    assert.equal((await f.call(newKey, 'review', '--record', f.done.run_record, '--recheck')).status, 'recovery_failed');
    assert.equal(f.calls.filter(c => c.path === '/e/v1/audios/generations').length, 1);
  } finally { await f.close(); }
});
