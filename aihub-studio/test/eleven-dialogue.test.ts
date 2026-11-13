import test from 'node:test';
import assert from 'node:assert/strict';
import { selectionPlan } from '../src/selection.js';
import { describe, validateGeneration } from '../src/models.js';
import type { LoadedConfig } from '../src/config.js';
import { ELEVEN_AUDIO_MODELS, ELEVEN_DIALOGUE_MODELS, elevenAudioParameters } from '../src/elevenlabs.js';

const cfg = (models?: string[]): LoadedConfig => ({ skill: 'aihub-audio', apiKey: 'fixture', baseUrl: 'https://fixture.invalid',
  sources: { AIHUB_API_KEY: 'fixture' }, speech: { defaultVoiceId: 'MiniMax-only', source: 'fixture' }, modelSelection: { policy: 'auto', models, sources: {} } });
const inputs = [{ text: '你好 👋', voice_id: 'existing-public-id' }, { text: '欢迎！', voice_id: 'existing-private-id' }, { text: '再见', voice_id: 'existing-public-id' }];
const request = { operation: 'audio-dialogue', original_request: '按顺序用这些音色读出台词', requirements: { inputs } };
const validate = (model: string, params: Record<string, unknown>) => validateGeneration('audio', model, params);

test('Dialogue maps ordered inputs without a prompt, MiniMax voice, splitting or default model', () => {
  assert.deepEqual(selectionPlan(cfg(), request).candidates, []);
  for (const model of ELEVEN_DIALOGUE_MODELS) {
    const plan = selectionPlan(cfg(), { ...request, model });
    assert.equal(plan.source, 'user'); assert.equal(plan.policy, 'off');
    assert.equal(plan.candidates[0]?.rejection, undefined);
    assert.deepEqual(plan.candidates[0]?.params, { inputs });
    assert.deepEqual(plan.request.requirements, request.requirements);
    assert.match(describe(model).capability, /dialogue/);
    assert.match(selectionPlan(cfg(), { ...request, model, prompt: 'Do not discard me' }).candidates[0]?.rejection ?? '', /prompt/);
    assert.equal(selectionPlan(cfg(), { operation: 'audio-tts', original_request: 'Read', prompt: 'Hello', model }).candidates.length, 0);
  }
  for (const model of ['speech-2.8-hd', 'paraformer-v2', 'eleven-v4-text-to-speech']) {
    assert.equal(selectionPlan(cfg(), { ...request, model }).candidates.length, 0);
  }
});

test('retired Eleven IDs explain purpose migration without rewriting personal model order', () => {
  const retired = ['eleven-v4', 'eleven-v4-turbo', 'eleven-v4-custom-voice', 'eleven-v4-turbo-custom-voice'];
  for (const model of retired) {
    assert.throws(() => describe(model), /no longer accepts new requests.*no alias/);
    assert.throws(() => validate(model, { text: 'Hello' }), /audio-tts.*audio-dialogue/);
    const plan = selectionPlan(cfg(), { ...request, model });
    assert.deepEqual(plan.candidates, []); assert.equal(plan.excluded[0]?.model, model);
    assert.match(plan.excluded[0]?.reason ?? '', /Personal model lists are not rewritten/);
  }
  const personal = [...retired, 'eleven-v4-text-to-dialogue-custom-voice', 'paraformer-v2', 'eleven-v4-text-to-dialogue'];
  const config = cfg(personal); const before = JSON.stringify(config);
  const planned = selectionPlan(config, request);
  assert.deepEqual(planned.candidates.map(c => c.model), ['eleven-v4-text-to-dialogue-custom-voice', 'eleven-v4-text-to-dialogue']);
  assert.equal(JSON.stringify(config), before);
});

