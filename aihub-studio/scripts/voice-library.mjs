// Private UI pipe: configuration values and remote error bodies never reach the browser.
import {loadVoiceLibrary} from '../dist/voiceLibrary.js';
import {ApiError} from '../dist/apiClient.js';
let input = '';
for await (const chunk of process.stdin) input += chunk;
try {
  const options = JSON.parse(input);
  const voices = await loadVoiceLibrary({cwd: options.project, useGlobalConfig: options.global_enabled});
  process.stdout.write(JSON.stringify({voices}));
} catch (error) {
  const status = error instanceof ApiError ? error.status : 0;
  const message = error.message === 'missing_key' ? '请先配置音频 Skill 使用的 AIhub API Key，再重新载入音色库。'
    : status === 401 || status === 403 ? '音色库鉴权失败，请检查音频 Skill 使用的 AIhub API Key。'
    : status === 429 ? '音色库暂时限流，请稍后重试。'
    : '音色库暂时无法读取，请稍后重试；仍可手填音色 ID，已有设置与收藏保留。';
  process.stdout.write(JSON.stringify({error: 'voice_library', message}));
  process.exitCode = 1;
}
