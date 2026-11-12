import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import type { AddressInfo } from 'node:net';
import type { LoadedConfig } from '../src/config.js';
import { selectionPlan } from '../src/selection.js';
import { describe, validateGeneration } from '../src/models.js';
import { fixtureTransport } from './fixture-transport.js';

const music = 'elevenlabs-music-v2.5';
const config = (skill: string, models?: string[]): LoadedConfig => ({ skill, apiKey: 'fixture', baseUrl: 'https://fixture.invalid',
  sources: { AIHUB_API_KEY: 'fixture' }, speech: { defaultVoiceId: 'MiniMax-specific-voice', source: 'fixture' }, modelSelection: { policy: 'auto', models, sources: {} } });
const speechRequest = { operation: 'audio-tts', original_request: 'Read this text aloud', prompt: '[whispering] Hello café 👋' };
const musicRequest = { operation: 'music-async', original_request: 'Make an instrumental', prompt: 'Gentle piano' };
const chunk = { text: '', duration_ms: 3000, positive_styles: ['ambient'] };
const planParams = (extra: Record<string, unknown> = {}) => ({ composition_plan: { chunks: [{ ...chunk, ...extra }] } });
const validate = (params: Record<string, unknown>) => validateGeneration('audio', music, params);

test('ElevenLabs defaults preserve explicit selection and personal order', () => {
  assert.equal(selectionPlan(config('aihub-audio'), speechRequest).candidates[0]?.model, 'eleven-v4');
  assert.equal(selectionPlan(config('aihub-music'), musicRequest).candidates[0]?.model, music);
  const configured = selectionPlan(config('aihub-audio', ['eleven-v4-turbo', 'eleven-v4', 'paraformer-v2']), speechRequest);
  assert.deepEqual(configured.candidates.map(c => c.model), ['eleven-v4-turbo', 'eleven-v4']);
  assert.equal(configured.source, 'configuration'); assert.equal(configured.excluded.length, 1);
  assert.ok(configured.candidates.every(c => !c.rejection));
  const explicit = selectionPlan(config('aihub-audio', ['speech-2.8-hd']), { ...speechRequest, model: 'eleven-v4' });
  assert.equal(explicit.source, 'user'); assert.equal(explicit.policy, 'off');
  assert.deepEqual(explicit.candidates[0]?.params, { text: speechRequest.prompt });
  assert.deepEqual(explicit.request, { ...speechRequest, model: 'eleven-v4' });
  const native = selectionPlan(config('aihub-music', [music, 'lyria-3-pro-preview']), { ...musicRequest, operation: 'music-native' });
  assert.deepEqual(native.candidates.map(c => c.model), ['lyria-3-pro-preview']);
});

test('TTS options remain exact and MiniMax parameters cannot leak into ElevenLabs', () => {
  const requirements = { voice: 'custom voice ID', stability: 0, similarity_boost: 1, seed: 4294967295, language_code: 'zh',
    apply_text_normalization: 'off', timestamps: true, enable_safety_checker: false, output_format: 'opus_48000_192' };
  for (const model of ['eleven-v4', 'eleven-v4-turbo']) {
    const p = selectionPlan(config('aihub-audio'), { ...speechRequest, model, requirements });
    assert.equal(p.candidates[0]?.rejection, undefined);
    assert.deepEqual(p.candidates[0]?.params, { text: speechRequest.prompt, ...requirements });
    for (const field of ['voice_setting', 'audio_setting', 'voice_modify', 'pronunciation_dict', 'language_boost']) {
      const invalid = selectionPlan(config('aihub-audio'), { ...speechRequest, model, requirements: { [field]: {} } });
      assert.match(invalid.candidates[0]?.rejection ?? '', new RegExp(field));
      assert.throws(() => validateGeneration('audio', model, { text: 'Hello', [field]: {} }), new RegExp(field));
    }
    assert.equal(describe(model).params.find(p => p.name === 'voice')?.default, 'Rachel');
    assert.throws(() => validateGeneration('audio', model, { prompt: 'old field' }), /text/);
  }
});

test('TTS contract enforces lengths, ranges, formats and nullable fields without altering text', () => {
  const valid = (params: Record<string, unknown>) => validateGeneration('audio', 'eleven-v4', params);
  valid({ text: '👋'.repeat(5000), seed: null, language_code: null });
  for (const [field, value] of [['text', ''], ['text', 'a'.repeat(5001)], ['stability', -0.1], ['similarity_boost', 1.01],
    ['seed', 4294967296], ['seed', 0.5], ['timestamps', 'true'], ['voice', null], ['output_format', 'wav'], ['apply_text_normalization', 'yes']] as const) {
    assert.throws(() => valid({ text: 'Hello', [field]: value }), new RegExp(field));
  }
  const fields = describe('eleven-v4').params;
  assert.equal(fields.find(p => p.name === 'output_format')?.enum?.length, 19);
});

