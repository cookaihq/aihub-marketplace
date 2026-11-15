// Private UI pipe: configuration values and remote error bodies never reach the browser.
import {loadVoiceLibrary, voiceLibraryIdentity} from '../dist/voiceLibrary.js';
import {ApiError} from '../dist/apiClient.js';
import {resolveConfiguration} from '../dist/config.js';
import {homedir} from 'node:os';
let input = '';
for await (const chunk of process.stdin) input += chunk;
try {
  const options = JSON.parse(input);
  if (options.provider !== undefined && !['minimax', 'elevenlabs'].includes(options.provider)) throw new Error('provider');
  if (options.operation === 'cache-identity') {
    const resolved = resolveConfiguration({cwd: options.project, useGlobalConfig: options.global_enabled, skill: 'aihub-audio'});
    if (resolved.inspection.problems.some(p => p.reason === 'unreadable')) throw new Error('configuration');
    const key = resolved.values.AIHUB_API_KEY;
    if (!key) throw new Error('missing_key');
    // The service uses an account-bound gateway key. Hash it with the provider,
    // service and exact fixed query; neither the cache nor its filename stores it.
    const identity = voiceLibraryIdentity(key, options.provider);
    process.stdout.write(JSON.stringify({identity, home_directory: homedir()}));
  } else {
    const voices = await loadVoiceLibrary({cwd: options.project, useGlobalConfig: options.global_enabled}, options.provider, options.expected_identity);
    process.stdout.write(JSON.stringify({voices}));
  }
} catch (error) {
  const status = error instanceof ApiError ? error.status : 0;
  const message = error.message === 'missing_key' ? '请先配置音频 Skill 使用的 AIhub API Key，再重新载入音色库。'
    : status === 401 || status === 403 ? '音色库鉴权失败，请检查音频 Skill 使用的 AIhub API Key。'
    : status === 429 ? '音色库暂时限流，请稍后重试。'
    : '音色库暂时无法读取，请稍后重试；仍可手填音色 ID，已有设置与收藏保留。';
  process.stdout.write(JSON.stringify({error: error.message === 'configuration_changed' ? 'conflict' : 'voice_library',
    message: error.message === 'configuration_changed' ? '音色库账号已改变，请重新载入。' : message}));
  process.exitCode = 1;
}
