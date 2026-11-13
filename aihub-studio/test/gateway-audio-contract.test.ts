import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { describe, validateGeneration } from '../src/models.js';
import { selectionPlan } from '../src/selection.js';
import { ELEVEN_AUDIO_MODELS, ELEVEN_SPEECH_MODELS } from '../src/elevenlabs.js';
import { result } from '../src/workflow.js';
import type { Job } from '../src/state.js';
import type { LoadedConfig } from '../src/config.js';
import { fixtureTransport } from './fixture-transport.js';

const source_url = 'https://fixtures.invalid/audio.wav';
const scribe = (params: Record<string, unknown> = {}) => validateGeneration('audio', 'scribe-v2', { source_url, ...params });
const cfg: LoadedConfig = { skill: 'aihub-audio', apiKey: 'fixture', baseUrl: 'https://fixture.invalid', sources: { AIHUB_API_KEY: 'fixture' } };

test('new usage and Scribe projections stay within the adapted model scope', () => {
  const task = { id: 'saved', status: 'completed' as const, usage: { credits_reserved: 0 }, results: [{ words: [], transcripts: [], channel_index: 0 }] };
  const job: Job = { schema_version: 1, local_id: 'saved', created_at: 'now', updated_at: 'now',
    skill: 'aihub-audio', media: 'audio', model: 'scribe-v2', service_url: cfg.baseUrl, credential_id: 'fixture',
    output_dir: 'fixture', files: [], failed: [], submission: { state: 'known', task } };
  assert.deepEqual(result(job, 'saved').result_metadata, { words: [], transcripts: [], channel_index: 0 });
  for (const model of [...ELEVEN_AUDIO_MODELS, 'scribe-v2', 'elevenlabs-music-v2.5']) assert.deepEqual(result({ ...job, model }, 'saved').usage, task.usage);
  for (const model of ['scribe-v3', 'paraformer-v2', 'gpt-image-2.6', 'sync-3', 'gemini-4-carbon', 'doc2x-v3']) {
    const output = result({ ...job, model }, 'saved');
    assert.equal(Object.hasOwn(output, 'usage'), false);
    assert.equal(Object.hasOwn(output, 'result_metadata'), false);
  }
});

test('renamed and moved fields explain migration before selection key rejection', () => {
  for (const model of ELEVEN_AUDIO_MODELS) {
    const speech = ELEVEN_SPEECH_MODELS.has(model);
    const operation = speech ? 'audio-tts' : 'audio-dialogue';
    const base = speech ? { text: 'Hi', voice_id: 'v' } : { inputs: [{ text: 'Hi', voice_id: 'v' }] };
    for (const field of ['voice', 'stability', 'similarity_boost', 'clone_strength', ...(speech ? ['future_text'] : [])]) {
      const params = { ...base, [field]: null };
      assert.throws(() => validateGeneration('audio', model, params), /migrate|moved/);
      const planned = selectionPlan(cfg, { operation, model, original_request: 'Keep all controls', ...(speech ? { prompt: 'Hi' } : {}),
        requirements: { ...(speech ? { voice_id: 'v' } : base), [field]: null } });
      assert.match(planned.candidates[0]?.rejection ?? '', /migrate|moved/);
    }
  }
  assert.throws(() => validateGeneration('audio', 'scribe-v2', { audio_url: source_url }), /audio_url.*source_url/);
});

test('Speech effects reject incompatible raw formats without changing explicit controls', () => {
  for (const model of ELEVEN_SPEECH_MODELS) {
    const check = (params: Record<string, unknown>) => validateGeneration('audio', model, { text: 'Hi', voice_id: 'v', ...params });
    for (const output_format of ['pcm_32000', 'ulaw_8000', 'alaw_8000']) {
      check({ output_format, audio_effects: { pan: 0, distance: 0, send_level: 0, environment_id: null } });
      for (const audio_effects of [{ pan: 0.1 }, { pan: -1 }, { environment_id: 'room' }]) assert.throws(() => check({ output_format, audio_effects }), /stereo/);
    }
    check({ output_format: 'wav_48000', audio_effects: { pan: -1, environment_id: 'room' }, enable_safety_checker: false });
    for (const audio_effects of [{ pan: 1.1 }, { distance: -0.1 }, { send_level: 2 }, { environment_id: '' }, { unexpected: true }]) assert.throws(() => check({ audio_effects }), /audio_effects/);
    for (const voice_id of ['', '  ', null]) assert.throws(() => check({ voice_id }), /voice_id/);
  }
});