test('Dialogue preserves long Unicode text and bounds distinct voices rather than turns', () => {
  for (const model of ELEVEN_DIALOGUE_MODELS) {
    validate(model, { inputs: [{ text: '👋'.repeat(2001), voice_id: 'v' }] });
    validate(model, { inputs: Array.from({ length: 20 }, (_, i) => ({ text: 'a', voice_id: `v${i % 10}` })) });
    for (const bad of [[], [{ text: '', voice_id: 'v' }], [{ text: 'hi' }], [{ voice_id: 'v' }],
      [{ text: 'hi', voice_id: '' }], [{ text: 'hi', voice_id: ' ' }], [{ text: 'hi', voice: 'v' }],
      [{ text: 'hi', voice_id: 'v', stability: 0.2 }],
      Array.from({ length: 11 }, (_, i) => ({ text: 'hi', voice_id: `v${i}` }))]) {
      assert.throws(() => validate(model, { inputs: bad }), /inputs/);
    }
    for (const field of ['text', 'voice', 'enable_safety_checker', 'unknown']) {
      assert.throws(() => validate(model, { inputs, [field]: null }), new RegExp(field));
    }
  }
  assert.throws(() => validate('eleven-v4-text-to-speech', { text: 'hi', voice_id: 'v', inputs }), /inputs/);
});

test('all four models preserve zero/false, omit only unspecified controls and validate dictionaries/formats', () => {
  for (const model of ELEVEN_AUDIO_MODELS) {
    const dialogue = ELEVEN_DIALOGUE_MODELS.has(model);
    const base = dialogue ? { inputs } : { text: 'Hello', voice_id: 'existing-id' };
    const settingsKey = dialogue ? 'settings' : 'voice_settings';
    const contextKey = dialogue ? 'future_text' : 'next_text';
    const nested = { stability: 0, [dialogue ? 'similarity' : 'similarity_boost']: 0, clone_strength: 0 };
    const controls = { [settingsKey]: nested, seed: 0, timestamps: false, language_code: 'xx',
      apply_text_normalization: 'off', previous_text: '👋'.repeat(101), [contextKey]: 'x'.repeat(101),
      pronunciation_dictionary_locators: [{ pronunciation_dictionary_id: 'dict', version_id: 'fixed-version' }] };
    validate(model, { ...base, ...controls });
    const formats = describe(model).params.find(p => p.name === 'output_format')?.enum ?? [];
    assert.equal(formats.length, 28);
    for (const output_format of formats) validate(model, { ...base, output_format });
    const nulls = { [settingsKey]: null, seed: null, language_code: null, previous_text: null, [contextKey]: null,
      pronunciation_dictionary_locators: null };
    validate(model, { ...base, ...nulls });
    assert.deepEqual(elevenAudioParameters(model, { ...base, ...controls, ...nulls }), {
      ...base, timestamps: false, apply_text_normalization: 'off' });
    validate(model, { ...base, [settingsKey]: { ...nested, stability: null } });
    for (const invalid of [{ [settingsKey]: { similarity_boost: dialogue ? 0 : -1, similarity: 0 } },
      { seed: -1 }, { seed: 4294967296 }, { seed: 0.1 }, { stability: null }, { timestamps: null },
      { output_format: 'wav' }, { [settingsKey]: { clone_strength: 2 } },
      { pronunciation_dictionary_locators: [{ pronunciation_dictionary_id: 'dict' }] },
      { pronunciation_dictionary_locators: [{ pronunciation_dictionary_id: ' ', version_id: 'v' }] },
      { pronunciation_dictionary_locators: [{ pronunciation_dictionary_id: 'dict', version_id: '' }] },
      { pronunciation_dictionary_locators: [{ pronunciation_dictionary_id: 'dict', version_id: 'v', other: true }] },
      { pronunciation_dictionary_locators: Array.from({ length: 4 }, () => ({ pronunciation_dictionary_id: 'dict', version_id: 'v' })) }]) {
      assert.throws(() => validate(model, { ...base, ...invalid }));
    }
  }
});
