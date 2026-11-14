import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { mkdir, mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import type { AddressInfo } from 'node:net';
import { AihubmaxClient, type TaskResponse } from '../src/apiClient.js';
import type { LoadedConfig } from '../src/config.js';
import { describe, validateGeneration } from '../src/models.js';
import { selectionPlan } from '../src/selection.js';
import { generate, resume, createVoice } from '../src/workflow.js';
import { readJob, writePrivateRecord } from '../src/state.js';
import { findTaskInfo, readTaskInfo, updateTaskInfo } from '../src/taskInfo.js';
import { VOICE_CREATE_MODEL as CREATE, VOICE_DESIGN_MODEL as DESIGN } from '../src/elevenlabs.js';
import { SAVE_VOICE_ID_NOTICE, voiceDesign } from '../src/voiceCreation.js';

const description = '自然、温暖、清晰的成年中文旁白声音，适合长篇知识讲解。';
const cfg: LoadedConfig = { skill: 'aihub-audio', apiKey: 'offline-fixture', baseUrl: 'https://fixture.invalid',
  sources: { AIHUB_API_KEY: 'fixture' }, modelSelection: { policy: 'auto', sources: {} } };
const selection = (task = 'design-1') => ({ design_task_id: task, generated_voice_id: 'candidate-B',
  auditioned_generated_voice_ids: ['candidate-A', 'candidate-B', 'candidate-C'], user_confirmation: '已试听全部三个候选，选第二个，保存为温暖旁白。',
  voice_name: '温暖旁白', voice_description: description, labels: { language: 'zh', purpose: '' } });

test('published Voice Design/Create contracts enforce alternatives, Unicode ranges and string labels', () => {
  assert.equal(describe(DESIGN).endpoint, 'POST /e/v1/audios/generations');
  assert.equal(describe(CREATE).request_schema?.properties?.labels?.anyOf?.[0]?.additionalProperties &&
    typeof describe(CREATE).request_schema?.properties?.labels?.anyOf?.[0]?.additionalProperties, 'object');
  const design = (params: Record<string, unknown>) => validateGeneration('audio', DESIGN, { voice_description: description, ...params });
  design({ auto_generate_text: true, seed: 0, loudness: -1, guidance_scale: 0, should_enhance: false, prompt_strength: 0 });
  design({ text: '👋'.repeat(100), auto_generate_text: false, reference_audio_base64: 'YXVkaW8=' });
  design({ auto_generate_text: true, text: null, reference_audio_base64: null });
  for (const fields of [{}, { text: '字'.repeat(99) }, { text: ' '.repeat(100) }, { text: '字'.repeat(1001) }, { auto_generate_text: true, text: '字'.repeat(100) },
    { auto_generate_text: true, quality: 'high' }, { auto_generate_text: true, seed: 2147483648 }, { auto_generate_text: true, reference_audio_base64: 'data:audio/wav;base64,YQ==' },
    { auto_generate_text: true, reference_audio_base64: 'https://fixture.invalid/a.wav' }, { auto_generate_text: true, voice_description: ' '.repeat(20) }]) assert.throws(() => design(fields));
  const create = { voice_name: '旁白', voice_description: description, generated_voice_id: 'candidate-B' };
  validateGeneration('audio', CREATE, { ...create, labels: { language: 'zh', empty: '' } });
  validateGeneration('audio', CREATE, { ...create, labels: null });
  validateGeneration('audio', CREATE, { ...create, voice_description: '  ' + '字'.repeat(1000) + '  ' });
  for (const fields of [{ labels: { language: 4 } }, { voice_name: '  ' }, { generated_voice_id: '' }, { voice_description: ' '.repeat(20) }, { text: 'unexpected' }]) {
    assert.throws(() => validateGeneration('audio', CREATE, { ...create, ...fields }));
  }
});

test('Voice Design has its own operation; existing defaults and explicit choices remain intact', () => {
  const request = { operation: 'audio-voice-design', original_request: '设计自然中文旁白，先试听再选择', requirements: { voice_description: description, auto_generate_text: true } };
  const plan = selectionPlan(cfg, request);
  assert.deepEqual(plan.candidates.map(c => c.model), [DESIGN]); assert.equal(plan.candidates[0]?.rejection, undefined);
  const custom = { ...cfg, modelSelection: { models: ['speech-2.8-hd'], policy: 'off' as const, sources: {} } };
  assert.deepEqual(selectionPlan(custom, request).candidates, [], 'never override a configured model list');
  assert.equal(selectionPlan(custom, { ...request, model: DESIGN }).candidates[0]?.model, DESIGN);
  assert.equal(selectionPlan(cfg, { operation: 'audio-tts', original_request: '朗读', prompt: '你好', requirements: { voice_id: 'saved-user-choice' } }).candidates[0]?.model, 'eleven-v4-text-to-speech');
  assert.equal(selectionPlan(cfg, { operation: 'audio-dialogue', original_request: '对话', requirements: { inputs: [{ text: '你好', voice_id: 'saved-user-choice' }] } }).candidates[0]?.model, 'eleven-v4-text-to-dialogue');
  assert.equal(selectionPlan(cfg, { operation: 'audio-transcribe', original_request: '转写', inputs: { audios: ['https://fixture.invalid/a.wav'] } }).candidates[0]?.model, 'paraformer-v2');
  assert.throws(() => selectionPlan(cfg, { ...request, operation: 'audio-voice-create' }), /operation must belong/);
});

test('all previews download; selection gate, free Create, recovery and full voice retention form one workflow', async t => {
  const root = resolve('tmp/voice-creation-tests'); await mkdir(root, { recursive: true });
  const dir = await mkdtemp(join(root, 'flow-'));
  const wav = Buffer.alloc(44 + 1600);
  wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28);
  wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(1600, 40);
  const downloads: string[] = [];
  const server = createServer((req, res) => { downloads.push(req.url!); res.setHeader('Content-Type', 'audio/wav'); res.end(wav); });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const rawDesign = { text: '欢迎收听'.repeat(30), previews: ['A', 'B', 'C'].map((id, i) => ({ generated_voice_id: `candidate-${id}`, url: `${base}/${id}.wav`, duration_secs: 0.1, media_type: 'audio/wav', language: i === 0 ? null : '', seed: 0 })), language: null, description: '', extra: { retained: true } };
  const rawVoice = { voice_id: 'saved-custom-id', name: '温暖旁白', category: 'generated', labels: {}, samples: null, sharing: null, settings: { stability: 0 }, extra: [] };
  let createStatus: 'completed' | 'processing' | 'failed' = 'completed';
  let createHasId = true;
  const posts: Array<Record<string, unknown>> = [];
  const queries: string[] = [];
  t.mock.method(AihubmaxClient.prototype, 'listLiveModels', async () => new Map([DESIGN, CREATE].map(id => [id, { id }])));
  t.mock.method(AihubmaxClient.prototype, 'submitGeneration', async (_path: string, body: Record<string, unknown>) => {
    posts.push(body);
    return body.model === DESIGN ? { id: 'design-1', model: DESIGN, status: 'completed', results: [rawDesign], usage: { quantity: [...rawDesign.text].length, unit: 'character' } }
      : { id: `create-${posts.length}`, model: CREATE, status: createStatus, results: createStatus === 'completed' ? [createHasId ? rawVoice : { name: 'no ID', samples: [] }] : null,
        ...(createStatus === 'failed' ? { error: { code: 'upstream_error', message: 'custom voice capacity 30/30' } } : {}), usage: { cost: 0 } };
  });
  let queried: TaskResponse;
  t.mock.method(AihubmaxClient.prototype, 'getTask', async (id: string) => { queries.push(id); return queried; });
  try {
    await assert.rejects(generate(cfg, { media: 'audio', model: CREATE, params: {}, outputDir: dir, waitSeconds: 0 }), /Direct Create generation is disabled/);
    assert.equal(posts.length, 0);
    const designed = await generate(cfg, { media: 'audio', model: DESIGN, params: { voice_description: description, auto_generate_text: true, seed: 0, should_enhance: false }, outputDir: dir, waitSeconds: 0 });
    assert.equal(designed.status, 'delivered'); assert.equal(posts.length, 1); assert.deepEqual(downloads.sort(), ['/A.wav', '/B.wav', '/C.wav']);
    const details = designed.voice_design as { previews: Array<Record<string, unknown>> };
    assert.equal(details.previews.length, 3); assert.ok(details.previews.every(p => p.file));
    assert.deepEqual(designed.result_metadata, rawDesign); assert.deepEqual(designed.usage, { quantity: [...rawDesign.text].length, unit: 'character' });
    const designRecord = String(designed.record);
    for (const invalid of [undefined, { ...selection(), user_confirmation: '' }, { ...selection(), generated_voice_id: 'not-from-this-design' },
      { ...selection(), auditioned_generated_voice_ids: ['candidate-B'] }, { ...selection(), auditioned_generated_voice_ids: ['candidate-A', 'candidate-A', 'candidate-B'] },
      { ...selection(), design_task_id: 'another-task' }, { ...selection(), labels: { number: 5 } }]) await assert.rejects(createVoice(cfg, designRecord, invalid, 0));
    assert.equal(posts.length, 1, 'invalid selections cannot submit Create');
    const created = await createVoice(cfg, designRecord, selection(), 0);
    assert.equal(created.status, 'delivered'); assert.equal(posts.length, 2);
    assert.equal(posts[1]?.generated_voice_id, 'candidate-B'); assert.equal(posts[1]?.model, CREATE);
    assert.deepEqual(posts[1]?.labels, { language: 'zh', purpose: '' });
    assert.equal(posts[1]?.user_confirmation, undefined, 'local selection evidence is not sent to the provider');
    assert.deepEqual(created.voice, rawVoice); assert.equal(created.voice_id, rawVoice.voice_id);
    assert.equal(created.user_notice, SAVE_VOICE_ID_NOTICE);
    const files = created.files as Array<{ path: string }>;
    assert.deepEqual(JSON.parse(await readFile(files.find(f => f.path.endsWith('.json'))!.path, 'utf8')), rawVoice);
    assert.match(await readFile(files.find(f => f.path.endsWith('.md'))!.path, 'utf8'), /平台不提供音色列表、音色查询或 ID 找回功能/);
    const taskInfo = (await findTaskInfo(designRecord))!;
    const childEntry = (await readTaskInfo(taskInfo)).records.find(entry => resolve(dirname(taskInfo), entry.path) === created.record);
    assert.equal(childEntry?.kind, 'aihub-job'); assert.equal(childEntry?.purpose, 'primary');
    assert.equal((await readTaskInfo(taskInfo)).delivery?.status, 'completed');
    // Recovery repairs the artifact index even after previews have been removed; it never submits again.
    await updateTaskInfo(taskInfo, info => { info.records = info.records.filter(entry => entry.path !== childEntry!.path); });
    await rm(String(details.previews[2]!.file));
    queried = { id: String(created.task_id), model: CREATE, status: 'completed', results: [rawVoice] };
    const restored = await createVoice(cfg, designRecord, undefined, 0);
    assert.equal(restored.voice_id, 'saved-custom-id'); assert.equal(posts.length, 2); assert.ok(queries.length);
    assert.equal((await readTaskInfo(taskInfo)).records.filter(entry => entry.path === childEntry!.path).length, 1);
    await assert.rejects(createVoice(cfg, designRecord, { ...selection(), generated_voice_id: 'candidate-A' }, 0), /another selection/);
    // Missing preview prevents a second design from reaching Create.
    const missing = await generate(cfg, { media: 'audio', model: DESIGN, params: { voice_description: description, auto_generate_text: true }, outputDir: dir, waitSeconds: 0 });
    const missingJob = await readJob(String(missing.record));
    await rm(missingJob.files.find(f => f.url.endsWith('/C.wav'))!.path);
    await assert.rejects(createVoice(cfg, String(missing.record), selection(), 0));
    // A definite capacity failure remains a failure on repeated recovery, with no second Create.
    createStatus = 'failed';
    const failedDesign = await generate(cfg, { media: 'audio', model: DESIGN, params: { voice_description: description, auto_generate_text: true }, outputDir: dir, waitSeconds: 0 });
    const failed = await createVoice(cfg, String(failedDesign.record), selection(), 0);
    assert.equal(failed.status, 'remote_failed'); assert.equal(failed.voice_id, undefined);
    const failedInfo = (await findTaskInfo(String(failedDesign.record)))!;
    assert.ok((await readTaskInfo(failedInfo)).records.some(entry => resolve(dirname(failedInfo), entry.path) === failed.record), 'failed Create remains visible in the artifact task');
    assert.equal((await readTaskInfo(failedInfo)).delivery?.status, 'partial');
    assert.match((await readTaskInfo(failedInfo)).delivery!.reason, /音色创建失败/);
    queried = { id: String(failed.task_id), model: CREATE, status: 'failed', error: { code: 'upstream_error', message: 'custom voice capacity 30/30' } };
    const before = posts.length;
    assert.equal((await createVoice(cfg, String(failedDesign.record), undefined, 0)).status, 'remote_failed'); assert.equal(posts.length, before);
    // An intent persisted without a task pointer is unknown, never safe to resubmit.
    const unknownDesign = await generate(cfg, { media: 'audio', model: DESIGN, params: { voice_description: description, auto_generate_text: true }, outputDir: dir, waitSeconds: 0 });
    createStatus = 'processing';
    const pending = await createVoice(cfg, String(unknownDesign.record), selection(), 0);
    const statePath = String(pending.creation_record);
    const state = JSON.parse(await readFile(statePath, 'utf8')); delete state.task_record; delete state.result;
    await writePrivateRecord(statePath, state);
    const unknownPosts = posts.length;
    assert.equal((await createVoice(cfg, String(unknownDesign.record), undefined, 0)).status, 'submission_unknown'); assert.equal(posts.length, unknownPosts);
    // A malformed completed Create cannot be reported as a saved voice.
    const malformedDesign = await generate(cfg, { media: 'audio', model: DESIGN, params: { voice_description: description, auto_generate_text: true }, outputDir: dir, waitSeconds: 0 });
    createStatus = 'completed'; createHasId = false;
    const malformed = await createVoice(cfg, String(malformedDesign.record), selection(), 0);
    assert.equal(malformed.status, 'download_failed'); assert.equal(malformed.voice_id, undefined); assert.deepEqual(malformed.result_metadata, { name: 'no ID', samples: [] });
  } finally {
    server.closeAllConnections(); await new Promise<void>(done => server.close(() => done()));
    await rm(dir, { recursive: true, force: true });
  }
});

test('incomplete Design results cannot become synthesized voice IDs', () => {
  for (const result of [{}, { text: '', previews: [] }, { text: 'test', previews: [{ generated_voice_id: 'one', url: 'data:audio/wav;base64,YQ==' }] },
    { text: 'test', previews: [{ generated_voice_id: 'one', url: 'https://fixture.invalid/one' }, { generated_voice_id: 'one', url: 'https://fixture.invalid/two' }] }]) {
    assert.throws(() => voiceDesign({ id: 'design-1', status: 'completed', results: [result] }));
  }
});
