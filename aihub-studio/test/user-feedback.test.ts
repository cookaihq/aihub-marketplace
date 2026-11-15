import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeFeedback } from '../src/userFeedback.js';
import type { FailureEvent } from '../src/diagnostics.js';

const event = (code: string, stage: FailureEvent['stage'] = 'submission', http: number | null = null): FailureEvent => ({
  id: 'synthetic-event', at: '2026-11-15T00:00:00Z', stage, http_status: http, http_status_source: 'client_response',
  code, message: 'private prompt /private/path <details>trace-secret</details>', ambiguous: false, upstream: [],
});
const feedback = (output: Record<string, unknown>, events: FailureEvent[] = []) => summarizeFeedback(output, events, 'aihub-understanding')!;

test('unknown service failures explain the incomplete operation without inventing a provider outage or dumping evidence', () => {
  const result = feedback({ status: 'failed', result: { status: 'remote_failed', error: { code: 'service_unavailable' } } },
    [event('service_unavailable', 'remote_execution', 200)]);
  assert.match(result.user_notice, /素材理解任务.*执行失败/);
  assert.match(result.user_notice, /原因尚未确认/);
  assert.match(result.advice, /Agent.*原任务.*管理员/);
  for (const raw of ['service_unavailable', 'remote_failed', 'private', 'trace-secret', '<details>', '宕机', '未计费']) {
    assert.ok(!result.user_notice.includes(raw), raw);
  }
});

test('authentication, explicit quota and permission evidence produce different actionable explanations', () => {
  const auth = feedback({ status: 'not_submitted', failure: { http_status: 401 } });
  const quota = feedback({ status: 'not_submitted', failure: { code: 'insufficient_quota' } });
  const payment = feedback({ status: 'not_submitted', failure: { http_status: 402 } });
  const permission = feedback({ status: 'not_submitted', failure: { http_status: 403 } });
  assert.match(auth.user_notice, /密钥.*认证/);
  assert.match(auth.advice, /配置来源.*配置中心/);
  assert.match(quota.user_notice, /明确.*额度不足/);
  assert.match(payment.user_notice, /具体限制尚未确认/);
  assert.doesNotMatch(payment.user_notice, /明确.*余额不足/);
  assert.match(permission.user_notice, /访问权限/);
  assert.doesNotMatch(permission.user_notice, /密钥.*错误|额度不足/);
});

test('an uncertain submission remains uncertain with or without a task handle', () => {
  for (const task_id of [undefined, 'synthetic-task']) {
    const result = feedback({ status: 'submission_unknown', ...(task_id ? { task_id } : {}), failure: { code: 'timeout', ambiguous: true } });
    assert.match(result.user_notice, /提交结果尚未确认.*可能已接收/);
    assert.match(result.user_notice, /超时/);
    assert.match(result.advice, /原任务|原请求/);
    assert.match(result.advice, /避免重复提交.*不能确认是否计费/);
    assert.doesNotMatch(result.user_notice, /提交失败|未计费|稍后重试/);
    if (!task_id) assert.match(result.advice, /没有可用任务编号.*管理员/);
  }
  const uncertainError = feedback({ status: 'not_submitted', failure: { code: 'timeout', ambiguous: true } });
  assert.match(uncertainError.user_notice, /提交结果尚未确认/);
  assert.doesNotMatch(uncertainError.user_notice, /本次未成功提交/);
});

test('failed queries do not turn a running task into a failed generation or reuse a historical submission cause', () => {
  const result = feedback({ status: 'query_failed', remote_status: 'processing' }, [event('invalid_api_key', 'submission'), event('timeout', 'query')]);
  assert.match(result.user_notice, /最新进度未能查到.*是否完成尚未确认/);
  assert.match(result.user_notice, /超时/);
  assert.doesNotMatch(result.user_notice, /认证|执行失败|重新生成/);
  assert.match(result.advice, /查询原任务/);
  const current = feedback({ status: 'remote_failed', error: { code: 'service_unavailable' } }, [event('invalid_api_key', 'remote_execution', 401)]);
  assert.match(current.user_notice, /原因尚未确认/);
  assert.doesNotMatch(current.user_notice, /认证/);
  const currentHttp = feedback({ status: 'query_failed', failure: { http_status: 503 } }, [event('invalid_api_key', 'query', 401)]);
  assert.match(currentHttp.user_notice, /原因尚未确认/);
  assert.doesNotMatch(currentHttp.user_notice, /认证/);
  const registry = feedback({ status: 'availability_unknown', failure: { http_status: 401 } });
  assert.match(registry.user_notice, /可用模型清单未能查到.*认证/);
  assert.doesNotMatch(registry.user_notice, /执行失败|生成失败/);
  assert.match(registry.user_notice, /不能据此认定所有模型都不可用/);
});

