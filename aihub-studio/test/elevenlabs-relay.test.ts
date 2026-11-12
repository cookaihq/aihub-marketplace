import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { selectionPlan } from '../src/selection.js';
import { validateGeneration } from '../src/models.js';
import type { LoadedConfig } from '../src/config.js';
import { fixtureTransport } from './fixture-transport.js';

const cfg = (models?: string[]): LoadedConfig => ({ skill: 'aihub-audio', apiKey: 'fixture', baseUrl: 'https://fixture.invalid', sources: { AIHUB_API_KEY: 'fixture' }, modelSelection: { policy: 'auto', models, sources: {} } });

test('custom TTS requires existing voice IDs and enforces official-only constraints without narrowing shared TTS', () => {
  const validate = (model: string, params: Record<string, unknown>) => validateGeneration('audio', model, { text: 'Hello', ...params });
  for (const model of ['eleven-v4-custom-voice', 'eleven-v4-turbo-custom-voice']) {
    assert.throws(() => validate(model, {}), /existing voice ID/);
    assert.throws(() => validate(model, { voice: 'Rachel' }), /existing voice ID/);
    validate(model, { voice: '21m00Tcm4TlvDq8ikWAM', pronunciation_dictionary_locators: [], clone_strength: 0, enable_safety_checker: null });
    const plan = selectionPlan(cfg(), { operation: 'audio-tts', original_request: 'Use my existing voice', model, prompt: 'Hello', requirements: { voice: '21m00Tcm4TlvDq8ikWAM', clone_strength: 0 } });
    assert.equal(plan.candidates[0]?.rejection, undefined); assert.deepEqual(plan.candidates[0]?.params, { text: 'Hello', voice: '21m00Tcm4TlvDq8ikWAM', clone_strength: 0 });
    assert.throws(() => validate(model, { voice: '21m00Tcm4TlvDq8ikWAM', text: 'x'.repeat(2001) }), /2000/);
  }
  validate('eleven-v4', { text: 'x'.repeat(5000), previous_text: null, similarity_boost: 0 });
  for (const param of [{ previous_text: 'context' }, { similarity_boost: 0 }, { seed: 0 }]) {
    assert.throws(() => validate('eleven-v4-turbo-custom-voice', { voice: '21m00Tcm4TlvDq8ikWAM', ...param }), /Turbo/);
  }
});

test('Scribe preserves nullable and explicit controls, rejects conflicts and never downgrades V3', () => {
  const request = { operation: 'audio-transcribe', original_request: 'Transcribe with V3', inputs: { audios: ['https://fixtures.invalid/audio.mp3'] },
    requirements: { keyterms: [], secondary_language_codes: [], no_verbatim: false, temperature: 0, seed: 0, num_speakers: null } };
  const plan = selectionPlan(cfg(['scribe-v3', 'scribe-v2']), request);
  assert.deepEqual(plan.candidates.map(c => c.model), ['scribe-v3']);
  assert.equal(plan.candidates[0]?.rejection, undefined);
  assert.equal(plan.candidates[0]?.transcription, undefined);
  assert.deepEqual(plan.candidates[0]?.params, { audio_url: request.inputs.audios[0], ...request.requirements });
  const validate = (params: Record<string, unknown>) => validateGeneration('audio', 'scribe-v3', params);
  for (const params of [{}, { audio_url: 'https://fixtures.invalid/a', file: 'a.wav' },
    { audio_url: 'https://fixtures.invalid/a', diarize: false, num_speakers: 2 },
    { audio_url: 'https://fixtures.invalid/a', num_speakers: 2, diarization_threshold: 0.2 }]) assert.throws(() => validate(params));
  assert.throws(() => validateGeneration('audio', 'scribe-v2', { audio_url: 'https://fixtures.invalid/a', secondary_language_codes: [] }), /secondary_language_codes/);
  assert.ok(selectionPlan(cfg(), { ...request, model: 'scribe-v3', inputs: { audios: ['a.wav', 'b.wav'] } }).candidates[0]?.rejection);
});