test('music prompt and plan modes preserve nested inputs and reject discarded legacy requirements', () => {
  const requirements = { music_length_ms: 60001, force_instrumental: true, output_format: 'pcm_44100', enable_safety_checker: true };
  const prompt = selectionPlan(config('aihub-music', [music, 'lyria-3-pro']), { ...musicRequest, requirements });
  assert.deepEqual(prompt.candidates[0]?.params, { prompt: musicRequest.prompt, ...requirements });
  assert.equal(prompt.candidates[0]?.rejection, undefined);
  assert.match(prompt.candidates[1]?.rejection ?? '', /music_length_ms/);
  const composition = { chunks: [{ ...chunk, duration_ms: 59900, text: '[Verse 1]\nHello', negative_styles: ['distortion'],
    context_adherence: 'high', audio_reference: { audio_url: 'https://fixtures.invalid/reference.wav', start_ms: 1500, end_ms: 31500, strength: 'xhigh' } }] };
  const plan = selectionPlan(config('aihub-music'), { operation: 'music-async', original_request: 'Follow this plan', model: music,
    requirements: { composition_plan: composition, seed: 42 } });
  assert.equal(plan.candidates[0]?.rejection, undefined);
  assert.deepEqual(plan.candidates[0]?.params, { composition_plan: composition, seed: 42 });
  for (const extra of [{ requirements: { negative_prompt: 'no drums' } }, { inputs: { images: ['https://fixtures.invalid/a.png'] } },
    { inputs: { audios: ['https://fixtures.invalid/a.wav'] } }]) {
    assert.ok(selectionPlan(config('aihub-music'), { ...musicRequest, model: music, ...extra }).candidates[0]?.rejection);
  }
  for (const field of ['image_urls', 'negative_prompt', 'lyrics']) assert.throws(() => validate({ prompt: 'Piano', [field]: 'keep me' }), new RegExp(field));
});

test('music contract rejects conflicting modes and invalid duration or plan shapes', () => {
  for (const params of [{}, { prompt: 'Piano', ...planParams() }, { prompt: 'Piano', seed: 0 }, { ...planParams(), music_length_ms: 3000 },
    { ...planParams(), force_instrumental: true }]) assert.throws(() => validate(params), /exactly one|only supported/);
  for (const music_length_ms of [3000, 59900, 60000, 60001, 600000]) validate({ prompt: 'Piano', music_length_ms });
  validate({ prompt: 'Piano' }); validate({ prompt: 'Piano', music_length_ms: null, seed: null, timestamps: false });
  validate({ ...planParams(), music_length_ms: null, force_instrumental: false, timestamps: null });
  for (const music_length_ms of [2999, 600001, 3000.1, '60000']) assert.throws(() => validate({ prompt: 'Piano', music_length_ms }), /music_length_ms/);
  for (const duration of [60, null]) assert.throws(() => validate({ prompt: 'Piano', duration }), /migrate.*music_length_ms/);
  for (const duration of [3, null]) assert.throws(() => validate(planParams({ duration })), /migrate.*duration_ms/);
  assert.throws(() => validate({ prompt: 'x'.repeat(4101) }), /4100/);
  assert.throws(() => validate({ composition_plan: { chunks: [] } }), /chunks/);
  assert.throws(() => validate({ composition_plan: { chunks: Array(31).fill(chunk) } }), /30/);
  assert.throws(() => validate(planParams({ duration_ms: 120001 })), /duration_ms/);
  assert.throws(() => validate(planParams({ duration_ms: 3000.1 })), /duration_ms/);
  assert.throws(() => validate(planParams({ positive_styles: [42] })), /positive_styles/);
  assert.throws(() => validate(planParams({ context_adherence: 'xhigh' })), /context_adherence/);
  assert.throws(() => validate(planParams({ unexpected: true })), /unexpected/);
  assert.throws(() => validate({ composition_plan: { chunks: [chunk], unexpected: true } }), /unexpected/);
  const longPlan = { composition_plan: { chunks: Array(5).fill({ ...chunk, duration_ms: 120000 }) } };
  validate(longPlan);
  assert.throws(() => validate({ composition_plan: { chunks: [...longPlan.composition_plan.chunks, chunk] } }), /600000 milliseconds/);
  assert.equal(describe(music).params.find(p => p.name === 'output_format')?.enum?.length, 25);
  assert.deepEqual(describe(music).conditionally_required_params, ['prompt', 'composition_plan']);
  assert.ok(describe(music).request_schema?.properties?.composition_plan);
});

