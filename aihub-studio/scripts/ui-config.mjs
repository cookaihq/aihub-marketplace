// Private pipe used only by the local UI; never prints values to Agent-facing commands.
import {resolveConfiguration, MODEL_KEYS, ELEVEN_PREFERENCE_KEYS} from '../dist/config.js';
import {agentDefaults,readSettings} from '../dist/agentDefaults.js';
import {MINIMAX_DEFAULT_VOICE_KEY} from '../dist/speech.js';
import {homedir} from 'node:os';
import {join} from 'node:path';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
try{
  const options=JSON.parse(raw),base={cwd:options.project,useGlobalConfig:options.global_enabled,fileOverrides:options.overrides};
  const shared=resolveConfiguration({...base,skill:options.skill||null});
  const all={shared,models:{},home_directory:homedir()};
  for(const [skill,key] of Object.entries(MODEL_KEYS)) {
    all.models[key]=resolveConfiguration({...base,skill});
    if(skill==='aihub-audio') for(const preference of [MINIMAX_DEFAULT_VOICE_KEY,...ELEVEN_PREFERENCE_KEYS])all.models[preference]=all.models[key];
  }
  if(options.global_enabled){
    all.settings_path=join(homedir(),'.config','aihub-studio','settings.json');
    all.settings=readSettings(all.settings_path,options.overrides?.[all.settings_path]??undefined);
    if(options.agent)all.reminder={config_dir:agentDefaults({agent:options.agent,configDir:options.config_dir||undefined,action:'preference'}).config_dir};
  }
  process.stdout.write(JSON.stringify(all));
}catch{process.stdout.write(JSON.stringify({error:'Configuration cannot be read. Check files and caller identity.'}));process.exitCode=1;}
