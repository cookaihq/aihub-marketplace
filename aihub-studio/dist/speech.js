/** MiniMax-specific defaults and user preferences; favorites never affect submission. */
export const MINIMAX_DEFAULT_VOICE_KEY = 'AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID';
export const MINIMAX_FAVORITES_KEY = 'audio.minimax_speech.favorite_voice_ids';
export const MINIMAX_SPEECH_MODELS = new Set(['speech-2.8-hd', 'speech-2.8-turbo']);
export function validVoiceId(value) {
    // Official IDs include spaces, e.g. Chinese (Mandarin)_Warm_Girl.
    return typeof value === 'string' && value.length > 0 && value.length <= 512 && value === value.trim()
        && !/[\x00-\x1f\x7f-\x9f\u2028\u2029]/.test(value);
}
export function speechParameters(model, params, defaultVoiceId) {
    if (!MINIMAX_SPEECH_MODELS.has(model) || !defaultVoiceId)
        return params;
    const settings = params.voice_setting;
    // Explicit values, including invalid ones, must be validated rather than replaced.
    if (settings !== undefined && (!settings || typeof settings !== 'object' || Array.isArray(settings)))
        return params;
    if (settings && Object.hasOwn(settings, 'voice_id'))
        return params;
    return { ...params, voice_setting: { ...settings, voice_id: defaultVoiceId } };
}
export function validateSpeechPreferences(settings) {
    const audio = settings.audio;
    if (audio === undefined)
        return;
    if (!audio || typeof audio !== 'object' || Array.isArray(audio))
        throw new Error('settings.json audio must be an object.');
    const speech = audio.minimax_speech;
    if (speech === undefined)
        return;
    if (!speech || typeof speech !== 'object' || Array.isArray(speech))
        throw new Error('settings.json audio.minimax_speech must be an object.');
    const favorites = speech.favorite_voice_ids;
    if (favorites !== undefined && (!Array.isArray(favorites) || favorites.length > 2000 || !favorites.every(validVoiceId) || new Set(favorites).size !== favorites.length)) {
        throw new Error('MiniMax favorite_voice_ids must contain at most 2000 distinct, nonempty voice IDs.');
    }
}
