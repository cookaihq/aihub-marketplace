import test from 'node:test';
import assert from 'node:assert/strict';
import { AihubmaxClient } from '../src/apiClient.js';
import { describe, models, validateGeneration, generationModelAvailable } from '../src/models.js';

const imageModels = ['gpt-image-2.5-flare', 'gpt-image-2.5-sunburst'];
const videoInputs: Array<[string, Record<string, unknown>]> = [
  ['seedance-2.5-text-to-video', {}],
  ['seedance-2.5-image-to-video', { image_url: 'https://example.test/first.png' }],
  ['seedance-2.5-reference-to-video', { image_urls: ['https://example.test/reference.png'] }],
];

test('GPT Image 2.5 accepts six quality settings, transparent output and mask/background together', () => {
  for (const model of imageModels) {
    for (const quality of ['auto', 'low', 'medium', 'high', 'xhigh', 'max']) {
      assert.equal(validateGeneration('image', model, { prompt: 'A product photo', quality, resolution: 'auto' }), '/e/v1/images/generations');
    }
    for (const output_format of ['png', 'webp']) {
      assert.doesNotThrow(() => validateGeneration('image', model, {
        prompt: 'Replace the masked background', image_urls: ['https://example.test/product.png'],
        mask_url: 'https://example.test/mask.png', background: 'transparent', output_format,
        resolution: { width: 2048, height: 1024 }, num_outputs: 10,
      }));
    }
    assert.doesNotThrow(() => validateGeneration('image', model, { prompt: 'An icon', background: 'transparent' }));
    assert.doesNotThrow(() => validateGeneration('image', model, { prompt: 'An icon', image_urls: null, mask_url: null }));
    assert.throws(() => validateGeneration('image', model, { prompt: 'An icon', background: 'transparent', output_format: 'jpeg' }), /requires png or webp/);
    for (const image_urls of [undefined, [], [' ']]) {
      assert.throws(() => validateGeneration('image', model, { prompt: 'Edit', mask_url: 'https://example.test/mask.png', image_urls }), /image_urls/);
    }
    assert.throws(() => validateGeneration('image', model, { prompt: 'Edit', image_urls: [42] }), /items/);
    assert.throws(() => validateGeneration('image', model, { prompt: 'Edit', mask_url: {} }), /mask_url/);
    for (const field of ['num_outputs', 'quality', 'background', 'output_format', 'resolution']) {
      assert.throws(() => validateGeneration('image', model, { prompt: 'An icon', [field]: null }), /cannot be null/);
    }
  }
  // The shared family must not accidentally give legacy Image 2 the 2.5-only options.
  assert.throws(() => validateGeneration('image', 'gpt-image-2', { prompt: 'An icon', quality: 'max' }), /quality/);
  assert.throws(() => validateGeneration('image', 'gpt-image-2', { prompt: 'An icon', background: 'transparent' }), /background/);
});

test('GPT Image 2.5 rejects invalid output counts and custom geometry before generation', () => {
  for (const num_outputs of [0, 11, 1.5, '2']) {
    assert.throws(() => validateGeneration('image', imageModels[0]!, { prompt: 'An icon', num_outputs }), /num_outputs/);
  }
  for (const resolution of [
    '2048x2048', [], 1024, { width: 1024 }, { width: '1024', height: 1024 },
    { width: 1025, height: 1024 }, { width: 4096, height: 2048 },
    { width: 256, height: 256 }, { width: 3840, height: 3840 }, { width: 2048, height: 512 },
  ]) assert.throws(() => validateGeneration('image', imageModels[0]!, { prompt: 'An icon', resolution }), /resolution/);
  for (const resolution of ['3840x2160', '2160x3840', { width: 1024, height: 640 }, { width: 3840, height: 2160 }]) {
    assert.doesNotThrow(() => validateGeneration('image', imageModels[0]!, { prompt: 'An icon', resolution }));
  }
});

test('Seedance 2.5 validates duration boundaries and the 1080p duration combination for each mode', () => {
  for (const [model, input] of videoInputs) {
    for (const resolution of ['480p', '720p']) {
      for (const duration of [4, 30]) assert.equal(validateGeneration('video', model, { prompt: 'A moving circle', ...input, resolution, duration }), '/e/v1/videos/generations');
    }
    for (const duration of [5, 10, 30]) assert.doesNotThrow(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, resolution: '1080p', duration }));
    assert.doesNotThrow(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, resolution: '1080p' }));
    for (const duration of [3, 31, -1, 5.5, '5']) assert.throws(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, duration }), /duration/);
    assert.throws(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, resolution: '1080p', duration: 6 }), /1080p/);
    assert.throws(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, resolution: '4k' }), /resolution/);
    assert.throws(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, aspect_ratio: 'auto' }), /aspect_ratio/);
    for (const field of ['duration', 'resolution', 'aspect_ratio']) assert.throws(() => validateGeneration('video', model, { prompt: 'A moving circle', ...input, [field]: null }), /cannot be null/);
  }
});

