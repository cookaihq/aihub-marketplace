import { createHash } from 'node:crypto';
import { mkdir, readFile, stat } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { AihubmaxClient, ApiError } from './apiClient.js';
import { credentialId, sanitized, type LoadedConfig } from './config.js';
import { downloadAssets } from './download.js';
import { audioContract, audioHash, checkAudioTools, prepareParts, probeAudio, remoteAudio, snapshotAudio, SOURCE_MAX_BYTES, type AudioContract, type AudioInfo, type AudioPart } from './audioMedia.js';
import { mergeTranscripts } from './transcript.js';
import { assertOutsideInstallation, withJobLock, writePrivateRecord, writePrivateText, type SavedFile } from './state.js';
import { adoptTask, failureInfo, generate, resume, TaskPersistenceError } from './workflow.js';

export interface AudioSource extends AudioInfo { original: string; global_start: number }
interface PartState extends AudioPart {
  upload?: { state: 'uploading' | 'known' | 'unknown' | 'rejected'; url?: string; result?: Record<string, unknown> };
  task_record?: string; result?: Record<string, unknown>;
}
export interface AudioRunRecord {
  schema_version: 1; kind: 'aihub-transcription'; model: string; binding: string;
  service_url: string; credential_id: string; contract: AudioContract;
  sources: AudioSource[]; parts: PartState[]; prepared: boolean; status: string;
  preparation_hash?: string;
  files: SavedFile[]; warnings?: string[];
}
const hash = (v: unknown) => createHash('sha256').update(JSON.stringify(v)).digest('hex');
const preparationHash = (v: AudioRunRecord) => hash({ sources: v.sources,
  parts: v.parts.map(({ upload: _upload, result: _result, task_record: _task, ...part }) => part) });
