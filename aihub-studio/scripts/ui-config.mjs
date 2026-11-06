// Private pipe used only by the local UI; never prints values to Agent-facing commands.
import {resolveConfiguration, MODEL_KEYS} from '../dist/config.js';
import {agentDefaults,readSettings} from '../dist/agentDefaults.js';
import {homedir} from 'node:os';
import {join} from 'node:path';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
try{
  const options=JSON.parse(raw),base={cwd:options.project,useGlobalConfig:options.global_enabled,fileOverrides:options.overrides};
  const shared=resolveConfiguration({...base,skill:options.skill||null});
  const all={shared,models:{}};
  for(const [skill,key] of Object.entries(MODEL_KEYS))all.models[key]=resolveConfiguration({...base,skill});
  if(options.global_enabled){
    all.settings_path=join(homedir(),'.config','aihub-studio','settings.json');
    all.settings=readSettings(all.settings_path,options.overrides?.[all.settings_path]??undefined);
    if(options.agent)all.reminder=agentDefaults({agent:options.agent,configDir:options.config_dir||undefined,action:'preference'});
  }
  process.stdout.write(JSON.stringify(all));
}catch{process.stdout.write(JSON.stringify({error:'Configuration cannot be read. Check files and caller identity.'}));process.exitCode=1;}
