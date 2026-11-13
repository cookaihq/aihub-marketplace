import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import type { AddressInfo } from 'node:net';
import { selectionPlan } from '../src/selection.js';
import { validateGeneration, describe } from '../src/models.js';
import { sunoParameters } from '../src/suno.js';
import type { LoadedConfig } from '../src/config.js';
import { fixtureTransport } from './fixture-transport.js';

const cfg = (models?: string[]): LoadedConfig => ({skill:'aihub-music', apiKey:'fixture', baseUrl:'https://example.invalid',
  sources:{AIHUB_API_KEY:'fixture'}, modelSelection:{models, policy:'auto', sources:{}}});
const request = {operation:'music-description', original_request:'写一首歌曲', prompt:'温暖的中文民谣'};

test('three Suno scenes map exact text and fixed intent without rewriting lyrics or injecting controls', () => {
  const cases = [
    ['music-description', {mode:'description', is_instrumental:false, prompt:request.prompt}],
    ['music-lyrics', {mode:'custom', is_instrumental:false, lyrics:request.prompt}],
    ['music-instrumental', {mode:'custom', is_instrumental:true, style:request.prompt}],
  ] as const;
  for (const [operation, expected] of cases) {
    const plan = selectionPlan(cfg(), {...request, operation});
    assert.equal(plan.source, 'built-in'); assert.equal(plan.candidates[0]?.model, 'suno-v6');
    assert.deepEqual(plan.candidates[0]?.params, expected); assert.equal(plan.candidates[0]?.rejection, undefined);
  }
  const lyrics = '[Verse]\n逐字保留 👋';
  const plan = selectionPlan(cfg(), {...request, operation:'music-lyrics', prompt:lyrics,
    requirements:{rewrite_lyrics:false, max_mode:false, style_weight:0, weirdness_constraint:0, vocal_gender:'Female'}});
  assert.deepEqual(plan.candidates[0]?.params, {mode:'custom',is_instrumental:false,lyrics,rewrite_lyrics:false,
    max_mode:false,style_weight:0,weirdness_constraint:0,vocal_gender:'f'});
  assert.equal(plan.request.requirements?.vocal_gender, 'Female');
  assert.deepEqual(describe('suno-v6').required_params, ['model']);
});

test('Suno contract validates forbidden presence, numeric bounds and Mini limitations without discarding options', () => {
  const validate = (params: Record<string, unknown>, model='suno-v6') => validateGeneration('audio', model, params);
  for (const key of ['lyrics', 'rewrite_lyrics', 'max_mode']) {
    for (const value of [null,false,0]) assert.throws(() => validate({prompt:'song',[key]:value}), new RegExp(key));
  }
  for (const key of ['duration','title','style','vocal_gender','style_weight']) {
    for (const value of [null,'',0]) assert.throws(() => validate({prompt:'song',[key]:value},'suno-v6-mini'), /Mini description/);
  }
  for (const value of [null,9,361,10.1,'30',Infinity]) assert.throws(() => validate({prompt:'song',duration:value}), /duration/);
  for (const key of ['style_weight','weirdness_constraint']) {
    for (const value of [null,-0.1,1.1,NaN,Infinity,'0']) assert.throws(() => validate({prompt:'song',[key]:value}), new RegExp(key));
  }
  for (const key of ['lyrics','rewrite_lyrics','vocal_gender']) assert.throws(() => validate({mode:'custom',is_instrumental:true,style:'piano',[key]:false}), new RegExp(key));
  assert.throws(() => validate({mode:'custom',lyrics:'  '}), /lyrics/);
  assert.throws(() => validate({mode:'custom',is_instrumental:true,style:'  '}), /style/);
  assert.throws(() => validate({prompt:'x'.repeat(3001)}), /prompt/);
  assert.throws(() => validate({prompt:'song',unknown:0}), /unknown/);
  assert.equal(validate({prompt:'song',duration:10,style_weight:0,output_format:'wav'}), '/e/v1/audios/generations');
  assert.deepEqual(sunoParameters('suno-v6', {mode:'custom',lyrics:'song',vocal_gender:'Male'}), {mode:'custom',lyrics:'song',vocal_gender:'m'});
  const personal = ['suno-v6-mini','suno-v6-wild'];
  const plan = selectionPlan(cfg(personal), {...request,requirements:{duration:30}});
  assert.equal(plan.source, 'configuration'); assert.match(plan.candidates[0]?.rejection ?? '', /duration/);
  assert.equal(plan.candidates[1]?.params?.duration, 30); assert.deepEqual(personal, ['suno-v6-mini','suno-v6-wild']);
  for (const extra of [{inputs:{audios:['https://example.invalid/reference.wav']}}, {requirements:{is_instrumental:true}}]) {
    assert.ok(selectionPlan(cfg(), {...request,...extra}).candidates[0]?.rejection);
  }
});

