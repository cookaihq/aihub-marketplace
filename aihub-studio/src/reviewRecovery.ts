import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { credentialId, sanitized, type LoadedConfig } from './config.js';
import type { RunRecord } from './runs.js';
import { assertOutsideInstallation, withJobLock, writePrivateRecord } from './state.js';

export interface VerifiedLocalFile { path: string; sha256: string; bytes: number }
export interface ReviewRecoveryBinding {
  run_sha256: string; audio_record: VerifiedLocalFile; artifacts: VerifiedLocalFile[]; sources: VerifiedLocalFile[];
}
interface RecoveryEvent {
  id: string; at: string; credential_id: string; outcome: 'authorized' | 'blocked'; reason: string;
  run_id: string; plan_hash: string; original_credential_id: string; skill: string; service_url: string;
  error?: string; binding?: ReviewRecoveryBinding;
}
interface RecoveryRecord {
  schema_version: 1; kind: 'aihub-review-recovery'; source_record: string;
  events: RecoveryEvent[];
}
export const recoveryRecord = (source: string) => join(dirname(source), 'review-recovery.json');
export async function localFileHash(file: string): Promise<string> {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk as Buffer);
  return hash.digest('hex');
}
function belongs(value: RecoveryRecord, source: string): boolean {
  return value.schema_version === 1 && value.kind === 'aihub-review-recovery' && value.source_record === source &&
    Array.isArray(value.events);
}
export async function appendRecoveryEvent(cfg: LoadedConfig, source: string, run: RunRecord, event: Pick<RecoveryEvent, 'outcome' | 'reason' | 'error' | 'binding'>): Promise<void> {
  const record = recoveryRecord(source);
  assertOutsideInstallation(record);
  await withJobLock(record, async () => {
    let saved: RecoveryRecord;
    try {
      saved = JSON.parse(await readFile(record, 'utf8')) as RecoveryRecord;
      if (!belongs(saved, source)) throw new Error('Recovery history belongs to another run. Restore the original records.');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      saved = { schema_version: 1, kind: 'aihub-review-recovery', source_record: source, events: [] };
    }
    saved.events.push({ id: randomUUID(), at: new Date().toISOString(), credential_id: credentialId(cfg.apiKey),
      run_id: run.id, plan_hash: run.plan_hash, original_credential_id: run.credential_id, skill: run.skill, service_url: run.service_url, ...event });
    await writePrivateRecord(record, sanitized(saved, [cfg.apiKey]));
  });
}
export async function verifyLocalFile(file: VerifiedLocalFile): Promise<void> {
  assertOutsideInstallation(file.path);
  const info = await stat(file.path);
  if (!info.isFile() || info.size !== file.bytes || !/^[0-9a-f]{64}$/.test(file.sha256) || await localFileHash(file.path) !== file.sha256) {
    throw new Error('Saved source or artifact is missing or changed. Restore the original local files.');
  }
}
/** A local authorization never changes the ASR credential or permits remote recovery. */
export async function verifyReviewRecovery(cfg: LoadedConfig, source: string, run: RunRecord): Promise<void> {
  if (run.status !== 'delivered' || run.skill !== 'aihub-audio' || run.plan.request.operation !== 'audio-transcribe') {
    throw new Error('Review credential recovery is only available for delivered local transcription runs.');
  }
  let saved: RecoveryRecord;
  try { saved = JSON.parse(await readFile(recoveryRecord(source), 'utf8')); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    throw new Error('This run belongs to another credential. Explicitly authorize delivered local review with review-recover first.');
  }
  if (!belongs(saved, source)) throw new Error('Recovery history does not match the original run identity.');
  const event = saved.events.filter(e => e.credential_id === credentialId(cfg.apiKey)).at(-1);
  if (event?.outcome !== 'authorized' || !event.binding) throw new Error('This credential has no valid local review recovery authorization.');
  if (event.run_id !== run.id || event.plan_hash !== run.plan_hash || event.original_credential_id !== run.credential_id ||
    event.skill !== cfg.skill || event.service_url !== cfg.baseUrl) throw new Error('Recovery authorization does not match the original run identity or current scope.');
  const binding = event.binding;
  if (await localFileHash(source) !== binding.run_sha256) throw new Error('The delivered run changed after review recovery authorization.');
  if (!Array.isArray(binding.artifacts) || !binding.artifacts.length || !Array.isArray(binding.sources) || !binding.sources.length ||
    resolve(run.attempts.at(-1)?.audio_record ?? '') !== binding.audio_record.path) throw new Error('Invalid local review recovery binding.');
  for (const file of [binding.audio_record, ...binding.artifacts, ...binding.sources]) await verifyLocalFile(file);
}
