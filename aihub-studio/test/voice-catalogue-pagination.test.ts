import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError } from '../src/apiClient.js';
import { loadVoiceLibrary, VoiceCatalogueError } from '../src/voiceLibrary.js';

const options = {cwd: process.cwd(), useGlobalConfig: false, env: {AIHUB_API_KEY: 'fixture-key'}};
const voice = (index: number) => ({voice_id: `voice-${index}`, name: `Voice ${index}`, languages: ['en', 'zh'],
  category: ['narration'], preview_url: 'https://storage.googleapis.com/sample.mp3',
  description: 'Complete description '.repeat(250), provider_metadata: {index, values: [false, 0, null]}});
const headers = (total: number, offset: number) => ({'X-Total-Count': String(total), 'X-Limit': '100',
  'X-Offset': String(offset), 'X-Next-Offset': offset + 100 < total ? String(offset + 100) : ''});

test('all catalogue pages retain source order, long fields and complete nested metadata', async () => {
  const original = globalThis.fetch, raw = Array.from({length: 201}, (_, index) => voice(index));
  // Even repeated IDs and fields matching UI aliases belong to the source data.
  raw[100]!.voice_id = raw[0]!.voice_id;
  Object.assign(raw[0]!, {voice_name: 'Upstream alias', language: 'upstream language', tag_list: ['upstream tag']});
  const routes: string[] = [];
  globalThis.fetch = async (url, init) => {
    const target = new URL(String(url)), offset = Number(target.searchParams.get('offset'));
    assert.equal(target.searchParams.get('limit'), '100');
    assert.equal(init?.method, 'GET');
    assert.equal((init?.headers as Record<string, string>).Authorization, 'Bearer fixture-key');
    routes.push(target.pathname + target.search);
    return new Response(JSON.stringify(raw.slice(offset, offset + 100)), {headers: headers(raw.length, offset)});
  };
  try {
    const result = await loadVoiceLibrary(options, 'elevenlabs');
    assert.equal(result.length, raw.length);
    assert.deepEqual(result.map(row => row.voice_id), raw.map(row => row.voice_id));
    for (const [index, row] of result.entries()) {
      for (const [key, value] of Object.entries(raw[index]!)) assert.deepEqual((row as any)[key], value);
    }
    assert.deepEqual(routes, [0, 100, 200].map(offset => `/e/v1/configs/elevenlabs-preset-voice-id?limit=100&offset=${offset}`));
  } finally {globalThis.fetch = original;}
});

test('empty and exactly full final pages stop on the empty next-offset header', async () => {
  const original = globalThis.fetch;
  try {
    for (const total of [0, 100, 200]) {
      const offsets: number[] = [];
      globalThis.fetch = async url => {
        const offset = Number(new URL(String(url)).searchParams.get('offset')); offsets.push(offset);
        return new Response(JSON.stringify(Array.from({length: Math.min(100, total - offset)}, (_, index) => voice(index + offset))),
          {headers: headers(total, offset)});
      };
      assert.equal((await loadVoiceLibrary(options, 'elevenlabs')).length, total);
      assert.deepEqual(offsets, total <= 100 ? [0] : [0, 100]);
    }
  } finally {globalThis.fetch = original;}
});

test('missing, malformed and inconsistent progress never yield a partial catalogue', async t => {
  const original = globalThis.fetch;
  const cases: Array<[string, (head: Record<string, string>) => void, unknown?]> = [
    ...Object.keys(headers(101, 0)).map(key => [`missing ${key}`, (head: Record<string, string>) => {delete head[key];}] as [string, (head: Record<string, string>) => void]),
    ...['-1', '+101', '1.0', '²', 'NaN', '9007199254740992', ''].map(value => [`invalid total ${value}`, (head: Record<string, string>) => {head['X-Total-Count'] = value;}] as [string, (head: Record<string, string>) => void]),
    ['wrong limit', head => {head['X-Limit'] = '99';}],
    ['wrong offset', head => {head['X-Offset'] = '1';}],
    ['premature end', head => {head['X-Next-Offset'] = '';}],
    ['repeated offset', head => {head['X-Next-Offset'] = '0';}],
    ['skipped offset', head => {head['X-Next-Offset'] = '101';}],
    ['backward offset', head => {head['X-Next-Offset'] = '-100';}],
    ['non-array body', () => {}, {}],
    ['short body', () => {}, [voice(0)]],
    ['oversized body', () => {}, Array.from({length: 101}, (_, index) => voice(index))],
  ];
  try {
    for (const [name, change, body] of cases) await t.test(name, async () => {
      let calls = 0;
      globalThis.fetch = async () => {
        calls++;
        const head: Record<string, string> = headers(101, 0); change(head);
        return new Response(JSON.stringify(body ?? Array.from({length: 100}, (_, index) => voice(index))), {headers: head});
      };
      await assert.rejects(loadVoiceLibrary(options, 'elevenlabs'), error => error instanceof VoiceCatalogueError && error.code === 'invalid_pagination');
      assert.equal(calls, 1);
    });
  } finally {globalThis.fetch = original;}
});

test('a changed total aborts and a new download starts again at offset zero', async () => {
  const original = globalThis.fetch, offsets: number[] = [];
  let changed = true;
  globalThis.fetch = async url => {
    const offset = Number(new URL(String(url)).searchParams.get('offset')); offsets.push(offset);
    const total = changed && offset ? 102 : 101;
    return new Response(JSON.stringify(Array.from({length: Math.min(100, total - offset)}, (_, index) => voice(index + offset))),
      {headers: headers(total, offset)});
  };
  try {
    await assert.rejects(loadVoiceLibrary(options, 'elevenlabs'), error => error instanceof VoiceCatalogueError && error.code === 'catalogue_changed');
    changed = false;
    assert.equal((await loadVoiceLibrary(options, 'elevenlabs')).length, 101);
    assert.deepEqual(offsets, [0, 100, 0, 100]);
  } finally {globalThis.fetch = original;}
});

test('authentication, malformed JSON and transport failures on an intermediate page abort', async () => {
  const original = globalThis.fetch;
  try {
    for (const failure of ['authentication', 'json', 'transport']) {
      let calls = 0;
      globalThis.fetch = async () => {
        if (++calls === 1) return new Response(JSON.stringify(Array.from({length: 100}, (_, index) => voice(index))), {headers: headers(101, 0)});
        if (failure === 'transport') throw new Error('synthetic transport failure');
        return failure === 'json' ? new Response('{') : new Response('{}', {status: 401});
      };
      await assert.rejects(loadVoiceLibrary(options, 'elevenlabs'), ApiError);
      assert.equal(calls, 2);
    }
  } finally {globalThis.fetch = original;}
});

test('all pages and GET retries share a finite download deadline', async () => {
  const original = globalThis.fetch, now = Date.now;
  let clock = 1_000, calls = 0;
  Date.now = () => clock;
  globalThis.fetch = async () => {
    calls++; clock += 300_001;
    return new Response(JSON.stringify(Array.from({length: 100}, (_, index) => voice(index))), {headers: headers(101, 0)});
  };
  try {
    await assert.rejects(loadVoiceLibrary(options, 'elevenlabs'), error => error instanceof ApiError && error.code === 'deadline_exceeded');
    assert.equal(calls, 1);
  } finally {Date.now = now; globalThis.fetch = original;}
});