test('Seedance 2.5 keeps text, starting frame and mixed-reference input contracts distinct', () => {
  assert.throws(() => validateGeneration('video', 'seedance-2.5-text-to-video', { prompt: 'Move', image_url: 'https://example.test/a.png' }), /image_url is not supported/);
  assert.throws(() => validateGeneration('video', 'seedance-2.5-image-to-video', { prompt: 'Move' }), /image_url/);
  assert.throws(() => validateGeneration('video', 'seedance-2.5-image-to-video', { prompt: 'Move', image_url: 'https://example.test/a.png', image_urls: ['https://example.test/b.png'] }), /image_urls is not supported/);
  assert.throws(() => validateGeneration('video', 'seedance-2.5-reference-to-video', { prompt: 'Move', image_url: 'https://example.test/a.png' }), /image_url is not supported/);
  assert.throws(() => validateGeneration('video', 'seedance-2.5-reference-to-video', { prompt: 'Move', image_urls: [], video_urls: [], audio_urls: [] }), /at least one/);
  for (const [field, limit] of [['image_urls', 30], ['video_urls', 10], ['audio_urls', 10]] as const) {
    assert.doesNotThrow(() => validateGeneration('video', 'seedance-2.5-reference-to-video', { prompt: 'Move', [field]: Array(limit).fill('https://example.test/reference') }));
    for (const invalid of [null, [''], [42], Array(limit + 1).fill('https://example.test/reference')]) {
      assert.throws(() => validateGeneration('video', 'seedance-2.5-reference-to-video', { prompt: 'Move', [field]: invalid }), new RegExp(field));
    }
  }
  assert.doesNotThrow(() => validateGeneration('video', 'seedance-2.5-reference-to-video', {
    prompt: 'Use the character, movement and sound', image_urls: ['https://example.test/a.png'],
    video_urls: ['https://example.test/a.mp4'], audio_urls: ['https://example.test/a.mp3'],
  }));
  assert.match(describe('seedance-2.5-reference-to-video').note, /may be combined/);
  for (const unsupported of ['end_image_url', 'generate_audio', 'seed']) {
    assert.throws(() => validateGeneration('video', 'seedance-2.5-image-to-video', { prompt: 'Move', image_url: 'https://example.test/a.png', [unsupported]: 1 }), /not supported/);
  }
});

test('explicitly selected Seedance 2.0 variants retain their existing generation parameters', () => {
  for (const speed of ['', 'fast-']) {
    for (const [mode, input] of [
      ['text-to-video', {}], ['image-to-video', { image_url: 'https://example.test/first.png' }],
      ['reference-to-video', { image_urls: ['https://example.test/reference.png'] }],
    ] as Array<[string, Record<string, unknown>]>) {
      const model = `seedance-2.0-${speed}${mode}`;
      assert.equal(validateGeneration('video', model, {
        prompt: 'A moving circle', ...input, duration: -1, aspect_ratio: 'adaptive', generate_audio: false, seed: 42,
      }), '/e/v1/videos/generations');
      assert.match(describe(model).capability, /explicit selection/);
    }
  }
});

