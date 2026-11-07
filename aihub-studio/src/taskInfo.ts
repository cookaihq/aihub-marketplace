import { AsyncLocalStorage } from 'node:async_hooks';
import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { mkdir, readFile, realpath, stat } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { sanitized } from './config.js';
import { assertOutsideInstallation, withJobLock, writePrivateRecord } from './state.js';

export interface Actor {
  host: string | null; conversation_id: string | null; conversation_title: string | null;
  agent_id: string | null; agent_name: string | null; agent_role: string | null; agent_model: string | null;
  parent_conversation_id: string | null; relationship: 'child' | 'fork' | null; source: string;
}
export interface TaskInfo {
  schema_version: 1; task_id: string; plugin: 'aihub-studio'; plugin_version: string; skill: string;
  title: string; project_root: string; created_at: string; updated_at: string; creator: Actor;
  participants: Array<Actor & { relation: 'created' | 'continued'; first_at: string; last_at: string }>;
  records: Array<{ path: string; kind: string; purpose: 'primary' | 'supporting' }>;
  registered_outputs: Array<{ id: string; path: string; title: string; bytes: number; sha256: string; registered_at: string }>;
  delivery: { status: 'completed' | 'partial' | 'failed'; at: string; reason: string } | null;
}
interface Execution { actor: Actor; name?: string; auxiliary?: boolean; warnings: string[] }
const execution = new AsyncLocalStorage<Execution>();
const allowedHosts = new Set(['Codex', 'Claude Code', 'WorkBuddy', 'Hermes']);
const VERSION = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8')).version as string;

