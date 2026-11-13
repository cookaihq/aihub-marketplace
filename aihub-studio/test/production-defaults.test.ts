import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import type { AddressInfo } from 'node:net';
import type { LoadedConfig } from '../src/config.js';
import { AihubmaxClient } from '../src/apiClient.js';
import { selectionPlan } from '../src/selection.js';
import { describe, models, validateGeneration } from '../src/models.js';
import { fixtureTransport } from './fixture-transport.js';

const exec = promisify(execFile);
const cfg = (skill: string, configured?: string[]): LoadedConfig => ({ skill, baseUrl: 'https://example.invalid', apiKey: 'fixture',
  sources: { AIHUB_API_KEY: 'fixture' }, modelSelection: { policy: 'auto', models: configured, sources: {} } });
const generation = { operation: 'image-generate', original_request: 'A blue circle', prompt: 'A blue circle' };
const editing = { ...generation, operation: 'image-edit', inputs: { images: ['https://example.invalid/source.png'], mask: 'https://example.invalid/mask.png' } };

test('new image defaults preserve the generation/edit boundary, input assets and personal choices', () => {
  for (const image_priority of ['speed', 'detail']) {
    const suffix = image_priority === 'detail' ? 'sunburst' : 'flare';
    const created = selectionPlan(cfg('aihub-image'), { ...generation, image_priority }).candidates[0]!;
    assert.equal(created.model, `gpt-image-2.6-${suffix}`);
    assert.deepEqual(created.params, { prompt: generation.prompt });
    const edited = selectionPlan(cfg('aihub-image'), { ...editing, image_priority }).candidates[0]!;
    assert.equal(edited.model, `gpt-image-2.5-${suffix}`);
    assert.deepEqual(edited.params, { prompt: generation.prompt, image_urls: editing.inputs.images, mask_url: editing.inputs.mask });
  }
  const personal = cfg('aihub-image', ['gpt-image-2.6-sunburst', 'gpt-image-2.5-flare']);
  assert.equal(selectionPlan(personal, generation).candidates[0]?.model, 'gpt-image-2.6-sunburst');
  assert.equal(selectionPlan(personal, editing).candidates[0]?.model, 'gpt-image-2.5-flare');
  const fixed = selectionPlan(personal, { ...editing, model: 'gpt-image-2.6-flare' });
  assert.equal(fixed.policy, 'off'); assert.deepEqual(fixed.candidates, []);
  assert.equal(fixed.excluded[0]?.model, 'gpt-image-2.6-flare');
  const preserved = selectionPlan(cfg('aihub-image'), { ...generation, inputs: editing.inputs });
  assert.match(preserved.candidates[0]!.rejection!, /input|not supported/);
  assert.deepEqual(preserved.request.inputs, editing.inputs);
});

test('Image 2.6 describes and enforces static inputs without promising requested output metadata', () => {
  for (const model of ['gpt-image-2.6-flare', 'gpt-image-2.6-sunburst']) {
    const contract = describe(model);
    assert.match(contract.capability, /static text-to-image/);
    assert.equal(contract.params.find(field => field.name === 'resolution')?.default, 'auto');
    assert.ok(!contract.params.some(field => ['image_urls', 'mask_url'].includes(field.name)));
    for (const quality of ['auto', 'low', 'medium', 'high', 'xhigh', 'max']) {
      assert.equal(validateGeneration('image', model, { prompt: 'A circle', quality, complexity: 'medium' }), '/e/v1/images/generations');
    }
    for (const params of [{ image_urls: null }, { image_urls: ['https://example.invalid/a.png'] }, { mask_url: null }, { markup: '<svg/>' }]) {
      assert.throws(() => validateGeneration('image', model, { prompt: 'A circle', ...params }), /static text-to-image/);
    }
    for (const output_format of ['gif', 'svg']) assert.throws(() => validateGeneration('image', model, { prompt: 'A circle', output_format }), /output_format/);
    assert.throws(() => validateGeneration('image', model, { prompt: 'A circle', complexity: 'extreme' }), /complexity/);
    assert.throws(() => validateGeneration('image', model, { prompt: 'A circle', resolution: { width: 1025, height: 1024 } }), /resolution/);
  }
});

