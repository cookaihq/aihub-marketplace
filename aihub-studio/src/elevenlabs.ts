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

export const ELEVEN_TTS_MODELS = new Set(['eleven-v4', 'eleven-v4-turbo']);
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
      if (Math.abs(units - Math.round(units)) > 1e-7) throw new Error(`${path} must be a multiple of ${schema.multipleOf} seconds.`);
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
  validateSchema({ ...params, model }, schema, 'params', true);
  if (model !== ELEVEN_MUSIC_MODEL) return;
  const plan = params.composition_plan as { chunks: Array<Record<string, unknown>> } | null | undefined;
  if ((params.prompt != null) === (plan != null)) throw new Error('Provide exactly one of prompt or composition_plan.');
  const unused = plan ? ['duration', 'force_instrumental'] : ['seed'];
  for (const key of unused) if (Object.hasOwn(params, key)) {
    throw new Error(`${key} is only supported in ${plan ? 'prompt' : 'composition_plan'} mode; it cannot be silently discarded.`);
  }
  if (!plan) return;
  // Integer milliseconds avoid float accumulation at the 600-second boundary.
  const totalMs = plan.chunks.reduce((sum, chunk) => sum + Math.round(Number(chunk.duration) * 1000), 0);
  if (totalMs > 600_000) throw new Error('composition_plan total duration must be <= 600 seconds.');
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
