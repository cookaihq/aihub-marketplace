import { createHash, randomUUID } from 'node:crypto';
import { readFile, realpath, stat, writeFile, mkdir } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { AihubmaxClient, ApiError, PollBudgetExceededError } from './apiClient.js';
import { credentialId, sanitized } from './config.js';
import { checkMediaTools, downloadAssets, downloadJsonAssets, validateLocalMedia } from './download.js';
import { validateGeneration, generationModelAvailable } from './models.js';
import { speechParameters } from './speech.js';
import { SUNO_MODELS, sunoParameters } from './suno.js';
import { bindDiagnosticRecord } from './diagnostics.js';
import { UPLOAD_MAX_BYTES } from './audioMedia.js';
import { transcriptText } from './transcript.js';
import { ELEVEN_AUDIO_MODELS, ELEVEN_MUSIC_MODEL, ELEVEN_VOICE_MODELS, VOICE_DESIGN_MODEL, VOICE_CREATE_MODEL, SCRIBE_MODELS, elevenAudioParameters } from './elevenlabs.js';
import { voiceObject, voiceDesign, createdVoice, previewOutput, designBinding, selectionParams, SAVE_VOICE_ID_NOTICE } from './voiceCreation.js';
import { assertOutsideInstallation, readJob, recordPath, withJobLock, writeJob, writePrivateText, writePrivateRecord } from './state.js';
import { createTask, findTaskInfo, outputDirectory, participate, readTaskInfo, touchTask, updateTaskInfo } from './taskInfo.js';
function cleanError(error, cfg) {
    return sanitized(error instanceof Error ? error.message : String(error), [cfg.apiKey]);
}
export function failureInfo(error, cfg) {
    return sanitized(error instanceof ApiError ? { http_status: error.status, code: error.code,
        type: error.type, request_id: error.requestId, ambiguous: error.ambiguous, ...(error.details ? { details: error.details } : {}) }
        : { http_status: 0, ambiguous: true }, [cfg.apiKey]);
}
export class TaskPersistenceError extends Error {
    job;
    record;
    constructor(job, record, message) {
        super(message);
        this.job = job;
        this.record = record;
        this.name = 'TaskPersistenceError';
    }
    output() {
        const output = result(this.job, this.record, 'persistence_failed');
        if (this.job.submission.state === 'known') {
            output.next_action = { command: 'task', args: ['--skill', this.job.skill, '--task-id', this.job.submission.task.id,
                    '--media', this.job.media, '--output-dir', dirname(dirname(this.record))] };
        }
        return { ...output, error: this.message, record_saved: false };
    }
}
const RESULT_METADATA_KEYS = [
    'lyrics', 'seed', 'degraded_reason', 'map_type', 'result_type',
    'profile_id', 'character_id', 'voice_id', 'duration', 'resolution',
    // Keep the provider's segmented alignment unchanged, including empty segments.
    'timestamps', 'alignment', 'normalized_alignment', 'voice_segments',
    'composition_plan', 'song_metadata', 'words_timestamps',
];
const SCRIBE_RESULT_METADATA_KEYS = ['words', 'transcripts', 'edited_transcript', 'entities', 'language_code',
    'language_probability', 'audio_duration_secs', 'channel_index'];