test('Scribe v2 separates defaults and expanded keyword boundaries from v3', () => {
  const fields = describe('scribe-v2').params;
  for (const [key, value] of [['diarize', false], ['tag_audio_events', true], ['timestamps_granularity', 'word'], ['no_verbatim', false]]) assert.equal(fields.find(p => p.name === key)?.default, value);
  assert.equal(describe('scribe-v3').params.find(p => p.name === 'diarize')?.default, true);
  scribe({ keyterms: Array(1000).fill('👋'.repeat(50)), no_verbatim: false, temperature: 0, seed: 0 });
  for (const keyterms of [Array(1001).fill('word'), [''], ['👋'.repeat(51)], ['one two three four five six'], ['a<b'], ['a>b'], ['{a}'], ['[a]'], ['a\\b']]) assert.throws(() => scribe({ keyterms }), /keyterms/);
  assert.throws(() => validateGeneration('audio', 'scribe-v3', { audio_url: source_url, keyterms: Array(101).fill('word') }), /100/);
  for (const params of [{ num_speakers: 2 }, { diarization_threshold: 0.2 }, { timestamps_granularity: null }, { no_verbatim: null },
    { diarize: true, num_speakers: 33 }, { diarize: true, num_speakers: 2, diarization_threshold: 0.2 }, { temperature: 2.1 }, { seed: 2147483648 }]) assert.throws(() => scribe(params));
  scribe({ diarize: true, num_speakers: 32 }); scribe({ diarize: true, diarization_threshold: 0.1 });
  scribe({ diarize: true, diarization_threshold: 0.4 }); scribe({ language_code: ' ZHO ' });
  assert.throws(() => scribe({ language_code: 'cmn' }), /zh.*zho/);
  for (const language_code of ['', 'english', 'zh_CN']) assert.throws(() => scribe({ language_code }), /language_code/);
});

test('Scribe v2 validates role, edit, multichannel and entity combinations without rewriting selections', () => {
  scribe({ diarize: true, detect_speaker_roles: true, transcript_edit: 'Add punctuation' });
  scribe({ use_multi_channel: true, diarize: false, detect_speaker_roles: false });
  scribe({ entity_detection: ['pii', 'phi'], entity_redaction: ['credit_card', 'condition'] });
  scribe({ entity_detection: 'all', entity_redaction: 'offensive_language' });
  scribe({ entity_detection: [], entity_redaction: [], transcript_edit: '' });
  for (const params of [{ detect_speaker_roles: true }, { detect_speaker_roles: true, use_multi_channel: true },
    { use_multi_channel: true, diarize: true }, { use_multi_channel: true, num_speakers: 2 },
    { use_multi_channel: true, file_format: 'pcm_s16le_16' }, { use_multi_channel: true, transcript_edit: 'edit' },
    { transcript_edit: 'edit', entity_detection: 'pii' }, { transcript_edit: 'x'.repeat(2001) },
    { entity_detection: 'pci', entity_redaction: 'pii' }, { entity_redaction: 'name' },
    { entity_detection: '__proto__' }, { entity_detection: ['unknown'] }, { entity_detection: true }]) assert.throws(() => scribe(params));
  for (const params of [{}, { source_url, file: 'a.wav' }, { source_url: 'file:///a.wav' }]) assert.throws(() => validateGeneration('audio', 'scribe-v2', params));
  validateGeneration('audio', 'scribe-v2', { file: 'local.wav' });
  for (const field of ['source_url', 'detect_speaker_roles', 'transcript_edit', 'use_multi_channel', 'entity_detection']) assert.throws(() => validateGeneration('audio', 'scribe-v3', { audio_url: source_url, [field]: true }), new RegExp(field));
});

