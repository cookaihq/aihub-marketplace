import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import type { AddressInfo } from 'node:net';
const exec = promisify(execFile);
async function fixture(large = false) {
  const dir = await mkdtemp(join(tmpdir(), 'aihub-audio-run-'));
  const source = join(dir, '录音.wav');
  await exec('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', `sine=frequency=440:sample_rate=48000:duration=${large ? 120 : 1}`, '-ac', '2', source]);
  const state = { uploads: 0, posts: [] as string[], queryFail: false, downloadFail: false, uploadFail: false, submitUnknown: false,
    terminal: false, terminalAt: 0, inline: false, visible: ['paraformer-v2','paraformer-8k-v2'], uploadSizes: [] as number[] };
  let base = '';
  const terminal = (id:string, model:string) => (state.terminal && model === 'paraformer-v2') || Number(id) === state.terminalAt;
  const task = (id: string, model: string, completed: boolean) => ({ id, model, status: terminal(id,model) ? 'failed' : completed ? 'completed' : 'pending',
    ...(terminal(id,model) ? { error: { code: 'model_unavailable' } } : {}),
    results: state.inline ? [{ transcripts: [{ text: '第一句。第二句。', sentences: [{ text: '第一句。', begin_time: 0, end_time: 200 }, { text: '第二句。', begin_time: 300, end_time: 800 }] }] }] : [{ transcription_url: `${base}/result/${id}` }] });
  const server = createServer(async (req,res) => {
    const json = (value: unknown, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    if (req.url === '/v1/models') return json({ data: state.visible.map(id => ({ id })) });
    if (req.method === 'POST') {
      let raw = ''; for await (const chunk of req) raw += chunk; const body = JSON.parse(raw);
      if (req.url === '/v1/files/upload/base64') {
        state.uploads++; const bytes = Buffer.from(body.file_data, 'base64'); state.uploadSizes.push(bytes.length);
        assert.equal(body.auto_cleanup, false);
        if (state.uploadFail) return json({ error: { code: 'uncertain' } }, 503);
        return json({ id: `file-${state.uploads}`, size: bytes.length, filename: body.file_name, url: `${base}/uploaded/${state.uploads}`, created: 0 });
      }
      state.posts.push(body.model);
      if (state.submitUnknown) return json({ error: { code: 'uncertain' } }, 503);
      return json(task(String(state.posts.length), body.model, state.inline || state.terminal));
    }
    if (req.url?.startsWith('/v1/tasks/')) {
      if (state.queryFail) return json({ error: { code: 'denied' } }, 403);
      const id = req.url.split('/').at(-1)!; return json(task(id, state.posts[Number(id)-1]!, true));
    }
    if (req.url?.startsWith('/result/')) {
      if (state.downloadFail) return json({ error: 'missing' }, 404);
      return json({ transcripts: [{ channel_id: 0, text: `片段${req.url.split('/').at(-1)}全文。后一句。`, sentences: [
        { text: `片段${req.url.split('/').at(-1)}全文。`, begin_time: 0, end_time: 200, speaker_id: 0 }, { text: '后一句。', begin_time: 300, end_time: 800, speaker_id: 0 }] }] });
    }
    res.writeHead(404); res.end();
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening'); base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const request = join(dir,'request.json');
  await writeFile(request, JSON.stringify({ operation:'audio-transcribe', original_request:'完整转写录音，保留时间戳与说话人', inputs:{ audios:[source] } }));
  const call = async (...args: string[]) => {
    const entry = process.platform === 'win32' ? 'powershell.exe' : process.execPath;
    const command = process.platform === 'win32' ? ['-NoProfile','-NonInteractive','-File',resolve('scripts/aihub.ps1')] : [resolve('scripts/aihub.mjs')];
    let stdout: string;
    try { ({ stdout } = await exec(entry, [...command,...args,'--skill','aihub-audio','--no-global-config'], { cwd:dir, timeout:90_000, windowsHide:true,
      env: { ...process.env, AIHUB_API_KEY:'synthetic-audio-key', AIHUB_BASE_URL:base, AIHUB_AUDIO_MODELS:'paraformer-v2,paraformer-8k-v2', AIHUB_MODEL_FALLBACK_POLICY:'auto', AIHUB_MODEL_MAX_ATTEMPTS:'', AIHUB_RESULT_CHECK_ENABLED:'1', AIHUB_RESULT_CHECK_PROVIDER:'host' } })); }
    catch(error) { stdout = (error as {stdout:string}).stdout; }
    assert.ok(!stdout.includes('synthetic-audio-key')); return JSON.parse(stdout);
  };
  return { dir, source, state, call, start:()=>call('run','--request-file',request,'--output-dir',dir),
    close:async()=>{ server.closeAllConnections(); await new Promise<void>(r=>server.close(()=>r())); await rm(dir,{recursive:true,force:true}); } };
}

test('native packaged entry splits over 20 MiB, resumes query/download failures once, and delivers full structured text', async () => {
  const f = await fixture(true);
  try {
    const start = await f.start(); assert.equal(start.status,'submitted', JSON.stringify(start)); assert.equal(f.state.posts.length,1);
    assert.ok(start.result.fragments.length > 1); assert.ok(start.result.fragments.every((p: any)=>p.bytes <= 20*1024**2*0.9));
    const more = ()=>f.call('continue','--record',start.run_record,'--wait-seconds','0');
    f.state.queryFail = true; assert.equal((await more()).status,'query_failed'); assert.equal(f.state.posts.length,1);
    f.state.queryFail = false; f.state.downloadFail = true; assert.equal((await more()).status,'download_failed'); assert.equal(f.state.posts.length,1);
    f.state.downloadFail = false;
    let done = await more(); for(let i=0;i<8&&done.status!=='delivered';i++) done = await more();
    assert.equal(done.status,'delivered'); assert.equal(f.state.posts.length,start.result.fragments.length); assert.equal(f.state.uploads,f.state.posts.length);
    const merged = JSON.parse(await readFile(done.files.find((file:any)=>file.mime_type==='application/json').path,'utf8'));
    assert.ok(merged.text.includes('片段1全文。\n后一句。')); assert.ok(merged.text.includes('片段2全文。\n后一句。'));
    assert.ok(merged.segments[2].start > 80); assert.notEqual(merged.segments[0].speaker,merged.segments[2].speaker);
    assert.ok(done.result_check.sources[0].path); assert.equal(done.result_check.sources[0].measurements.duration_seconds,120);
    const review = done.result_check;
    const assets = [...review.artifacts, ...review.sources];
    const report = join(f.dir,'partial-review.json');
    await writeFile(report, JSON.stringify({ findings: review.requirements.map((r:any) => ({requirement_id:r.id,verdict:'matched',
      evidence:assets.map((a:any)=>({asset_id:a.id,observation:'Synthetic fixture check',location:'first second only'}))})),
      coverage:assets.map((a:any)=>({asset_id:a.id,complete:true,note:'Claimed full, but only one second observed',
        ...(a.type==='audio_url'?{time_ranges:[[0,1]],audio_checked:true}:{})})) }));
    const checked = await f.call('review-submit','--record',start.run_record,'--review-token',review.review_token,'--review-file',report);
    assert.equal(checked.status,'inconclusive');
    const again = await more(); assert.equal(again.status,'delivered'); assert.equal(f.state.posts.length,2);
  } finally { await f.close(); }
});

test('upload/submission uncertainty persists across native CLI processes without replacement requests', async () => {
  for (const phase of ['upload','submit']) {
    const f = await fixture();
    try {
      f.state.uploadFail = phase==='upload'; f.state.submitUnknown = phase==='submit';
      const first = await f.start(); assert.equal(first.status,phase==='upload'?'upload_unknown':'submission_unknown');
      f.state.uploadFail=false; f.state.submitUnknown=false;
      const next = await f.call('continue','--record',first.run_record,'--wait-seconds','0');
      assert.equal(next.status,first.status); assert.equal(f.state.uploads,1); assert.equal(f.state.posts.length,phase==='upload'?0:1);
    } finally { await f.close(); }
  }
});

test('whole small audio stays one file; permitted fallback rechecks 8 kHz constraints and inline JSON remains resumable', async () => {
  const f = await fixture();
  try {
    f.state.inline = true; f.state.terminal = true;
    const done = await f.start(); assert.equal(done.status,'delivered'); assert.deepEqual(f.state.posts,['paraformer-v2','paraformer-8k-v2']);
    const run = JSON.parse(await readFile(done.run_record,'utf8'));
    const first = JSON.parse(await readFile(run.attempts[0].audio_record,'utf8'));
    const second = JSON.parse(await readFile(run.attempts[1].audio_record,'utf8'));
    assert.equal(first.parts.length,1); assert.equal(first.parts[0].boundary,'whole'); assert.equal(first.parts[0].sample_rate,48000);
    assert.equal(second.parts.length,1); assert.equal(second.parts[0].sample_rate,8000);
    assert.equal(done.result.text,'第一句。\n第二句。');
    await f.call('resume','--record',second.parts[0].task_record,'--wait-seconds','0');
    assert.equal(f.state.posts.length,2);
  } finally { await f.close(); }
});

test('a terminal failure after partial success preserves completed parts without model fallback or resubmission', async () => {
  const f = await fixture();
  try {
    f.state.inline = true; f.state.terminalAt = 2;
    await writeFile(join(f.dir,'request.json'), JSON.stringify({operation:'audio-transcribe',original_request:'转写两个录音',inputs:{audios:[f.source,f.source]}}));
    let first = await f.start();
    for (let i=0;i<4 && first.status!=='failed';i++) first = await f.call('continue','--record',first.run_record);
    assert.equal(first.status,'failed'); assert.equal(first.result.status,'transcription_failed');
    assert.deepEqual(f.state.posts,['paraformer-v2','paraformer-v2']);
    assert.equal(first.result.fragments[0].status,'delivered');
    assert.equal(first.result.fragments[1].status,'remote_failed');
    assert.ok(first.files.length > 0);
    const next = await f.call('continue','--record',first.run_record);
    assert.equal(next.status,'failed'); assert.equal(f.state.posts.length,2);
  } finally { await f.close(); }
});
