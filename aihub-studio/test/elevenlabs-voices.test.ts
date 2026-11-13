import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadConfig, resolveConfiguration } from '../src/config.js';
import { selectionPlan } from '../src/selection.js';
import { elevenPresetVoices, loadVoiceLibrary } from '../src/voiceLibrary.js';
import { AihubmaxClient } from '../src/apiClient.js';

test('ElevenLabs voice and favorites use audio layers, support explicit empty favorites and keep selection separate from dialogue', async () => {
  const dir=await mkdtemp(join(tmpdir(),'aihub-eleven-voices-')), project=join(dir,'project'), home=join(dir,'home');
  await mkdir(project);await mkdir(join(home,'.config','aihub-studio'),{recursive:true});
  const global=join(home,'.config','aihub-studio','.env'), local=join(project,'.env.local.aihub-studio');
  await writeFile(global,'AIHUB_API_KEY=fixture\nAIHUB_ELEVENLABS_DEFAULT_VOICE_ID=global-voice\nAIHUB_ELEVENLABS_FAVORITE_VOICE_IDS=["global-voice"]\n');
  await writeFile(local,'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID=project-voice\nAIHUB_ELEVENLABS_FAVORITE_VOICE_IDS=[]\n');
  const options={cwd:project,homeDirectory:home,env:{},skill:'aihub-audio'};
  try {
    const cfg=loadConfig(options);
    assert.equal(cfg.elevenlabs?.defaultVoiceId,'project-voice');assert.deepEqual(cfg.elevenlabs?.favoriteVoiceIds,[]);
    assert.equal(cfg.elevenlabs?.sources.AIHUB_ELEVENLABS_DEFAULT_VOICE_ID,local);assert.equal(cfg.elevenlabs?.cloneModel,undefined);
    const request={operation:'audio-tts',original_request:'Read aloud',prompt:'Hello'};
    const speech=selectionPlan(cfg,request).candidates[0]!;
    assert.equal(speech.model,'eleven-v4-text-to-speech');assert.deepEqual(speech.params,{text:'Hello',voice_id:'project-voice'});
    assert.equal(selectionPlan(cfg,{...request,requirements:{voice_id:'explicit'}}).candidates[0]?.params?.voice_id,'explicit');
    assert.match(selectionPlan(cfg,{...request,requirements:{voice_id:''}}).candidates[0]?.rejection??'',/voice_id/);
    const inputs=[{text:'One',voice_id:'A'},{text:'Two',voice_id:'B'}];
    assert.deepEqual(selectionPlan(cfg,{operation:'audio-dialogue',original_request:'A dialogue',requirements:{inputs}}).candidates[0]?.params,{inputs});
    assert.throws(()=>selectionPlan(cfg,{operation:'audio-clone',original_request:'Clone'}),/placeholder.*No cloning request/);
    assert.equal(loadConfig({...options,skill:'aihub-image'}).elevenlabs,undefined);
    const isolated=loadConfig({...options,useGlobalConfig:false,env:{AIHUB_API_KEY:'fixture'}});
    assert.equal(isolated.elevenlabs?.defaultVoiceId,'project-voice');
    await writeFile(local,'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID=\n');
    assert.equal(loadConfig(options).elevenlabs?.defaultVoiceId,'global-voice');
    assert.deepEqual(loadConfig(options).elevenlabs?.favoriteVoiceIds,['global-voice']);
    for (const value of ['{}','["a","a"]','[""]','bad']) {
      await writeFile(local,'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS='+value+'\n');
      assert.throws(()=>loadConfig(options),/expected_json_array/);
    }
    assert.throws(()=>resolveConfiguration({...options,skill:'aihub-document'}),/valid caller/);
  } finally {await rm(dir,{recursive:true,force:true});}
});

test('ElevenLabs directory keeps stable IDs, multilingual filters, categories and original preview metadata', async () => {
  const raw=[{voice_id:'v1',name:'Narrator',languages:['en','zh'],category:['narration'],preview_url:'https://storage.googleapis.com/sample.mp3',description:'Warm'}];
  const rows=elevenPresetVoices(raw);
  assert.deepEqual(rows[0]?.languages,['en','zh']);assert.deepEqual(rows[0]?.tag_list,['narration']);assert.equal(rows[0]?.voice_name,'Narrator');
  assert.equal(rows[0]?.sample_audio,raw[0]!.preview_url);
  const request=AihubmaxClient.prototype.request;
  const routes:string[]=[];
  AihubmaxClient.prototype.request=async function<T>(_method:string,path:string):Promise<T>{routes.push(path);return raw as T;};
  try {
    const result=await loadVoiceLibrary({cwd:process.cwd(),useGlobalConfig:false,env:{AIHUB_API_KEY:'fixture'}},'elevenlabs');
    assert.deepEqual(result,rows);assert.deepEqual(routes,['/e/v1/configs/elevenlabs-preset-voice-id']);
  } finally {AihubmaxClient.prototype.request=request;}
});

test('ElevenLabs full preset directory supports the observed 15450 entries without truncation', () => {
  const rows = Array.from({length:15450}, (_, index) => ({voice_id:'voice-' + index, name:'Preset ' + index, languages:['zh','en'], category:['high_quality']}));
  const voices = elevenPresetVoices(rows);
  assert.equal(voices.length, rows.length);
  assert.equal(voices.at(-1)?.voice_id, 'voice-15449');
});
