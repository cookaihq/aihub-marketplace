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
import { fixtureTransport } from './fixture-transport.js';

const exec = promisify(execFile);

test('packaged defaults submit the documented video bodies, deliver media, and preserve saved plans', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'aihub-default-video-'));
  const videoPath = join(dir, 'fixture.mp4');
  await exec('ffmpeg', ['-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=32x32:d=0.2', '-y', videoPath]);
  const video = await readFile(videoPath);
  const posts: Array<Record<string, unknown>> = [];
  let base = '';
  let visible = ['sync-3', 'fabric-1.0[720p]'];
  const server = createServer(async (req, res) => {
    const json = (value: unknown, code = 200) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    if (req.url === '/v1/models') return json({ data: visible.map(id => ({ id })) });
    if (req.method === 'POST' && req.url === '/e/v1/videos/generations') {
      let text = ''; for await (const chunk of req) text += chunk;
      const body = JSON.parse(text); posts.push(body);
      return json({ id: `fixture-${posts.length}`, status: 'completed', model: body.model, results: [{ url: `${base}/fixture.mp4` }] });
    }
    if (req.url === '/fixture.mp4') { res.writeHead(200, { 'Content-Type': 'video/mp4' }); return res.end(video); }
    return json({ error: 'Unexpected route' }, 404);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const env = { ...process.env, ...fixtureTransport(base), AIHUB_API_KEY: 'offline-default-models',
    AIHUB_VIDEO_MODELS: '', AIHUB_MODEL_FALLBACK_POLICY: '', AIHUB_MODEL_MAX_ATTEMPTS: '', AIHUB_RESULT_CHECK_ENABLED: '0' };
  const call = async (extra: NodeJS.ProcessEnv, ...args: string[]) => {
    try {
      const { stdout } = await exec(process.execPath, [resolve('scripts/aihub.mjs'), ...args, '--skill', 'aihub-video', '--no-global-config'],
        { cwd: dir, env: { ...env, ...extra }, timeout: 30_000 });
      return JSON.parse(stdout);
    } catch (error) {
      const { stdout } = error as { stdout?: string };
      if (!stdout) throw error;
      return JSON.parse(stdout);
    }
  };
  const request = join(dir, 'request.json');
  try {
    for (const [operation, visual] of [['video-lipsync', 'videos'], ['video-avatar', 'images']]) {
      const url = `https://fixtures.invalid/${visual}`;
      await writeFile(request, JSON.stringify({ operation, original_request: 'Use this recording with the supplied visual',
        inputs: { [visual!]: [url], audios: ['https://fixtures.invalid/voice.wav'] } }));
      const output = await call({}, 'run', '--request-file', request, '--output-dir', dir);
      assert.equal(output.status, 'delivered'); assert.equal(output.files.length, 1);
      const expected = operation === 'video-lipsync'
        ? { model: 'sync-3', video_url: url, audio_url: 'https://fixtures.invalid/voice.wav' }
        : { model: 'fabric-1.0', image_url: url, audio_url: 'https://fixtures.invalid/voice.wav', resolution: '720p' };
      assert.deepEqual(posts.at(-1), expected);
      const count = posts.length;
      const resumed = await call({ AIHUB_VIDEO_MODELS: 'omnihuman-1.5' }, 'continue', '--record', output.run_record);
      assert.equal(resumed.status, 'delivered'); assert.equal(posts.length, count);
      assert.equal(resumed.model, expected.model);
    }
    // A visible 480p billing variant cannot authorize the default 720p request.
    visible = ['fabric-1.0[480p]'];
    const stopped = await call({}, 'run', '--request-file', request, '--output-dir', dir);
    assert.equal(stopped.status, 'no_compatible_model'); assert.equal(posts.length, 2);
  } finally {
    server.closeAllConnections(); await new Promise<void>(r => server.close(() => r()));
    await rm(dir, { recursive: true, force: true });
  }
});

test('Carbon understanding preserves all four media types and fails closed when the registry lacks the model or capability', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'aihub-default-understanding-'));
  const posts: Array<Record<string, unknown>> = [];
  let registry = [{ id: 'gemini-4-carbon', capabilities: ['vision', 'audio', 'video', 'file'] }];
  const server = createServer(async (req, res) => {
    const json = (value: unknown, code = 200) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    if (req.url === '/e/v1/configs/llm_generations_models') return json({ data: registry });
    if (req.method === 'POST' && req.url === '/e/v1/llm/generations') {
      let text = ''; for await (const chunk of req) text += chunk;
      const body = JSON.parse(text); posts.push(body);
      return json({ id: 'understanding-fixture', status: 'completed', model: body.model, results: [{ choices: [{ message: { content: 'Fixture analysis complete' } }] }] });
    }
    return json({ error: 'Unexpected route' }, 404);
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const request = join(dir, 'request.json');
  const inputs = { images: ['https://fixtures.invalid/image.png'], audios: ['https://fixtures.invalid/audio.wav'],
    videos: ['https://fixtures.invalid/video.mp4'], files: ['https://fixtures.invalid/file.pdf'] };
  await writeFile(request, JSON.stringify({ operation: 'understanding', original_request: 'Compare these four media inputs', prompt: 'Compare the content', inputs }));
  const env = { ...process.env, ...fixtureTransport(base), AIHUB_API_KEY: 'offline-default-models', AIHUB_UNDERSTANDING_MODELS: '',
    AIHUB_MODEL_FALLBACK_POLICY: '', AIHUB_MODEL_MAX_ATTEMPTS: '', AIHUB_RESULT_CHECK_ENABLED: '0' };
  const call = async () => {
    try {
      const { stdout } = await exec(process.execPath, [resolve('scripts/aihub.mjs'), 'run', '--request-file', request, '--output-dir', dir,
        '--skill', 'aihub-understanding', '--no-global-config'], { cwd: dir, env, timeout: 30_000 });
      return JSON.parse(stdout);
    } catch (error) {
      const { stdout } = error as { stdout?: string };
      if (!stdout) throw error;
      return JSON.parse(stdout);
    }
  };
  try {
    const output = await call();
    assert.equal(output.status, 'delivered'); assert.equal(output.model, 'gemini-4-carbon');
    assert.equal(output.files.length, 1); assert.equal(posts.length, 1);
    assert.equal(await readFile(output.files[0].path, 'utf8'), 'Fixture analysis complete');
    assert.deepEqual(posts[0], { model: 'gemini-4-carbon', messages: [{ role: 'user', content: [
      { type: 'text', text: 'Compare the content' },
      { type: 'image_url', image_url: { url: inputs.images[0] } }, { type: 'video_url', video_url: { url: inputs.videos[0] } },
      { type: 'audio_url', audio_url: { url: inputs.audios[0] } }, { type: 'file_url', file_url: { url: inputs.files[0] } },
    ] }] });
    for (const capabilities of [[], ['vision']]) {
      registry = [{ id: 'gemini-4-carbon', capabilities }];
      assert.equal((await call()).status, 'no_compatible_model');
    }
    registry = [];
    assert.equal((await call()).status, 'no_compatible_model');
    assert.equal(posts.length, 1, 'missing registry entries or capabilities never authorize a submission or replacement');
  } finally {
    server.closeAllConnections(); await new Promise<void>(r => server.close(() => r()));
    await rm(dir, { recursive: true, force: true });
  }
});
