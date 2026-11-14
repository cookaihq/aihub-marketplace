// Offline-only Design/Create service for native CLI and host acceptance.
// Start with Node; stdout prints the loopback origin. Inspect GET /__audit.
import { createServer } from 'node:http';
import { once } from 'node:events';
import { pathToFileURL } from 'node:url';

const DESIGN = 'elevenlabs-voice-design', CREATE = 'elevenlabs-voice-create';
const text = '这是离线验收使用的合成试听材料，不代表真实音色创建或生产接口成功。'.repeat(4);
function tone(frequency) {
  const rate = 16000, samples = rate, wav = Buffer.alloc(44 + samples * 2);
  wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) wav.writeInt16LE(Math.round(Math.sin(2 * Math.PI * frequency * i / rate) * 4000 * Math.min(i / 800, (samples - i) / 800, 1)), 44 + i * 2);
  return wav;
}
export async function voiceService() {
  const audit = [], tasks = new Map();
  let mode = 'success', count = 0, origin;
  const server = createServer(async (req, res) => {
    const send = (status, value) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    try {
      if (req.method === 'GET' && req.url === '/__audit') return send(200, audit);
      if (req.method === 'POST' && req.url === '/__mode') {
        let raw = ''; for await (const chunk of req) raw += chunk;
        const input = JSON.parse(raw);
        if (!['success', 'capacity', 'missing-id'].includes(input.create)) return send(400, { error: 'Unknown fixture mode' });
        mode = input.create; return send(200, { mode });
      }
      if (/^\/audio\/[ABC]\.wav$/.test(req.url) && req.method === 'GET') {
        const wav = tone({ A: 330, B: 440, C: 550 }[req.url[7]]);
        audit.push({ method: 'GET', path: req.url });
        res.writeHead(200, { 'Content-Type': 'audio/wav', 'Content-Length': wav.length }); return res.end(wav);
      }
      if (req.headers.authorization !== 'Bearer synthetic-voice-acceptance') return send(401, { error: 'Synthetic fixture key required' });
      if (req.method === 'GET' && req.url === '/v1/models') return send(200, { data: [DESIGN, CREATE].map(id => ({ id, object: 'model' })) });
      if (req.method === 'GET' && req.url.startsWith('/e/v1/tasks/')) {
        const id = decodeURIComponent(req.url.slice('/e/v1/tasks/'.length));
        audit.push({ method: 'GET', path: req.url });
        return send(tasks.has(id) ? 200 : 404, tasks.get(id) ?? { error: 'Unknown fixture task' });
      }
      if (req.method === 'POST' && req.url === '/e/v1/audios/generations') {
        let raw = ''; for await (const chunk of req) raw += chunk;
        const body = JSON.parse(raw); audit.push({ method: 'POST', path: req.url, body });
        const id = `fixture-${++count}`;
        let task;
        if (body.model === DESIGN) task = { id, model: DESIGN, status: 'completed',
          results: [{ text, previews: ['A', 'B', 'C'].map((candidate, i) => ({ generated_voice_id: `${id}-candidate-${candidate}`,
            url: `${origin}/audio/${candidate}.wav`, media_type: 'audio/wav', duration_secs: 1, language: null, seed: i })), extra: { synthetic: true } }],
          usage: { quantity: [...text].length, unit: 'character', fixture_only: true } };
        else if (body.model === CREATE) {
          const design = [...tasks.values()].find(t => t.model === DESIGN && t.results[0].previews.some(p => p.generated_voice_id === body.generated_voice_id));
          if (!design) return send(400, { error: 'Candidate must belong to a fixture Design' });
          task = mode === 'capacity' ? { id, model: CREATE, status: 'failed', error: { code: 'upstream_error', message: 'Synthetic capacity failure: 30/30' }, usage: { cost: 0, fixture_only: true } }
            : { id, model: CREATE, status: 'completed', results: [{ ...(mode === 'success' ? { voice_id: 'fixture-saved-voice-B' } : {}), name: body.voice_name,
              description: body.voice_description, category: 'generated', labels: body.labels ?? {}, samples: null, sharing: null,
              settings: { stability: 0 }, synthetic: true }], usage: { cost: 0, fixture_only: true } };
        } else return send(400, { error: 'Only synthetic Voice Design/Create supported' });
        tasks.set(id, task); return send(200, task);
      }
      send(404, { error: 'Unsupported fixture route' });
    } catch (error) { send(500, { error: String(error) }); }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  origin = `http://127.0.0.1:${server.address().port}`;
  return { server, origin };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const service = await voiceService();
  console.log(JSON.stringify({ origin: service.origin, synthetic: true }));
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { service.server.closeAllConnections(); service.server.close(); });
}
