import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadConfig, resolveConfiguration } from '../src/config.js';

test('directory settings select new business roots without falling back to the old roots', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-directories-'));
  const home = join(root, 'user'), project = join(root, 'project');
  const global = join(root, '配置 global'), local = join(root, '配置 project');
  const anchor = join(home, '.config/aihub-studio');
  const ordinary = join(home, '.config/aihub-image');
  for (const dir of [anchor, ordinary, project, global, local]) await mkdir(dir, { recursive: true });
  try {
    await writeFile(join(anchor, '.env'), `AIHUB_GLOBAL_CONFIG_DIR="${global}"\nAIHUB_API_KEY=old-global\n`);
    await writeFile(join(project, '.env.local.aihub-studio'), `AIHUB_PROJECT_CONFIG_DIR="${local}"\nAIHUB_API_KEY=old-project\n`);
    await writeFile(join(ordinary, '.env'), 'AIHUB_API_KEY=ordinary\n');
    const options = { skill: 'aihub-image', cwd: project, homeDirectory: home, env: {} };
    assert.throws(() => loadConfig(options), /Missing AIHUB_API_KEY/);
    await writeFile(join(global, '.env'), 'AIHUB_API_KEY=new-global\n');
    assert.equal(loadConfig(options).apiKey, 'new-global');
    await writeFile(join(local, '.env.aihub-studio'), 'AIHUB_API_KEY=new-project\n');
    assert.equal(loadConfig(options).apiKey, 'new-project');
    assert.equal(loadConfig(options).sources.AIHUB_API_KEY, join(local, '.env.aihub-studio'));
    assert.equal(resolveConfiguration(options).inspection.cwd, project);
    assert.equal(loadConfig({ ...options, useGlobalConfig: false }).apiKey, 'new-project');
    assert.equal(loadConfig({ ...options, env: { AIHUB_API_KEY: 'process' } }).apiKey, 'process');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('selectors use fixed anchors, preserve environment priority and report invalid or unreadable roots', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-directory-errors-'));
  const home = join(root, 'user'), project = join(root, 'project'), selected = join(root, 'selected');
  const anchor = join(home, '.config/aihub-studio');
  await mkdir(project, { recursive: true });await mkdir(anchor, { recursive: true });await mkdir(selected);
  const options = {skill:'aihub-image',cwd:project,homeDirectory:home,env:{}};
  try {
    await writeFile(join(anchor,'.env'), 'AIHUB_GLOBAL_CONFIG_DIR=relative\nAIHUB_API_KEY=old\n');
    assert.ok(resolveConfiguration(options).inspection.problems.some(p=>p.reason==='expected_absolute_config_directory'));
    assert.throws(()=>loadConfig(options));
    await writeFile(join(selected,'.env'), 'AIHUB_API_KEY=selected\nAIHUB_GLOBAL_CONFIG_DIR=/ignored-recursive-key\n');
    await writeFile(join(anchor,'.env'), `AIHUB_GLOBAL_CONFIG_DIR="${selected}"\n`);
    assert.equal(loadConfig(options).apiKey,'selected');
    assert.equal(resolveConfiguration(options).directories.global,selected);
    const skillRoot=join(selected,'aihub-image');await mkdir(skillRoot);
    await writeFile(join(skillRoot,'.env.local'),'AIHUB_API_KEY=skill-selected\n');
    assert.equal(loadConfig(options).apiKey,'skill-selected');
    const processRoot=join(root,'process');await mkdir(processRoot);await writeFile(join(processRoot,'.env'),'AIHUB_API_KEY=process-root\n');
    assert.equal(loadConfig({...options,env:{AIHUB_GLOBAL_CONFIG_DIR:processRoot}}).apiKey,'process-root');
    const disabled=resolveConfiguration({...options,useGlobalConfig:false,env:{AIHUB_GLOBAL_CONFIG_DIR:processRoot}});
    assert.ok(!disabled.inspection.layers.some(l=>l.path.startsWith(anchor)||l.path.startsWith(selected)||l.path.startsWith(processRoot)));
    await rm(join(anchor,'.env'));await mkdir(join(anchor,'.env'));
    assert.ok(resolveConfiguration(options).inspection.problems.some(p=>p.reason==='unreadable'));
    assert.throws(()=>loadConfig(options),/Cannot read/);
    assert.ok(!resolveConfiguration({...options,useGlobalConfig:false}).inspection.problems.some(p=>p.reason==='unreadable'));
  } finally {await rm(root,{recursive:true,force:true});}
});