test('packaged Relay CLI handles URL and multipart Scribe, full voice catalog, errors and recovery without replay', async () => {
  const exec = promisify(execFile); const dir = await mkdtemp(join(tmpdir(), 'aihub-relay-'));
  const posts: Record<string, unknown>[] = []; let errorCode: string | undefined; let taskFailure = false;
  const transcript = { text: 'Hello', words: [{ text: 'Hello', start: 0, end: 0.3, speaker_id: 'speaker_0', type: 'word' }], characters: [{ text: 'H', start: 0, end: 0.05 }] };
  const optionError = () => ({ code: errorCode, type: 'invalid_request_error', message: 'Requested controls are unavailable', unsupported_parameters: ['timestamps', 'clone_strength'], suggested_remove_parameters: ['timestamps'] });
  const server = createServer(async (req, res) => {
    const json = (data: unknown, status = 200) => res.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(data));
    assert.equal(req.headers.authorization, 'Bearer offline-relay');
    if (req.url === '/v1/models') return json({ data: ['scribe-v2', 'scribe-v3', 'eleven-v4', 'eleven-v4-turbo'].map(id => ({ id })) });
    if (req.url === '/e/v1/configs/elevenlabs-preset-voice-id') return json(Array.from({ length: 15450 }, (_, i) => ({ voice_id: `voice-${i}`, name: `Voice ${i}`, description: 'full metadata', preview_url: 'https://fixtures.invalid/preview.mp3', languages: ['en'], notice_period_days: 730 })));
    if (req.method === 'POST' && req.url === '/e/v1/audios/generations') {
      const parts: Buffer[] = []; for await (const part of req) parts.push(Buffer.from(part)); const bytes = Buffer.concat(parts);
      let params: Record<string, unknown>;
      if (req.headers['content-type']?.startsWith('multipart/')) {
        const form = await new Response(bytes, { headers: { 'Content-Type': req.headers['content-type'] } }).formData();
        const file = form.get('file') as File; assert.deepEqual(Buffer.from(await file.arrayBuffer()), Buffer.from('fixture-audio'));
        params = Object.fromEntries([...form.entries()].filter(([key]) => key !== 'file'));
        assert.equal(form.has('num_speakers'), false); assert.equal(params.no_verbatim, 'false'); assert.equal(params.temperature, '0');
        assert.equal(params.keyterms, '[]'); assert.equal(params.secondary_language_codes, '["en"]');
        params.file = file.name;
      } else params = JSON.parse(bytes.toString());
      posts.push(params);
      if (errorCode && !taskFailure) return json({ error: optionError() }, 422);
      return json({ id: `relay-${posts.length}`, model: params.model, status: 'processing' });
    }
    if (req.url?.startsWith('/e/v1/tasks/')) {
      const id = req.url.split('/').at(-1)!; const model = posts[Number(id.split('-').at(-1)) - 1]?.model;
      return json({ id, model, status: taskFailure ? 'failed' : 'completed', ...(taskFailure ? { error: optionError() } : { results: [transcript] }) });
    }
    return json({ error: 'Unexpected path' }, 404);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening'); const address = server.address(); assert(address && typeof address === 'object');
  const call = async (...args: string[]) => {
    try {
      const { stdout } = await exec(process.execPath, [resolve('scripts/aihub.mjs'), ...args, '--skill', 'aihub-audio', '--no-global-config'], { cwd: dir, env: { ...process.env, ...fixtureTransport(`http://127.0.0.1:${address.port}`), AIHUB_API_KEY: 'offline-relay', AIHUB_RESULT_CHECK_ENABLED: '0', AIHUB_AUDIO_MODELS: 'eleven-v4,eleven-v4-turbo' }, timeout: 45_000, maxBuffer: 16 * 1024 * 1024 });
      return JSON.parse(stdout);
    } catch (error) { const { stdout } = error as { stdout?: string }; if (!stdout) throw error; return JSON.parse(stdout); }
  };
  try {
    const voices = await call('voices'); assert.equal(voices.voices.length, 15450); assert.equal(voices.voices[15449].notice_period_days, 730); assert.equal(posts.length, 0);
    const file = join(dir, 'local.wav'); await writeFile(file, 'fixture-audio'); const requestFile = join(dir, 'request.json');
    for (const [model, input] of [['scribe-v2', 'https://fixtures.invalid/a.mp3'], ['scribe-v3', file]]) {
      await writeFile(requestFile, JSON.stringify({ operation: 'audio-transcribe', original_request: 'Transcribe without splitting', model, inputs: { audios: [input] }, requirements: model === 'scribe-v3' ? { keyterms: [], secondary_language_codes: ['en'], no_verbatim: false, temperature: 0, num_speakers: null } : {} }));
      const start = await call('run', '--request-file', requestFile, '--output-dir', dir); assert.equal(start.status, 'submitted', JSON.stringify(start)); const count: number = posts.length;
      const done = await call('continue', '--record', start.run_record, '--wait-seconds', '0'); assert.equal(done.status, 'delivered', JSON.stringify(done)); assert.equal(done.result.text, 'Hello');
      assert.deepEqual(JSON.parse(await readFile(done.files[0].path, 'utf8')), [transcript]);
      assert.equal((await call('continue', '--record', start.run_record, '--wait-seconds', '0')).status, 'delivered'); assert.equal(posts.length, count);
    }
    for (const code of ['requested_options_unavailable', 'unsupported_parameters']) for (const remoteFailure of [false, true]) {
      errorCode = code; taskFailure = remoteFailure;
      await writeFile(requestFile, JSON.stringify({ operation: 'audio-tts', original_request: 'Keep timestamps', prompt: 'Hello', requirements: { timestamps: true, clone_strength: 0 } }));
      const before: number = posts.length; let failed = await call('run', '--request-file', requestFile, '--output-dir', dir);
      if (remoteFailure) failed = await call('continue', '--record', failed.run_record, '--wait-seconds', '0');
      assert.equal(posts.length, before + 1, 'option errors must not submit a replacement model');
      assert.equal(failed.status, 'failed');
      const detail = remoteFailure ? failed.result.error : failed.result.failure.details;
      assert.equal(detail.type, 'invalid_request_error');
      assert.deepEqual(detail.unsupported_parameters, ['timestamps', 'clone_strength']); assert.deepEqual(detail.suggested_remove_parameters, ['timestamps']);
      const diagnostic = JSON.parse(await readFile(join(failed.run_record, '..', 'diagnostic.json'), 'utf8'));
      const event = diagnostic.events.at(-1);
      assert.equal(event.type, detail.type); assert.deepEqual(event.unsupported_parameters, detail.unsupported_parameters);
      assert.deepEqual(event.suggested_remove_parameters, detail.suggested_remove_parameters);
      assert.match(await readFile(join(failed.run_record, '..', 'error-report.md'), 'utf8'), /不得自动删参/);
      assert.match(await readFile(join(failed.run_record, '..', 'issue-draft.md'), 'utf8'), new RegExp(code));
      assert.equal(posts.at(-1)?.timestamps, true); assert.equal(posts.at(-1)?.clone_strength, 0);
      await call('continue', '--record', failed.run_record, '--wait-seconds', '0'); assert.equal(posts.length, before + 1);
    }
  } finally { server.closeAllConnections(); await new Promise<void>(done => server.close(() => done())); await rm(dir, { recursive: true, force: true }); }
});