test('Music preserves explicit false timestamps and enforces C2PA and plan-only seed', () => {
  const music = (params: Record<string, unknown>) => validateGeneration('audio', 'elevenlabs-music-v2.5', params);
  for (const output_format of describe('elevenlabs-music-v2.5').params.find(p => p.name === 'output_format')!.enum!) {
    music({ prompt: 'Piano', output_format, timestamps: false });
    if (String(output_format).startsWith('mp3_') || output_format === 'auto') music({ prompt: 'Piano', output_format, sign_with_c2pa: true });
    else assert.throws(() => music({ prompt: 'Piano', output_format, sign_with_c2pa: true }), /C2PA|sign_with_c2pa/);
  }
  const composition_plan = { chunks: [{ text: '', duration_ms: 3000, positive_styles: Array(51).fill('ambient') }] };
  music({ composition_plan, seed: 2147483647 });
  assert.throws(() => music({ composition_plan, force_instrumental: false }), /including false/);
  assert.throws(() => music({ prompt: 'Piano', seed: 0 }), /seed/);
});

test('CLI sends v2 URL/multipart extensions, saves exact results and usage, and stops invalid voices', async () => {
  const exec = promisify(execFile); const dir = await mkdtemp(join(tmpdir(), 'aihub-gateway-contract-'));
  const posts: Record<string, unknown>[] = [];
  const words = [{ text: 'Hi', start: 0, end: 0.3, type: 'word', speaker_id: 'agent', logprob: 0 }, { text: ' ', start: 0.3, end: 0.3, type: 'spacing', speaker_id: 'customer' }];
  const results = [
    { text: 'Hi ', words, edited_transcript: { kind: 'transcript', text: 'Hi ', edited_text: 'Hi.', arbitrary: null } },
    { text: 'Hi ', words, edited_transcript: { kind: 'error', error_type: 'edit_unavailable', message: 'Try later' } },
    { text: 'Hi ', words, entities: [{ entity_type: 'name', text: 'Hi', start_char: 0, end_char: 2 }] },
    { transcripts: [{ text: 'Left', words, channel_index: 0 }, { text: 'Right', words: [], channel_index: 1 }], audio_duration_secs: 0.6 },
  ];
  const usage = { credits_reserved: 0, user_group: 'fixture-zero', returned_extension: { ratio: 0 } };
  const server = createServer(async (req, res) => {
    const json = (data: unknown, status = 200) => res.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(data));
    if (req.url === '/v1/models') return json({ data: ['scribe-v2', ...ELEVEN_SPEECH_MODELS].map(id => ({ id })) });
    if (req.method === 'POST') {
      const buffers: Buffer[] = []; for await (const buffer of req) buffers.push(Buffer.from(buffer));
      const bytes = Buffer.concat(buffers);
      let params: Record<string, unknown>;
      if (req.headers['content-type']?.startsWith('multipart/')) {
        const form = await new Response(bytes, { headers: { 'Content-Type': req.headers['content-type'] } }).formData();
        assert.equal(form.has('source_url'), false); assert.equal(form.has('audio_url'), false);
        assert.deepEqual(Buffer.from(await (form.get('file') as File).arrayBuffer()), Buffer.from('fixture-audio'));
        params = Object.fromEntries([...form.entries()].filter(([key]) => key !== 'file'));
        assert.equal(params.language_code, 'zho'); assert.equal(params.diarize, 'false');
        assert.equal(params.use_multi_channel, 'true'); assert.equal(params.temperature, '0');
        assert.equal(params.entity_detection, '["pii","phi"]'); assert.equal(params.keyterms, '["Gateway"]');
      } else params = JSON.parse(bytes.toString());
      posts.push(params);
      return json({ id: `contract-${posts.length}`, model: params.model, status: 'processing' });
    }
    if (req.url?.startsWith('/e/v1/tasks/')) {
      const index = Number(req.url.split('-').at(-1)) - 1; const model = posts[index]?.model;
      return json({ id: `contract-${index + 1}`, model, status: index < 4 ? 'completed' : 'failed',
        ...(index < 4 ? { results: [results[index]], usage } : { error: { code: 'audio_voice_unavailable', message: 'Voice is unavailable' } }) });
    }
    return json({ error: 'Unexpected route' }, 404);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening'); const address = server.address(); assert(address && typeof address === 'object');
  const call = async (...args: string[]) => {
    try {
      const { stdout } = await exec(process.execPath, [resolve('scripts/aihub.mjs'), ...args, '--skill', 'aihub-audio', '--no-global-config'],
        { cwd: dir, env: { ...process.env, ...fixtureTransport(`http://127.0.0.1:${address.port}`), AIHUB_API_KEY: 'offline-contract', AIHUB_RESULT_CHECK_ENABLED: '0', AIHUB_AUDIO_MODELS: [...ELEVEN_SPEECH_MODELS].join(',') }, timeout: 45_000 });
      return JSON.parse(stdout);
    } catch (error) { const { stdout } = error as { stdout?: string }; if (!stdout) throw error; return JSON.parse(stdout); }
  };
  try {
    const requestFile = join(dir, 'request.json'); const file = join(dir, 'local.wav'); await writeFile(file, 'fixture-audio');
    const requirements = [
      { diarize: true, detect_speaker_roles: true, transcript_edit: 'Punctuate', temperature: 0 },
      { transcript_edit: 'Punctuate', no_verbatim: false },
      { entity_detection: ['pii'], entity_redaction: ['credit_card'] },
      { use_multi_channel: true, diarize: false, temperature: 0, language_code: ' ZHO ', entity_detection: ['pii', 'phi'], keyterms: ['Gateway'] },
    ];
    for (const [index, requirement] of requirements.entries()) {
      await writeFile(requestFile, JSON.stringify({ operation: 'audio-transcribe', original_request: 'Transcribe with extensions', model: 'scribe-v2', inputs: { audios: [index === 3 ? file : source_url] }, requirements: requirement }));
      const start = await call('run', '--request-file', requestFile, '--output-dir', dir);
      assert.equal(start.status, 'submitted', JSON.stringify(start));
      if (index < 3) assert.deepEqual(posts[index], { model: 'scribe-v2', source_url, ...requirement });
      const done = await call('continue', '--record', start.run_record, '--wait-seconds', '0');
      assert.equal(done.status, 'delivered', JSON.stringify(done));
      assert.deepEqual(JSON.parse(await readFile(done.files[0].path, 'utf8')), [results[index]]);
      assert.deepEqual(done.result.usage, usage); assert.equal(done.result.result_metadata.alignment, undefined);
      if (index < 3) assert.deepEqual(done.result.result_metadata.words, words);
      assert.equal((await call('continue', '--record', start.run_record, '--wait-seconds', '0')).status, 'delivered');
      assert.equal(posts.length, index + 1, 'continuing a saved task never replays POST');
    }
    await writeFile(requestFile, JSON.stringify({ operation: 'audio-tts', original_request: 'Use this voice', prompt: 'Hi', requirements: { voice_id: 'unavailable' } }));
    const start = await call('run', '--request-file', requestFile, '--output-dir', dir);
    const failed = await call('continue', '--record', start.run_record, '--wait-seconds', '0');
    assert.equal(failed.status, 'failed'); assert.equal(failed.result.error.code, 'audio_voice_unavailable');
    assert.equal(posts.length, 5, 'invalid voice must not try the next configured model');
    await call('continue', '--record', start.run_record, '--wait-seconds', '0'); assert.equal(posts.length, 5);
  } finally { server.closeAllConnections(); await new Promise<void>(done => server.close(() => done())); await rm(dir, { recursive: true, force: true }); }
});
