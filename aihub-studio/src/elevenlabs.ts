/** Request constraints are extracted from the delivered OpenAPI into the catalog. */
export interface RequestSchema {
  type?: string;
  properties?: Record<string, RequestSchema>;
  required?: string[];
  additionalProperties?: boolean;
  anyOf?: RequestSchema[];
  enum?: unknown[];
  items?: RequestSchema;
  minItems?: number;
  maxItems?: number;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  multipleOf?: number;
}

export const ELEVEN_SPEECH_MODELS = new Set(['eleven-v4-text-to-speech', 'eleven-v4-text-to-speech-custom-voice']);
export const ELEVEN_DIALOGUE_MODELS = new Set(['eleven-v4-text-to-dialogue', 'eleven-v4-text-to-dialogue-custom-voice']);
export const ELEVEN_AUDIO_MODELS = new Set([...ELEVEN_SPEECH_MODELS, ...ELEVEN_DIALOGUE_MODELS]);
const RETIRED_ELEVEN_MODELS = new Set(['eleven-v4', 'eleven-v4-turbo', 'eleven-v4-custom-voice', 'eleven-v4-turbo-custom-voice']);
export function elevenMigration(model: string): string | undefined {
  if (!RETIRED_ELEVEN_MODELS.has(model)) return;
  return `Model ${model} no longer accepts new requests and has no alias or Turbo replacement. For audio-tts select eleven-v4-text-to-speech or eleven-v4-text-to-speech-custom-voice; for audio-dialogue select eleven-v4-text-to-dialogue or eleven-v4-text-to-dialogue-custom-voice with ordered inputs. Personal model lists are not rewritten. Query/resume historical task IDs without resubmission.`;
}
/** Null means unspecified for these controls; false and zero remain explicit. Validate first. */
export function elevenAudioParameters(model: string, params: Record<string, unknown>): Record<string, unknown> {
  if (!ELEVEN_AUDIO_MODELS.has(model)) return params;
  const nullable = new Set(['similarity_boost', 'seed', 'language_code', 'previous_text', 'future_text',
    'pronunciation_dictionary_locators', 'clone_strength', ...(ELEVEN_SPEECH_MODELS.has(model) ? ['enable_safety_checker'] : [])]);
  return Object.fromEntries(Object.entries(params).filter(([key, value]) => value !== null || !nullable.has(key)));
}
export const SCRIBE_MODELS = new Set(['scribe-v2', 'scribe-v3']);
export const ELEVEN_MUSIC_MODEL = 'elevenlabs-music-v2.5';

/** Only the schema vocabulary used by these bundled, dereferenced contracts. */
function validateSchema(value: unknown, schema: RequestSchema, path: string, strictObject = false): void {
  if (schema.anyOf) {
    const errors: Error[] = [];
    for (const variant of schema.anyOf) {
      try { validateSchema(value, variant, path); return; }
      catch (error) { errors.push(error as Error); }
    }
    throw errors[0];
  }
  const validType = schema.type === 'null' ? value === null
    : schema.type === 'array' ? Array.isArray(value)
    : schema.type === 'object' ? value !== null && typeof value === 'object' && !Array.isArray(value)
    : schema.type === 'integer' ? Number.isSafeInteger(value)
    : schema.type === 'number' ? typeof value === 'number' && Number.isFinite(value)
    : !schema.type || typeof value === schema.type;
  if (!validType) throw new Error(`${path} must have type ${schema.type}.`);
  if (schema.enum && !schema.enum.includes(value)) throw new Error(`${path} must be one of ${schema.enum.join(', ')}.`);
  if (typeof value === 'string') {
    const length = [...value].length;
    if (schema.minLength !== undefined && length < schema.minLength) throw new Error(`${path} requires at least ${schema.minLength} characters.`);
    if (schema.maxLength !== undefined && length > schema.maxLength) throw new Error(`${path} allows at most ${schema.maxLength} characters.`);
  }
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) throw new Error(`${path} must be >= ${schema.minimum}.`);
    if (schema.maximum !== undefined && value > schema.maximum) throw new Error(`${path} must be <= ${schema.maximum}.`);
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) throw new Error(`${path} must be > ${schema.exclusiveMinimum}.`);
    if (schema.multipleOf !== undefined) {
      const units = value / schema.multipleOf;
      if (Math.abs(units - Math.round(units)) > 1e-7) throw new Error(`${path} must be a multiple of ${schema.multipleOf}.`);
    }
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) throw new Error(`${path} requires at least ${schema.minItems} items.`);
    if (schema.maxItems !== undefined && value.length > schema.maxItems) throw new Error(`${path} allows at most ${schema.maxItems} items.`);
    if (schema.items) value.forEach((item, index) => validateSchema(item, schema.items!, `${path}[${index}]`));
  } else if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const name of schema.required ?? []) if (record[name] === undefined) throw new Error(`${path}.${name} is required.`);
    for (const [name, item] of Object.entries(record)) {
      const field = Object.hasOwn(schema.properties ?? {}, name) ? schema.properties![name] : undefined;
      if (field) validateSchema(item, field, `${path}.${name}`);
      else if (strictObject || schema.additionalProperties === false) throw new Error(`${path}.${name} is not supported; no parameter may be silently discarded.`);
    }
  }
}

