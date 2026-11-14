import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { credentialId } from './config.js';
import { VOICE_DESIGN_MODEL } from './elevenlabs.js';
export const SAVE_VOICE_ID_NOTICE = '生成的 `voice_id` 请自行妥善保存。平台不提供音色列表、音色查询或 ID 找回功能。';
export function voiceObject(task) {
    const first = task.results?.[0];
    if (!first || typeof first !== 'object' || Array.isArray(first))
        throw new Error('Voice task results[0] must be an object. Query the original task; do not submit another request.');
    return first;
}
export function voiceDesign(task) {
    const first = voiceObject(task);
    if (typeof first.text !== 'string' || !first.text || !Array.isArray(first.previews) || !first.previews.length)
        throw new Error('Design must return text and every preview; incomplete results cannot be selected.');
    const ids = new Set();
    for (const item of first.previews) {
        if (!item || typeof item !== 'object' || typeof item.generated_voice_id !== 'string' || !item.generated_voice_id.trim() || ids.has(item.generated_voice_id))
            throw new Error('Design preview IDs must be nonempty and distinct.');
        ids.add(item.generated_voice_id);
        let url;
        try {
            url = new URL(item.url);
        }
        catch {
            throw new Error('Each Design preview requires its downloadable URL.');
        }
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
            throw new Error('Design preview URLs must use HTTP(S) without embedded credentials.');
    }
    return first;
}
export function createdVoice(task) {
    const voice = voiceObject(task);
    if (typeof voice.voice_id !== 'string' || !voice.voice_id.trim())
        throw new Error('Create returned no voice_id. Keep the original task ID and query it; never invent an ID or repeat Create automatically.');
    return voice;
}
export function previewOutput(design, files) {
    return { ...design, previews: design.previews.map((preview, index) => ({ ...preview, candidate_number: index + 1,
            ...(files.find(file => file.url === preview.url) ? { file: files.find(file => file.url === preview.url).path } : {}) })) };
}
export function selectionParams(value, design, taskId) {
    const allowed = ['design_task_id', 'generated_voice_id', 'auditioned_generated_voice_ids', 'user_confirmation', 'voice_name', 'voice_description', 'labels'];
    for (const key of Object.keys(value))
        if (!allowed.includes(key))
            throw new Error(`selection.${key} is not supported.`);
    if (value.design_task_id !== taskId)
        throw new Error('Selection belongs to another Design task.');
    const ids = design.previews.map(p => p.generated_voice_id);
    const heard = value.auditioned_generated_voice_ids;
    if (!Array.isArray(heard) || heard.length !== ids.length || new Set(heard).size !== ids.length || ids.some(id => !heard.includes(id)))
        throw new Error('All Design candidates must be presented for audition before selection. Preserve every auditioned generated_voice_id.');
    if (typeof value.generated_voice_id !== 'string' || !ids.includes(value.generated_voice_id))
        throw new Error('Select exactly one generated_voice_id returned by this Design.');
    if (typeof value.user_confirmation !== 'string' || !value.user_confirmation.trim())
        throw new Error('Explicit user selection is required after all candidate auditions; the Agent cannot choose automatically.');
    const params = Object.fromEntries(['voice_name', 'voice_description', 'generated_voice_id', 'labels'].filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]]));
    return { selection: value, params };
}
/** Bind selection to the credential/task; first submission also requires every delivered preview. */
export async function designBinding(cfg, job, requirePreviews = true) {
    if (cfg.skill !== 'aihub-audio' || job.skill !== cfg.skill || job.model !== VOICE_DESIGN_MODEL || job.media !== 'audio' ||
        job.service_url !== cfg.baseUrl || job.credential_id !== credentialId(cfg.apiKey) || job.submission.state !== 'known' || job.submission.task.status !== 'completed')
        throw new Error('Use a completed Voice Design task record from this Skill, service and credential.');
    const design = voiceDesign(job.submission.task);
    if (requirePreviews && job.failed.length)
        throw new Error('Download every Design preview first by resuming the original task.');
    const digest = createHash('sha256').update(JSON.stringify(job.submission.task));
    for (const preview of requirePreviews ? design.previews : []) {
        const file = job.files.find(f => f.url === preview.url);
        if (!file || !(await stat(file.path)).isFile())
            throw new Error('Every Design preview must be locally available for audition. Resume the Design download.');
        const bytes = await readFile(file.path);
        if (!bytes.length || bytes.length !== file.bytes)
            throw new Error('A Design preview changed or is missing. Resume the Design download.');
    }
    return { design, fingerprint: digest.digest('hex'), taskId: job.submission.task.id };
}