const STRUCTURED_AUDIO_MODELS = new Set(['paraformer-v2', 'paraformer-8k-v2', 'cohere-transcribe', ...SCRIBE_MODELS]);
const LLM_SUBMIT_TIMEOUT_MS = 120_000;
/** Keep task-specific fields visible without exposing the full remote response. */
function resultMetadata(task, model) {
    if (ELEVEN_VOICE_MODELS.has(model)) {
        try {
            return voiceObject(task);
        }
        catch {
            return;
        }
    }
    const metadata = {};
    const keys = model === 'scribe-v2' ? [...RESULT_METADATA_KEYS, ...SCRIBE_RESULT_METADATA_KEYS] : RESULT_METADATA_KEYS;
    for (const key of keys) {
        const value = task[key];
        if (value !== undefined && (value !== null || key === 'alignment' || key === 'normalized_alignment'))
            metadata[key] = value;
    }
    for (const item of task.results ?? []) {
        if (!item || typeof item !== 'object' || Array.isArray(item))
            continue;
        const record = item;
        for (const key of keys) {
            const value = record[key];
            if (value !== undefined && (value !== null || key === 'alignment' || key === 'normalized_alignment') && metadata[key] === undefined)
                metadata[key] = value;
        }
    }
    return Object.keys(metadata).length ? metadata : undefined;
}
async function newJob(cfg, media, model, outputDir, existingRecord) {
    const id = randomUUID();
    const parent = await findTaskInfo(outputDir);
    const record = existingRecord ?? (parent ? recordPath(outputDir, id) : (await createTask(outputDir, cfg.skill, 'aihub-job', 'task.json', [cfg.apiKey])).record);
    assertOutsideInstallation(record);
    const now = new Date().toISOString();
    return { record, job: { schema_version: 1, local_id: id, created_at: now, updated_at: now,
            skill: cfg.skill, media, model, service_url: cfg.baseUrl, credential_id: credentialId(cfg.apiKey),
            output_dir: await outputDirectory(record, join(dirname(record), 'files')), submission: { state: 'submitting' }, files: [], failed: [] } };
}
export function result(job, record, statusOverride) {
    const sub = job.submission;
    let status;
    if (sub.state !== 'known')
        status = sub.state === 'submitting' ? 'submission_unknown' : sub.state;
    else if (sub.task.status === 'failed')
        status = 'remote_failed';
    else if (sub.task.status !== 'completed')
        status = job.last_error ? 'query_failed' : 'waiting';
    else if (job.media === 'understanding' && job.text !== undefined)
        status = 'delivered';
    else if (job.failed.length)
        status = job.files.length ? 'partial' : 'download_failed';
    else
        status = job.files.length ? 'delivered' : 'download_pending';
    const error = sub.state === 'known'
        ? sub.task.error ?? job.last_error
        : sub.state === 'submitting' ? 'The process stopped before submission was confirmed. Do not resubmit automatically.' : sub.error;
    const metadata = sub.state === 'known' ? resultMetadata(sub.task, job.model) : undefined;
    const showUsage = ELEVEN_AUDIO_MODELS.has(job.model) || ELEVEN_VOICE_MODELS.has(job.model) || job.model === ELEVEN_MUSIC_MODEL || job.model === 'scribe-v2' || SUNO_MODELS.has(job.model);
    let voice = {};
    if (sub.state === 'known' && sub.task.status === 'completed') {
        try {
            if (job.model === VOICE_DESIGN_MODEL)
                voice = { voice_design: previewOutput(voiceDesign(sub.task), job.files),
                    selection_required: true, user_notice: '请试听全部候选后明确选择一个；候选 generated_voice_id 不能用于语音合成，尚未创建音色。' };
            if (job.model === VOICE_CREATE_MODEL)
                voice = { voice: createdVoice(sub.task), voice_id: createdVoice(sub.task).voice_id, user_notice: SAVE_VOICE_ID_NOTICE };
        }
        catch { /* Incomplete provider results stay visible in the saved task; never invent an ID. */ }
    }
    const tracks = SUNO_MODELS.has(job.model) && sub.state === 'known' ? (sub.task.results ?? []).map(item => {
        const track = item && typeof item === 'object' && !Array.isArray(item) ? item : {};
        const url = typeof track.audio_url === 'string' && track.audio_url ? track.audio_url : track.url;
        return { ...Object.fromEntries(['id', 'title', 'lyrics', 'duration'].filter(key => track[key] !== undefined).map(key => [key, track[key]])),
            ...(typeof url === 'string' ? { audio_url: url, file: job.files.find(file => file.url === url)?.path } : {}) };
    }) : undefined;
    return { schema_version: 1, status: statusOverride ?? status, record, media: job.media, model: job.model,
        ...voice,
        ...(job.failure ? { failure: job.failure } : {}),
        ...(sub.state === 'known' ? { task_id: sub.task.id, remote_status: sub.task.status, progress: sub.task.progress } : {}),
        ...(showUsage && sub.state === 'known' && sub.task.usage !== undefined ? { usage: sub.task.usage } : {}),
        ...(tracks ? { tracks } : {}),
        ...(job.text !== undefined ? { text: job.text } : {}), files: job.files, failed: job.failed, ...(metadata ? { result_metadata: metadata } : {}), ...(error ? { error } : {}),
        ...(sub.state === 'known' && status !== 'remote_failed' && status !== 'delivered'
            ? { next_action: { command: 'resume', args: ['--skill', job.skill, '--record', record, '--wait-seconds', '30'] } }
            : {}) };
}
async function save(record, job, cfg) {
    try {
        await writeJob(record, sanitized(job, [cfg.apiKey]));
    }
    catch (error) {
        if (job.submission.state === 'known')
            throw new TaskPersistenceError(job, record, `Task is known, but its recovery record could not be saved: ${cleanError(error, cfg)}. Keep task_id; use task after repairing storage.`);
        throw error;
    }
}
async function finishTextResult(job, record, cfg) {
    if (job.media !== 'understanding' || job.text === undefined || job.submission.state !== 'known' || job.submission.task.status !== 'completed')
        return;
    await mkdir(job.output_dir, { recursive: true, mode: 0o700 });
    const bytes = Buffer.byteLength(job.text, 'utf8');
    const existing = job.files.find(file => file.mime_type === 'text/plain' && file.path.startsWith(resolve(job.output_dir)));
    if (existing) {
        try {
            const info = await stat(existing.path);
            if (info.isFile() && info.size === bytes)
                return;
        }
        catch { /* Recreate a missing text result below. */ }
    }
    const path = join(job.output_dir, `result-${job.local_id}.txt`);
    await writeFile(path, job.text, { encoding: 'utf8', mode: 0o600 });
    job.files = [{ url: `task://${job.submission.task.id}/text`, path, bytes, mime_type: 'text/plain' }];
    await save(record, job, cfg);
}
async function finishDownload(job, record, cfg) {
    if (job.submission.state !== 'known' || job.submission.task.status !== 'completed' || job.media === 'understanding')
        return;
    const urls = [...new Set(job.model === VOICE_DESIGN_MODEL ? voiceDesign(job.submission.task).previews.map(p => p.url) : (job.submission.task.results ?? []).flatMap(item => {
            if (!item || typeof item !== 'object' || Array.isArray(item))
                return [];
            const result = item;
            if (SUNO_MODELS.has(job.model)) {
                const url = typeof result.audio_url === 'string' && result.audio_url ? result.audio_url : result.url;
                return typeof url === 'string' && url ? [url] : [];
            }
            return ['url', 'image_url', 'video_url', 'audio_url']
                .flatMap(key => typeof result[key] === 'string' ? [result[key]] : []);
        }))];
    if (!urls.length) {
        job.failed = [{ url: '', error: 'The completed task contains no downloadable media URL.' }];
        await save(record, job, cfg);
        return;
    }
    // Keep verified successful files when retrying only failed or missing assets.
    const kept = [];
    for (const file of job.files) {
        try {
            const info = await stat(file.path);
            if (urls.includes(file.url) && info.isFile() && info.size === file.bytes && info.size > 0)
                kept.push(file);
        }
        catch { /* A removed file must be downloaded again. */ }
    }
    job.files = kept;
    const pending = urls.filter(url => !kept.some(file => file.url === url));
    if (pending.length) {
        if (job.media !== 'document')
            await checkMediaTools();
        const downloaded = await downloadAssets(pending, job.output_dir, job.media);
        job.files.push(...downloaded.files);
        job.failed = downloaded.failed;
    }
    else
        job.failed = [];
    await save(record, job, cfg);
}
async function finishVoiceResult(job, record, cfg) {
    if (job.submission.state !== 'known' || job.submission.task.status !== 'completed')
        return;
    const task = job.submission.task;
    let body;
    let markdown;
    if (job.model === VOICE_DESIGN_MODEL) {
        body = voiceDesign(task);
        await finishDownload(job, record, cfg);
        job.files.sort((a, b) => body.previews.findIndex(p => p.url === a.url) - body.previews.findIndex(p => p.url === b.url));
        const output = previewOutput(body, job.files);
        markdown = '# ElevenLabs 音色候选\n\n请试听全部候选，然后在对话中明确选择一个。候选 ID 不能用于语音合成；尚未创建音色。\n\n' +
            '试听文本：\n\n' + JSON.stringify(body.text) + '\n\n' + output.previews.map(p => `- 候选 ${p.candidate_number}：${JSON.stringify(p.generated_voice_id)}\n  [试听音频](${encodeURI(p.url).replace(/[()]/g, c => encodeURIComponent(c))})` +
            (p.file ? `\n  本地音频：${JSON.stringify(basename(String(p.file)))}（也可在任务音频列表中试听）` : '')).join('\n') + '\n';
    }
    else {
        body = createdVoice(task);
        job.failed = [];
        markdown = '# ElevenLabs 音色已创建\n\n**' + SAVE_VOICE_ID_NOTICE + '**\n\nvoice_id：' + JSON.stringify(body.voice_id) +
            '\n\n后续自定义音色合成请显式选择 Speech / Dialogue 的 custom-voice 模型，并使用此 voice_id。平台任务查询仍可用，但不能替代自行保存。\n';
    }
    await mkdir(job.output_dir, { recursive: true, mode: 0o700 });
    for (const [extension, text, mime] of [['json', JSON.stringify(body, null, 2) + '\n', 'application/json'], ['md', markdown, 'text/markdown']]) {
        const path = join(job.output_dir, `${job.model}-${job.local_id}.${extension}`);
        await writePrivateText(path, text);
        job.files = job.files.filter(file => file.path !== path);
        job.files.push({ url: `task://${task.id}/voice.${extension}`, path, bytes: Buffer.byteLength(text), mime_type: mime });
    }
    await save(record, job, cfg);
}
function structuredResultUrls(task) {
    const urls = [];
    const visit = (value) => {
        if (!value || typeof value !== 'object')
            return;
        if (Array.isArray(value)) {
            for (const item of value)
                visit(item);
            return;
        }
        for (const [key, entry] of Object.entries(value)) {
            if ((key === 'transcription_url' || key === 'result_url') && typeof entry === 'string')
                urls.push(entry);
            else if (key !== 'file_url')
                visit(entry);
        }
    };
    visit(task.results);
    return [...new Set(urls)];
}
async function finishStructuredAudio(job, record, cfg) {
    if (job.submission.state !== 'known' || job.submission.task.status !== 'completed')
        return;
    const urls = structuredResultUrls(job.submission.task);
    let downloaded;
    if (urls.length) {
        const kept = [];
        for (const file of job.files) {
            try {
                if (!urls.includes(file.url) || (await stat(file.path)).size !== file.bytes)
                    continue;
                JSON.parse(await readFile(file.path, 'utf8'));
                kept.push(file);
            }
            catch { /* Retry only missing or invalid downloads, never the paid task. */ }
        }
        downloaded = await downloadJsonAssets(urls.filter(url => !kept.some(f => f.url === url)), job.output_dir);
        downloaded.files.unshift(...kept);
        downloaded.files.sort((a, b) => urls.indexOf(a.url) - urls.indexOf(b.url));
    }
    else {
        await mkdir(job.output_dir, { recursive: true, mode: 0o700 });
        const path = join(job.output_dir, `transcription-${job.local_id}.json`);
        const body = JSON.stringify(job.submission.task.results ?? [], null, 2) + '\n';
        await writePrivateText(path, body);
        downloaded = { files: [{ url: `task://${job.submission.task.id}/results`, path, bytes: Buffer.byteLength(body), mime_type: 'application/json' }], failed: [] };
    }
    job.files = downloaded.files;
    job.failed = downloaded.failed;
    const texts = [];
    for (const file of job.files)
        texts.push(transcriptText(JSON.parse(await readFile(file.path, 'utf8'))));
    job.text = texts.filter(Boolean).join('\n');
    await save(record, job, cfg);
}
async function finishResult(job, record, cfg) {
    if (ELEVEN_VOICE_MODELS.has(job.model))
        await finishVoiceResult(job, record, cfg);
    else if (job.media === 'understanding')
        await finishTextResult(job, record, cfg);
    else if (job.media === 'audio' && STRUCTURED_AUDIO_MODELS.has(job.model))
        await finishStructuredAudio(job, record, cfg);
    else
        await finishDownload(job, record, cfg);
}
async function queryAndDeliver(client, cfg, job, record, waitSeconds) {
    if (job.submission.state !== 'known')
        return result(job, record);
    const id = job.submission.task.id;
    delete job.last_error;
    try {
        const task = waitSeconds > 0
            ? await client.pollTask(id, waitSeconds, false, async (update) => {
                job.submission = { state: 'known', task: sanitized(update, [cfg.apiKey]) };
                await save(record, job, cfg);
            })
            : await client.getTask(id);
        job.submission = { state: 'known', task: sanitized(task, [cfg.apiKey]) };
        delete job.failure;
        if (task.model)
            job.model = task.model;
        if (job.media === 'understanding' && task.status === 'completed')
            job.text = extractText(task) ?? undefined;
        await save(record, job, cfg);
    }
    catch (error) {
        if (error instanceof TaskPersistenceError)
            throw error;
        if (error instanceof PollBudgetExceededError) {
            if (error.lastTask)
                job.submission = { state: 'known', task: sanitized(error.lastTask, [cfg.apiKey]) };
            await save(record, job, cfg);
            return { ...result(job, record, 'waiting'), wait_result: 'budget_exhausted' };
        }
        job.last_error = cleanError(error, cfg);
        job.failure = failureInfo(error, cfg);
        try {
            await save(record, job, cfg);
        }
        catch { /* Return the known task ID even if persistence fails. */ }
        return result(job, record, 'query_failed');
    }
    try {
        await finishResult(job, record, cfg);
    }
    catch (error) {
        if (error instanceof TaskPersistenceError)
            throw error;
        job.last_error = cleanError(error, cfg);
        try {
            await save(record, job, cfg);
        }
        catch { /* Remote task must stay visible to the caller. */ }
        return result(job, record, 'download_failed');
    }
    return result(job, record);
}
export async function generate(cfg, options) {
    if (options.model === VOICE_CREATE_MODEL)
        throw new Error('Use voice-create with a completed Design record and explicit user selection after all candidate auditions. Direct Create generation is disabled.');
    return generateJob(cfg, options);
}
async function generateJob(cfg, options) {
    // Stored run candidates are already resolved, even when they contain no voice ID.
    const params = options.parametersResolved ? options.params : speechParameters(options.model, options.params, cfg.speech?.defaultVoiceId, cfg.elevenlabs?.defaultVoiceId);
    const path = validateGeneration(options.media, options.model, params);
    const requestParams = SUNO_MODELS.has(options.model) ? sunoParameters(options.model, params) : elevenAudioParameters(options.model, params);
    let body = { ...requestParams, model: options.model };
    if (SCRIBE_MODELS.has(options.model) && typeof params.file === 'string') {
        // Whole-file multipart is independent of Paraformer's splitting and upload protocol.
        // Keep memory bounded in the Node 18 runtime; larger inputs use the documented URL path.
        const info = await stat(params.file);
        const maxBytes = 256 * 1024 * 1024;
        if (!info.isFile() || !info.size || info.size > maxBytes)
            throw new Error(`Scribe local file must be nonempty and <=256 MiB; use ${options.model === 'scribe-v2' ? 'source_url' : 'audio_url'} for larger inputs.`);
        const bytes = await readFile(params.file);
        if (bytes.length > maxBytes || bytes.length !== info.size)
            throw new Error('Scribe file changed while reading; no task was submitted.');
        const form = new FormData();
        form.set('model', options.model);
        form.set('file', new Blob([bytes]), basename(params.file));
        for (const [key, value] of Object.entries(requestParams)) {
            if (key === 'file' || value == null)
                continue; // Nullable controls are unspecified by contract.
            form.set(key, typeof value === 'string' ? value : JSON.stringify(value));
        }
        body = form;
    }
    assertOutsideInstallation(options.outputDir);
    if (options.media !== 'document' && options.model !== VOICE_CREATE_MODEL)
        await checkMediaTools();
    const { job, record } = await newJob(cfg, options.media, options.model, options.outputDir);
    await bindDiagnosticRecord(cfg, record, { model: options.model, parameters: params, original_request: null });
    const client = new AihubmaxClient(cfg);
    job.submission = { state: 'not_submitted', error: 'Model availability has not been verified. No generation was submitted.' };
    await save(record, job, cfg);
    try {
        const live = await client.listLiveModels();
        if (!generationModelAvailable(live, options.model, options.params))
            throw new Error('The model and requested variant are not present in the current key model list. Run models and check the requested parameters. No generation was submitted.');
    }
    catch (error) {
        job.submission = { state: 'not_submitted', error: cleanError(error, cfg) };
        await save(record, job, cfg);
        throw error;
    }
    job.submission = { state: 'submitting' };
    await save(record, job, cfg);
    await options.onRecord?.(record);
    process.stderr.write(`AIhub task record: ${record}\n`);
    return withJobLock(record, async () => {
        try {
            const task = await client.submitGeneration(path, body);
            job.submission = { state: 'known', task: sanitized(task, [cfg.apiKey]) };
            await save(record, job, cfg);
        }
        catch (error) {
            if (error instanceof TaskPersistenceError)
                throw error;
            if (job.submission.state === 'known') {
                job.last_error = `Task accepted, but saving its ID failed: ${cleanError(error, cfg)}. Keep this task_id and use task to recover.`;
                return result(job, record, 'query_failed');
            }
            job.failure = failureInfo(error, cfg);
            job.submission = { state: error instanceof ApiError && !error.ambiguous ? 'not_submitted' : 'submission_unknown', error: cleanError(error, cfg) };
            try {
                await save(record, job, cfg);
            }
            catch { /* Still return the submission outcome. */ }
            return result(job, record);
        }
        if (job.submission.task.status === 'completed' || job.submission.task.status === 'failed') {
            try {
                await finishResult(job, record, cfg);
            }
            catch (error) {
                if (error instanceof TaskPersistenceError)
                    throw error;
                job.last_error = cleanError(error, cfg);
                return result(job, record, 'download_failed');
            }
            return result(job, record);
        }
        if (!options.waitSeconds)
            return result(job, record, 'submitted');
        return queryAndDeliver(client, cfg, job, record, options.waitSeconds);
    });
}
async function registerVoiceCreateTask(designRecord, taskRecord, cfg, result) {
    try {
        const infoPath = await findTaskInfo(designRecord);
        if (!infoPath)
            return;
        const path = relative(dirname(infoPath), taskRecord).split(sep).join('/');
        await updateTaskInfo(infoPath, info => {
            if (!info.records.some(entry => resolve(dirname(infoPath), entry.path) === resolve(taskRecord))) {
                info.records.push({ path, kind: 'aihub-job', purpose: 'primary' });
            }
            const completed = result?.status === 'delivered' && typeof result.voice_id === 'string' && result.voice_id.trim();
            info.delivery = { status: completed ? 'completed' : 'partial', at: new Date().toISOString(),
                reason: completed ? '已创建用户选中的音色，请自行妥善保存 voice_id；平台不提供音色查询或 ID 找回。'
                    : result?.status === 'remote_failed' ? '候选已交付；音色创建失败，尚未获得可合成的 voice_id。请由 Agent 核对原任务。'
                        : '候选已交付；音色创建结果尚未确认。请由 Agent 继续原任务，勿重复创建。' };
        });
    }
    catch (error) {
        // Metadata can be repaired on recovery; it must never cause another Create submission.
        process.stderr.write(`Create task metadata update failed; recover the saved task, do not resubmit: ${cleanError(error, cfg)}\n`);
    }
}
/** One local Create attempt per Design; subsequent calls recover that exact attempt. */
export async function createVoice(cfg, designRecord, selection, waitSeconds) {
    const source = resolve(designRecord);
    assertOutsideInstallation(source);
    const record = join(dirname(source), 'voice-create.json');
    return withJobLock(record, async () => {
        const job = await readJob(source);
        let state;
        try {
            state = JSON.parse(await readFile(record, 'utf8'));
        }
        catch (error) {
            if (error.code !== 'ENOENT')
                throw error;
        }
        const binding = await designBinding(cfg, job, !state);
        const saveState = () => writePrivateRecord(record, sanitized(state, [cfg.apiKey]));
        const present = () => ({ ...(state?.result ?? { status: 'submission_unknown', error: 'Create was prepared but its submission outcome is unknown. Reconcile the original task; never submit another Create.' }),
            creation_record: record, design_record: source, selected_generated_voice_id: state.selection.generated_voice_id });
        if (state) {
            if (state.schema_version !== 1 || state.kind !== 'aihub-voice-create' || state.design_record !== source || state.design_fingerprint !== binding.fingerprint)
                throw new Error('Create recovery does not match this Design result. Preserve the original records.');
            const parsed = selectionParams(state.selection, binding.design, binding.taskId);
            if (JSON.stringify(parsed.params) !== JSON.stringify(state.params))
                throw new Error('Saved Create parameters no longer match the user selection.');
            if (selection && JSON.stringify(selectionParams(selection, binding.design, binding.taskId).params) !== JSON.stringify(state.params))
                throw new Error('A Create attempt already exists for another selection. Recover that attempt; do not create all candidates.');
            if (state.task_record) {
                const childPath = relative(dirname(source), state.task_record);
                if (!childPath || childPath === '..' || childPath.startsWith(`..${sep}`) || isAbsolute(childPath))
                    throw new Error('Create task record must remain inside its Design task.');
                const child = await readJob(state.task_record);
                if (child.model !== VOICE_CREATE_MODEL)
                    throw new Error('Create recovery refers to another model.');
                await registerVoiceCreateTask(source, state.task_record, cfg);
                state.result = await resume(cfg, state.task_record, waitSeconds);
                await saveState();
                await registerVoiceCreateTask(source, state.task_record, cfg, state.result);
            }
            return present();
        }
        if (!selection)
            throw new Error('First Create requires --selection-file with the explicit user choice and all auditioned candidate IDs.');
        const parsed = selectionParams(selection, binding.design, binding.taskId);
        validateGeneration('audio', VOICE_CREATE_MODEL, parsed.params);
        state = { schema_version: 1, kind: 'aihub-voice-create', design_record: source, design_fingerprint: binding.fingerprint,
            selection: parsed.selection, params: parsed.params };
        // Persist intent before any submission. A crash without a known task record cannot safely replay.
        await saveState();
        try {
            state.result = await generateJob(cfg, { media: 'audio', model: VOICE_CREATE_MODEL, params: parsed.params, outputDir: dirname(source), waitSeconds,
                onRecord: async (path) => { state.task_record = path; await saveState(); await registerVoiceCreateTask(source, path, cfg); } });
        }
        catch (error) {
            if (error instanceof TaskPersistenceError) {
                state.task_record = error.record;
                state.result = error.output();
            }
            else
                state.result = { status: state.task_record ? 'submission_unknown' : 'not_submitted', error: cleanError(error, cfg) };
        }
        await saveState();
        if (state.task_record)
            await registerVoiceCreateTask(source, state.task_record, cfg, state.result);
        return present();
    });
}
export async function resume(cfg, recordInput, waitSeconds) {
    const record = resolve(recordInput);
    assertOutsideInstallation(record);
    return withJobLock(record, async () => {
        const job = await readJob(record);
        if (job.service_url !== cfg.baseUrl) {
            throw new Error('This record belongs to another service. AIhub Studio uses a fixed service address; continue this task with its original service client.');
        }
        if (job.skill !== cfg.skill || job.credential_id !== credentialId(cfg.apiKey)) {
            throw new Error('This record belongs to a different Skill or key. Restore its original configuration; to query with a deliberately changed key, use task with the known task ID.');
        }
        await participate(record, [cfg.apiKey]);
        await bindDiagnosticRecord(cfg, record);
        if (job.submission.state !== 'known')
            return result(job, record);
        return queryAndDeliver(new AihubmaxClient(cfg), cfg, job, record, waitSeconds);
    });
}
export async function adoptTask(cfg, id, media, outputDir, waitSeconds) {
    assertOutsideInstallation(outputDir);
    const identity = createHash('sha256').update(`${cfg.baseUrl}\0${cfg.skill}\0${credentialId(cfg.apiKey)}\0${id}`).digest('hex');
    const links = join(resolve(outputDir), '.task-links');
    await mkdir(links, { recursive: true, mode: 0o700 });
    const pointer = join(links, identity + '.json');
    return withJobLock(pointer, async () => {
        let record;
        const contents = await readFile(pointer, 'utf8').catch(error => {
            if (error.code === 'ENOENT')
                return undefined;
            throw error;
        });
        if (contents !== undefined) {
            const saved = JSON.parse(contents);
            if (saved.identity !== identity || typeof saved.record !== 'string')
                throw new Error('Invalid adoption pointer.');
            record = resolve(saved.record);
            assertOutsideInstallation(record);
            const root = await realpath(resolve(outputDir));
            const delta = relative(root, await realpath(dirname(record)));
            if (isAbsolute(delta) || delta === '..' || delta.startsWith('..' + sep))
                throw new Error('Adoption pointer is outside its output directory.');
            const metadata = await findTaskInfo(dirname(record));
            if (!metadata)
                throw new Error('Adopted task metadata is missing; repair locally before querying again.');
            const info = await readTaskInfo(metadata);
            if (info.task_id !== saved.task_id || info.skill !== cfg.skill || await realpath(info.project_root) !== await realpath(process.cwd()))
                throw new Error('Adoption pointer task binding is invalid.');
            if (await stat(record).then(s => s.isFile()).catch(() => false)) {
                const job = await readJob(record);
                if (job.submission.state !== 'known' || job.submission.task.id !== id || job.media !== media)
                    throw new Error('Adoption pointer refers to another remote task.');
                return resume(cfg, record, waitSeconds);
            }
        }
        else {
            record = (await findTaskInfo(outputDir)) ? recordPath(outputDir, `task-${identity}`)
                : (await createTask(outputDir, cfg.skill, 'aihub-job', 'task.json', [cfg.apiKey])).record;
            const metadata = await findTaskInfo(dirname(record));
            if (!metadata)
                throw new Error('Adoption task metadata is missing.');
            await writePrivateRecord(pointer, { identity, record, task_id: (await readTaskInfo(metadata)).task_id });
        }
        const { job } = await newJob(cfg, media, '', outputDir, record);
        await bindDiagnosticRecord(cfg, record, { task_id: id, original_request: null });
        const client = new AihubmaxClient(cfg);
        let task;
        try {
            task = await client.getTask(id);
        }
        catch (error) {
            return { schema_version: 1, status: 'query_failed', task_id: id, record, error: cleanError(error, cfg), failure: failureInfo(error, cfg) };
        }
        job.model = task.model ?? '';
        job.submission = { state: 'known', task: sanitized(task, [cfg.apiKey]) };
        await save(record, job, cfg);
        return withJobLock(record, async () => {
            if (waitSeconds && task.status !== 'completed' && task.status !== 'failed')
                return queryAndDeliver(client, cfg, job, record, waitSeconds);
            try {
                await finishResult(job, record, cfg);
            }
            catch (error) {
                if (error instanceof TaskPersistenceError)
                    throw error;
                job.last_error = cleanError(error, cfg);
                return result(job, record, 'download_failed');
            }
            return result(job, record);
        });
    });
}
function extractText(task) {
    const first = Array.isArray(task.results) ? task.results[0] : undefined;
    if (typeof first === 'string')
        return first;
    if (!first || typeof first !== 'object')
        return null;
    const record = first;
    const choices = Array.isArray(record.choices) ? record.choices : [];
    const message = choices[0]?.message;
    const messageText = message && typeof message === 'object' ? message.content : undefined;
    if (typeof messageText === 'string')
        return messageText;
    if (typeof record.text === 'string')
        return record.text;
    if (typeof record.content === 'string')
        return record.content;
    return null;
}
export async function understand(cfg, options) {
    if (!options.content.length)
        throw new Error('understand 至少需要一个 image_url、audio_url、video_url 或 file_url 内容块。');
    if (!options.content.some((item) => ['image_url', 'audio_url', 'video_url', 'file_url'].includes(String(item.type))))
        throw new Error('understand 只接受图片、音频、视频或文件内容块；纯文本请求不属于 E1。');
    for (const item of options.content) {
        const type = String(item.type);
        if (!['image_url', 'audio_url', 'video_url', 'file_url'].includes(type))
            continue;
        const value = item[type];
        if (!value || typeof value !== 'object' || Array.isArray(value) || typeof value.url !== 'string') {
            throw new Error(`understand 的 ${type} 内容块必须是 {"url":"https://..."} 对象。`);
        }
    }
    const { job, record } = await newJob(cfg, 'understanding', options.model, options.outputDir);
    await bindDiagnosticRecord(cfg, record, { model: options.model, prompt: options.prompt, content: options.content, original_request: null });
    const client = new AihubmaxClient(cfg);
    job.submission = { state: 'not_submitted', error: 'Model capabilities have not been verified. No generation was submitted.' };
    await save(record, job, cfg);
    try {
        const available = await client.listLlmModels();
        const live = available.find((item) => item.id === options.model);
        if (!live)
            throw new Error(`模型 ${options.model} 不在 /e/v1/configs/llm_generations_models 返回的当前账号清单中。`);
        const needed = new Set(options.content.map((item) => String(item.type).replace('_url', '').replace('image', 'vision')));
        if (live.capabilities && [...needed].some((cap) => !live.capabilities.includes(cap)))
            throw new Error(`模型 ${options.model} 不具备所需多模态能力；不会静默切换模型。`);
    }
    catch (error) {
        job.submission = { state: 'not_submitted', error: cleanError(error, cfg) };
        await save(record, job, cfg);
        throw error;
    }
    const body = { model: options.model, messages: [{ role: 'user', content: [{ type: 'text', text: options.prompt }, ...options.content] }] };
    if (options.systemPrompt)
        body.system_prompt = options.systemPrompt;
    if (options.maxTokens !== undefined)
        body.max_tokens = options.maxTokens;
    if (options.temperature !== undefined)
        body.temperature = options.temperature;
    job.submission = { state: 'submitting' };
    await save(record, job, cfg);
    await options.onRecord?.(record);
    return withJobLock(record, async () => {
        try {
            const task = await client.submitGeneration('/e/v1/llm/generations', body, { timeoutMs: LLM_SUBMIT_TIMEOUT_MS });
            job.submission = { state: 'known', task: sanitized(task, [cfg.apiKey]) };
            await save(record, job, cfg);
        }
        catch (error) {
            if (error instanceof TaskPersistenceError)
                throw error;
            job.failure = failureInfo(error, cfg);
            job.submission = { state: error instanceof ApiError && !error.ambiguous ? 'not_submitted' : 'submission_unknown', error: cleanError(error, cfg) };
            await save(record, job, cfg).catch(() => { });
            return result(job, record);
        }
        if (job.submission.task.status === 'completed' || job.submission.task.status === 'failed') {
            if (job.submission.task.status === 'completed')
                job.text = extractText(job.submission.task) ?? undefined;
            try {
                await finishResult(job, record, cfg);
            }
            catch (error) {
                job.last_error = cleanError(error, cfg);
                return result(job, record, 'download_failed');
            }
            return result(job, record);
        }
        if (!options.waitSeconds)
            return result(job, record, 'submitted');
        return queryAndDeliver(client, cfg, job, record, options.waitSeconds);
    });
}
export async function nativeMusic(cfg, options) {
    if (options.model !== 'lyria-3-pro-preview')
        throw new Error('Gemini 原生音乐命令只接受模型 lyria-3-pro-preview；异步 lyria-3-pro 请使用 generate。');
    if (!Array.isArray(options.body.contents) || !options.body.contents.length)
        throw new Error('Gemini 原生音乐请求必须包含非空 contents。');
    const generationConfig = options.body.generationConfig;
    const modalities = generationConfig && typeof generationConfig === 'object' ? generationConfig.responseModalities : undefined;
    if (!Array.isArray(modalities) || !modalities.includes('AUDIO')) {
        throw new Error('Gemini 原生音乐请求的 generationConfig.responseModalities 必须包含 AUDIO。');
    }
    assertOutsideInstallation(options.outputDir);
    await checkMediaTools();
    const parent = await findTaskInfo(options.outputDir);
    const record = parent ? join(resolve(options.outputDir), 'native-music.json')
        : (await createTask(options.outputDir, cfg.skill, 'aihub-native-music', 'native-music.json', [cfg.apiKey])).record;
    await bindDiagnosticRecord(cfg, record, { model: options.model, parameters: options.body, original_request: null });
    const saveStatus = (status, error) => writePrivateRecord(record, sanitized({ schema_version: 1, kind: 'aihub-native-music', model: options.model, status, files: [], updated_at: new Date().toISOString(), ...(error ? { error: cleanError(error, cfg) } : {}) }, [cfg.apiKey]));
    await saveStatus('not_submitted');
    let submitted = false, received = false;
    try {
        await options.onSubmit?.();
        await saveStatus('submission_unknown');
        submitted = true;
        const response = await new AihubmaxClient(cfg).generateGeminiMusic(options.model, options.body);
        received = true;
        const parts = response.candidates?.flatMap((candidate) => candidate.content?.parts ?? []) ?? [];
        const audio = parts.find((item) => item.inlineData?.data);
        if (!audio?.inlineData?.data)
            throw new Error('Gemini 音乐响应没有 inlineData 音频结果。');
        const mime = audio.inlineData.mimeType ?? 'audio/mpeg';
        const ext = mime === 'audio/wav' ? '.wav' : '.mp3';
        const dir = await outputDirectory(record, join(dirname(record), 'files'));
        await mkdir(dir, { recursive: true });
        const path = join(dir, `lyria-${randomUUID()}${ext}`);
        const bytes = Buffer.from(audio.inlineData.data, 'base64');
        if (!bytes.length)
            throw new Error('Gemini 音乐 inlineData 为空。');
        await writeFile(path, bytes, { mode: 0o600, flag: 'wx' });
        let file;
        try {
            file = await validateLocalMedia(path, 'audio');
        }
        catch (error) {
            await import('node:fs/promises').then(fs => fs.unlink(path)).catch(() => { });
            throw error;
        }
        const text = parts.find((item) => item.text)?.text;
        const delivered = { schema_version: 1, kind: 'aihub-native-music', status: 'delivered', record, model: options.model, files: [file], updated_at: new Date().toISOString(), ...(text ? { text } : {}) };
        try {
            await writePrivateRecord(record, sanitized(delivered, [cfg.apiKey]));
            await touchTask(record);
        }
        catch {
            return { ...delivered, metadata_warning: 'Music was saved, but its record needs local repair. Do not regenerate.' };
        }
        return delivered;
    }
    catch (error) {
        const status = !submitted || (error instanceof ApiError && !error.ambiguous) ? 'not_submitted' : received ? 'failed' : 'submission_unknown';
        await saveStatus(status, error).catch(() => { });
        await touchTask(record);
        throw error;
    }
}
// Retained from the source upload guard: the endpoint accepts whole-file base64 JSON.
export async function upload(cfg, input) {
    const supplied = ['path', 'url', 'base64'].filter(key => input[key] !== undefined);
    if (supplied.length !== 1)
        throw new Error('Provide exactly one upload source: path, url or base64.');
    for (const key of supplied)
        if (typeof input[key] !== 'string' || !input[key])
            throw new Error(`${key} must be a nonempty string.`);
    if (input.file_name !== undefined && typeof input.file_name !== 'string')
        throw new Error('file_name must be a string.');
    const client = new AihubmaxClient(cfg);
    const name = input.file_name;
    try {
        let data;
        if (typeof input.url === 'string') {
            const url = new URL(input.url);
            if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
                throw new Error('Upload URL must use HTTP(S) without embedded credentials.');
            data = await client.uploadUrl(input.url, name);
        }
        else if (typeof input.path === 'string') {
            const info = await stat(input.path);
            if (!info.isFile() || info.size > UPLOAD_MAX_BYTES || info.size === 0)
                throw new Error('Local upload must be a nonempty file no larger than 20 MiB. Use an accessible URL for larger files.');
            const bytes = await readFile(input.path);
            if (bytes.length > UPLOAD_MAX_BYTES)
                throw new Error('File changed while reading; upload exceeds 20 MiB.');
            data = await client.uploadBase64(bytes.toString('base64'), name ?? basename(input.path));
        }
        else {
            const base64 = input.base64;
            if (base64.length > Math.ceil(UPLOAD_MAX_BYTES / 3) * 4 + 256)
                throw new Error('Base64 upload exceeds the 20 MiB limit.');
            data = await client.uploadBase64(base64, name);
        }
        return { schema_version: 1, status: 'ok', ...data };
    }
    catch (error) {
        return { schema_version: 1, status: error instanceof ApiError && error.ambiguous ? 'submission_unknown' : 'not_submitted', error: cleanError(error, cfg), failure: failureInfo(error, cfg) };
    }
}
