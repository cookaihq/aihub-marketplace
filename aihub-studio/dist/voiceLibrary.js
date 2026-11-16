import { AihubmaxClient } from './apiClient.js';
import { AIHUB_SERVICE_URL, resolveConfiguration, sanitized } from './config.js';
import { validVoiceId } from './speech.js';
import { createHash } from 'node:crypto';
const cataloguePaths = {
    minimax: '/e/v1/configs/minimax-preset-voice-id?language=zh',
    elevenlabs: '/e/v1/configs/elevenlabs-preset-voice-id',
};
const ELEVENLABS_PAGE_SIZE = 100;
// A complete catalogue takes many sequential metadata requests. Keep one budget
// for all pages, including the client's bounded GET retries and backoff.
const ELEVENLABS_DOWNLOAD_BUDGET_MS = 300_000;
const VOICE_PAGE_TIMEOUT_MS = 12_000;
export class VoiceCatalogueError extends Error {
    code;
    constructor(code) {
        super(code);
        this.code = code;
        this.name = 'VoiceCatalogueError';
    }
}
function paginationNumber(value) {
    if (value === null || !/^[0-9]+$/.test(value) || !Number.isSafeInteger(Number(value))) {
        throw new VoiceCatalogueError('invalid_pagination');
    }
    return Number(value);
}
export async function downloadElevenlabsCatalogue(client) {
    const deadline = Date.now() + ELEVENLABS_DOWNLOAD_BUDGET_MS;
    const rows = [];
    let offset = 0, total;
    for (;;) {
        let headers;
        const page = await client.request('GET', `${cataloguePaths.elevenlabs}?limit=${ELEVENLABS_PAGE_SIZE}&offset=${offset}`, undefined, { timeoutMs: VOICE_PAGE_TIMEOUT_MS, deadline, onResponseHeaders: value => { headers = value; } });
        if (!headers || !Array.isArray(page))
            throw new VoiceCatalogueError('invalid_pagination');
        const count = paginationNumber(headers.get('x-total-count'));
        const limit = paginationNumber(headers.get('x-limit'));
        const current = paginationNumber(headers.get('x-offset'));
        const next = headers.get('x-next-offset');
        if (total !== undefined && count !== total)
            throw new VoiceCatalogueError('catalogue_changed');
        total = count;
        if (limit !== ELEVENLABS_PAGE_SIZE || current !== offset || offset > total ||
            page.length !== Math.min(limit, total - offset) || next === null) {
            throw new VoiceCatalogueError('invalid_pagination');
        }
        const end = offset + page.length;
        if (next === '' ? end !== total : paginationNumber(next) !== end || end <= offset || end >= total) {
            throw new VoiceCatalogueError('invalid_pagination');
        }
        // Preserve page order and every source field; no sorting or ID deduplication.
        for (const row of page)
            rows.push(row);
        if (next === '')
            return rows;
        offset = paginationNumber(next);
    }
}
export function voiceLibraryIdentity(apiKey, provider) {
    return createHash('sha256').update(JSON.stringify([AIHUB_SERVICE_URL, provider, apiKey, cataloguePaths[provider]])).digest('hex');
}
export function elevenPresetVoices(value) {
    if (!Array.isArray(value))
        throw new Error('Invalid ElevenLabs voice library response.');
    return value.map(row => {
        if (!row || typeof row !== 'object' || !validVoiceId(row.voice_id))
            throw new Error('Voice entry has no valid voice_id.');
        const text = (value) => typeof value === 'string' ? value : '';
        const languages = Array.isArray(row.languages) ? row.languages.filter((v) => typeof v === 'string') : [];
        // Keep the original fields intact beside the aliases used by the existing UI.
        return { voice_name: text(row.name) || row.voice_id, language: languages.join(', '),
            accent: text(row.accent), gender: text(row.gender), age: text(row.age), description: text(row.description),
            tag_list: Array.isArray(row.category) ? row.category.filter((v) => typeof v === 'string') : [],
            sample_audio: text(row.preview_url), languages, ...row };
    });
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
export async function loadVoiceLibrary(options, provider = 'minimax', expectedIdentity) {
    const resolved = resolveConfiguration({ ...options, skill: 'aihub-audio' });
    if (resolved.inspection.problems.some(p => p.reason === 'unreadable'))
        throw new Error('configuration');
    const apiKey = resolved.values.AIHUB_API_KEY;
    if (!apiKey)
        throw new Error('missing_key');
    if (expectedIdentity && voiceLibraryIdentity(apiKey, provider) !== expectedIdentity)
        throw new Error('configuration_changed');
    const client = new AihubmaxClient({ baseUrl: AIHUB_SERVICE_URL, apiKey });
    const result = provider === 'elevenlabs' ? await downloadElevenlabsCatalogue(client)
        : await client.request('GET', cataloguePaths[provider], undefined, { timeoutMs: VOICE_PAGE_TIMEOUT_MS, deadline: Date.now() + 30000 });
    return sanitized(provider === 'elevenlabs' ? elevenPresetVoices(result) : presetVoices(result), [apiKey]);
}
