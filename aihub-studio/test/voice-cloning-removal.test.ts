import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AihubmaxClient } from '../src/apiClient.js';
import type { LoadedConfig } from '../src/config.js';
import { describe, models } from '../src/models.js';
import { selectionPlan } from '../src/selection.js';
import { generate } from '../src/workflow.js';

const cloningModels = ['voice-clone', 'minimax-voice-clone'];
const cloningIds = cloningModels.flatMap(model => [model, `minimax/${model}`, `${model}[preview]`]);
const config: LoadedConfig = { skill: 'aihub-audio', apiKey: 'offline-fixture', baseUrl: 'https://example.invalid',
  sources: { AIHUB_API_KEY: 'fixture' }, modelSelection: { policy: 'auto', sources: {} } };

test('audio planning rejects the removed cloning operation', () => {
  assert.throws(() => selectionPlan(config, {
    operation: 'audio-clone', original_request: 'Clone this voice',
    inputs: { audios: ['https://example.invalid/reference.wav'] },
  }), /Supported operations: audio-tts, audio-transcribe/);
});

test('old cloning preferences cannot replace speech synthesis or transcription', () => {
  const configured: LoadedConfig = { ...config, modelSelection: {
    policy: 'auto', models: [...cloningIds, 'speech-2.8-hd', 'paraformer-v2'], sources: {},
  } };
  for (const [operation, expected, input] of [
    ['audio-tts', 'speech-2.8-hd', { prompt: 'Welcome.' }],
    ['audio-transcribe', 'paraformer-v2', { inputs: { audios: ['https://example.invalid/recording.wav'] } }],
  ] as const) {
    const request = { operation, original_request: 'Process this audio request', ...input };
    const plan = selectionPlan(configured, request);
    assert.deepEqual(plan.candidates.map(candidate => candidate.model), [expected]);
    assert.equal(plan.candidates[0]?.rejection, undefined);
    for (const model of cloningIds) {
      const explicit = selectionPlan(configured, { ...request, model });
      assert.equal(explicit.policy, 'off');
      assert.deepEqual(explicit.candidates, []);
      assert.deepEqual(explicit.excluded.map(candidate => candidate.model), [model]);
    }
  }
});

test('cloning models and their family aliases are absent from live and offline model discovery', async () => {
  const client = new AihubmaxClient(config);
  client.listLiveModels = async () => new Map([...cloningIds, 'speech-2.8-hd', 'paraformer-v2'].map(id => [id, { id }]));
  const live = await models(client, 'audio');
  assert.equal(live.status, 'ok');
  assert.deepEqual(live.models.map(row => row.model), ['speech-2.8-hd', 'paraformer-v2']);
  assert.ok(live.catalog_only.every(row => !cloningModels.includes(row.model)));
  client.listLiveModels = async () => { throw new Error('Offline fixture'); };
  const offline = await models(client, 'audio');
  assert.equal(offline.status, 'availability_unknown');
  assert.ok(offline.catalog_only.every(row => !cloningModels.includes(row.model)));
  for (const model of cloningIds) assert.throws(() => describe(model), /Voice cloning has been removed/);
});

test('direct generation rejects cloning before network calls or task creation', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'aihub-no-cloning-'));
  const list = t.mock.method(AihubmaxClient.prototype, 'listLiveModels', async () => { throw new Error('Unexpected model lookup'); });
  const submit = t.mock.method(AihubmaxClient.prototype, 'submitGeneration', async () => { throw new Error('Unexpected generation'); });
  try {
    for (const model of cloningIds) {
      await assert.rejects(generate(config, {
        media: 'audio', model, params: { audio_url: 'https://example.invalid/reference.wav' },
        outputDir: join(directory, 'output'), waitSeconds: 0,
      }), /Voice cloning has been removed/);
    }
    assert.equal(list.mock.callCount(), 0);
    assert.equal(submit.mock.callCount(), 0);
    assert.deepEqual(await readdir(directory), []);
  } finally { await rm(directory, { recursive: true, force: true }); }
});
