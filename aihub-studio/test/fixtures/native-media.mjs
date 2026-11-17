// Offline integration check. Run from a writable project with an installed Plugin
// path and a fresh output directory outside that installation; no service calls.
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

assert.equal(process.argv.length, 4, 'Pass the Plugin directory and fixture output directory.');
const plugin = resolve(process.argv[2]);
const base = resolve(process.argv[3]);
const load = name => import(pathToFileURL(join(plugin, 'dist', `${name}.js`)));
const { runLocalTool } = await load('localProcess');
const { writePrivateRecord, withJobLock } = await load('state');
const { snapshotAudio, prepareParts, audioContract, checkAudioTools } = await load('audioMedia');
const { measureLocalMedia, validateLocalMedia, checkMediaTools } = await load('download');
const { createTask, readTaskInfo, participate } = await load('taskInfo');

await mkdir(base, { recursive: true });
await checkMediaTools(); await checkAudioTools();
const task = await createTask(base, 'aihub-audio', 'offline-fixture', 'fixture.json');
const metadata = join(task.root, 'task-info.json');
const original = await readTaskInfo(metadata);
await writePrivateRecord(task.record, { revision: 1 });
await withJobLock(task.record, () => writePrivateRecord(task.record, { revision: 2 }));
assert.equal(JSON.parse(await readFile(task.record, 'utf8')).revision, 2);
await participate(task.record);
assert.equal((await readTaskInfo(metadata)).task_id, original.task_id);
const input = join(task.root, 'synth 中文 with spaces.wav');
await runLocalTool('ffmpeg', ['-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000:duration=4', '-ac', '2', input], { timeout: 30000 });
const source = await snapshotAudio(input, join(task.root, 'snapshot'), 0);
// Repeat the snapshot to cover replacement of an existing private file.
await snapshotAudio(input, join(task.root, 'snapshot'), 0);
const contract = audioContract('paraformer-8k-v2'); contract.max_bytes = 100000;
const parts = await prepareParts(source, 0, contract, join(task.root, 'parts'));
assert.ok(parts.length > 1);
assert.equal(parts.at(-1).core_end, source.duration);
for (const [i, part] of parts.entries()) {
  assert.equal(part.sample_rate, 8000); assert.equal(part.channels, 2);
  assert.ok(part.bytes <= 90000);
  if (i) assert.equal(part.core_start, parts[i-1].core_end);
}
const measurements = await measureLocalMedia(parts[0].path);
assert.equal(measurements.has_audio, true);
const validation = await validateLocalMedia(parts[0].path, 'audio');
assert.equal(validation.mime_type, 'audio/wav');
await assert.rejects(validateLocalMedia(parts[0].path, 'video'));
console.log(JSON.stringify({ status: 'passed', plugin_version: original.plugin_version,
  task_id: original.task_id, task_root: task.root, private_files: [metadata, task.record, source.path, ...parts.map(p => p.path)],
  directories: [base, task.root, join(task.root, 'snapshot'), join(task.root, 'parts')],
  duration: source.duration, parts: parts.length, measurements, validation }));
