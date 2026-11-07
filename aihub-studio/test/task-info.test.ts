import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { actorContext, createTask, participate, readTaskInfo, registerOutputs, withArtifactContext } from '../src/taskInfo.js';

test('new tasks have distinct named folders; continuing keeps creator and deduplicates outputs', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'aihub-artifacts-'));
  try {
    const context = join(directory, 'context.json');
    await writeFile(context, JSON.stringify({ host: 'Codex', conversation_id: 'created-session', agent_id: 'writer' }));
    const first = await withArtifactContext(context, '抖音评论分析', () => createTask(directory, 'aihub-understanding', 'aihub-job', 'task.json'));
    const second = await withArtifactContext(context, '抖音评论分析', () => createTask(directory, 'aihub-understanding', 'aihub-job', 'task.json'));
    assert.match(basename(first.root), /^\d{14}-抖音评论分析-run-[a-f0-9]{8}$/);
    assert.notEqual(first.root, second.root);
    const metadata = join(first.root, 'task-info.json');
    const before = await readTaskInfo(metadata);
    await writeFile(context, JSON.stringify({ host: 'WorkBuddy', conversation_id: 'continued-session', agent_id: 'reviewer' }));
    await withArtifactContext(context, undefined, () => participate(metadata));
    const file = join(directory, 'report.md');
    await writeFile(file, '# Final findings\nSaved outside the task by explicit request.\n');
    await withArtifactContext(context, undefined, () => registerOutputs(metadata, [file], 'completed', 'Report saved and checked'));
    await withArtifactContext(context, undefined, () => registerOutputs(metadata, [file]));
    const info = await readTaskInfo(metadata);
    assert.equal(info.task_id, before.task_id);
    assert.deepEqual(info.creator, before.creator);
    assert.equal(info.participants.length, 2);
    assert.equal(info.participants[1]!.relation, 'continued');
    assert.equal(info.registered_outputs.length, 1);
    assert.equal(info.registered_outputs[0]!.path, file);
    assert.equal(info.registered_outputs[0]!.sha256.length, 64);
    assert.equal(info.delivery?.status, 'completed');
    await assert.rejects(() => registerOutputs(metadata, [join(directory, 'missing.csv')]));
    assert.equal((await readTaskInfo(metadata)).registered_outputs.length, 1);
    for (const name of ['run.json', 'error-report.md', 'unfinished.mp4.part']) {
      const auxiliary = join(first.root, name);
      await writeFile(auxiliary, 'supporting');
      await assert.rejects(() => registerOutputs(metadata, [auxiliary]), /final output/);
    }
    const unsupported = JSON.parse(await readFile(metadata, 'utf8'));
    unsupported.schema_version = 900;
    await writeFile(metadata, JSON.stringify(unsupported));
    await assert.rejects(() => participate(metadata), /unsupported/);
    assert.equal(JSON.parse(await readFile(metadata, 'utf8')).schema_version, 900);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test('unknown host identity is not fabricated from a Claude-compatible variable', () => {
  assert.equal(actorContext({}, { CLAUDE_SESSION_ID: 'may-be-workbuddy' }).host, null);
  assert.equal(actorContext({}, { CLAUDE_SESSION_ID: 'may-be-workbuddy' }).conversation_id, null);
  const child = actorContext({ host: 'Codex', conversation_id: 'worker', parent_conversation_id: 'parent', relationship: 'child', agent_id: 'worker-agent' }, {});
  assert.equal(child.parent_conversation_id, 'parent');
  assert.equal(child.agent_id, 'worker-agent');
  assert.throws(() => actorContext({ host: 'Codex', parent_conversation_id: 'guessed' }, {}));
});

test('Hermes session identity is preserved and conflicting inherited hosts need explicit context', () => {
  const env = { HERMES_SESSION_ID: 'hermes-session' };
  assert.equal(actorContext({}, env).host, 'Hermes');
  assert.equal(actorContext({}, env).conversation_id, 'hermes-session');
  const inherited = { ...env, CODEX_THREAD_ID: 'parent-codex-session' };
  assert.equal(actorContext({}, inherited).host, null);
  assert.equal(actorContext({}, inherited).conversation_id, null);
  assert.equal(actorContext({ host: 'Hermes' }, inherited).conversation_id, 'hermes-session');
  assert.equal(actorContext({ host: 'Codex' }, inherited).conversation_id, 'parent-codex-session');
});
