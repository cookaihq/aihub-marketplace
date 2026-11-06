import { closeSync, existsSync, lstatSync, mkdirSync, openSync, readFileSync, readlinkSync, realpathSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, isAbsolute, join, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

const PLUGIN = 'aihub-studio';
const AGENTS = ['codex', 'claude-code', 'workbuddy', 'hermes'];
type Entry = { agent: string; config_dir: string; enabled: boolean };
type Settings = Record<string, unknown> & { default_skill_reminders?: { version: number; agents: Entry[] } };
export interface DefaultsOptions {
  agent: string; action?: string; configDir?: string; globalEnabled?: boolean;
  homeDirectory?: string; env?: NodeJS.ProcessEnv;
}

function canonical(path: string, depth = 0): string {
  if (depth > 40) throw new Error('Too many symbolic links in configuration path.');
  try {
    if (lstatSync(path).isSymbolicLink()) return canonical(resolve(dirname(path), readlinkSync(path)), depth + 1);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
  try { return realpathSync(path); } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    const parent = dirname(path);
    if (parent === path) return path;
    return join(canonical(parent, depth + 1), basename(path));
  }
}
export function readSettings(path: string, contents?: string): Settings {
  let value: unknown;
  try { value = JSON.parse(contents ?? readFileSync(path, 'utf8')); } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return {};
    throw new Error('Cannot read Plugin settings.json; preserve the file and ask the user to repair it.');
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('settings.json must be an object.');
  const settings = value as Settings;
  const preferences = settings.default_skill_reminders;
  if (preferences !== undefined) {
    if (!preferences || preferences.version !== 1 || !Array.isArray(preferences.agents)) throw new Error('Unsupported default_skill_reminders schema; preserve settings.json.');
    const seen = new Set<string>();
    for (const entry of preferences.agents) {
      if (!entry || !AGENTS.includes(entry.agent) || typeof entry.config_dir !== 'string' || !isAbsolute(entry.config_dir) || typeof entry.enabled !== 'boolean') throw new Error('Invalid reminder entry; preserve settings.json.');
      const key = JSON.stringify([entry.agent, entry.config_dir]);
      if (seen.has(key)) throw new Error('Duplicate reminder entries; preserve settings.json.');
      seen.add(key);
    }
  }
  return settings;
}

function savePreference(path: string, agent: string, configDir: string, enabled: boolean): void {
  const target = canonical(path);
  mkdirSync(dirname(target), { recursive: true });
  const lock = `${target}.default-skills.lock`;
  const fd = openSync(lock, 'wx', 0o600);
  const temporary = join(dirname(target), `.default-skills-${randomUUID()}.tmp`);
  try {
    const original = existsSync(target) ? readFileSync(target, 'utf8') : undefined;
    const settings = readSettings(target);
    const preferences = settings.default_skill_reminders ?? { version: 1, agents: [] };
    const entry = preferences.agents.find(item => item.agent === agent && item.config_dir === configDir);
    if (entry) entry.enabled = enabled;
    else preferences.agents.push({ agent, config_dir: configDir, enabled });
    settings.default_skill_reminders = preferences;
    writeFileSync(temporary, `${JSON.stringify(settings, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
    const current = existsSync(target) ? readFileSync(target, 'utf8') : undefined;
    if (current !== original) throw new Error('settings.json changed concurrently; inspect it before retrying.');
    renameSync(temporary, target);
  } finally {
    if (existsSync(temporary)) unlinkSync(temporary);
    closeSync(fd); unlinkSync(lock);
  }
}

export function agentDefaults(options: DefaultsOptions): Record<string, unknown> {
  const { agent, action = 'check', env = process.env, globalEnabled = true } = options;
  if (!AGENTS.includes(agent)) throw new Error('--agent must identify the current host: codex, claude-code, workbuddy or hermes.');
  if (!['check', 'dismiss', 'enable', 'preference'].includes(action)) throw new Error('--action must be check, dismiss or enable.');
  if (!globalEnabled) {
    if (!['check', 'preference'].includes(action)) throw new Error('Cannot save reminder preferences with --no-global-config.');
    return { status: 'skipped', reason: 'global_config_disabled', plugin: PLUGIN, agent };
  }
  const userDirectory = resolve(options.homeDirectory ?? homedir());
  if (agent === 'workbuddy' && !options.configDir && env.WORKBUDDY_CONFIG_DIR && env.CODEBUDDY_CONFIG_DIR && canonical(resolve(env.WORKBUDDY_CONFIG_DIR)) !== canonical(resolve(env.CODEBUDDY_CONFIG_DIR))) {
    throw new Error('WorkBuddy configuration directories disagree; pass the active directory with --config-dir.');
  }
  const defaultDirs: Record<string, string> = { codex: '.codex', 'claude-code': '.claude', workbuddy: '.workbuddy', hermes: '.hermes' };
  const hermesDefault = process.platform === 'win32'
    ? join(env.LOCALAPPDATA?.trim() || join(userDirectory, 'AppData', 'Local'), `hermes${env.HERMES_DATA_DIR_SUFFIX ?? ''}`)
    : join(userDirectory, `.hermes${env.HERMES_DATA_DIR_SUFFIX ?? ''}`);
  const configured = agent === 'codex' ? env.CODEX_HOME : agent === 'claude-code' ? env.CLAUDE_CONFIG_DIR : agent === 'hermes' ? env.HERMES_HOME?.trim() : env.WORKBUDDY_CONFIG_DIR || env.CODEBUDDY_CONFIG_DIR;
  let directory = options.configDir || configured || (agent === 'hermes' ? hermesDefault : join(userDirectory, defaultDirs[agent]!));
  if (agent === 'hermes') {
    directory = directory.replace(/\$([A-Za-z0-9_]+)|\$\{([^}]+)\}/g, (original, plain, braced) => env[plain || braced] ?? original);
    if (process.platform === 'win32') directory = directory.replace(/%([^%]+)%/g, (original, name) => env[name] ?? original);
  }
  const configDir = canonical(resolve(directory.replace(/^~(?=[/\\]|$)/, userDirectory)));
  const settingsFile = join(userDirectory, '.config', PLUGIN, 'settings.json');
  if (!['check', 'preference'].includes(action)) savePreference(settingsFile, agent, configDir, action === 'enable');
  const preferences = readSettings(settingsFile).default_skill_reminders;
  const enabled = preferences?.agents.find(item => item.agent === agent && item.config_dir === configDir)?.enabled ?? true;
  const base = { plugin: PLUGIN, agent, config_dir: configDir, settings_file: settingsFile, reminder_enabled: enabled };
  if (action === 'preference') return base;
  if (!enabled) return { ...base, status: 'dismissed' };
  if (action === 'enable') return { ...base, status: 'enabled', next_step: 'Run check and review the active instructions.' };
  const names = agent === 'codex' ? ['AGENTS.override.md', 'AGENTS.md'] : [agent === 'claude-code' ? 'CLAUDE.md' : agent === 'hermes' ? 'SOUL.md' : 'CODEBUDDY.md'];
  const candidates = names.map(name => join(configDir, name));
  let primary = candidates[candidates.length - 1]!;
  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    if (!statSync(candidate).isFile() || statSync(candidate).size > 1024 * 1024) throw new Error('Agent rule file is not a regular text file within the inspection limit.');
    if (readFileSync(candidate, 'utf8').trim()) { primary = candidate; break; }
  }
  const rule = readFileSync(new URL('../references/default-skills-rule.md', import.meta.url), 'utf8').trim();
  return { ...base, status: 'review_required', global_candidates: candidates, primary_rule: primary,
    primary_real_path: canonical(primary), additional_rules_directory: ['codex', 'hermes'].includes(agent) ? null : join(configDir, 'rules'),
    proposed_rule: rule, session_loaded: 'not_verified',
    next_step: 'Read the active global and project instructions, imports and host overrides. Decide semantic equivalence before offering a default. Never infer missing rules from this report alone.' };
}
