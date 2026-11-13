import { AihubmaxClient } from './apiClient.js';
import { AIHUB_SERVICE_URL, resolveConfiguration, sanitized } from './config.js';
import { validVoiceId } from './speech.js';
export function elevenPresetVoices(value) {
    if (!Array.isArray(value))
        throw new Error('Invalid ElevenLabs voice library response.');
    return presetVoices(value.map(row => row && typeof row === 'object' ? { ...row, voice_name: row.name,
        language: Array.isArray(row.languages) ? row.languages.filter((v) => typeof v === 'string').join(', ') : '',
        tag_list: row.category, sample_audio: row.preview_url } : row)).map(voice => ({ ...voice,
        languages: voice.language ? voice.language.split(', ') : [] }));
}
/** Only documented display fields leave the private loader. Never return credentials. */
export function presetVoices(value) {
    if (!Array.isArray(value) || value.length > 50000)
        throw new Error('Invalid voice library response.');
    const voices = new Map();
    const text = (value) => typeof value === 'string' ? value.slice(0, 4000) : '';
    for (const row of value) {
        if (!row || !validVoiceId(row.voice_id))
            throw new Error('Voice entry has no valid voice_id.');
        const voice_id = row.voice_id;
        voices.set(voice_id, { voice_id, voice_name: text(row.voice_name) || voice_id,
            language: text(row.language), accent: text(row.accent), gender: text(row.gender), age: text(row.age),
            tag_list: Array.isArray(row.tag_list) ? [...new Set(row.tag_list.filter((tag) => typeof tag === 'string').map(text))].slice(0, 100) : [],
            description: text(row.description), sample_audio: text(row.sample_audio) });
    }
    return [...voices.values()];
}
export async function loadVoiceLibrary(options, provider = 'minimax') {
    const resolved = resolveConfiguration({ ...options, skill: 'aihub-audio' });
    if (resolved.inspection.problems.some(p => p.reason === 'unreadable'))
        throw new Error('configuration');
    const apiKey = resolved.values.AIHUB_API_KEY;
    if (!apiKey)
        throw new Error('missing_key');
    const client = new AihubmaxClient({ baseUrl: AIHUB_SERVICE_URL, apiKey });
    const result = await client.request('GET', provider === 'elevenlabs' ? '/e/v1/configs/elevenlabs-preset-voice-id' : '/e/v1/configs/minimax-preset-voice-id?language=zh', undefined, { timeoutMs: 12000, deadline: Date.now() + 30000 });
    return sanitized(provider === 'elevenlabs' ? elevenPresetVoices(result) : presetVoices(result), [apiKey]);
}