export function actorContext(input: Record<string, unknown> = {}, env = process.env): Actor {
  const keys = ['host', 'conversation_id', 'conversation_title', 'agent_id', 'agent_name', 'agent_role', 'agent_model', 'parent_conversation_id', 'relationship'];
  if (Object.keys(input).some(k => !keys.includes(k))) throw new Error('Unknown execution context field. Do not include chat, prompts or credentials.');
  const string = (key: string): string | null => {
    const value = input[key];
    if (value === undefined || value === null || value === '') return null;
    if (typeof value !== 'string' || value.length > 256 || /[\x00-\x1f]/.test(value)) throw new Error(`Invalid context field: ${key}`);
    return value;
  };
  const suppliedHost = string('host');
  if (suppliedHost && !allowedHosts.has(suppliedHost)) throw new Error('Context host must be Codex, Claude Code, WorkBuddy or Hermes.');
  const detected = [env.CODEX_THREAD_ID ? 'Codex' : null, env.HERMES_SESSION_ID ? 'Hermes' : null].filter(Boolean);
  const host = suppliedHost ?? (detected.length === 1 ? detected[0]! : null);
  const conversation_id = string('conversation_id') ?? (host === 'Codex' ? env.CODEX_THREAD_ID || env.CODEX_SESSION_ID : host === 'WorkBuddy' ? env.CODEBUDDY_SESSION_ID : host === 'Claude Code' ? env.CLAUDE_SESSION_ID : host === 'Hermes' ? env.HERMES_SESSION_ID : null) ?? null;
  const relationship = string('relationship');
  if (relationship && relationship !== 'child' && relationship !== 'fork') throw new Error('Context relationship must be child or fork.');
  const parent = string('parent_conversation_id');
  if (Boolean(parent) !== Boolean(relationship) || (parent && !conversation_id)) throw new Error('A verified parent relationship needs both conversation IDs and its kind.');
  return { host, conversation_id, conversation_title: string('conversation_title'), agent_id: string('agent_id'),
    agent_name: string('agent_name'), agent_role: string('agent_role'), agent_model: string('agent_model'),
    parent_conversation_id: parent, relationship: relationship as Actor['relationship'],
    source: Object.keys(input).length ? 'caller-context' : conversation_id ? 'host-environment' : 'unavailable' };
}
export async function withArtifactContext<T>(contextFile: string | undefined, name: string | undefined, action: () => Promise<T>): Promise<T> {
  const input = contextFile ? JSON.parse(await readFile(contextFile, 'utf8')) : {};
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Context must be a JSON object.');
  return execution.run({ actor: actorContext(input), name, warnings: [] }, action);
}
export function withAuxiliaryOutputs<T>(action: () => Promise<T>): Promise<T> {
  return execution.run({ ...(execution.getStore() ?? { actor: actorContext(), warnings: [] }), auxiliary: true }, action);
}
export function artifactWarnings(): string[] { return execution.getStore()?.warnings ?? []; }
export function taskTitle(skill: string, secrets: string[] = []): string {
  const names: Record<string, string> = { 'aihub-image': '图片生成', 'aihub-video': '视频生成', 'aihub-audio': '音频任务',
    'aihub-music': '音乐生成', 'aihub-understanding': '多模态分析', 'aihub-document': '文档转换' };
  const value = (execution.getStore()?.name ?? names[skill] ?? skill).normalize('NFKC').trim();
  if (sanitized(value, secrets) !== value || /https?:\/\//i.test(value)) throw new Error('Task name must not contain credentials or URLs.');
  const title = value.replace(/[^A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]+/g, '-').replace(/^-|-$/g, '').slice(0, 32).replace(/-$/, '');
  if (!title) throw new Error('Provide a short Chinese or English task name.');
  return title;
}
function timestamp(date = new Date()): string {
  return [date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((v, i) => String(v).padStart(i ? 2 : 4, '0')).join('');
}
export async function readTaskInfo(path: string): Promise<TaskInfo> {
  const value = JSON.parse(await readFile(path, 'utf8')) as TaskInfo;
  if (value.schema_version !== 1 || value.plugin !== 'aihub-studio' || typeof value.task_id !== 'string' ||
      typeof value.title !== 'string' || !isAbsolute(value.project_root ?? '') || !value.creator ||
      !Array.isArray(value.participants) || !Array.isArray(value.records) || !Array.isArray(value.registered_outputs)) {
    throw new Error('Invalid or unsupported task-info.json; it was not overwritten.');
  }
  return value;
}
export async function findTaskInfo(path: string): Promise<string | undefined> {
  let directory = resolve(path);
  if (await stat(directory).then(s => s.isFile()).catch(() => false)) directory = dirname(directory);
  for (;;) {
    const info = join(directory, 'task-info.json');
    try { await stat(info); await readTaskInfo(info); return info; }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
    const parent = dirname(directory);
    if (parent === directory) return undefined;
    directory = parent;
  }
}
export async function createTask(outputRoot: string, skill: string, kind: string, recordName: string, secrets: string[] = []): Promise<{ root: string; record: string }> {
  assertOutsideInstallation(outputRoot);
  const title = taskTitle(skill, secrets), actor = sanitized(execution.getStore()?.actor ?? actorContext(), secrets);
  const project = await realpath(process.cwd());
  await mkdir(resolve(outputRoot), { recursive: true, mode: 0o700 });
  for (let attempt = 0; attempt < 10; attempt++) {
    const id = randomUUID(), root = join(resolve(outputRoot), `${timestamp()}-${title}-run-${id.replaceAll('-', '').slice(0, 8)}`);
    try { await mkdir(root, { mode: 0o700 }); }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'EEXIST') continue; throw error; }
    const now = new Date().toISOString();
    const info: TaskInfo = { schema_version: 1, task_id: id, plugin: 'aihub-studio', plugin_version: VERSION, skill,
      title, project_root: project, created_at: now, updated_at: now, creator: actor,
      participants: [{ ...actor, relation: 'created', first_at: now, last_at: now }],
      records: [{ path: recordName, kind, purpose: 'primary' }], registered_outputs: [], delivery: null };
    await writePrivateRecord(join(root, 'task-info.json'), info);
    return { root, record: join(root, recordName) };
  }
  throw new Error('Could not reserve a unique task directory.');
}
function storedPath(root: string, path: string): string {
  const delta = relative(root, resolve(path));
  return delta && delta !== '..' && !delta.startsWith('..' + sep) && !isAbsolute(delta) ? delta.split(sep).join('/') : resolve(path);
}
export async function updateTaskInfo(path: string, action: (info: TaskInfo) => Promise<void> | void): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      await withJobLock(path, async () => {
        const info = await readTaskInfo(path);
        await action(info);
        info.updated_at = new Date().toISOString();
        await writePrivateRecord(path, info);
      });
      return;
    } catch (error) {
      if (attempt >= 75 || !/Task record is in use|Could not acquire task record lock/.test(String(error))) throw error;
      await delay(40);
    }
  }
}
export async function participate(record: string, secrets: string[] = [], invalidateDelivery = false): Promise<void> {
  const path = await findTaskInfo(record);
  if (!path) return; // Explicit old-record recovery does not create or backfill metadata.
  const actor = sanitized(execution.getStore()?.actor ?? actorContext(), secrets);
  await updateTaskInfo(path, info => {
    const now = new Date().toISOString();
    const identity = (a: Actor) => JSON.stringify([a.host, a.conversation_id, a.agent_id, a.parent_conversation_id, a.relationship]);
    const existing = info.participants.find(p => identity(p) === identity(actor));
    if (existing) { Object.assign(existing, Object.fromEntries(Object.entries(actor).filter(([, value]) => value !== null))); existing.last_at = now; }
    else info.participants.push({ ...actor, relation: 'continued', first_at: now, last_at: now });
    if (invalidateDelivery) info.delivery = null;
  });
}
export async function touchTask(record: string): Promise<void> {
  try {
    const path = await findTaskInfo(record);
    if (path) await updateTaskInfo(path, () => {});
  } catch {
    const message = `Task metadata update failed; business record remains authoritative: ${record}. Repair locally; do not resubmit.`;
    execution.getStore()?.warnings.push(message);
    process.stderr.write(message + '\n');
  }
}
export async function outputDirectory(record: string, fallback: string): Promise<string> {
  if (execution.getStore()?.auxiliary) return fallback;
  const info = await findTaskInfo(record);
  return info ? join(dirname(info), 'files') : fallback;
}
export async function registerOutputs(record: string, files: string[], delivery?: string, reason = ''): Promise<Record<string, unknown>> {
  const path = await findTaskInfo(record);
  if (!path) throw new Error('Only tasks with task-info.json can register outputs.');
  if (delivery && !['completed', 'partial', 'failed'].includes(delivery)) throw new Error('Delivery must be completed, partial or failed.');
  if (delivery && !reason.trim()) throw new Error('Delivery needs a completion or stopping reason.');
  const project = await realpath(process.cwd());
  const initial = await readTaskInfo(path);
  if (await realpath(initial.project_root) !== project) throw new Error('Task belongs to another project. Use its original working directory.');
  const operational = new Set(initial.records.map(entry => resolve(dirname(path), entry.path).toLowerCase()));
  const auxiliary = /^(task-info\.json|task\.json|run\.json|native-music\.json|download\.json|diagnostic\.json|error-report\.(md|json)|execution-context\.json)$/i;
  const entries: TaskInfo['registered_outputs'] = [];
  for (const file of files) {
    const resolved = await realpath(resolve(file));
    assertOutsideInstallation(resolved);
    const before = await stat(resolved);
    if (!before.isFile() || auxiliary.test(basename(resolved)) || /\.(part|tmp|lock)$/i.test(resolved) || operational.has(resolved.toLowerCase())) throw new Error('Register final output files only; execution records and temporary files are supporting material.');
    const hash = createHash('sha256');
    for await (const chunk of createReadStream(resolved)) hash.update(chunk);
    const after = await stat(resolved);
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs) throw new Error('Output changed while registering it.');
    entries.push({ id: '', path: storedPath(dirname(path), resolved), title: basename(resolved), bytes: after.size, sha256: hash.digest('hex'), registered_at: new Date().toISOString() });
  }
  await updateTaskInfo(path, info => {
    if (resolve(info.project_root) !== project) throw new Error('Task belongs to another project. Use its original working directory.');
    for (const entry of entries) {
      entry.id = createHash('sha256').update(info.task_id + '\0' + entry.path).digest('hex').slice(0, 24);
      const index = info.registered_outputs.findIndex(f => f.path === entry.path);
      if (index < 0) info.registered_outputs.push(entry); else info.registered_outputs[index] = entry;
    }
    if (delivery) info.delivery = { status: delivery as NonNullable<TaskInfo['delivery']>['status'], at: new Date().toISOString(), reason: reason.trim() };
  });
  await participate(path);
  return { status: 'ok', task_info: path, registered: entries.length, delivery: delivery ?? null };
}