/** Cross-field rules expressed in the contract descriptions, beyond JSON Schema. */
export function validateElevenLabs(model: string, params: Record<string, unknown>, schema: RequestSchema): void {
  if (model === ELEVEN_MUSIC_MODEL) {
    if (Object.hasOwn(params, 'duration')) throw new Error('duration in seconds was removed; migrate to integer music_length_ms (milliseconds).');
    const chunks = (params.composition_plan as { chunks?: unknown } | null)?.chunks;
    if (Array.isArray(chunks)) chunks.forEach((chunk, index) => {
      if (chunk && typeof chunk === 'object' && Object.hasOwn(chunk, 'duration')) {
        throw new Error(`composition_plan.chunks[${index}].duration in seconds was removed; migrate to integer duration_ms (milliseconds).`);
      }
    });
  }
  validateSchema({ ...params, model }, schema, 'params', true);
  if (ELEVEN_SPEECH_MODELS.has(model) && params.voice !== undefined &&
    (typeof params.voice !== 'string' || !params.voice.trim())) throw new Error('voice must be nonempty.');
  if (ELEVEN_SPEECH_MODELS.has(model) && model.endsWith('-custom-voice') &&
    (typeof params.voice !== 'string' || !params.voice.trim() || params.voice === 'Rachel')) {
    throw new Error('custom-voice requires an explicit existing voice ID; it does not create or clone a voice.');
  }
  if (ELEVEN_SPEECH_MODELS.has(model) && model.endsWith('-custom-voice')) {
    if ([...String(params.text)].length > 2000) throw new Error('custom-voice text allows at most 2000 Unicode characters.');
    if (params.enable_safety_checker != null) throw new Error('custom-voice does not support enable_safety_checker; preserve the explicit control and select a compatible model.');
  }
  if (ELEVEN_DIALOGUE_MODELS.has(model)) {
    const inputs = params.inputs as Array<{ text: string; voice: string }>;
    if (inputs.some(input => !input.voice.trim() || input.voice === 'Rachel')) throw new Error('Each inputs voice requires a nonempty existing voice ID; no default alias.');
    if (inputs.reduce((total, input) => total + [...input.text].length, 0) > 2000) throw new Error('inputs text must total at most 2000 Unicode characters.');
    if (new Set(inputs.map(input => input.voice)).size > 10) throw new Error('inputs must use at most 10 distinct voice IDs.');
  }
  if (ELEVEN_AUDIO_MODELS.has(model) && Array.isArray(params.pronunciation_dictionary_locators)) {
    for (const locator of params.pronunciation_dictionary_locators as Array<Record<string, string>>) {
      if (!locator.pronunciation_dictionary_id?.trim() || !locator.version_id?.trim()) throw new Error('pronunciation_dictionary_locators requires a nonempty dictionary ID and fixed version_id.');
    }
  }
  if (SCRIBE_MODELS.has(model)) {
    if ((params.audio_url !== undefined) === (params.file !== undefined)) throw new Error('Provide exactly one of audio_url or file.');
    if (params.audio_url !== undefined) {
      let url: URL;
      try { url = new URL(params.audio_url as string); } catch { throw new Error('audio_url must use public HTTP(S).'); }
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('audio_url must use HTTP(S) without credentials.');
    }
    if (params.file !== undefined && (typeof params.file !== 'string' || !params.file.trim())) throw new Error('file must be a nonempty local audio path.');
    const speakers = params.num_speakers != null; const threshold = params.diarization_threshold != null;
    if (speakers && threshold) throw new Error('num_speakers and diarization_threshold are mutually exclusive.');
    if (params.diarize === false && (speakers || threshold)) throw new Error('num_speakers and diarization_threshold require diarize=true.');
    return;
  }
  if (model !== ELEVEN_MUSIC_MODEL) return;
  const plan = params.composition_plan as { chunks: Array<Record<string, unknown>> } | null | undefined;
  if ((params.prompt != null) === (plan != null)) throw new Error('Provide exactly one of prompt or composition_plan.');
  if (plan && (params.music_length_ms != null || params.force_instrumental === true)) throw new Error('music_length_ms and force_instrumental=true are only supported in prompt mode.');
  if (!plan && params.seed != null) throw new Error('seed is only supported in composition_plan mode.');
  if (!plan && typeof params.prompt === 'string' && !params.prompt.trim()) throw new Error('prompt must not be blank.');
  if (!plan) return;
  // Integer milliseconds avoid float accumulation at the 600-second boundary.
  const totalMs = plan.chunks.reduce((sum, chunk) => sum + Number(chunk.duration_ms), 0);
  if (totalMs > 600_000) throw new Error('composition_plan total duration must be <= 600000 milliseconds.');
  for (const [index, chunk] of plan.chunks.entries()) {
    const label = `composition_plan.chunks[${index}]`;
    const text = chunk.text as string;
    const lines = text.split(/\r\n|\r|\n/);
    if (lines.length > 30 || lines.some(line => [...line].length > 200)) throw new Error(`${label}.text allows at most 30 lines of 200 characters.`);
    const section = /^\[([^\]\r\n]*)\]/.exec(text);
    if (section && ([...section[1]!].length < 1 || [...section[1]!].length > 100)) throw new Error(`${label}.text section name must contain 1–100 characters.`);
    const reference = chunk.audio_reference as Record<string, unknown> | null | undefined;
    if (!reference) continue;
    let url: URL;
    try { url = new URL(reference.audio_url as string); } catch { throw new Error(`${label}.audio_reference.audio_url must use public HTTP(S).`); }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error(`${label}.audio_reference.audio_url must use public HTTP(S) without credentials.`);
    const start = Number(reference.start_ms ?? 0);
    if (reference.end_ms != null && (Number(reference.end_ms) <= start || Number(reference.end_ms) - start > 30_000)) {
      throw new Error(`${label}.audio_reference.end_ms must exceed start_ms with a window of at most 30000 milliseconds.`);
    }
  }
}
