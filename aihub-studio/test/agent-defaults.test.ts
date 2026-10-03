import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { agentDefaults } from '../src/agentDefaults.js';

function fixture(run: (root: string) => void) {
  const root = mkdtempSync(join(tmpdir(), 'aihub-defaults-'));
  try { run(root); } finally { rmSync(root, { recursive: true, force: true }); }
}
test('fresh checks are read-only, credential-free and require semantic review in all three hosts', () => fixture(root => {
  for (const agent of ['codex', 'claude-code', 'workbuddy']) {
    const result = agentDefaults({ agent, homeDirectory: root, env: {} });
    assert.equal(result.status, 'review_required');
    assert.equal(result.session_loaded, 'not_verified');
    assert.equal(existsSync(join(root, '.config')), false);
    assert.match(String(result.proposed_rule), /aihub-image/);
    assert.match(String(result.proposed_rule), /实际完整调用标识/);
  }
}));
test('dismissal survives separate calls, isolates host profiles and preserves unrelated settings', () => fixture(root => {
  const path = join(root, '.config/aihub-studio/settings.json');
  mkdirSync(join(root, '.config/aihub-studio'), { recursive: true });
  writeFileSync(path, JSON.stringify({ untouched: { enabled: 7 } }));
  const options = { agent: 'workbuddy', homeDirectory: root, env: {} };
  assert.equal(agentDefaults({ ...options, action: 'dismiss' }).status, 'dismissed');
  assert.equal(agentDefaults(options).status, 'dismissed');
  assert.equal(agentDefaults({ ...options, agent: 'codex' }).status, 'review_required');
  assert.equal(agentDefaults({ ...options, configDir: join(root, 'another-profile') }).status, 'review_required');
  assert.equal(agentDefaults({ ...options, action: 'enable' }).reminder_enabled, true);
  assert.equal(agentDefaults({ ...options, action: 'enable' }).reminder_enabled, true);
  const settings = JSON.parse(readFileSync(path, 'utf8'));
  assert.deepEqual(settings.untouched, { enabled: 7 });
  assert.equal(settings.default_skill_reminders.agents.length, 1);
  assert.equal(existsSync(join(root, '.workbuddy/CODEBUDDY.md')), false);
}));
test('Codex overrides and shared symlinks resolve without modifying rule files', () => fixture(root => {
  const directory = join(root, '.codex');
  mkdirSync(directory);
  writeFileSync(join(root, 'shared.md'), 'Existing rule');
  symlinkSync(join(root, 'shared.md'), join(directory, 'AGENTS.md'));
  writeFileSync(join(directory, 'AGENTS.override.md'), ' ');
  const options = { agent: 'codex', homeDirectory: root, env: {} };
  assert.equal(agentDefaults(options).primary_real_path, join(root, 'shared.md'));
  writeFileSync(join(directory, 'AGENTS.override.md'), 'A higher-priority rule');
  assert.equal(agentDefaults(options).primary_rule, join(directory, 'AGENTS.override.md'));
  assert.equal(readFileSync(join(root, 'shared.md'), 'utf8'), 'Existing rule');
  symlinkSync(directory, join(root, 'alias'));
  agentDefaults({ ...options, configDir: join(root, 'alias'), action: 'dismiss' });
  assert.equal(agentDefaults(options).status, 'dismissed');
}));
test('global disabling bypasses corrupt settings and prevents writes; bad schema and locks preserve bytes', () => fixture(root => {
  const path = join(root, '.config/aihub-studio/settings.json');
  mkdirSync(join(root, '.config/aihub-studio'), { recursive: true });
  writeFileSync(path, 'broken');
  const options = { agent: 'codex', homeDirectory: root, env: {} };
  assert.equal(agentDefaults({ ...options, globalEnabled: false }).status, 'skipped');
  assert.throws(() => agentDefaults({ ...options, action: 'dismiss', globalEnabled: false }));
  assert.throws(() => agentDefaults({ ...options, action: 'dismiss' }));
  assert.equal(readFileSync(path, 'utf8'), 'broken');
  writeFileSync(path, '{"default_skill_reminders":{"version":2,"agents":[]}}');
  assert.throws(() => agentDefaults({ ...options, action: 'dismiss' }));
  assert.match(readFileSync(path, 'utf8'), /"version":2/);
  writeFileSync(path, '{}');
  writeFileSync(`${path}.default-skills.lock`, '');
  assert.throws(() => agentDefaults({ ...options, action: 'dismiss' }));
  assert.equal(readFileSync(path, 'utf8'), '{}');
}));
test('public CLI has a working offline entry and every Skill names its shared workflow', () => fixture(root => {
  const env = { ...process.env, HOME: root, USERPROFILE: root, CODEX_HOME: '', AIHUB_API_KEY: '', AIHUB_BASE_URL: '' };
  const result = spawnSync(process.execPath, [resolve('scripts/aihub.mjs'), 'default-skills', '--skill', 'aihub-image', '--agent', 'workbuddy'], { cwd: root, env, encoding: 'utf8', timeout: 10_000 });
  assert.equal(result.status, 0, result.stderr + result.stdout);
  assert.equal(JSON.parse(result.stdout).status, 'review_required');
  for (const skill of ['image', 'video', 'audio', 'music', 'understanding', 'document']) {
    const doc = readFileSync(resolve(`skills/aihub-${skill}/SKILL.md`), 'utf8');
    assert.match(doc, /默认 Skill 检查与提醒/);
    const version = JSON.parse(readFileSync(resolve('package.json'), 'utf8')).version;
    assert.ok(doc.includes(`version: ${version}\n`));
    assert.ok(doc.includes(`description: v${version}｜`));
  }
}));
test('saving through a dangling settings symlink preserves the link and creates its target', () => fixture(root => {
  const directory = join(root, '.config/aihub-studio');
  mkdirSync(directory, { recursive: true });
  const path = join(directory, 'settings.json');
  const target = join(root, 'preferences/aihub.json');
  symlinkSync(target, path);
  agentDefaults({ agent: 'workbuddy', action: 'dismiss', homeDirectory: root, env: {} });
  assert.equal(lstatSync(path).isSymbolicLink(), true);
  assert.equal(JSON.parse(readFileSync(target, 'utf8')).default_skill_reminders.agents[0].enabled, false);
}));
test('ambiguous WorkBuddy configuration requires explicit active directory before saving', () => fixture(root => {
  const options = { agent: 'workbuddy', homeDirectory: root, env: { WORKBUDDY_CONFIG_DIR: join(root, 'first'), CODEBUDDY_CONFIG_DIR: join(root, 'second') } };
  assert.throws(() => agentDefaults({ ...options, action: 'dismiss' }), /disagree/);
  assert.equal(existsSync(join(root, '.config')), false);
  assert.equal(agentDefaults({ ...options, configDir: join(root, 'first') }).config_dir, join(root, 'first'));
}));
