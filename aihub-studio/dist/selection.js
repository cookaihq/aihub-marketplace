import { modelEntry, validateGeneration, VIDEO_DEFAULT_MODELS, IMAGE_DEFAULT_MODELS, PREFERRED_MODELS } from './models.js';
import { resolve } from 'node:path';
import { audioContract, remoteAudio } from './audioMedia.js';
import { speechParameters } from './speech.js';
import { ELEVEN_SPEECH_MODELS, ELEVEN_DIALOGUE_MODELS, ELEVEN_MUSIC_MODEL, SCRIBE_MODELS, elevenMigration, assertElevenParameterMigration } from './elevenlabs.js';
import { SUNO_MODELS, SUNO_DEFAULT_MODEL, sunoParameters, sunoSceneParameters } from './suno.js';
export const OPERATIONS = {
    'image-generate': 'aihub-image', 'image-edit': 'aihub-image',
    'video-text': 'aihub-video', 'video-start-frame': 'aihub-video', 'video-reference': 'aihub-video',
    'video-lipsync': 'aihub-video', 'video-avatar': 'aihub-video',
    'audio-tts': 'aihub-audio', 'audio-dialogue': 'aihub-audio', 'audio-transcribe': 'aihub-audio', 'audio-clone': 'aihub-audio',
    'music-description': 'aihub-music', 'music-lyrics': 'aihub-music', 'music-instrumental': 'aihub-music',
    understanding: 'aihub-understanding',
};
const IMAGE = PREFERRED_MODELS.image;
const TRANSCRIBE = ['paraformer-v2', 'paraformer-8k-v2', 'cohere-transcribe', ...SCRIBE_MODELS];
const LIPSYNC = ['lipsync-2', 'lipsync-2-pro', 'sync-3'];
const AVATAR = ['omnihuman-1.5', 'fabric-1.0', 'fabric-1.0-fast', 'creatify-aurora'];
function object(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function assertKeys(value, allowed, label) {
    for (const key of Object.keys(value))
        if (!allowed.includes(key))
            throw new Error(`${label}.${key} is not supported; no input or requirement may be silently discarded.`);
}
export function readTaskRequest(value, skill) {
    assertKeys(value, ['operation', 'original_request', 'prompt', 'model', 'image_priority', 'inputs', 'requirements', 'review_requirements', 'requirement_revisions'], 'request');
    if (typeof value.operation !== 'string' || !Object.hasOwn(OPERATIONS, value.operation) || OPERATIONS[value.operation] !== skill) {
        throw new Error(`operation must belong to ${skill}. Supported operations: ${Object.entries(OPERATIONS).filter(([, owner]) => owner === skill).map(([op]) => op).join(', ')}`);
    }
    if (typeof value.original_request !== 'string' || !value.original_request.trim())
        throw new Error('original_request must preserve the user request; do not substitute the generated prompt.');
    for (const key of ['prompt', 'model'])
        if (value[key] !== undefined && (typeof value[key] !== 'string' || !String(value[key]).trim()))
            throw new Error(`${key} must be a nonempty string.`);
    if (value.image_priority !== undefined && !['speed', 'detail'].includes(String(value.image_priority)))
        throw new Error('image_priority must be speed or detail.');
    if (value.requirements !== undefined && !object(value.requirements))
        throw new Error('requirements must be an object.');
    if (value.review_requirements !== undefined) {
        const checks = value.review_requirements;
        if (!Array.isArray(checks) || checks.some(item => !object(item) || typeof item.id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(item.id) ||
            typeof item.text !== 'string' || !item.text.trim() || !['required', 'preference'].includes(String(item.priority))) ||
            new Set(checks.map(item => item.id)).size !== checks.length)
            throw new Error('review_requirements must contain distinct IDs, nonempty text and required/preference priority.');
    }
    if (value.requirement_revisions !== undefined && (!Array.isArray(value.requirement_revisions) || value.requirement_revisions.some(item => !object(item) || typeof item.request !== 'string' || !item.request.trim() || typeof item.user_confirmation !== 'string' || !item.user_confirmation.trim()))) {
        throw new Error('Each requirement revision must preserve the revised request and the user confirmation; the Agent cannot silently lower requirements.');
    }
    if (value.inputs !== undefined) {
        if (!object(value.inputs))
            throw new Error('inputs must be an object.');
        assertKeys(value.inputs, ['images', 'videos', 'audios', 'files', 'mask'], 'inputs');
        for (const [key, input] of Object.entries(value.inputs)) {
            const urls = key === 'mask' ? [input] : input;
            if (!Array.isArray(urls) || !urls.length || urls.some(url => typeof url !== 'string' || !url.trim()))
                throw new Error(`inputs.${key} must contain nonempty remote URLs.`);
            for (const url of urls) {
                if (value.operation === 'audio-transcribe' && key === 'audios' && !remoteAudio(url) &&
                    (!/^[a-z][a-z0-9+.-]*:/i.test(url) || /^[a-z]:[\\/]/i.test(url)))
                    continue;
                let parsed;
                try {
                    parsed = new URL(url);
                }
                catch {
                    throw new Error(`inputs.${key} must use remote HTTP(S) URLs; upload local files first.`);
                }
                if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password)
                    throw new Error(`inputs.${key} must use HTTP(S) without embedded credentials.`);
            }
        }
    }
    const request = JSON.parse(JSON.stringify(value));
    if (request.operation === 'audio-transcribe' && request.inputs?.audios)
        request.inputs.audios = request.inputs.audios.map(v => remoteAudio(v) ? v : resolve(v));
    return request;
}
function defaults(request) {
    switch (request.operation) {
        case 'image-generate': return [IMAGE_DEFAULT_MODELS.generation[request.image_priority === 'detail' ? 1 : 0]];
        case 'image-edit': return [IMAGE_DEFAULT_MODELS.edit[request.image_priority === 'detail' ? 1 : 0]];
        case 'video-text': return ['seedance-2.5-text-to-video'];
        case 'video-start-frame': return ['seedance-2.5-image-to-video'];
        case 'video-reference': return ['seedance-2.5-reference-to-video'];
        case 'video-lipsync': return [...VIDEO_DEFAULT_MODELS.c1];
        case 'video-avatar': return [...VIDEO_DEFAULT_MODELS.c2];
        case 'audio-tts': return ['eleven-v4-text-to-speech'];
        case 'audio-dialogue': return ['eleven-v4-text-to-dialogue'];
        case 'audio-transcribe': return ['paraformer-v2'];
        case 'audio-clone': return [];
        case 'music-description':
        case 'music-lyrics':
        case 'music-instrumental': return [SUNO_DEFAULT_MODEL];
        case 'understanding': return [PREFERRED_MODELS.understanding[0]];
    }
}
/** Task purpose is resolved before availability or parameter checks. */
function matchesOperation(model, operation) {
    if (operation === 'understanding')
        return true; // The live LLM registry is authoritative.
    if (model === 'lyria-3-pro-preview')
        return operation === 'music-description';
    let media;
    try {
        media = modelEntry(model).entry.mediaType;
    }
    catch {
        return false;
    }
    switch (operation) {
        case 'image-generate': return media === 'image';
        case 'image-edit': return media === 'image' && !modelEntry(model).catalogModel.startsWith('gpt-image-2.6-');
        case 'video-text': return /^seedance-2\.[05]-(fast-)?text-to-video$/.test(model);
        case 'video-start-frame': return /^seedance-2\.[05]-(fast-)?image-to-video$/.test(model);
        case 'video-reference': return /^seedance-2\.[05]-(fast-)?reference-to-video$/.test(model);
        case 'video-lipsync': return LIPSYNC.includes(model);
        case 'video-avatar': return AVATAR.includes(model);
        case 'audio-tts': return /^speech-/.test(model) || ELEVEN_SPEECH_MODELS.has(model);
        case 'audio-dialogue': return ELEVEN_DIALOGUE_MODELS.has(model);
        case 'audio-transcribe': return TRANSCRIBE.includes(model);
        case 'music-description':
        case 'music-lyrics':
        case 'music-instrumental':
            return SUNO_MODELS.has(model) || model === 'lyria-3-pro' || model === ELEVEN_MUSIC_MODEL;
        case 'audio-clone': return false;
    }
}
function buildCandidate(request, model, defaultVoiceId, elevenVoiceId) {
    const op = request.operation;
    const protocol = op === 'understanding' ? 'understanding' : op.startsWith('music-') && model === 'lyria-3-pro-preview' ? 'native-music' : 'generation';
    const media = op.startsWith('image-') ? 'image' : op.startsWith('video-') ? 'video'
        : op === 'understanding' ? 'understanding' : 'audio';
    const candidate = { model, media, protocol };
    try {
        const inputs = request.inputs ?? {};
        const requirements = request.requirements ?? {};
        if (op.startsWith('music-') && SUNO_MODELS.has(model)) {
            assertKeys(inputs, [], 'inputs');
            const params = sunoParameters(model, sunoSceneParameters(op, request.prompt, requirements));
            validateGeneration('audio', model, params);
            candidate.params = params;
            return candidate;
        }
        if (protocol === 'native-music') {
            assertKeys(inputs, [], 'inputs');
            assertKeys(requirements, [], 'requirements');
            if (!request.prompt)
                throw new Error('Native music requires a prompt.');
            candidate.params = { contents: [{ role: 'user', parts: [{ text: request.prompt }] }], generationConfig: { responseModalities: ['AUDIO', 'TEXT'] } };
            return candidate;
        }
        const params = {};
        const inputFields = {};
        let allowedRequirements = [];
        let requiredInputs = [];
        let promptField;
        if (op === 'image-generate' || op === 'image-edit') {
            if (!IMAGE.includes(model))
                throw new Error('No verified task-to-parameter mapping for this image model. Use its documented single-model command or add a verified mapping.');
            promptField = 'prompt';
            allowedRequirements = ['resolution', 'quality', 'background', 'output_format', 'num_outputs'];
            if (model.startsWith('gpt-image-2.6-'))
                allowedRequirements.push('complexity');
            if (op === 'image-edit') {
                inputFields.images = ['image_urls', 'many'];
                inputFields.mask = ['mask_url', 'one'];
                requiredInputs = ['images'];
            }
        }
        else if (['video-text', 'video-start-frame', 'video-reference'].includes(op)) {
            promptField = 'prompt';
            allowedRequirements = ['duration', 'resolution', 'aspect_ratio'];
            if (model.startsWith('seedance-2.0-'))
                allowedRequirements.push('seed', 'generate_audio');
            if (op === 'video-start-frame') {
                inputFields.images = ['image_url', 'one'];
                requiredInputs = ['images'];
            }
            if (op === 'video-reference') {
                inputFields.images = ['image_urls', 'many'];
                inputFields.videos = ['video_urls', 'many'];
                inputFields.audios = ['audio_urls', 'many'];
                if (!inputs.images?.length && !inputs.videos?.length && !inputs.audios?.length)
                    throw new Error('Reference video requires at least one reference input.');
            }
            // Pin task defaults before constructing each model request; provider defaults differ.
            params.duration = requirements.duration ?? 5;
            params.resolution = requirements.resolution ?? '720p';
            params.aspect_ratio = requirements.aspect_ratio ?? '9:16';
            if (model.startsWith('seedance-2.0-')) {
                if (!Number.isInteger(params.duration) || Number(params.duration) < 4 || Number(params.duration) > 15)
                    throw new Error('Seedance 2.0 cannot preserve the requested duration (verified range: 4–15 seconds).');
                if (!['480p', '720p', ...(model.includes('-fast-') ? [] : ['1080p'])].includes(String(params.resolution)))
                    throw new Error('This Seedance 2.0 variant cannot preserve the requested resolution.');
                if (!['16:9', '4:3', '1:1', '3:4', '9:16', '21:9', 'adaptive'].includes(String(params.aspect_ratio)))
                    throw new Error('This Seedance 2.0 variant cannot preserve the requested aspect ratio.');
                if (op === 'video-reference' && ((inputs.images?.length ?? 0) > 9 || (inputs.videos?.length ?? 0) > 3 || (inputs.audios?.length ?? 0) > 3))
                    throw new Error('Seedance 2.0 reference counts are lower; input assets cannot be dropped.');
                if (op === 'video-reference' && inputs.audios?.length && !inputs.images?.length && !inputs.videos?.length)
                    throw new Error('Seedance 2.0 does not accept audio-only references.');
                // URL-only requests cannot prove the stricter 2.0 clip size/duration limits.
                if (op === 'video-reference' && (inputs.videos?.length || inputs.audios?.length))
                    throw new Error('Seedance 2.0 reference clip duration and byte limits require verified metadata; automatic mapping is unavailable.');
            }
        }
        else if (op === 'video-lipsync') {
            inputFields.videos = ['video_url', 'one'];
            inputFields.audios = ['audio_url', 'one'];
            requiredInputs = ['videos', 'audios'];
            if (model === 'sync-3')
                allowedRequirements = ['sync_mode'];
            else if (model === 'lipsync-2')
                allowedRequirements = ['active_speaker', 'sync_mode', 'temperature'];
            else
                throw new Error('This lip-sync variant needs a verified task parameter mapping before automatic selection.');
        }
        else if (op === 'video-avatar') {
            inputFields.images = ['image_url', 'one'];
            inputFields.audios = ['audio_url', 'one'];
            requiredInputs = ['images', 'audios'];
            if (model === 'fabric-1.0') {
                allowedRequirements = ['resolution'];
                // Fabric requires an explicit resolution; preserve the user's choice.
                params.resolution = requirements.resolution ?? '720p';
            }
            else if (model === 'omnihuman-1.5') {
                promptField = 'prompt';
                allowedRequirements = ['advanced', 'turbo_mode'];
            }
            else
                throw new Error('This avatar model needs a verified task parameter mapping before automatic selection.');
        }
        else if (op === 'audio-tts') {
            if (ELEVEN_SPEECH_MODELS.has(model)) {
                promptField = 'text';
                allowedRequirements = modelEntry(model).entry.params.filter(name => !['model', 'text'].includes(name));
            }
            else {
                if (!['speech-2.8-hd', 'speech-2.8-turbo'].includes(model))
                    throw new Error('Voice IDs and speech options require a verified mapping for this TTS model.');
                promptField = 'prompt';
                allowedRequirements = ['voice_setting', 'audio_setting', 'voice_modify', 'pronunciation_dict', 'language_boost'];
            }
        }
        else if (op === 'audio-dialogue') {
            allowedRequirements = modelEntry(model).entry.params.filter(name => name !== 'model');
        }
        else if (op === 'audio-transcribe') {
            if (SCRIBE_MODELS.has(model)) {
                const audio = inputs.audios;
                inputFields.audios = [audio?.[0] && !remoteAudio(audio[0]) ? 'file' : model === 'scribe-v2' ? 'source_url' : 'audio_url', 'one'];
                requiredInputs = ['audios'];
                allowedRequirements = modelEntry(model).entry.params.filter(name => !['model', 'source_url', 'audio_url', 'file'].includes(name));
            }
            else {
                candidate.transcription = audioContract(model);
                inputFields.audios = ['file_urls', 'many'];
                requiredInputs = ['audios'];
                allowedRequirements = ['channel_id', 'diarization', 'language_hints', 'recognition'];
                if (model === 'paraformer-8k-v2')
                    allowedRequirements = allowedRequirements.filter(name => name !== 'language_hints');
            }
        }
        else if (op.startsWith('music-')) {
            promptField = 'prompt';
            if (op === 'music-lyrics')
                throw new Error('This model has no verified mapping for preserving supplied lyrics. Select a Suno model for this scene.');
            if (model === ELEVEN_MUSIC_MODEL) {
                allowedRequirements = modelEntry(model).entry.params.filter(name => !['model', 'prompt'].includes(name));
                if (op === 'music-instrumental') {
                    if (Object.hasOwn(requirements, 'force_instrumental') && requirements.force_instrumental !== true)
                        throw new Error('force_instrumental conflicts with the instrumental scene.');
                    params.force_instrumental = true;
                }
            }
            else {
                if (op === 'music-instrumental')
                    throw new Error('This model has no verified instrumental control mapping. Select Suno or ElevenLabs Music.');
                if (model !== 'lyria-3-pro')
                    throw new Error('This music model needs verified duration, lyrics and parameter mappings before automatic selection.');
                inputFields.images = ['image_urls', 'many'];
                allowedRequirements = ['negative_prompt'];
            }
        }
        else if (op === 'understanding') {
            assertKeys(requirements, ['system_prompt', 'max_tokens', 'temperature'], 'requirements');
            if (inputs.mask)
                throw new Error('A mask cannot be discarded by an understanding request.');
            const content = Object.entries({ images: 'image_url', videos: 'video_url', audios: 'audio_url', files: 'file_url' })
                .flatMap(([field, type]) => (inputs[field] ?? []).map(url => ({ type, [type]: { url } })));
            if (!content.length || !request.prompt)
                throw new Error('Understanding requires a prompt and at least one media input.');
            candidate.params = { ...requirements, model, prompt: request.prompt, content };
            return candidate;
        }
        assertElevenParameterMigration(model, requirements);
        assertKeys(requirements, allowedRequirements, 'requirements');
        assertKeys(inputs, Object.keys(inputFields), 'inputs');
        for (const key of requiredInputs)
            if (!inputs[key])
                throw new Error(`inputs.${key} is required for ${op}.`);
        for (const [key, value] of Object.entries(inputs)) {
            const [field, cardinality] = inputFields[key];
            const values = Array.isArray(value) ? value : [value];
            if (cardinality === 'one' && values.length !== 1)
                throw new Error(`${op} requires exactly one ${key} input; no input may be dropped.`);
            params[field] = cardinality === 'one' ? values[0] : [...values];
        }
        if (request.prompt !== undefined) {
            if (!promptField)
                throw new Error(`A prompt has no verified meaning for ${op}; express the requirement through supported fields.`);
            params[promptField] = request.prompt;
        }
        Object.assign(params, JSON.parse(JSON.stringify(requirements)));
        if (op === 'audio-tts')
            Object.assign(params, speechParameters(model, params, defaultVoiceId, elevenVoiceId));
        // Reject every unmapped field even where a catalog schema is permissive.
        const entry = modelEntry(model).entry;
        assertKeys(params, entry.params.filter(name => name !== 'model'), 'model_parameters');
        validateGeneration(media, model, params);
        candidate.params = params;
    }
    catch (error) {
        candidate.rejection = error.message;
    }
    return candidate;
}
export function selectionPlan(cfg, value) {
    const request = readTaskRequest(value, cfg.skill);
    if (request.operation === 'audio-clone')
        throw new Error('ElevenLabs voice cloning is a configuration placeholder with no default model or enabled API contract. No cloning request was submitted.');
    const source = request.model ? 'user' : cfg.modelSelection?.models ? 'configuration' : 'built-in';
    const selected = request.model ? [request.model] : cfg.modelSelection?.models ?? defaults(request);
    const candidates = [];
    const excluded = [];
    for (const model of selected) {
        const migration = elevenMigration(model);
        if (migration) {
            excluded.push({ model, reason: migration });
            continue;
        }
        if (request.operation === 'audio-transcribe' && model === 'scribe-v2' && selected.includes('scribe-v3')) {
            excluded.push({ model, reason: 'Scribe V3 must not automatically downgrade to V2. Explicitly select V2 for a new request.' });
            continue;
        }
        if (!matchesOperation(model, request.operation)) {
            excluded.push({ model, reason: 'This exact model is not supported for the selected task purpose/protocol.' });
            continue;
        }
        candidates.push(buildCandidate(request, model, cfg.speech?.defaultVoiceId, cfg.elevenlabs?.defaultVoiceId));
    }
    return { request, candidates, excluded, source,
        policy: source === 'user' ? 'off' : cfg.modelSelection?.policy ?? 'auto',
        max_attempts: Math.min(cfg.modelSelection?.maxAttempts ?? candidates.length, candidates.length) };
}
