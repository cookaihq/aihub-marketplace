import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createReadStream, createWriteStream } from 'node:fs';
import { mkdir, open, stat } from 'node:fs/promises';
import { extname, join, resolve } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { promisify } from 'node:util';
import { preparePrivateFile } from './privateFile.js';
import { assertOutsideInstallation } from './state.js';
const exec = promisify(execFile);
// This is the shipped base64 adapter's client-side bound, not a model limit.
export const UPLOAD_MAX_BYTES = 20 * 1024 * 1024;
export const SOURCE_MAX_BYTES = 8 * 1024 ** 3;
const MARGIN = 0.9;
const OVERLAP_SECONDS = 0.4;
const FORMATS = 'aac,amr,avi,flac,flv,mov,mp3,mpeg,ogg,opus,wav,matroska,asf,aiff,ac3,eac3';
const INPUT_GUARDS = ['-protocol_whitelist', 'file', '-format_whitelist', FORMATS];
export function audioContract(model) {
    if (!['paraformer-v2', 'paraformer-8k-v2'].includes(model)) {
        throw new Error(`No verified size/duration/format contract for ${model}; automatic transcription preparation is unavailable. Do not assume another model's limits.`);
    }
    return { model, max_bytes: 2_000_000_000, max_seconds: 12 * 3600,
        formats: ['aac', 'amr', 'avi', 'flac', 'flv', 'm4a', 'mkv', 'mov', 'mp3', 'mp4', 'mpeg', 'ogg', 'opus', 'wav', 'webm', 'wma', 'wmv'],
        ...(model === 'paraformer-8k-v2' ? { sample_rate: 8000 } : {}),
        upload: { endpoint: '/v1/files/upload/base64', max_bytes: UPLOAD_MAX_BYTES, basis: 'client-adapter-bound' },
        source: 'https://docs.aihubmax.com/openapi/zh/paraformer-v2.json' };
}
export function remoteAudio(input) { return /^https?:\/\//i.test(input); }
export async function audioHash(path) {
    const digest = createHash('sha256');
    for await (const chunk of createReadStream(path))
        digest.update(chunk);
    return digest.digest('hex');
}
export async function checkAudioTools() {
    for (const program of ['ffmpeg', 'ffprobe']) {
        try {
            const { stdout } = await exec(program, ['-version'], { timeout: 10_000, windowsHide: true });
            if (!stdout.startsWith(`${program} version `))
                throw new Error('Unexpected executable');
        }
        catch {
            const install = process.platform === 'win32' ? 'winget install Gyan.FFmpeg' : process.platform === 'darwin' ? 'brew install ffmpeg' : 'sudo apt-get install ffmpeg';
            throw new Error(`${program} cannot run. Put an existing FFmpeg installation on PATH, or install it: ${install}`);
        }
    }
}
export async function probeAudio(path) {
    const info = await stat(path);
    if (!info.isFile() || info.size <= 0 || info.size > SOURCE_MAX_BYTES)
        throw new Error('Audio source must be a nonempty file within the 8 GiB local preparation budget.');
    const { stdout } = await exec('ffprobe', ['-v', 'error', ...INPUT_GUARDS, '-show_entries',
        'stream=codec_type,sample_rate,channels,duration:format=duration,format_name', '-of', 'json', resolve(path)], { timeout: 120_000, maxBuffer: 1024 * 1024, windowsHide: true });
    const data = JSON.parse(stdout);
    const streams = (data.streams ?? []).filter((s) => s.codec_type === 'audio');
    if (streams.length !== 1)
        throw new Error('Expected one audio stream; separate multiple streams explicitly so none is silently discarded.');
    const audio = streams[0];
    const duration = Number(audio.duration ?? data.format?.duration);
    const rate = Number(audio.sample_rate);
    const channels = Number(audio.channels);
    if (!Number.isFinite(duration) || duration <= 0 || !Number.isInteger(rate) || rate < 1000 || !Number.isInteger(channels) || channels < 1 || channels > 32) {
        throw new Error('Cannot establish finite audio duration, sample rate and channel count.');
    }
    // Trust the probed container, with its documented extension aliases, not the filename alone.
    const format = String(data.format?.format_name).split(',')[0];
    return { path: resolve(path), bytes: info.size, duration, sample_rate: rate, channels, format, sha256: await audioHash(path) };
}
async function emptyPrivateFile(path) {
    const handle = await open(path, 'w', 0o600);
    await handle.close();
    await preparePrivateFile(path);
}
export async function snapshotAudio(input, directory, index) {
    assertOutsideInstallation(directory);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    const before = await stat(input);
    if (!before.isFile() || before.size <= 0 || before.size > SOURCE_MAX_BYTES)
        throw new Error('Audio source exceeds the 8 GiB local preparation budget or is empty.');
    const path = join(directory, `source-${index + 1}${extname(input).replace(/[^.a-zA-Z0-9]/g, '').slice(0, 16) || '.audio'}`);
    await emptyPrivateFile(path);
    await pipeline(createReadStream(input), createWriteStream(path, { flags: 'w', mode: 0o600 }));
    const after = await stat(input);
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs)
        throw new Error('Source changed during snapshot; no upload was attempted.');
    return probeAudio(path);
}
function acceptedFormat(info, contract) {
    const aliases = { mov: 'mp4', matroska: 'mkv', asf: 'wma' };
    return contract.formats.includes(aliases[info.format] ?? info.format);
}
export function canSendWhole(info, contract, remote) {
    return info.bytes <= Math.min(contract.max_bytes, remote ? Infinity : contract.upload.max_bytes) &&
        info.duration <= contract.max_seconds && acceptedFormat(info, contract) &&
        (!contract.sample_rate || contract.sample_rate === info.sample_rate);
}
/** At most 60 seconds of 8 kHz PCM (<= 62 MiB for 32 channels), independent of recording duration. */
async function waveform(path, start, end, channels) {
    const { stdout } = await exec('ffmpeg', ['-nostdin', '-v', 'error', ...INPUT_GUARDS,
        '-ss', String(start), '-i', path, '-t', String(end - start), '-map', '0:a:0', '-vn',
        '-ar', '8000', '-f', 'f32le', 'pipe:1'], { encoding: 'buffer', timeout: 120_000, maxBuffer: 64 * 1024 * 1024, windowsHide: true });
    const frames = [];
    for (let byte = 0; byte + 640 * channels <= stdout.length; byte += 640 * channels) {
        const sums = Array(channels).fill(0);
        for (let i = 0; i < 160; i++)
            for (let ch = 0; ch < channels; ch++) {
                const sample = stdout.readFloatLE(byte + (i * channels + ch) * 4);
                sums[ch] += sample * sample;
            }
        // Max channel energy avoids opposite-phase channels cancelling into false silence.
        frames.push({ time: start + byte / (32000 * channels) + 0.01, rms: Math.sqrt(Math.max(...sums) / 160) });
    }
    if (!frames.length)
        throw new Error('No decoded waveform at the planned boundary.');
    return frames;
}
export function chooseBoundary(frames, earliest, latest) {
    const eligible = frames.filter(f => f.time >= earliest && f.time <= latest);
    if (!eligible.length || eligible.some(f => !Number.isFinite(f.rms)))
        throw new Error('No usable energy samples near the boundary.');
    const levels = eligible.map(f => f.rms).sort((a, b) => a - b);
    const speech = levels[Math.floor(levels.length * 0.8)];
    const threshold = Math.max(0.0003, Math.min(0.01, speech * 0.15));
    const pauses = [];
    let start;
    for (const f of eligible) {
        if (f.rms <= threshold) {
            start ??= f.time - 0.01;
        }
        else if (start !== undefined) {
            pauses.push({ start, end: f.time - 0.01 });
            start = undefined;
        }
    }
    if (start !== undefined)
        pauses.push({ start, end: eligible.at(-1).time + 0.01 });
    const pause = pauses.filter(p => p.end - p.start >= 0.35)
        .sort((a, b) => (b.end - b.start) - (a.end - a.start) || b.end - a.end)[0];
    if (pause)
        return { time: Math.max(earliest, Math.min(latest, (pause.start + pause.end) / 2)), kind: 'pause' };
    const low = eligible.reduce((a, b) => b.rms < a.rms || (b.rms === a.rms && b.time > a.time) ? b : a);
    return { time: low.time, kind: 'low_energy' };
}
/** PCM makes the capacity estimate independent of compression, then ffprobe/stat verify every output. */
export async function prepareParts(source, sourceIndex, contract, directory, remote = false) {
    assertOutsideInstallation(directory);
    if (canSendWhole(source, contract, remote))
        return [{ ...source, index: 0, source_index: sourceIndex, start: 0, end: source.duration,
                core_start: 0, core_end: source.duration, boundary: 'whole' }];
    await mkdir(directory, { recursive: true, mode: 0o700 });
    const byteBudget = Math.floor(Math.min(contract.max_bytes, contract.upload.max_bytes) * MARGIN);
    const rate = contract.sample_rate ?? source.sample_rate;
    const capacity = Math.min(contract.max_seconds * MARGIN, (byteBudget - 4096) / (rate * source.channels * 2));
    if (capacity < 2)
        throw new Error('This model/upload capacity cannot hold a safe audio fragment.');
    const parts = [];
    let coreStart = 0;
    let overlapBefore = 0;
    const deadline = Date.now() + 30 * 60_000;
    while (coreStart < source.duration - 0.0001) {
        if (parts.length >= 10_000 || Date.now() >= deadline)
            throw new Error('Audio preparation resource budget exhausted; no transcription was submitted.');
        const start = Math.max(0, coreStart - overlapBefore);
        let end = Math.min(source.duration, start + capacity);
        let boundary = 'end';
        let coreEnd = end;
        let overlapAfter = 0;
        if (end < source.duration) {
            const latest = end - OVERLAP_SECONDS;
            const earliest = Math.max(coreStart + 0.5, latest - Math.min(60, capacity * 0.25));
            const cut = chooseBoundary(await waveform(source.path, earliest, latest, source.channels), earliest, latest);
            coreEnd = cut.time;
            boundary = cut.kind;
            overlapAfter = boundary === 'low_energy' ? OVERLAP_SECONDS : 0;
            end = coreEnd + overlapAfter;
        }
        const path = join(directory, `part-${parts.length + 1}.wav`);
        await emptyPrivateFile(path);
        await exec('ffmpeg', ['-nostdin', '-v', 'error', ...INPUT_GUARDS, '-ss', String(start), '-i', source.path,
            '-t', String(end - start), '-map', '0:a:0', '-vn', '-c:a', 'pcm_s16le', '-ar', String(rate), '-y', path], { timeout: Math.ceil(Math.min(10 * 60_000, Math.max(30_000, (end - start) * 1000))), maxBuffer: 1024 * 1024, windowsHide: true });
        const actual = await probeAudio(path);
        if (actual.bytes > byteBudget || actual.duration > contract.max_seconds * MARGIN || Math.abs(actual.duration - (end - start)) > 0.025 ||
            actual.channels !== source.channels || actual.sample_rate !== rate)
            throw new Error('Encoded fragment failed its measured size, duration, channels or coverage check; no upload was attempted.');
        parts.push({ ...actual, index: parts.length, source_index: sourceIndex, start, end, core_start: coreStart, core_end: coreEnd, boundary });
        coreStart = coreEnd;
        overlapBefore = overlapAfter;
    }
    return parts;
}