test('partial results and failed downloads preserve usable work and recover only missing outputs', () => {
  const partial = feedback({ status: 'partial', files: [{ path: 'saved-result.txt' }] });
  const download = feedback({ status: 'download_failed', remote_status: 'completed' });
  assert.match(partial.user_notice, /一部分.*保留/);
  assert.match(partial.advice, /交付可用部分.*缺失内容及其影响/);
  assert.match(download.user_notice, /服务处理已完成.*保存到本机/);
  assert.match(download.advice, /只继续取得缺失文件.*不重新生成/);
});

test('successful recovery overrides account and option failures from previous attempts', () => {
  const result = feedback({ status: 'delivered', files: [{ path: 'saved-result.txt' }] }, [event('invalid_api_key'), event('requested_options_unavailable')]);
  assert.match(result.user_notice, /素材理解任务已完成/);
  assert.doesNotMatch(result.user_notice, /失败|密钥|修改要求|次数|requested_options/);
  assert.match(result.advice, /交付已有结果/);
  const catalog = feedback({ status: 'ok', models: ['available-model'] }, [event('invalid_api_key', 'registry', 401)]);
  assert.match(catalog.user_notice, /本次操作已完成/);
  assert.doesNotMatch(catalog.user_notice, /认证|尚未完成/);
});

test('result checking has its own outcome after generation has succeeded', () => {
  for (const embedded of [false, true]) {
    const review = { status: 'checking', delivery_status: 'delivered', external: { result: { status: 'query_failed', failure: { code: 'timeout' } } } };
    const result = feedback(embedded ? { status: 'delivered', result_check: review } : review);
    assert.match(result.user_notice, /已有结果.*结果检查尚未完成/);
    assert.match(result.advice, /查询原检查任务.*交付已有生成结果/);
    assert.doesNotMatch(result.user_notice, /生成失败|重新生成/);
  }
  const uncertain = feedback({ status: 'unavailable', delivery_status: 'delivered', external: { result: { status: 'submission_unknown' } } });
  assert.match(uncertain.advice, /原检查请求是否已被接受.*避免重复提交/);
  const mismatch = feedback({ status: 'delivered', result_check: { status: 'mismatched' } });
  assert.match(mismatch.advice, /说明具体差异.*你决定/);
  const unavailable = feedback({ status: 'delivered', result_check: { status: 'unavailable' } }, [event('invalid_api_key', 'registry', 401)]);
  assert.doesNotMatch(unavailable.user_notice, /认证/);
});

test('unsupported options and candidate confirmation keep the user choice intact', () => {
  const unavailable = feedback({ status: 'remote_failed', error: { code: 'requested_options_unavailable' } });
  assert.match(unavailable.advice, /你选择保留要求.*明确修改要求/);
  assert.doesNotMatch(unavailable.advice, /自动删参|自动切换/);
  const confirmation = feedback({ status: 'confirmation_required', result: { status: 'remote_failed', error: { code: 'model_unavailable' } } });
  assert.match(confirmation.advice, /展示下一模型.*费用.*等你确认/);
});

test('recording and recovery failures keep the remote outcome open and preserve identifiers', () => {
  const storage = feedback({ status: 'persistence_failed', task_id: 'synthetic-task' });
  assert.match(storage.user_notice, /本地恢复记录.*不代表远端任务失败/);
  assert.match(storage.advice, /保留已知任务编号.*避免重复提交/);
  const recovery = feedback({ status: 'recovery_failed' });
  assert.match(recovery.user_notice, /原任务结果仍需核对/);
  assert.equal(summarizeFeedback({ status: 'ok' }, [], 'aihub-image'), undefined);
});
