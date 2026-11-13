/** Suno v6 public contract: https://docs.aihubmax.com/openapi/zh/suno-music-generation.json */
export const SUNO_MODELS = new Set(['suno-v6', 'suno-v6-wild', 'suno-v6-mini']);
export const SUNO_DEFAULT_MODEL = 'suno-v6';
const FIELDS = new Set(['model', 'mode', 'prompt', 'lyrics', 'style', 'title', 'duration', 'vocal_gender',
    'style_weight', 'weirdness_constraint', 'style_variation', 'negative_prompt', 'rewrite_lyrics',
    'max_mode', 'is_instrumental', 'output_format']);
const has = (params, key) => Object.hasOwn(params, key);
function text(params, key, limit, required = false) {
    const value = params[key];
    if (value === undefined || value === null) {
        if (required)
            throw new Error(`${key} is required and must be nonempty.`);
        return;
    }
    if (typeof value !== 'string' || Array.from(value).length > limit || (required && !value.trim())) {
        throw new Error(`${key} must be ${required ? 'nonempty ' : ''}text of at most ${limit} characters.`);
    }
}
/** Validate presence as well as values: even false/0/null can be forbidden in a mode. */
export function validateSuno(model, params) {
    if (!SUNO_MODELS.has(model))
        throw new Error('Unsupported Suno model; select an exact documented v6 ID.');
    for (const key of Object.keys(params))
        if (!FIELDS.has(key))
            throw new Error(`Unsupported Suno parameter: ${key}`);
    if (has(params, 'model') && params.model !== model)
        throw new Error('params.model conflicts with the selected model.');
    const mode = has(params, 'mode') ? params.mode : 'description';
    if (mode !== 'description' && mode !== 'custom')
        throw new Error('mode must be description or custom.');
    for (const key of ['is_instrumental', 'rewrite_lyrics', 'max_mode']) {
        if (has(params, key) && typeof params[key] !== 'boolean')
            throw new Error(`${key} must be boolean.`);
    }
    const instrumental = params.is_instrumental === true;
    const forbid = (keys, reason) => {
        for (const key of keys)
            if (has(params, key))
                throw new Error(`${key} is not accepted ${reason}; explicit values cannot be discarded.`);
    };
    if (mode === 'description') {
        forbid(['lyrics', 'rewrite_lyrics', 'max_mode'], 'in description mode');
        if (model === 'suno-v6-mini')
            forbid(['duration', 'title', 'style', 'vocal_gender', 'style_weight'], 'in Suno Mini description mode');
        text(params, 'prompt', 3000, true);
    }
    else {
        forbid(['prompt'], 'in custom mode');
        if (instrumental)
            text(params, 'style', 1000, true);
        else
            text(params, 'lyrics', 5000, true);
    }
    if (instrumental)
        forbid(['lyrics', 'rewrite_lyrics', 'vocal_gender'], 'for instrumental music');
    text(params, 'style', 1000);
    text(params, 'title', 80);
    if (has(params, 'duration') && (!Number.isInteger(params.duration) || Number(params.duration) < 10 || Number(params.duration) > 360)) {
        throw new Error('duration must be an integer target of 10–360 seconds; actual duration may differ.');
    }
    for (const key of ['style_weight', 'weirdness_constraint']) {
        if (has(params, key) && (typeof params[key] !== 'number' || !Number.isFinite(params[key]) || Number(params[key]) < 0 || Number(params[key]) > 1)) {
            throw new Error(`${key} must be a finite number from 0 to 1.`);
        }
    }
    for (const [key, values] of Object.entries({ vocal_gender: ['Male', 'Female', 'm', 'f'],
        style_variation: ['off', 'normal', 'high', 'extra', 'max'], output_format: ['mp3', 'm4a', 'wav'] })) {
        if (has(params, key) && !values.includes(params[key]))
            throw new Error(`Invalid ${key}; use describe for accepted values.`);
    }
    if (has(params, 'negative_prompt') && typeof params.negative_prompt !== 'string')
        throw new Error('negative_prompt must be text.');
}
/** Only documented normalization; no control or target-duration defaults are injected. */
export function sunoParameters(model, params) {
    validateSuno(model, params);
    return { ...params, ...(has(params, 'vocal_gender') ? { vocal_gender: params.vocal_gender === 'Male' ? 'm' : params.vocal_gender === 'Female' ? 'f' : params.vocal_gender } : {}) };
}
export function sunoSceneParameters(scene, prompt, requirements) {
    const fixed = scene === 'music-description' ? { mode: 'description', is_instrumental: false }
        : { mode: 'custom', is_instrumental: scene === 'music-instrumental' };
    for (const key of ['model', 'prompt', 'lyrics', 'style']) {
        if (has(requirements, key) && (key !== 'style' || scene === 'music-instrumental')) {
            throw new Error(`requirements.${key} conflicts with the scene input; preserve that input in prompt.`);
        }
    }
    for (const [key, value] of Object.entries(fixed)) {
        if (has(requirements, key) && requirements[key] !== value)
            throw new Error(`${key} conflicts with ${scene}; choose the matching scene.`);
    }
    const field = scene === 'music-description' ? 'prompt' : scene === 'music-lyrics' ? 'lyrics' : 'style';
    return { ...requirements, ...fixed, [field]: prompt };
}
