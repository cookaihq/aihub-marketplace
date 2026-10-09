/** Local evidence may contain private prompts; credentials and binary payloads never belong in it. */
const SECRET_KEY = /authorization|cookie|api[_.-]?key|password|secret|credential|accessToken|refreshToken|idToken|sessionId|(?:^|[_-])(?:auth|token|signature|sign|sig|session|jwt)(?:$|[_-])|^x-amz-|^x-goog-/i;
const MAX_TEXT = 32_768;

export function redactEvidence(value: unknown, secrets: string[] = [], key = '', depth = 0): unknown {
  if (SECRET_KEY.test(key)) return '[REDACTED]';
  if (depth > 20) return '[OMITTED: nesting limit]';
  if (typeof value === 'string') {
    let text = value;
    for (const secret of secrets.filter(Boolean).sort((a, b) => b.length - a.length)) text = text.split(secret).join('[REDACTED]');
    text = text.replace(/data:[^\s;,]+;base64,[a-zA-Z0-9+/=\s]+/g, '[OMITTED: base64 data]')
      .replace(/\b(?:Bearer|Basic)\s+[^\s,;"'<>]+/gi, '[REDACTED authorization]')
      .replace(/((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization|cookie|password|secret|signature)\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, '$1[REDACTED]')
      .replace(/https?:\/\/[^\s"'<>]+/gi, raw => {
        try {
          const url = new URL(raw);
          if (url.username || url.password) { url.username = 'REDACTED'; url.password = ''; }
          // Signed URL formats vary. Keep the resource and query names only.
          for (const name of [...url.searchParams.keys()]) url.searchParams.set(name, '[REDACTED]');
          if (url.hash) url.hash = '[REDACTED]';
          return url.toString();
        } catch { return '[REDACTED malformed URL]'; }
      });
    if ((/base64|file_data|inline_data/i.test(key) || text.length > 1024) && /^[A-Za-z0-9+/=\r\n]+$/.test(text)) return `[OMITTED: binary/base64, ${value.length} characters]`;
    return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT)}\n[OMITTED: ${text.length - MAX_TEXT} characters]` : text;
  }
  if (ArrayBuffer.isView(value) || value instanceof ArrayBuffer) return '[OMITTED: binary]';
  if (Array.isArray(value)) return [...value.slice(0, 200).map(item => redactEvidence(item, secrets, '', depth + 1)), ...(value.length > 200 ? [`[OMITTED: ${value.length - 200} items]`] : [])];
  if (value && typeof value === 'object') {
    const entries = Object.entries(value);
    return Object.fromEntries([...entries.slice(0, 300).map(([name, item]) => [name, redactEvidence(item, secrets, name, depth + 1)]), ...(entries.length > 300 ? [['_omitted_fields', entries.length - 300]] : [])]);
  }
  return value ?? null;
}

export interface HttpEvidence {
  id: string; at: string; method: string; url: string; elapsed_ms: number;
  attempt: number; max_attempts: number; retry_policy: string; retry_scheduled: boolean; retry_delay_ms: number | null;
  timeout_ms: number; timeout_stage: string | null;
  request: { headers: Record<string, string>; body: unknown; query?: Record<string, string[]> };
  response: { http_status: number | null; headers: Record<string, string>; body: unknown };
}

export function upstreamEvidence(body: unknown): Array<{ source: string; value: unknown }> {
  const found: Array<{ source: string; value: unknown }> = [];
  function visit(value: unknown, path: string, depth: number): void {
    if (!value || typeof value !== 'object' || depth > 8) return;
    for (const [key, item] of Object.entries(value)) {
      const source = `${path}.${key}`;
      if (/upstream|provider|trace[_-]?id|request[_-]?id|route|retries|retry_count|timeout_stage/i.test(key)) found.push({ source, value: item });
      else visit(item, source, depth + 1);
    }
  }
  visit(body, 'response.body', 0);
  return found;
}

export function localLink(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  return `[${normalized.replace(/([\[\]])/g, '\\$1')}](<${normalized.replace(/%/g, '%25').replace(/#/g, '%23').replace(/\?/g, '%3F').replace(/</g, '%3C').replace(/>/g, '%3E')}>)`;
}
export function jsonBlock(value: unknown): string {
  const json = JSON.stringify(value ?? null, null, 2);
  const fence = '`'.repeat(Math.max(3, ...[...json.matchAll(/`+/g)].map(match => match[0].length + 1)));
  return `${fence}json\n${json}\n${fence}`;
}