test('model discovery distinguishes image task defaults and marks the approved audio defaults', async () => {
  const ids = ['gpt-image-2.6-flare', 'gpt-image-2.6-sunburst', 'gpt-image-2.5-flare', 'gpt-image-2.5-sunburst',
    'eleven-v4-text-to-speech', 'eleven-v4-text-to-dialogue', 'speech-2.8-hd', 'elevenlabs-music-v2.5', 'lyria-3-pro', 'paraformer-v2', 'scribe-v3', 'suno-v6'];
  const client = new AihubmaxClient(cfg('aihub-image'));
  client.listLiveModels = async () => new Map(ids.map(id => [id, { id }]));
  const output = await models(client);
  assert.deepEqual(output.models.filter(row => row.default).map(row => row.model), [
    'gpt-image-2.6-flare', 'gpt-image-2.5-flare', 'eleven-v4-text-to-speech', 'eleven-v4-text-to-dialogue', 'paraformer-v2', 'suno-v6',
  ]);
  const imageRows = output.models as Array<{ model: string; default_for?: string[] }>;
  assert.deepEqual(imageRows.find(row => row.model === 'gpt-image-2.6-flare')?.default_for, ['image-generate']);
  assert.deepEqual(imageRows.find(row => row.model === 'gpt-image-2.5-flare')?.default_for, ['image-edit']);
});

test('packaged CLI submits the new defaults and editing model, then resumes without another generation', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'aihub-production-defaults-'));
  const audioPath = join(dir, 'fixture.wav'); const imagePath = join(dir, 'fixture.png');
  await exec('ffmpeg', ['-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.1', '-y', audioPath]);
  await exec('ffmpeg', ['-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=16x16', '-frames:v', '1', '-y', imagePath]);
  const audio = await readFile(audioPath); const image = await readFile(imagePath);
  const posts: Array<Record<string, unknown>> = []; let base = '';
  const server = createServer(async (req, res) => {
    const json = (value: unknown) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(value)); };
    if (req.url === '/v1/models') return json({ data: ['gpt-image-2.6-flare', 'gpt-image-2.5-flare', 'eleven-v4-text-to-speech', 'suno-v6'].map(id => ({ id })) });
    if (req.method === 'POST') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      const body = JSON.parse(raw); posts.push(body);
      const isImage = String(body.model).startsWith('gpt-image');
      return json({ id: `fixture-${posts.length}`, model: body.model, status: 'completed', results: [{ url: `${base}/${isImage ? 'fixture.png' : 'fixture.wav'}` }] });
    }
    const isImage = req.url === '/fixture.png'; res.setHeader('Content-Type', isImage ? 'image/png' : 'audio/wav'); res.end(isImage ? image : audio);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening'); base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const env = { ...process.env, ...fixtureTransport(base), AIHUB_API_KEY: 'offline-production-defaults',
    AIHUB_IMAGE_MODELS: '', AIHUB_AUDIO_MODELS: '', AIHUB_MUSIC_MODELS: '', AIHUB_RESULT_CHECK_ENABLED: '0', AIHUB_MODEL_FALLBACK_POLICY: '' };
  const cli = async (skill: string, ...args: string[]) => {
    const { stdout } = await exec(process.execPath, [resolve('scripts/aihub.mjs'), ...args, '--skill', skill, '--no-global-config'], { cwd: dir, env, timeout: 30_000 });
    return JSON.parse(stdout);
  };
  try {
    const cases = [
      ['aihub-image', generation, { prompt: generation.prompt, model: 'gpt-image-2.6-flare' }],
      ['aihub-image', editing, { prompt: generation.prompt, image_urls: editing.inputs.images, mask_url: editing.inputs.mask, model: 'gpt-image-2.5-flare' }],
      ['aihub-audio', { operation: 'audio-tts', original_request: 'Say hello', prompt: 'Hello', requirements: { voice_id: 'existing-eleven-voice' } }, { text: 'Hello', voice_id: 'existing-eleven-voice', model: 'eleven-v4-text-to-speech' }],
      ['aihub-music', { operation: 'music-description', original_request: 'Piano music', prompt: 'Piano music', requirements: { duration: 30 } }, { prompt: 'Piano music', duration: 30, mode: 'description', is_instrumental: false, model: 'suno-v6' }],
    ] as const;
    for (const [skill, request, expected] of cases) {
      const requestPath = join(dir, 'request.json'); await writeFile(requestPath, JSON.stringify(request));
      const done = await cli(skill, 'run', '--request-file', requestPath, '--output-dir', dir);
      assert.equal(done.status, 'delivered'); assert.equal(done.files.length, 1); assert.deepEqual(posts.at(-1), expected);
      const count = posts.length;
      const resumed = await cli(skill, 'continue', '--record', done.run_record);
      assert.equal(resumed.status, 'delivered'); assert.equal(posts.length, count); assert.equal(resumed.model, expected.model);
    }
  } finally {
    server.closeAllConnections(); await new Promise<void>(resolveClose => server.close(() => resolveClose()));
    await rm(dir, { recursive: true, force: true });
  }
});