function owned(path: string, root: string): void {
  const sub = relative(root, path);
  if (!isAbsolute(path) || !sub || sub === '..' || sub.startsWith(`..${sep}`) || isAbsolute(sub)) throw new Error('Transcription recovery file is outside this run.');
}
export async function readAudioRun(path: string): Promise<AudioRunRecord> {
  const value = JSON.parse(await readFile(path, 'utf8')) as AudioRunRecord;
  if (value.kind !== 'aihub-transcription' || value.schema_version !== 1 || !Array.isArray(value.parts) || !Array.isArray(value.sources)) throw new Error('Invalid transcription record.');
  const root = dirname(dirname(path));
  for (const source of value.sources) owned(source.path, root);
  for (const part of value.parts) { owned(part.path, root); if (part.task_record) owned(part.task_record, dirname(path)); }
  return value;
}
async function sourceSnapshots(inputs: string[], directory: string): Promise<AudioSource[]> {
  const record = join(directory, 'sources.json');
  const binding = hash(inputs);
  let sources: AudioSource[] = [];
  try {
    const saved = JSON.parse(await readFile(record, 'utf8'));
    if (saved.binding !== binding || !Array.isArray(saved.sources)) throw new Error('Source snapshot manifest does not match this request.');
    sources = saved.sources;
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  for (const s of sources) {
    owned(s.path, directory);
    if (await audioHash(s.path) !== s.sha256) throw new Error('Saved source audio has changed. Restore the original snapshot before continuing.');
  }
  for (let i = sources.length; i < inputs.length; i++) {
    const input = inputs[i]!;
    let info: AudioInfo;
    if (remoteAudio(input)) {
      const downloaded = await downloadAssets([input], join(directory, `remote-${i+1}`), 'audio', SOURCE_MAX_BYTES);
      if (!downloaded.files.length || downloaded.failed.length) throw new Error(downloaded.failed[0]?.error ?? 'Source audio could not be downloaded for measurements.');
      info = await probeAudio(downloaded.files[0]!.path);
    } else info = await snapshotAudio(input, directory, i);
    const previous = sources.at(-1);
    sources.push({ ...info, original: input, global_start: previous ? previous.global_start + previous.duration : 0 });
    await writePrivateRecord(record, { binding, sources });
  }
  return sources;
}
function present(value: AudioRunRecord, record: string, detail?: Record<string, unknown>): Record<string, unknown> {
  return { ...detail, status: value.status, model: value.model, transcription_record: record,
    sources: value.sources, fragments: value.parts.map(p => ({ index: p.index, source_index: p.source_index, path: p.path,
      start: p.start, end: p.end, core_start: p.core_start, core_end: p.core_end, boundary: p.boundary, bytes: p.bytes, duration: p.duration,
      upload_state: p.upload?.state, task_record: p.task_record, task_id: p.result?.task_id, status: p.result?.status ?? 'prepared' })),
    files: value.status === 'delivered' ? value.files : value.parts.flatMap(p => p.result?.files as SavedFile[] ?? []),
    ...(value.warnings ? { warnings: value.warnings } : {}) };
}
export async function runTranscription(cfg: LoadedConfig, options: {
  model: string; params: Record<string, unknown>; inputs: string[]; outputDir: string; waitSeconds: number;
  onRecord: (path: string) => Promise<void>; onSubmit: () => Promise<void>;
}): Promise<Record<string, unknown>> {
  const record = join(resolve(options.outputDir), 'transcription.json');
  assertOutsideInstallation(record);
  const contract = audioContract(options.model); // Each actual candidate gets its own contract and fresh capacity checks.
  const binding = hash({ model: options.model, params: options.params, inputs: options.inputs });
  let value: AudioRunRecord;
  try { value = await readAudioRun(record); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    value = { schema_version: 1, kind: 'aihub-transcription', model: options.model, binding, service_url: cfg.baseUrl,
      credential_id: credentialId(cfg.apiKey), contract, sources: [], parts: [], prepared: false, status: 'preparing', files: [] };
    await writePrivateRecord(record, value);
  }
  if (value.binding !== binding || value.service_url !== cfg.baseUrl || value.credential_id !== credentialId(cfg.apiKey) || hash(value.contract) !== hash(contract)) {
    throw new Error('Transcription model, contract, inputs or account changed; restore the saved context instead of editing an active run.');
  }
  if (value.prepared && value.preparation_hash !== preparationHash(value)) throw new Error('Prepared source/fragment metadata changed; restore the original record.');
  await options.onRecord(record);
  return withJobLock(record, async () => {
    const save = () => writePrivateRecord(record, sanitized(value, [cfg.apiKey]));
    const finish = async (status: string, detail?: Record<string, unknown>) => { value.status = status; await save(); return present(value, record, detail); };
    const deadline = Date.now() + options.waitSeconds * 1000;
    const remaining = () => Math.max(0, Math.floor((deadline-Date.now())/1000));
    try {
      await checkAudioTools();
      if (!value.prepared) {
        value.sources = await sourceSnapshots(options.inputs, join(dirname(options.outputDir), 'audio-sources'));
        value.parts = [];
        for (const [i, source] of value.sources.entries()) {
          const channels = options.params.channel_id;
          if (channels !== undefined && channels !== null && (!Array.isArray(channels) || !channels.length || channels.some(c => !Number.isInteger(c) || c < 0 || c >= source.channels))) {
            throw new Error('channel_id must select existing channels without changing their numbering.');
          }
          const parts = await prepareParts(source, i, contract, join(options.outputDir, `source-${i+1}`), remoteAudio(source.original));
          for (const part of parts) value.parts.push({ ...part, index: value.parts.length });
        }
        value.prepared = true; value.preparation_hash = preparationHash(value); await save();
      }
    } catch (error) { return finish('preprocessing_failed', { error: (error as Error).message }); }
    if (value.status === 'delivered') return present(value, record);
    for (const part of value.parts) {
      if (part.result?.status === 'delivered') {
        try {
          for (const file of part.result.files as SavedFile[]) {
            if ((await stat(file.path)).size !== file.bytes) throw new Error('Changed result');
            JSON.parse(await readFile(file.path, 'utf8'));
          }
          continue;
        } catch { /* Recover the same accepted task when a local result went missing. */ }
      }
      try {
        if (part.result?.status === 'persistence_failed' && typeof part.result.task_id === 'string') {
          part.result = await adoptTask(cfg, part.result.task_id, 'audio', join(options.outputDir, `task-${part.index+1}`), remaining());
          if (typeof part.result.record === 'string') part.task_record = part.result.record;
        } else if (part.task_record) part.result = await resume(cfg, part.task_record, remaining());
        else {
          if (await audioHash(part.path) !== part.sha256 || (await stat(part.path)).size !== part.bytes) return finish('preprocessing_failed', { error: 'Prepared audio changed; restore saved fragments before continuing.' });
          if (part.upload && part.upload.state !== 'known') return finish(part.upload.state === 'rejected' ? 'upload_rejected' : 'upload_unknown', part.upload.result);
          if (!part.upload) {
            const source = value.sources[part.source_index]!;
            if (part.boundary === 'whole' && remoteAudio(source.original)) part.upload = { state: 'known', url: source.original };
            else {
              // Persist intent before a non-idempotent upload. A crash/malformed response must not replay it.
              part.upload = { state: 'uploading' }; await save();
              try {
                const uploaded = await new AihubmaxClient(cfg).request<Record<string, unknown>>('POST', contract.upload.endpoint,
                  { file_data: (await readFile(part.path)).toString('base64'), file_name: basename(part.path), auto_cleanup: false },
                  { timeoutMs: 120_000 });
                const url = typeof uploaded.url === 'string' ? new URL(uploaded.url) : undefined;
                if (!url || !['https:', 'http:'].includes(url.protocol) || url.username || url.password || uploaded.size !== part.bytes) {
                  throw new ApiError('Upload response did not identify the measured audio bytes; upload outcome is unknown.', 200, 'protocol', 'invalid_response', undefined, true);
                }
                part.upload = { state: 'known', url: url.href, result: uploaded }; await save();
              } catch (error) {
                const unknown = !(error instanceof ApiError) || error.ambiguous;
                part.upload = { state: unknown ? 'unknown' : 'rejected', result: { error: (error as Error).message, failure: failureInfo(error, cfg) } };
                return finish(unknown ? 'upload_unknown' : 'upload_rejected', part.upload.result);
              }
            }
            await save();
          }
          part.result = await generate(cfg, { media: 'audio', model: options.model, params: { ...options.params, file_urls: [part.upload.url!] },
            outputDir: join(options.outputDir, `task-${part.index+1}`), waitSeconds: remaining(),
            onRecord: async path => { part.task_record = path; await save(); await options.onSubmit(); } });
        }
      } catch (error) {
        if (error instanceof TaskPersistenceError) part.result = error.output();
        else return finish(part.task_record ? 'recovery_failed' : 'preprocessing_failed', { error: (error as Error).message });
      }
      await save();
      if (part.result.model !== options.model) return finish('merge_failed', { error: 'The remote task reported a different model; its result and task ID were retained without resubmission.' });
      if (part.result.status !== 'delivered') {
        const terminal = ['remote_failed', 'not_submitted'].includes(String(part.result.status));
        const alreadyDelivered = value.parts.some(p => p !== part && p.result?.status === 'delivered');
        // Never pay again for successful fragments by replacing an entire partially completed attempt.
        return finish(terminal && alreadyDelivered ? 'transcription_failed' : String(part.result.status), part.result);
      }
      if (Date.now() >= deadline && value.parts.some(p => p.result?.status !== 'delivered')) return finish('waiting');
    }
    try {
      const pieces = [];
      for (const part of value.parts) {
        const files = part.result!.files as SavedFile[];
        const results = [];
        for (const file of files) results.push(JSON.parse(await readFile(file.path, 'utf8')));
        pieces.push({ part, global_start: value.sources[part.source_index]!.global_start, results });
      }
      const merged = mergeTranscripts(pieces);
      const directory = join(options.outputDir, 'merged'); await mkdir(directory, { recursive: true, mode: 0o700 });
      const json = join(directory, 'transcript.json'); const text = join(directory, 'transcript.txt');
      await writePrivateRecord(json, { ...merged, sources: value.sources, fragments: value.parts.map(p => ({ ...p, raw_files: p.result?.files })) });
      await writePrivateText(text, merged.text + '\n');
      value.files = await Promise.all([{ path: json, mime_type: 'application/json' }, { path: text, mime_type: 'text/plain' }]
        .map(async f => ({ ...f, url: `transcription://${options.model}/${basename(f.path)}`, bytes: (await stat(f.path)).size })));
      value.warnings = merged.warnings;
      return finish('delivered', { text: merged.text });
    } catch (error) { return finish('merge_failed', { error: (error as Error).message }); }
  });
}