test('live model output marks Flare as the ordinary image default and all three Seedance 2.5 input modes as preferred defaults', async () => {
  const ids = [...imageModels, ...videoInputs.map(([model]) => model), 'sync-3', 'fabric-1.0[480p]', 'fabric-1.0[720p]', 'lipsync-2', 'omnihuman-1.5', 'seedance-2.0-text-to-video', 'seedance-2.0-fast-reference-to-video'];
  const client = new AihubmaxClient({ apiKey: 'offline-fixture', baseUrl: 'https://example.invalid' });
  client.listLiveModels = async () => new Map(ids.map(id => [id, { id }]));
  const output = await models(client);
  const rows = output.models as Array<{ model: string; preferred: boolean; default: boolean }>;
  assert.deepEqual(rows.filter(row => row.model.startsWith('gpt-image')).map(row => [row.model, row.preferred, row.default]), [
    ['gpt-image-2.5-flare', true, true], ['gpt-image-2.5-sunburst', true, false],
  ]);
  assert.deepEqual(rows.filter(row => row.model.startsWith('seedance-2.5-')).map(row => [row.model, row.preferred, row.default]), videoInputs.map(([model]) => [model, true, true]));
  for (const model of ['sync-3', 'fabric-1.0']) {
    assert.ok(rows.find(row => row.model === model)?.default);
    assert.ok(rows.find(row => row.model === model)?.preferred);
  }
  assert.equal(rows.filter(row => row.model === 'fabric-1.0').length, 1);
  for (const model of ['lipsync-2', 'omnihuman-1.5']) assert.equal(rows.find(row => row.model === model)?.default, false);
  assert.deepEqual(rows.filter(row => row.model.startsWith('seedance-2.0-')).map(row => [row.model, row.preferred, row.default]), [
    ['seedance-2.0-text-to-video', false, false], ['seedance-2.0-fast-reference-to-video', false, false],
  ]);
  client.listLiveModels = async () => new Map([['seedance-2.0-text-to-video', { id: 'seedance-2.0-text-to-video' }]]);
  const unavailable = await models(client, 'video');
  const legacy = unavailable.models as Array<{ model: string; preferred: boolean; default: boolean }>;
  assert.deepEqual(legacy.map(row => [row.model, row.preferred, row.default]), [['seedance-2.0-text-to-video', false, false]]);
  assert.ok(unavailable.catalog_only.some(row => row.model === 'seedance-2.5-text-to-video'));
});

test('digital-human schemas enforce the selected model without accepting unrelated legacy fields', () => {
  const sync = { video_url: 'https://example.test/person.mp4', audio_url: 'https://example.test/voice.wav' };
  for (const sync_mode of ['bounce', 'loop', 'cut_off', 'silence', 'remap']) {
    assert.equal(validateGeneration('video', 'sync-3', { ...sync, sync_mode }), '/e/v1/videos/generations');
  }
  for (const params of [{ temperature: 0.5 }, { active_speaker: true }, { sync_mode: 'unknown' }, { sync_mode: null }, { prompt: 'talk' }]) {
    assert.throws(() => validateGeneration('video', 'sync-3', { ...sync, ...params }));
  }
  assert.ok(describe('sync-3').params.every(field => !['temperature', 'active_speaker'].includes(field.name)));
  assert.ok(describe('lipsync-2').params.some(field => field.name === 'temperature'));
  const avatar = { image_url: 'https://example.test/face.png', audio_url: sync.audio_url };
  for (const resolution of ['480p', '720p']) assert.doesNotThrow(() => validateGeneration('video', 'fabric-1.0', { ...avatar, resolution }));
  for (const params of [{}, { resolution: '1080p' }, { resolution: null }, { resolution: '720p', prompt: 'talk' }, { resolution: '720p', turbo_mode: true }]) {
    assert.throws(() => validateGeneration('video', 'fabric-1.0', { ...avatar, ...params }));
  }
});

test('Fabric availability requires the requested resolution and never infers other model families', async () => {
  const live = new Map([['fabric-1.0[480p]', { id: 'fabric-1.0[480p]' }]]);
  assert.equal(generationModelAvailable(live, 'fabric-1.0', { resolution: '480p' }), true);
  assert.equal(generationModelAvailable(live, 'fabric-1.0', { resolution: '720p' }), false);
  assert.equal(generationModelAvailable(live, 'fabric-1.0', { resolution: '1080p' }), false);
  assert.equal(generationModelAvailable(live, 'fabric-1.0-fast', { resolution: '480p' }), false);
  const client = new AihubmaxClient({ apiKey: 'offline-fixture', baseUrl: 'https://example.invalid' });
  client.listLiveModels = async () => live;
  const output = await models(client, 'video');
  assert.deepEqual(output.models.map(row => ({ model: row.model, resolutions: 'available_resolutions' in row ? row.available_resolutions : undefined })), [
    { model: 'fabric-1.0', resolutions: ['480p'] },
  ]);
});

test('understanding model discovery marks only Carbon as the built-in default and preserves live capabilities', async () => {
  const client = new AihubmaxClient({ apiKey: 'offline-fixture', baseUrl: 'https://example.invalid' });
  client.listLlmModels = async () => [
    { id: 'gemini-4-carbon', capabilities: ['vision', 'audio', 'video', 'file'] },
    { id: 'gemini-3.1-pro-preview', capabilities: ['vision'] },
  ];
  const output = await models(client, 'understanding');
  assert.deepEqual(output.models.map(row => [row.model, row.default]), [['gemini-4-carbon', true], ['gemini-3.1-pro-preview', false]]);
  client.listLlmModels = async () => [{ id: 'gemini-3.1-pro-preview', capabilities: ['vision'] }];
  const missing = await models(client, 'understanding');
  assert.equal(missing.models.some(row => row.default), false, 'a missing default must not be invented or silently replaced');
});
