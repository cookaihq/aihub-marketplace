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
  if (model === 'scribe-v2' && typeof params.language_code === 'string') {
    return { ...params, language_code: params.language_code.trim().toLowerCase() };
  }
  if (!ELEVEN_AUDIO_MODELS.has(model)) return params;
  const nullable = new Set(['seed', 'language_code', 'previous_text', 'future_text', 'next_text',
    'pronunciation_dictionary_locators', 'voice_settings', 'settings', 'audio_effects', 'enable_safety_checker']);
  return Object.fromEntries(Object.entries(params).filter(([key, value]) => value !== null || !nullable.has(key)));
}
export const SCRIBE_MODELS = new Set(['scribe-v2', 'scribe-v3']);
export const ELEVEN_MUSIC_MODEL = 'elevenlabs-music-v2.5';

/** Run before flat-key checks so old requests receive actionable migration errors. */
export function assertElevenParameterMigration(model: string, params: Record<string, unknown>): void {
  if (model === 'scribe-v2' && Object.hasOwn(params, 'audio_url')) throw new Error('audio_url was removed for scribe-v2; migrate to source_url (or multipart file). scribe-v3 keeps audio_url.');
  if (!ELEVEN_AUDIO_MODELS.has(model)) return;
  if (Object.hasOwn(params, 'voice')) throw new Error('voice was removed; migrate to an explicit voice_id. No default voice is supplied.');
  const speech = ELEVEN_SPEECH_MODELS.has(model);
  const settings = speech ? 'voice_settings' : 'settings';
  for (const field of ['stability', 'similarity_boost', 'clone_strength']) {
    if (Object.hasOwn(params, field)) throw new Error(`${field} moved to ${settings}.${!speech && field === 'similarity_boost' ? 'similarity' : field}; migrate the field into the settings object.`);
  }
  if (speech && Object.hasOwn(params, 'future_text')) throw new Error('Speech future_text was removed; migrate to next_text. Dialogue still uses future_text.');
  if (!speech && Array.isArray(params.inputs)) params.inputs.forEach((item, index) => {
    if (item && typeof item === 'object' && Object.hasOwn(item, 'voice')) throw new Error(`inputs[${index}].voice was removed; migrate to inputs[${index}].voice_id.`);
  });
}

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
  assertElevenParameterMigration(model, params);
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
  if (ELEVEN_SPEECH_MODELS.has(model)) {
    if (!(params.voice_id as string).trim()) throw new Error('voice_id must be a nonempty existing voice ID.');
    const effects = params.audio_effects as Record<string, unknown> | null | undefined;
    if (effects && (effects.environment_id != null || (effects.pan != null && effects.pan !== 0)) &&
      /^(pcm_|ulaw_|alaw_)/.test(String(params.output_format ?? 'mp3_44100_128'))) {
      throw new Error('audio_effects.environment_id and nonzero audio_effects.pan require a stereo-capable output_format; pcm_, ulaw_ and alaw_ cannot be used.');
    }
  }
  if (ELEVEN_DIALOGUE_MODELS.has(model)) {
    const inputs = params.inputs as Array<{ text: string; voice_id: string }>;
    if (inputs.some(input => !input.voice_id.trim())) throw new Error('Each inputs[].voice_id requires a nonempty existing voice ID.');
    if (new Set(inputs.map(input => input.voice_id)).size > 10) throw new Error('inputs must use at most 10 distinct voice IDs.');
  }
  if (ELEVEN_AUDIO_MODELS.has(model) && Array.isArray(params.pronunciation_dictionary_locators)) {
    for (const locator of params.pronunciation_dictionary_locators as Array<Record<string, string>>) {
      if (!locator.pronunciation_dictionary_id?.trim() || !locator.version_id?.trim()) throw new Error('pronunciation_dictionary_locators requires a nonempty dictionary ID and fixed version_id.');
    }
  }
  if (SCRIBE_MODELS.has(model)) {
    const source = model === 'scribe-v2' ? 'source_url' : 'audio_url';
    if ((params[source] !== undefined) === (params.file !== undefined)) throw new Error(`Provide exactly one of ${source} or file.`);
    if (params[source] !== undefined) validateHttpUrl(params[source] as string, source);
    if (params.file !== undefined && (typeof params.file !== 'string' || !params.file.trim())) throw new Error('file must be a nonempty local audio path.');
    const speakers = params.num_speakers != null; const threshold = params.diarization_threshold != null;
    if (speakers && threshold) throw new Error('num_speakers and diarization_threshold are mutually exclusive.');
    const diarize = params.diarize ?? (model === 'scribe-v3');
    if (!diarize && (speakers || threshold)) throw new Error('num_speakers and diarization_threshold require diarize=true.');
    if (model === 'scribe-v2') validateScribeV2(params);
    return;
  }
  if (model !== ELEVEN_MUSIC_MODEL) return;
  const plan = params.composition_plan as { chunks: Array<Record<string, unknown>> } | null | undefined;
  if ((params.prompt != null) === (plan != null)) throw new Error('Provide exactly one of prompt or composition_plan.');
  if (plan && (params.music_length_ms != null || Object.hasOwn(params, 'force_instrumental'))) throw new Error('music_length_ms and explicit force_instrumental (including false) are only supported in prompt mode.');
  if (!plan && params.seed != null) throw new Error('seed is only supported in composition_plan mode.');
  if (params.sign_with_c2pa === true && params.output_format !== undefined && params.output_format !== 'auto' && !String(params.output_format).startsWith('mp3_')) throw new Error('sign_with_c2pa requires MP3 output_format (including auto); the specified format will not be changed.');
  if (!plan && typeof params.prompt === 'string' && !params.prompt.trim()) throw new Error('prompt must not be blank.');
  if (!plan) return;
  // Integer milliseconds avoid float accumulation at the 600-second boundary.
  const totalMs = plan.chunks.reduce((sum, chunk) => sum + Number(chunk.duration_ms), 0);
  if (totalMs > 600_000) throw new Error('composition_plan total duration must be <= 600000 milliseconds.');
  for (const [index, chunk] of plan.chunks.entries()) {
    const label = `composition_plan.chunks[${index}]`;
    const text = chunk.text as string;
    // Match the contract's Python splitlines, including a final line terminator.
    const lines = text.split(/\r\n|[\n\r\v\f\u001c-\u001e\u0085\u2028\u2029]/);
    if (lines.at(-1) === '') lines.pop();
    if (lines.length > 30 || lines.some(line => [...line].length > 200)) throw new Error(`${label}.text allows at most 30 lines of 200 characters.`);
    const sectionEnd = text.indexOf(']');
    const sectionLength = [...text.slice(1, sectionEnd)].length;
    if (text.startsWith('[') && (sectionEnd < 0 || sectionLength < 1 || sectionLength > 100)) throw new Error(`${label}.text section name must contain 1–100 characters and a closing bracket.`);
    const reference = chunk.audio_reference as Record<string, unknown> | null | undefined;
    if (!reference) continue;
    validateHttpUrl(reference.audio_url as string, `${label}.audio_reference.audio_url`);
    const start = Number(reference.start_ms ?? 0);
    if (reference.end_ms != null && (Number(reference.end_ms) <= start || Number(reference.end_ms) - start > 30_000)) {
      throw new Error(`${label}.audio_reference.end_ms must exceed start_ms with a window of at most 30000 milliseconds.`);
    }
  }
}