test('packaged Suno delivery keeps two independent tracks, downloads each alias once and resumes without submitting', async () => {
  const exec = promisify(execFile), dir = await mkdtemp(join(tmpdir(),'aihub-suno-'));
  const wav = join(dir,'fixture.wav');
  await exec('ffmpeg',['-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.1','-y',wav]);
  const bytes = await readFile(wav), posts: Record<string, unknown>[] = [], gets: string[] = [];
  let base = '', count = 2;
  const task = () => ({id:'suno-task',status:'completed',model:'suno-v6',usage:{tracks:count},results:Array.from({length:count},(_,i)=>({
    id:'track-'+i,title:'Song '+i,lyrics:'Verse '+i,audio_url:base+'/track-'+i+'.wav',url:base+'/alias-'+i+'.wav'}))});
  const server = createServer(async(req,res) => {
    const json = (value:unknown) => {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));};
    if (req.url === '/v1/models') return json({data:[{id:'suno-v6'}]});
    if (req.method === 'POST' && req.url === '/e/v1/audios/generations') {
      let raw='';for await(const chunk of req)raw+=chunk;posts.push(JSON.parse(raw));return json(task());
    }
    if (req.url === '/e/v1/tasks/suno-task') return json(task());
    if (req.url?.startsWith('/track-') || req.url?.startsWith('/alias-')) {gets.push(req.url);res.setHeader('Content-Type','audio/wav');return res.end(bytes);}
    res.writeHead(404);res.end();
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');base=`http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const call = async (...args:string[]) => JSON.parse((await exec(process.execPath,[resolve('scripts/aihub.mjs'),...args,'--skill','aihub-music','--no-global-config'],{
    cwd:dir,timeout:30_000,env:{...process.env,...fixtureTransport(base),AIHUB_API_KEY:'fixture',AIHUB_MUSIC_MODELS:'',AIHUB_RESULT_CHECK_ENABLED:'0'}})).stdout);
  try {
    const path=join(dir,'request.json');await writeFile(path,JSON.stringify({...request,operation:'music-lyrics',prompt:'[Verse]\nHello',requirements:{vocal_gender:'Female',rewrite_lyrics:false,max_mode:false,style_weight:0}}));
    const done=await call('run','--request-file',path,'--output-dir',dir);
    assert.equal(done.status,'delivered');assert.equal(done.files.length,2);assert.equal(done.result.tracks.length,2);
    assert.deepEqual(gets,['/track-0.wav','/track-1.wav']);
    assert.deepEqual(posts[0],{model:'suno-v6',mode:'custom',is_instrumental:false,lyrics:'[Verse]\nHello',vocal_gender:'f',rewrite_lyrics:false,max_mode:false,style_weight:0});
    assert.equal((await call('continue','--record',done.run_record)).status,'delivered');assert.equal(posts.length,1);assert.equal(gets.length,2);
    count=1;
    const single=await call('run','--request-file',path,'--output-dir',dir);
    assert.equal(single.files.length,1);assert.equal(single.result.tracks.length,1);assert.equal(posts.length,2);
  } finally {server.closeAllConnections();server.close();await rm(dir,{recursive:true,force:true});}
});
