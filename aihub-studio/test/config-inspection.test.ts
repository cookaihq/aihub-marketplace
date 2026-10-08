import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { inspectConfig, loadConfig, ConfigurationError } from '../src/config.js';
const exec = promisify(execFile);

test('shared inspection and deletion projections use the real loader without modifying files', async () => {
  const root = await mkdtemp(join(tmpdir(), '配置 preview '));
  const home = join(root, '用户');
  const shared = join(home, '.config/aihub-studio/.env');
  const target = join(root, '.env.local');
  const options = { skill: null, cwd: root, homeDirectory: home, env: {} };
  try {
    await mkdir(join(home, '.config/aihub-studio'), { recursive: true });
    await writeFile(shared, 'AIHUB_API_KEY=synthetic-shared');
    await writeFile(join(root, '.env.aihub-image'), 'AIHUB_API_KEY=synthetic-skill');
    await writeFile(target, 'AIHUB_API_KEY=synthetic-old\r\nAIHUB_API_KEY=synthetic-new\r\nUNRELATED=keep\r\n');
    const bytes = await readFile(target);
    const before = inspectConfig(options, true);
    assert.equal(before.skill, null);
    assert.equal(before.layers.length, 4);
    assert.equal(before.fields.AIHUB_API_KEY?.source, target);
    const projected = inspectConfig({ ...options, deletion: { path: target, fields: ['AIHUB_API_KEY'] } }, true);
    assert.equal(projected.fields.AIHUB_API_KEY?.source, shared);
    assert.deepEqual(projected.layers, before.layers);
    assert.deepEqual(await readFile(target), bytes);
    const disabled = inspectConfig({ ...options, useGlobalConfig: false, deletion: { path: target, fields: ['AIHUB_API_KEY'] } }, true);
    assert.equal(disabled.status, 'configuration_required');
    assert.equal(disabled.layers.length, 2);
    assert.throws(() => inspectConfig({ ...options, deletion: { path: target, fields: ['AIHUB_BASE_URL'] } }, true));
    assert.throws(() => inspectConfig({ ...options, deletion: { path: join(root, '.env.aihub-image'), fields: ['AIHUB_API_KEY'] } }, true));
    const childEnv = { ...process.env, HOME: home, USERPROFILE: home, AIHUB_API_KEY: '', AIHUB_BASE_URL: '' };
    const cli = resolve('scripts/aihub.mjs');
    const result = await exec(process.execPath, [cli, 'config-check', '--plugin-only', '--credentials-only', '--delete-from', target, '--delete-fields', 'AIHUB_API_KEY'], { cwd: root, env: childEnv });
    const report = JSON.parse(result.stdout);
    assert.equal(report.schema, 'config-deletion-preview/v1');
    assert.equal(report.before.skill, null);
    assert.equal(report.after.fields.AIHUB_API_KEY.source, shared);
    assert.ok(!result.stdout.includes('synthetic-new'));
    await assert.rejects(exec(process.execPath, [cli, 'config-check', '--plugin-only', '--skill', 'aihub-image'], { cwd: root, env: childEnv }));
    await assert.rejects(exec(process.execPath, [cli, 'models', '--plugin-only'], { cwd: root, env: childEnv }));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('inspection reports missing, invalid and unreadable sources without credential values', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-inspection-'));
  const options = { cwd: root, homeDirectory: join(root, 'home'), skill: 'aihub-image', env: {} };
  try {
    const missing = inspectConfig(options);
    assert.equal(missing.status, 'configuration_required');
    assert.deepEqual(missing.fields.AIHUB_API_KEY, { source: 'missing', present: false, problem: 'missing' });
    assert.equal(missing.fields.AIHUB_BASE_URL?.source, 'built-in default');
    const credentialReport = inspectConfig(options, true);
    assert.deepEqual(Object.keys(credentialReport.fields), ['AIHUB_API_KEY']);
    assert.deepEqual(Object.keys(credentialReport.environment), ['AIHUB_API_KEY']);
    assert.deepEqual(credentialReport.layers, missing.layers);
    assert.equal(credentialReport.status, 'configuration_required');
    const path = join(root, '.env.local');
    await writeFile(path, 'AIHUB_API_KEY=synthetic-inspection-key\nAIHUB_BASE_URL=https://account:synthetic-url-secret@host.invalid');
    const invalid = inspectConfig(options);
    assert.deepEqual(invalid.fields.AIHUB_BASE_URL, { source: path, present: true, problem: 'invalid_url' });
    for (const value of ['synthetic-inspection-key', 'synthetic-url-secret', 'account:']) assert.ok(!JSON.stringify(invalid).includes(value));
    const keyOnly = inspectConfig(options, true);
    assert.equal(keyOnly.status, 'ok');
    assert.equal(keyOnly.fields.AIHUB_API_KEY?.source, path);
    assert.deepEqual(keyOnly.layers, invalid.layers);
    assert.notDeepEqual(keyOnly.layers, credentialReport.layers);
    assert.throws(() => loadConfig(options), (error: unknown) => {
      assert.ok(error instanceof ConfigurationError);
      assert.deepEqual(error.inspection, invalid); return true;
    });
    const override = inspectConfig({ ...options, env: { AIHUB_API_KEY: 'process-synthetic-key' } });
    assert.equal(override.fields.AIHUB_API_KEY?.source, 'environment');
    assert.ok(!JSON.stringify(override).includes('process-synthetic-key'));
    await rm(path); await mkdir(path);
    const unreadable = inspectConfig(options);
    assert.ok(unreadable.problems.some(p => p.reason === 'unreadable' && p.source === path));
    assert.ok(inspectConfig(options, true).problems.some(p => p.reason === 'unreadable' && p.source === path));
    const disabled = inspectConfig({ ...options, useGlobalConfig: false });
    assert.equal(disabled.layers.length, 3);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('CLI distinguishes authentication rejection from balance, permissions and rate limits', async () => {
  const root = await mkdtemp(join(tmpdir(), 'aihub-auth-sources-'));
  const config = join(root, '.env.local');
  let status = 401;
  let requests = 0;
  const server = createServer((_req, res) => {
    requests++;
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: { message: 'synthetic rejection', code: 'synthetic_error' } }));
  });
  await new Promise<void>(resolveListen => server.listen(0, '127.0.0.1', resolveListen));
  const port = (server.address() as { port: number }).port;
  const env = { ...process.env, HOME: join(root, 'home'), USERPROFILE: join(root, 'home'), AIHUB_API_KEY: '', AIHUB_BASE_URL: '' };
  const cli = resolve('scripts/aihub.mjs');
  try {
    await writeFile(config, `AIHUB_API_KEY=synthetic-cli-secret\nAIHUB_BASE_URL=http://127.0.0.1:${port}`);
    // No media tools, credentials or network are needed for config-check itself.
    const inspected = await exec(process.execPath, [cli, 'config-check', '--skill', 'aihub-image'], { cwd: root, env: { ...env, PATH: '' } });
    assert.equal(JSON.parse(inspected.stdout).status, 'ok');
    const credentialInspection = await exec(process.execPath, [cli, 'config-check', '--skill', 'aihub-image', '--credentials-only'], { cwd: root, env: { ...env, PATH: '' } });
    const credentialOutput = JSON.parse(credentialInspection.stdout);
    assert.deepEqual(Object.keys(credentialOutput.fields), ['AIHUB_API_KEY']);
    assert.deepEqual(Object.keys(credentialOutput.environment), ['AIHUB_API_KEY']);
    assert.equal(credentialOutput.fields.AIHUB_API_KEY.source, config);
    assert.deepEqual(credentialOutput.layers, JSON.parse(inspected.stdout).layers);
    assert.ok(!credentialInspection.stdout.includes('synthetic-cli-secret'));
    assert.equal(requests, 0);
    for (const code of [401, 402, 403, 429]) {
      status = code;
      await assert.rejects(exec(process.execPath, [cli, 'models', '--skill', 'aihub-image', '--media', 'image'], { cwd: root, env, timeout: 20_000 }), (error: unknown) => {
        const stdout = (error as { stdout: string }).stdout;
        assert.ok(!stdout.includes('synthetic-cli-secret'));
        const output = JSON.parse(stdout);
        if (code === 401) {
          assert.equal(output.configuration_issue.reason, 'authentication_rejected');
          assert.deepEqual(output.configuration_issue.keys, ['AIHUB_API_KEY']);
          assert.deepEqual(output.configuration_issue.sources, { AIHUB_API_KEY: config });
          assert.equal(output.configuration_issue.service_url, `http://127.0.0.1:${port}`);
        } else assert.equal(output.configuration_issue, undefined);
        return true;
      });
    }
    await rm(config);
    await assert.rejects(exec(process.execPath, [cli, 'config-check', '--skill', 'aihub-image'], { cwd: root, env }), (error: unknown) => {
      const failed = error as { code: number; stdout: string };
      assert.equal(failed.code, 3);
      assert.equal(JSON.parse(failed.stdout).fields.AIHUB_API_KEY.source, 'missing');
      return true;
    });
  } finally {
    await new Promise<void>(resolveClose => server.close(() => resolveClose()));
    await rm(root, { recursive: true, force: true });
  }
});
