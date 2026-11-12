export const ELEVEN_TTS_MODELS = new Set(['eleven-v4', 'eleven-v4-turbo', 'eleven-v4-custom-voice', 'eleven-v4-turbo-custom-voice']);
export const SCRIBE_MODELS = new Set(['scribe-v2', 'scribe-v3']);
export const ELEVEN_MUSIC_MODEL = 'elevenlabs-music-v2.5';
/** Only the schema vocabulary used by these bundled, dereferenced contracts. */
function validateSchema(value, schema, path, strictObject = false) {
    if (schema.anyOf) {
        const errors = [];
        for (const variant of schema.anyOf) {
            try {
                validateSchema(value, variant, path);
                return;
            }
            catch (error) {
                errors.push(error);
            }
        }
        throw errors[0];
    }
    const validType = schema.type === 'null' ? value === null
        : schema.type === 'array' ? Array.isArray(value)
            : schema.type === 'object' ? value !== null && typeof value === 'object' && !Array.isArray(value)
                : schema.type === 'integer' ? Number.isSafeInteger(value)
                    : schema.type === 'number' ? typeof value === 'number' && Number.isFinite(value)
                        : !schema.type || typeof value === schema.type;
    if (!validType)
        throw new Error(`${path} must have type ${schema.type}.`);
    if (schema.enum && !schema.enum.includes(value))
        throw new Error(`${path} must be one of ${schema.enum.join(', ')}.`);
    if (typeof value === 'string') {
        const length = [...value].length;
        if (schema.minLength !== undefined && length < schema.minLength)
            throw new Error(`${path} requires at least ${schema.minLength} characters.`);
        if (schema.maxLength !== undefined && length > schema.maxLength)
            throw new Error(`${path} allows at most ${schema.maxLength} characters.`);
    }
    if (typeof value === 'number') {
        if (schema.minimum !== undefined && value < schema.minimum)
            throw new Error(`${path} must be >= ${schema.minimum}.`);
        if (schema.maximum !== undefined && value > schema.maximum)
            throw new Error(`${path} must be <= ${schema.maximum}.`);
        if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum)
            throw new Error(`${path} must be > ${schema.exclusiveMinimum}.`);
        if (schema.multipleOf !== undefined) {
            const units = value / schema.multipleOf;
            if (Math.abs(units - Math.round(units)) > 1e-7)
                throw new Error(`${path} must be a multiple of ${schema.multipleOf}.`);
        }
    }
    if (Array.isArray(value)) {
        if (schema.minItems !== undefined && value.length < schema.minItems)
            throw new Error(`${path} requires at least ${schema.minItems} items.`);
        if (schema.maxItems !== undefined && value.length > schema.maxItems)
            throw new Error(`${path} allows at most ${schema.maxItems} items.`);
        if (schema.items)
            value.forEach((item, index) => validateSchema(item, schema.items, `${path}[${index}]`));
    }
    else if (value !== null && typeof value === 'object') {
        const record = value;
        for (const name of schema.required ?? [])
            if (record[name] === undefined)
                throw new Error(`${path}.${name} is required.`);
        for (const [name, item] of Object.entries(record)) {
            const field = Object.hasOwn(schema.properties ?? {}, name) ? schema.properties[name] : undefined;
            if (field)
                validateSchema(item, field, `${path}.${name}`);
            else if (strictObject || schema.additionalProperties === false)
                throw new Error(`${path}.${name} is not supported; no parameter may be silently discarded.`);
        }
    }
}
/** Cross-field rules expressed in the contract descriptions, beyond JSON Schema. */
export function validateElevenLabs(model, params, schema) {
    if (model === ELEVEN_MUSIC_MODEL) {
        if (Object.hasOwn(params, 'duration'))
            throw new Error('duration in seconds was removed; migrate to integer music_length_ms (milliseconds).');
        const chunks = params.composition_plan?.chunks;
        if (Array.isArray(chunks))
            chunks.forEach((chunk, index) => {
                if (chunk && typeof chunk === 'object' && Object.hasOwn(chunk, 'duration')) {
                    throw new Error(`composition_plan.chunks[${index}].duration in seconds was removed; migrate to integer duration_ms (milliseconds).`);
                }
            });
    }
    validateSchema({ ...params, model }, schema, 'params', true);
    if (ELEVEN_TTS_MODELS.has(model) && model.endsWith('-custom-voice') &&
        (typeof params.voice !== 'string' || !params.voice.trim() || params.voice === 'Rachel')) {
        throw new Error('custom-voice requires an explicit existing voice ID; it does not create or clone a voice.');
    }
    if (model.endsWith('-custom-voice')) {
        if ([...String(params.text)].length > 2000)
            throw new Error('Official custom-voice text allows at most 2000 characters.');
        if (model.includes('-turbo-')) {
            for (const key of ['previous_text', 'future_text', 'similarity_boost'])
                if (params[key] != null)
                    throw new Error(`Official Turbo does not support ${key}; preserve the request and select a compatible model.`);
            if (params.seed === 0)
                throw new Error('Official Turbo seed must be > 0.');
        }
    }
    if (SCRIBE_MODELS.has(model)) {
        if ((params.audio_url !== undefined) === (params.file !== undefined))
            throw new Error('Provide exactly one of audio_url or file.');
        if (params.audio_url !== undefined) {
            let url;
            try {
                url = new URL(params.audio_url);
            }
            catch {
                throw new Error('audio_url must use public HTTP(S).');
            }
            if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
                throw new Error('audio_url must use HTTP(S) without credentials.');
        }
        if (params.file !== undefined && (typeof params.file !== 'string' || !params.file.trim()))
            throw new Error('file must be a nonempty local audio path.');
        const speakers = params.num_speakers != null;
        const threshold = params.diarization_threshold != null;
        if (speakers && threshold)
            throw new Error('num_speakers and diarization_threshold are mutually exclusive.');
        if (params.diarize === false && (speakers || threshold))
            throw new Error('num_speakers and diarization_threshold require diarize=true.');
        return;
    }
    if (model !== ELEVEN_MUSIC_MODEL)
        return;
    const plan = params.composition_plan;
    if ((params.prompt != null) === (plan != null))
        throw new Error('Provide exactly one of prompt or composition_plan.');
    if (plan && (params.music_length_ms != null || params.force_instrumental === true))
        throw new Error('music_length_ms and force_instrumental=true are only supported in prompt mode.');
    if (!plan && params.seed != null)
        throw new Error('seed is only supported in composition_plan mode.');
    if (!plan && typeof params.prompt === 'string' && !params.prompt.trim())
        throw new Error('prompt must not be blank.');
    if (!plan)
        return;
    // Integer milliseconds avoid float accumulation at the 600-second boundary.
    const totalMs = plan.chunks.reduce((sum, chunk) => sum + Number(chunk.duration_ms), 0);
    if (totalMs > 600_000)
        throw new Error('composition_plan total duration must be <= 600000 milliseconds.');
    for (const [index, chunk] of plan.chunks.entries()) {
        const label = `composition_plan.chunks[${index}]`;
        const text = chunk.text;
        const lines = text.split(/\r\n|\r|\n/);
        if (lines.length > 30 || lines.some(line => [...line].length > 200))
            throw new Error(`${label}.text allows at most 30 lines of 200 characters.`);
        const section = /^\[([^\]\r\n]*)\]/.exec(text);
        if (section && ([...section[1]].length < 1 || [...section[1]].length > 100))
            throw new Error(`${label}.text section name must contain 1–100 characters.`);
        const reference = chunk.audio_reference;
        if (!reference)
            continue;
        let url;
        try {
            url = new URL(reference.audio_url);
        }
        catch {
            throw new Error(`${label}.audio_reference.audio_url must use public HTTP(S).`);
        }
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
            throw new Error(`${label}.audio_reference.audio_url must use public HTTP(S) without credentials.`);
        const start = Number(reference.start_ms ?? 0);
        if (reference.end_ms != null && (Number(reference.end_ms) <= start || Number(reference.end_ms) - start > 30_000)) {
            throw new Error(`${label}.audio_reference.end_ms must exceed start_ms with a window of at most 30000 milliseconds.`);
        }
    }
}
