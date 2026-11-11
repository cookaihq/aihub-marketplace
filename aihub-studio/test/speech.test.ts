import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { loadConfig, type LoadedConfig } from '../src/config.js';
import { selectionPlan } from '../src/selection.js';
import { speechParameters, MINIMAX_DEFAULT_VOICE_KEY as KEY } from '../src/speech.js';
import { readSettings } from '../src/agentDefaults.js';
import { loadVoiceLibrary, presetVoices } from '../src/voiceLibrary.js';
import { generate } from '../src/workflow.js';
import { startRun, continueRun } from '../src/runs.js';

test('default voice follows audio layers with blank fallback and other caller isolation', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'speech-config-'));
  try {
    const user = join(dir, 'user'), project = join(dir, 'project'); await mkdir(project);
    const folder = join(user, '.config', 'aihub-studio');
    const paths = [join(project, '.env.local.aihub-studio'), join(project, '.env.aihub-studio'), join(project, '.env.local'), join(project, '.env'),
      join(folder, 'aihub-audio', '.env.local'), join(folder, 'aihub-audio', '.env'), join(folder, '.env.local'), join(folder, '.env'), join(user, '.config', 'aihub-audio', '.env')];
    for (const [i, path] of paths.entries()) { await mkdir(join(path, '..'), {recursive:true}); await writeFile(path, `${KEY}=voice-${i}\n`); }
    const options = {skill:'aihub-audio', cwd:project, homeDirectory:user, env:{AIHUB_API_KEY:'fixture'}};
    assert.equal(loadConfig({...options, env:{...options.env,[KEY]:'process-voice'}}).speech?.defaultVoiceId, 'process-voice');
    assert.equal(loadConfig({...options,skill:'aihub-image'}).speech, undefined);
    for (const [i, path] of paths.entries()) {
      assert.deepEqual(loadConfig(options).speech, {defaultVoiceId:`voice-${i}`,source:path});
      await writeFile(path, `${KEY}=" "\n`);
    }
    assert.equal(loadConfig(options).speech, undefined);
    await writeFile(paths[7]!, `${KEY}=global\n`);
    assert.equal(loadConfig({...options,useGlobalConfig:false}).speech, undefined);
    assert.equal(loadConfig({...options,env:{...options.env,[KEY]:'Chinese (Mandarin)_Warm_Girl'}}).speech?.defaultVoiceId,'Chinese (Mandarin)_Warm_Girl');
    for (const value of [' leading','trailing ','x\u0001', 'x'.repeat(513)]) {
      assert.throws(() => loadConfig({...options, env:{...options.env,[KEY]:value}}), /expected_voice_id/);
    }
  } finally { await rm(dir, {recursive:true,force:true}); }
});

const config = (baseUrl='https://fixture.invalid', voice='chosen'): LoadedConfig => ({skill:'aihub-audio',baseUrl,apiKey:'fixture',
  sources:{AIHUB_API_KEY:'fixture'}, modelSelection:{policy:'auto',models:['speech-2.8-hd','speech-2.8-turbo'],sources:{}},
  ...(voice ? {speech:{defaultVoiceId:voice,source:'fixture'}} : {})});
const request = {operation:'audio-tts',original_request:'Read this sentence',prompt:'Read this sentence'};

test('plans freeze the default while preserving explicit voice and other speech settings', () => {
  const requirements = {voice_setting:{speed:1.1,vol:0.8,emotion:'happy'}};
  const plan = selectionPlan(config(), {...request,requirements});
  assert.equal(plan.candidates.length, 2);
  for (const candidate of plan.candidates) assert.deepEqual(candidate.params?.voice_setting, {...requirements.voice_setting,voice_id:'chosen'});
  assert.deepEqual(requirements.voice_setting, {speed:1.1,vol:0.8,emotion:'happy'});
  const explicit = {voice_setting:{voice_id:'custom',speed:0.8}};
  assert.deepEqual(selectionPlan(config(), {...request,requirements:explicit}).candidates[0]?.params?.voice_setting, explicit.voice_setting);
  for (const value of [null, [], '', {voice_id:''}, {voice_id:null}]) {
    const params = {voice_setting:value};
    assert.equal(speechParameters('speech-2.8-hd', params, 'default'), params);
  }
  const params = {prompt:'hello'};
  assert.equal(speechParameters('paraformer-v2', params, 'default'), params);
});