test('music validates text and reference windows without mixing seconds and milliseconds', () => {
  const reference = { audio_url: 'https://fixtures.invalid/a.wav' };
  validate(planParams({ audio_reference: reference }));
  validate(planParams({ audio_reference: { ...reference, start_ms: 1000, end_ms: 31000 } }));
  for (const extra of [{ start_ms: -1 }, { start_ms: 0.5 }, { start_ms: 1000, end_ms: 1000 }, { end_ms: 30001 },
    { end_ms: 0 }, { audio_url: 'file:///a.wav' }, { audio_url: 'https://user:password@fixtures.invalid/a.wav' },
    { strength: 'invalid' }, { duration: 30 }]) {
    assert.throws(() => validate(planParams({ audio_reference: { ...reference, ...extra } })), /audio_reference/);
  }
  for (const text of ['x\n'.repeat(30), '👋'.repeat(201), '[]\nhello', `[${'a'.repeat(101)}]`]) {
    assert.throws(() => validate(planParams({ text })), /text/);
  }
  validate(planParams({ text: '👋'.repeat(200), negative_styles: null, context_adherence: null, audio_reference: null }));
});

test('packaged CLI preserves timestamps and real containers through billing wait and download recovery', async () => {
  const exec = promisify(execFile);
  const dir = await mkdtemp(join(tmpdir(), 'aihub-elevenlabs-'));
  const timestamps = JSON.parse(await readFile(new URL('./fixtures/elevenlabs-timestamps.json', import.meta.url), 'utf8'));
  const alignment = { characters: ['H'], character_start_times_seconds: [0], character_end_times_seconds: [0.1] };
  const musicMetadata = { composition_plan: { chunks: [{ duration_ms: 60000 }] }, song_metadata: { title: 'Fixture' }, words_timestamps: [] };
  assert.equal(timestamps.length, 7);
  assert.equal(timestamps.filter((t: { characters: string[] }) => !t.characters.length).length, 2);
  const files = new Map<string, Buffer>();
  for (const [extension, codec] of [['wav', 'pcm_s16le'], ['ogg', 'libopus'], ['mp3', 'libmp3lame']]) {
    const path = join(dir, `fixture.${extension}`);
    await exec('ffmpeg', ['-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2', '-c:a', codec!, '-y', path]);
    files.set(extension!, await readFile(path));
  }
  const posts: Array<Record<string, unknown>> = [];
  const queries: string[] = [];
  const models = ['eleven-v4', 'eleven-v4-turbo', music];
  let base = ''; let settled = false; let serveMusic = false;
  const server = createServer(async (req, res) => {
    const json = (data: unknown, code = 200) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
    if (req.url === '/v1/models') return json({ data: models.map(id => ({ id })) });
    if (req.method === 'POST' && req.url === '/e/v1/audios/generations') {
      let text = ''; for await (const piece of req) text += piece;
      const body = JSON.parse(text); posts.push(body);
      return json({ id: `eleven-${posts.length}`, model: body.model, status: 'processing' });
    }
    if (req.url?.startsWith('/e/v1/tasks/')) {
      queries.push(req.url);
      const index = Number(req.url.split('-').at(-1)) - 1;
      const model = posts[index]?.model;
      const task = { id: `eleven-${index + 1}`, model, status: settled ? 'completed' : 'processing' };
      return json({ ...task, ...(settled ? { results: [{ url: `${base}/asset-${index}.pcm`, content_type: 'application/octet-stream',
        ...(index < 2 ? { timestamps, alignment, normalized_alignment: alignment } : musicMetadata) }] } : {}) });
    }
    const asset = /^\/asset-(\d)\.pcm$/.exec(req.url ?? '');
    if (asset) {
      if (asset[1] === '2' && !serveMusic) return json({ error: 'Not ready' }, 404);
      res.writeHead(200, { 'Content-Type': 'application/octet-stream' });
      return res.end(files.get(['mp3', 'ogg', 'wav'][Number(asset[1])]!));
    }
    return json({ error: 'Unexpected route' }, 404);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const requestPath = join(dir, 'request.json');
  const call = async (skill: string, ...args: string[]) => {
    try {
      const { stdout } = await exec(process.execPath, [resolve('scripts/aihub.mjs'), ...args, '--skill', skill, '--no-global-config'],
        { cwd: dir, env: { ...process.env, ...fixtureTransport(base), AIHUB_API_KEY: 'offline-elevenlabs', AIHUB_RESULT_CHECK_ENABLED: '0',
          AIHUB_AUDIO_MODELS: 'speech-2.8-hd', AIHUB_MUSIC_MODELS: 'lyria-3-pro', AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID: 'MiniMax-voice' }, timeout: 30_000 });
      return JSON.parse(stdout);
    } catch (error) {
      const { stdout } = error as { stdout?: string }; if (!stdout) throw error; return JSON.parse(stdout);
    }
  };
  try {
    for (const [index, model] of models.entries()) {
      settled = false;
      const isMusic = model === music; const skill = isMusic ? 'aihub-music' : 'aihub-audio';
      const request = { ...(isMusic ? musicRequest : speechRequest), model, requirements: isMusic
        ? { music_length_ms: 60000, output_format: 'pcm_44100' }
        : { timestamps: true, ...(index === 1 ? { output_format: 'opus_48000_128' } : {}) } };
      await writeFile(requestPath, JSON.stringify(request));
      const planned = await call(skill, 'plan', '--request-file', requestPath);
      assert.equal(planned.candidates[0].rejection, undefined);
      const start = await call(skill, 'run', '--request-file', requestPath, '--output-dir', dir, '--wait-seconds', '0');
      assert.ok(['submitted', 'waiting'].includes(start.status), JSON.stringify(start));
      assert.equal(posts.length, index + 1);
      assert.deepEqual(posts[index], { model, ...planned.candidates[0].params });
      const waiting = await call(skill, 'continue', '--record', start.run_record, '--wait-seconds', '0');
      assert.equal(waiting.status, 'waiting'); assert.equal(waiting.task_id, start.task_id);
      assert.equal(posts.length, index + 1, 'reconciliation wait must query the existing task');
      settled = true;
      let delivered = await call(skill, 'continue', '--record', start.run_record, '--wait-seconds', '0');
      if (isMusic) {
        assert.equal(delivered.status, 'download_failed');
        serveMusic = true;
        delivered = await call(skill, 'continue', '--record', start.run_record, '--wait-seconds', '0');
      }
      assert.equal(delivered.status, 'delivered', JSON.stringify(delivered));
      assert.equal(delivered.files.length, 1);
      assert.ok(delivered.files[0].path.endsWith(['.mp3', '.ogg', '.wav'][index]));
      assert.equal(delivered.files[0].mime_type, ['audio/mpeg', 'audio/ogg', 'audio/wav'][index]);
      assert.equal(posts.length, index + 1);
      const job = JSON.parse(await readFile(delivered.result.record, 'utf8'));
      if (!isMusic) {
        assert.deepEqual(delivered.result.result_metadata.timestamps, timestamps);
        assert.deepEqual(delivered.result.result_metadata.alignment, alignment);
        assert.deepEqual(delivered.result.result_metadata.normalized_alignment, alignment);
        assert.deepEqual(job.submission.task.results[0].timestamps, timestamps);
      } else {
        assert.deepEqual(delivered.result.result_metadata, musicMetadata);
        assert.equal(delivered.result.result_metadata.duration, undefined, 'do not invent duration or billed minutes');
        assert.equal(posts[index]?.music_length_ms, 60000, 'requested milliseconds are preserved, never converted to a billing estimate');
      }
      const resumed = await call(skill, 'resume', '--record', delivered.result.record, '--wait-seconds', '0');
      assert.equal(resumed.status, 'delivered'); assert.deepEqual(resumed.files, delivered.files);
      if (!isMusic) assert.deepEqual(resumed.result_metadata.timestamps, timestamps);
      assert.equal(posts.length, index + 1);
    }
    assert.ok(queries.length >= 6);
    await writeFile(requestPath, JSON.stringify({ ...musicRequest, model: music, requirements: { negative_prompt: 'no drums' } }));
    assert.equal((await call('aihub-music', 'run', '--request-file', requestPath, '--output-dir', dir, '--wait-seconds', '0')).status, 'no_compatible_model');
    assert.equal(posts.length, 3);
  } finally {
    server.closeAllConnections(); await new Promise<void>(done => server.close(() => done()));
    await rm(dir, { recursive: true, force: true });
  }
});
