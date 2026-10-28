import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { audioContract, canSendWhole, prepareParts, probeAudio, type AudioPart } from '../src/audioMedia.js';
import { mergeTranscripts, transcriptText } from '../src/transcript.js';
import { selectionPlan } from '../src/selection.js';
const exec = promisify(execFile);

test('waveform segmentation prefers a longer pause, keeps all channels, and verifies real byte/duration margins', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'aihub-waveform-'));
  try {
    const path = join(dir, 'pauses.wav');
    await exec('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', "aevalsrc='if(between(t,7,8),0,0.2*sin(2*PI*440*t))':s=16000:d=20", '-ac', '2', path]);
    const source = await probeAudio(path);
    const contract = audioContract('paraformer-v2'); contract.max_bytes = 640_000;
    const parts = await prepareParts(source, 0, contract, join(dir, 'parts'));
    assert.equal(parts[0]!.boundary, 'pause'); assert.ok(parts[0]!.core_end >= 7 && parts[0]!.core_end <= 8);
    assert.equal(parts[0]!.start, 0); assert.equal(parts.at(-1)!.core_end, source.duration);
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]!;
      assert.ok(part.bytes <= contract.max_bytes * 0.9); assert.equal(part.channels, 2);
      assert.ok(Math.abs(part.duration - (part.end-part.start)) < 0.025);
      if (i) assert.equal(part.core_start, parts[i-1]!.core_end);
    }
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('continuous opposite-phase stereo uses low-energy overlap, never cancellation as a false pause', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'aihub-no-pause-'));
  try {
    const path = join(dir, 'continuous.wav');
    await exec('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'aevalsrc=0.2*sin(2*PI*440*t)|-0.2*sin(2*PI*440*t):s=16000:d=12', path]);
    const source = await probeAudio(path);
    const contract = audioContract('paraformer-v2'); contract.max_bytes = 400_000;
    const parts = await prepareParts(source, 0, contract, join(dir, 'parts'));
    assert.equal(parts[0]!.boundary, 'low_energy');
    assert.ok(parts[1]!.start < parts[0]!.end);
    assert.ok(parts[0]!.end-parts[1]!.start <= 0.801);
    assert.equal(parts.at(-1)!.end, 12);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('whole-file eligibility uses actual model, format, duration and upload channel independently', () => {
  const info = { path: '/recording.wav', bytes: 25*1024**2, duration: 600, sample_rate: 16000, channels: 1, format: 'wav', sha256: 'fixture' };
  const standard = audioContract('paraformer-v2');
  assert.equal(canSendWhole(info, standard, false), false);
  assert.equal(canSendWhole(info, standard, true), true);
  assert.equal(canSendWhole({ ...info, duration: 43201 }, standard, true), false);
  assert.equal(canSendWhole({ ...info, format: 'aiff' }, standard, true), false);
  assert.equal(canSendWhole({ ...info, bytes: 10000 }, audioContract('paraformer-8k-v2'), false), false);
  assert.throws(() => audioContract('scribe-v2'), /No verified/);
  const cfg = { skill: 'aihub-audio', apiKey: 'fixture', baseUrl: 'https://fixture.invalid', sources: { AIHUB_API_KEY: 'fixture', AIHUB_BASE_URL: 'fixture' }, modelSelection: { policy: 'auto' as const, models: ['paraformer-v2','paraformer-8k-v2'], sources: {} } };
  const plan = selectionPlan(cfg, { operation: 'audio-transcribe', original_request: 'Transcribe in English', inputs: { audios: ['voice.wav'] }, requirements: { language_hints: ['en'] } });
  assert.equal(plan.candidates[0]!.rejection, undefined); assert.match(plan.candidates[1]!.rejection!, /language_hints/);
});

const part = (index: number, start: number, end: number, source_index = 0): AudioPart => ({ index, source_index, start, end,
  core_start: start, core_end: end, boundary: 'low_energy', path: 'fixture', bytes: 100, duration: end-start, sample_rate: 16000, channels: 1, format: 'wav', sha256: 'fixture' });
test('merge preserves every transcript, global times and local speakers; only overlapping equal words are removed', () => {
  const sentence = (text: string, begin_time: number, end_time: number) => ({ text, begin_time, end_time, speaker_id: 0 });
  const merged = mergeTranscripts([
    { part: part(0,0,10.4), global_start: 0, results: [{ transcripts: [{ channel_id: 0, text: '你好。重复。', sentences: [sentence('你好。',0,1000), sentence('重复。',9900,10200)] }] }] },
    { part: part(1,9.6,20), global_start: 0, results: [{ transcripts: [{ channel_id: 0, sentences: [sentence('重复。',300,600), sentence('继续。',700,1200), sentence('重复。',3000,3400)] }] }] },
    { part: part(2,0,2,1), global_start: 20, results: [{ transcripts: [{ channel_id: 0, sentences: [sentence('最后。',100,900)] }] }] },
  ]);
  assert.equal(merged.text, '你好。\n重复。\n继续。\n重复。\n最后。');
  assert.equal(merged.duplicates.length, 1); assert.equal(merged.segments.at(-1)!.start, 20.1);
  assert.notEqual(merged.segments[0]!.speaker, merged.segments[2]!.speaker);
  assert.equal(merged.speaker_alignment, 'fragment-local');
  assert.equal(transcriptText([{ transcripts: [{ text: '第一段', sentences: [{ text: '第一段' }] }, { text: '第二段' }] }, { text: '第三段' }]), '第一段\n第二段\n第三段');
});

test('missing timestamps are explicit and exact overlap trimming never removes repetition at non-overlap boundaries', () => {
  const merged = mergeTranscripts([
    { part: part(0,0,10.4), global_start: 0, results: [{ text: '这是一句完整的话' }] },
    { part: part(1,9.6,20), global_start: 0, results: [{ text: '完整的话继续说下去' }] },
    { part: part(2,20,30), global_start: 0, results: [{ text: '继续说下去' }] },
  ]);
  assert.equal(merged.text, '这是一句完整的话\n继续说下去\n继续说下去');
  assert.ok(merged.warnings.some(w => /no timestamps/.test(w))); assert.equal(merged.segments[1]!.start, undefined);
});

test('incomplete sentence lists keep full text and separate global timestamps without claiming alignment', () => {
  const merged = mergeTranscripts([{ part: part(1,10,20), global_start: 30,
    results: [{ transcripts: [{ channel_id: 1, text: '开头。遗漏的中间句。结尾。', sentences: [
      { text: '开头。', begin_time: 0, end_time: 1000, speaker_id: 0 },
      { text: '结尾。', begin_time: 2000, end_time: 3000, speaker_id: 0 },
    ] }] }] }]);
  assert.equal(merged.text, '开头。遗漏的中间句。结尾。');
  assert.equal(merged.segments[0]!.text_alignment, 'unverified');
  assert.equal(merged.segments[0]!.start, undefined);
  assert.equal(merged.segments[0]!.sentences![1]!.start, 42);
  assert.match(merged.segments[0]!.sentences![0]!.speaker!, /source-1\/part-2\/channel-1\/speaker-0/);
  assert.ok(merged.warnings.some(w => /differs from the sentence list/.test(w)));
  assert.throws(() => mergeTranscripts([{ part: part(0,0,1), global_start: 0, results: [{text:'句子',words:[{text:'句子',begin_time:0,end_time:3000}]}] }]), /timestamps exceed/);
});

test('incomplete word lists cannot erase parent sentence text during overlap removal', () => {
  const merged = mergeTranscripts([
    { part: part(0,0,10.4), global_start: 0, results: [{text:'开始重复',begin_time:9700,end_time:10200,words:[{text:'开始',begin_time:9700,end_time:9900},{text:'重复',begin_time:9900,end_time:10200}]}] },
    { part: part(1,9.6,20), global_start: 0, results: [{text:'重复不能丢失的文字结束',begin_time:300,end_time:2000,words:[{text:'重复',begin_time:300,end_time:600},{text:'结束',begin_time:1700,end_time:2000}]}] },
  ]);
  assert.ok(merged.text.includes('不能丢失的文字结束'));
  assert.ok(merged.warnings.some(w => /word list differs/.test(w)));
});

test('timed channels interleave chronologically while source files retain their requested order', () => {
  const merged = mergeTranscripts([{part:part(0,0,5),global_start:0,results:[{transcripts:[
    {channel_id:0,sentences:[{text:'先说',begin_time:0,end_time:1000},{text:'再说',begin_time:3000,end_time:4000}]},
    {channel_id:1,sentences:[{text:'回应',begin_time:1500,end_time:2500}]},
  ]}] }]);
  assert.equal(merged.text,'先说\n回应\n再说');
});
