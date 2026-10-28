import type { AudioPart } from './audioMedia.js';

type Row = Record<string, unknown>;
const object = (v: unknown): v is Row => !!v && typeof v === 'object' && !Array.isArray(v);
export interface TranscriptUnit {
  text: string; start?: number; end?: number; speaker?: string; channel?: string;
  words?: TranscriptUnit[]; sentences?: TranscriptUnit[]; text_alignment?: 'unverified'; source_index?: number; part_index?: number;
}
/** Prefer a complete parent transcript; do not repeat its word/sentence children. */
export function transcriptText(value: unknown): string {
  if (Array.isArray(value)) return value.map(transcriptText).filter(Boolean).join('\n');
  if (!object(value)) return typeof value === 'string' ? value : '';
  if (typeof value.text === 'string') return value.text;
  return Object.entries(value).filter(([key,v]) => typeof v === 'object' && !['file_url', 'transcription_url', 'result_url'].includes(key))
    .map(([,v]) => transcriptText(v)).filter(Boolean).join('\n');
}
function timing(row: Row): Pick<TranscriptUnit, 'start' | 'end'> {
  // Paraformer returns milliseconds; never guess units from the magnitude.
  const start = row.begin_time; const end = row.end_time;
  return typeof start === 'number' && typeof end === 'number' && Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end >= start
    ? { start: start / 1000, end: end / 1000 } : {};
}
export function transcriptUnits(value: unknown, channel?: string): TranscriptUnit[] {
  if (Array.isArray(value)) return value.flatMap(v => transcriptUnits(v, channel));
  if (!object(value)) return typeof value === 'string' && value ? [{ text: value }] : [];
  const localChannel = value.channel_id === undefined ? channel : String(value.channel_id);
  const children = Array.isArray(value.transcripts) ? value.transcripts : Array.isArray(value.sentences) && value.sentences.length ? value.sentences : undefined;
  if (children) {
    const units = transcriptUnits(children, localChannel);
    if (typeof value.text !== 'string' || normalized(value.text) === normalized(units.map(u => u.text).join(''))) return units;
    // Keep the complete parent text when sentence data is incomplete or inconsistent.
    // Child timestamps remain available, but must not be asserted as an alignment for that text.
    return [{ text: value.text, ...timing(value), text_alignment: 'unverified', sentences: units,
      ...(localChannel === undefined ? {} : { channel: localChannel }) }];
  }
  if (typeof value.text === 'string') return [{ text: value.text, ...timing(value),
    ...(localChannel === undefined ? {} : { channel: localChannel }),
    ...(value.speaker_id === undefined ? {} : { speaker: String(value.speaker_id) }),
    ...(Array.isArray(value.words) ? { words: transcriptUnits(value.words, localChannel) } : {}) }];
  return Object.values(value).filter(v => typeof v === 'object').flatMap(v => transcriptUnits(v, localChannel));
}
function normalized(text: string): string { return text.normalize('NFKC').toLowerCase().replace(/[\p{P}\p{Z}\s]/gu, ''); }
function joinWords(units: TranscriptUnit[]): string {
  return units.map(u => u.text).reduce((text, next) => !text ? next : `${text}${/[a-z0-9]$/i.test(text) && /^[a-z0-9]/i.test(next) ? ' ' : ''}${next}`, '');
}
function trimOverlap(previous: string, text: string): { text: string; removed: string } {
  // Only exact boundary matches inside an actual overlapping cut. No document-wide deduplication.
  for (let n = Math.min(previous.length, text.length, 500); n >= 2; n--) {
    const prefix = text.slice(0,n);
    if (previous.endsWith(prefix) && (/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]{2}/u.test(prefix) || prefix.trim().split(/\s+/).length >= 2)) {
      return { text: text.slice(n).trimStart(), removed: prefix };
    }
  }
  return { text, removed: '' };
}
export interface TranscriptPiece { part: AudioPart; global_start: number; results: unknown[] }
export function mergeTranscripts(pieces: TranscriptPiece[]) {
  const segments: TranscriptUnit[] = [];
  const duplicates: Array<{ part_index: number; text: string; method: string }> = [];
  const warnings = new Set<string>(['Speaker IDs are local to each fragment and channel; cross-fragment identity has not been established.']);
  let previousPiece: TranscriptPiece | undefined;
  let previousUnits: TranscriptUnit[] = [];
  for (const piece of pieces) {
    const { part } = piece;
    const offset = piece.global_start + part.start;
    const overlap = previousPiece?.part.source_index === part.source_index && previousPiece.part.end > part.start + 0.01;
    const overlapEnd = overlap ? piece.global_start + previousPiece!.part.end : -1;
    const map = (unit: TranscriptUnit): TranscriptUnit => ({ ...unit,
      ...(unit.start === undefined ? {} : { start: unit.start + offset, end: unit.end! + offset }),
      ...(unit.speaker === undefined ? {} : { speaker: `source-${part.source_index+1}/part-${part.index+1}/channel-${unit.channel ?? '0'}/speaker-${unit.speaker}` }),
      source_index: part.source_index, part_index: part.index,
      ...(unit.words ? { words: unit.words.map(map) } : {}),
      ...(unit.sentences ? { sentences: unit.sentences.map(map) } : {}) });
    const current = transcriptUnits(piece.results).map(map);
    if (!current.length) throw new Error(`No recognizable transcription content for fragment ${part.index+1}; preserve the task and raw results, do not resubmit.`);
    if (current.every(unit => unit.start !== undefined)) current.sort((a,b) => a.start! - b.start!);
    const boundaryByChannel = new Map<string | undefined, TranscriptUnit[]>();
    // Compare only the adjacent overlapping fragment, not the entire recording for every sentence.
    if (overlap) for (const unit of previousUnits) {
      const channel = boundaryByChannel.get(unit.channel) ?? [];
      channel.push(unit); boundaryByChannel.set(unit.channel, channel);
    }
    const accepted: TranscriptUnit[] = [];
    const validate = (unit: TranscriptUnit): void => {
      if (unit.start !== undefined && (unit.end! > piece.global_start + part.end + 0.25 || unit.start < offset - 0.05)) {
        throw new Error('Transcript timestamps exceed their source fragment; raw results were retained for inspection.');
      }
      for (const child of [...(unit.words ?? []), ...(unit.sentences ?? [])]) validate(child);
    };
    for (const [index, unit] of current.entries()) {
      validate(unit);
      if (unit.text_alignment === 'unverified') warnings.add('Full text differs from the sentence list; complete text and separate sentence timestamps were preserved without claiming alignment.');
      if (unit.start === undefined) warnings.add('Some results have no timestamps; global timestamps cannot be reconstructed for those text spans.');
      const prior = boundaryByChannel.get(unit.channel) ?? [];
      const duplicate = (candidate: TranscriptUnit, earlier: TranscriptUnit[]) => overlap && candidate.start !== undefined && candidate.end !== undefined &&
        candidate.start < overlapEnd && candidate.end >= offset && earlier.some(p => p.start !== undefined && p.end !== undefined &&
          normalized(p.text) === normalized(candidate.text) && normalized(candidate.text).length > 0 &&
          Math.min(p.end, candidate.end!) - Math.max(p.start, candidate.start!) > 0 && Math.abs(p.start-candidate.start!) <= 0.3);
      const completeWords = unit.words?.length && normalized(joinWords(unit.words)) === normalized(unit.text);
      if (unit.words?.length && !completeWords) warnings.add('A word list differs from its full sentence; sentence text was preserved and word-level deduplication was skipped.');
      if (completeWords && unit.words!.every(w => w.start !== undefined)) {
        const words = unit.words!.filter(w => !duplicate(w, prior.flatMap(p => p.words ?? [])));
        if (words.length !== unit.words!.length) {
          duplicates.push({ part_index: part.index, text: unit.words!.filter(w => !words.includes(w)).map(w => w.text).join(''), method: 'overlapping-word-time-and-text' });
          if (!words.length) continue;
          unit.words = words; unit.text = joinWords(words); unit.start = words[0]!.start; unit.end = words.at(-1)!.end;
        }
      } else if (duplicate(unit, prior)) {
        duplicates.push({ part_index: part.index, text: unit.text, method: 'overlapping-sentence-time-and-text' }); continue;
      } else if (overlap && index === 0) {
        const last = prior.at(-1);
        if (last && (unit.start === undefined || unit.start < overlapEnd)) {
          const trimmed = trimOverlap(last.text, unit.text);
          if (trimmed.removed) {
            duplicates.push({ part_index: part.index, text: trimmed.removed, method: 'exact-boundary-text' });
            unit.text = trimmed.text;
            // A partial sentence's original timing remains a span, never an invented word alignment.
            warnings.add('Boundary text deduplication used an exact text match; sentence timestamps retain the original span.');
          } else warnings.add('An overlapping boundary could not be aligned confidently; both text spans were retained for review.');
        }
      }
      if (unit.text) { segments.push(unit); accepted.push(unit); }
    }
    previousPiece = piece;
    previousUnits = accepted;
  }
  return { schema_version: 1, time_unit: 'seconds', speaker_alignment: 'fragment-local',
    text: segments.map(s => s.text).join('\n'), segments, duplicates, warnings: [...warnings] };
}
