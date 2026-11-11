import { AihubmaxClient } from './apiClient.js';
import { AIHUB_SERVICE_URL, resolveConfiguration, sanitized, type ConfigOptions } from './config.js';
import { validVoiceId } from './speech.js';

export interface PresetVoice {
  voice_id: string; voice_name: string; language: string; accent: string;
  gender: string; age: string; tag_list: string[]; description: string; sample_audio: string;
}

/** Only documented display fields leave the private loader. Never return credentials. */
export function presetVoices(value: unknown): PresetVoice[] {
  if (!Array.isArray(value) || value.length > 10000) throw new Error('Invalid voice library response.');
  const voices = new Map<string, PresetVoice>();
  const text = (value: unknown) => typeof value === 'string' ? value.slice(0, 4000) : '';
  for (const row of value) {
    if (!row || !validVoiceId(row.voice_id)) throw new Error('Voice entry has no valid voice_id.');
    const voice_id = row.voice_id;
    voices.set(voice_id, {voice_id, voice_name: text(row.voice_name) || voice_id,
      language: text(row.language), accent: text(row.accent), gender: text(row.gender), age: text(row.age),
      tag_list: Array.isArray(row.tag_list) ? [...new Set<string>(row.tag_list.filter((tag: unknown) => typeof tag === 'string').map(text))].slice(0, 100) : [],
      description: text(row.description), sample_audio: text(row.sample_audio)});
  }
  return [...voices.values()];
}

export async function loadVoiceLibrary(options: Omit<ConfigOptions, 'skill'>): Promise<PresetVoice[]> {
  const resolved = resolveConfiguration({...options, skill: 'aihub-audio'});
  if (resolved.inspection.problems.some(p => p.reason === 'unreadable')) throw new Error('configuration');
  const apiKey = resolved.values.AIHUB_API_KEY;
  if (!apiKey) throw new Error('missing_key');
  const client = new AihubmaxClient({baseUrl: AIHUB_SERVICE_URL, apiKey});
  const result = await client.request<unknown>('GET', '/e/v1/configs/minimax-preset-voice-id?language=zh', undefined,
    {timeoutMs: 12000, deadline: Date.now() + 30000});
  return sanitized(presetVoices(result), [apiKey]);
}