function validateHttpUrl(value: string, field: string): void {
  let url: URL;
  try { url = new URL(value); } catch { throw new Error(`${field} must use public HTTP(S).`); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error(`${field} must use HTTP(S) without credentials.`);
}

// Native Scribe selections: expand only for validation; send the original value.
const ENTITY_CATEGORIES: Record<string, string[]> = {
  pii: `account_number age bank_account cardinal credit_card credit_card_expiration cvv date date_interval dob driver_license email_address event filename gender gender_sexuality sexual_orientation healthcare_number ip_address location location_address location_city location_coordinate location_country location_state location_zip money name name_given name_family name_medical_professional numerical_pii occupation ordinal origin passport_number password percent phone_number physical_attribute ssn time url username vehicle_id`.split(' '),
  phi: 'condition drug injury blood_type medical_process clinical_measurement statistics'.split(' '),
  pci: 'credit_card credit_card_expiration cvv'.split(' '),
  other: 'language marital_status organization political_affiliation religion routing_number zodiac_sign product_or_service food_or_beverage document_reference generic_id measurement time_duration'.split(' '),
  offensive_language: ['very_offensive_language', 'less_offensive_language'],
};
const ENTITY_TYPES = new Set(Object.values(ENTITY_CATEGORIES).flat());
function expandEntities(selection: unknown): Set<string> {
  const selected = typeof selection === 'string' ? [selection] : (selection ?? []) as string[];
  const expanded = new Set<string>();
  for (const name of selected) {
    const category = Object.hasOwn(ENTITY_CATEGORIES, name) ? ENTITY_CATEGORIES[name] : undefined;
    const types = name === 'all' ? [...ENTITY_TYPES] : category ?? (ENTITY_TYPES.has(name) ? [name] : undefined);
    if (!types) throw new Error(`Unknown Scribe entity type or category: ${name}`);
    types.forEach(type => expanded.add(type));
  }
  return expanded;
}
function validateScribeV2(params: Record<string, unknown>): void {
  if (typeof params.language_code === 'string') {
    const language = params.language_code.trim().toLowerCase();
    if (!/^[a-z]{2,3}$/.test(language)) throw new Error('language_code must be a 2-letter or 3-letter ISO code.');
    if (language === 'cmn') throw new Error("language_code='cmn' is not supported; use 'zh' or 'zho' for Mandarin Chinese.");
  }
  for (const term of (params.keyterms ?? []) as string[]) {
    if (term.trim().split(/\s+/).length > 5 || /[<>{}\[\]\\]/.test(term)) throw new Error('Each keyterms item allows at most 5 words and cannot contain < > { } [ ] or backslash.');
  }
  const multi = params.use_multi_channel === true;
  if (params.detect_speaker_roles === true && (params.diarize !== true || multi)) throw new Error('detect_speaker_roles requires diarize=true and use_multi_channel=false.');
  if (multi && (params.diarize === true || params.num_speakers != null || params.diarization_threshold != null || params.file_format === 'pcm_s16le_16')) throw new Error('use_multi_channel cannot be combined with diarization controls or file_format=pcm_s16le_16.');
  const detection = expandEntities(params.entity_detection);
  const redaction = expandEntities(params.entity_redaction);
  const hasEntities = [params.entity_detection, params.entity_redaction].some(value => Array.isArray(value) ? value.length > 0 : Boolean(value));
  if (params.transcript_edit && (hasEntities || multi)) throw new Error('transcript_edit cannot be combined with entity_detection, entity_redaction or use_multi_channel.');
  if ([...redaction].some(type => !detection.has(type))) throw new Error('entity_redaction must be a subset of entity_detection.');
}