test('direct generation uses the default and continuing frozen or legacy candidates never adds a new one', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'speech-run-'));
  const posts: Array<Record<string, any>> = [];
  const paths: string[] = [];
  const server = createServer(async (req,res) => {
    paths.push(req.url!);
    const json = (data:unknown) => res.end(JSON.stringify(data));
    if (req.url === '/e/v1/models') return json({data:['speech-2.8-hd','speech-2.8-turbo'].map(id=>({id}))});
    if (req.method === 'POST' && req.url === '/e/v1/audios/generations') {
      let raw=''; for await (const chunk of req) raw += chunk;
      const body = JSON.parse(raw); posts.push(body);
      return json({id:body.model,status:'pending',model:body.model});
    }
    if (req.url === '/e/v1/tasks/speech-2.8-hd') return json({id:'speech-2.8-hd',status:'failed',error:{code:'model_unavailable'}});
    res.writeHead(404); json({error:{message:'Unexpected path'}});
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  try {
    const started = await generate(config(base), {media:'audio',model:'speech-2.8-hd',params:{prompt:'Hi',voice_setting:{speed:1.1}},outputDir:dir,waitSeconds:0});
    assert.equal(started.status,'submitted');
    assert.deepEqual(posts[0]?.voice_setting,{speed:1.1,voice_id:'chosen'});
    for (const voice of ['frozen','']) {
      const original = await startRun(config(base,voice), request, dir, 0);
      assert.equal(original.status,'submitted');
      const saved = await readFile(original.run_record as string,'utf8');
      await continueRun(config(base,'changed-later'), original.run_record as string, 0);
      assert.equal(posts.at(-1)?.model,'speech-2.8-turbo');
      assert.deepEqual(posts.at(-1)?.voice_setting, voice ? {voice_id:voice} : undefined);
      assert(!saved.includes('changed-later'));
    }
    assert(!paths.some(path=>path.startsWith('/v1/')||path.includes('/e/e/')));
  } finally { server.closeAllConnections(); await new Promise<void>(r=>server.close(()=>r())); await rm(dir,{recursive:true,force:true}); }
});

test('favorites preserve other settings and reject malformed preference data', () => {
  const settings = {other:{keep:true},default_skill_reminders:{version:1,agents:[]},audio:{unrelated:42,minimax_speech:{favorite_voice_ids:['custom','builtin']}}};
  assert.deepEqual(readSettings('unused',JSON.stringify(settings)),settings);
  for (const value of [null, 'voice', ['same','same'], [' leading'], ['x'.repeat(513)], Array.from({length:2001},(_,i)=>`voice-${i}`)]) {
    assert.throws(()=>readSettings('unused',JSON.stringify({audio:{minimax_speech:{favorite_voice_ids:value}}})));
  }
});

test('voice library uses the audio credential chain and returns documented fields only', async t => {
  const dir = await mkdtemp(join(tmpdir(),'speech-library-'));
  const sample = {id:'internal-id',voice_id:'Chinese (Mandarin)_Warm_Girl',voice_name:'Voice',tag_list:null,sample_audio:'https://filecdn.minimax.chat/public/example.mp3',secret:'must-not-leave'};
  let calls=0;
  t.mock.method(globalThis,'fetch',async (url: Parameters<typeof fetch>[0], opts?: RequestInit) => {
    calls++; assert.equal(String(url),'https://api.aihubmax.com/e/v1/configs/minimax-preset-voice-id?language=zh');
    assert.equal((opts?.headers as Record<string,string>).Authorization,'Bearer audio-credential');
    return new Response(JSON.stringify([sample]));
  });
  try {
    const path = join(dir,'.config','aihub-studio','aihub-audio'); await mkdir(path,{recursive:true});
    await writeFile(join(path,'.env'),'AIHUB_API_KEY=audio-credential');
    const voices = await loadVoiceLibrary({cwd:join(dir,'project'),homeDirectory:dir,env:{}});
    assert.equal(voices[0]?.voice_id,'Chinese (Mandarin)_Warm_Girl');
    assert.deepEqual(voices[0]?.tag_list,[]); assert(!JSON.stringify(voices).includes('internal-id')); assert(!JSON.stringify(voices).includes('must-not-leave'));
    await assert.rejects(loadVoiceLibrary({cwd:dir,homeDirectory:dir,useGlobalConfig:false,env:{}}),/missing_key/);
    assert.equal(calls,1);
    assert.throws(()=>presetVoices([{id:'internal-only'}]),/voice_id/);
  } finally { await rm(dir,{recursive:true,force:true}); }
});
