import type { FailureEvent } from './diagnostics.js';

type RecordValue = Record<string, unknown>;
function record(value: unknown): RecordValue {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
}

const TASK_NAMES: Record<string, string> = {
  'aihub-image': '图片任务', 'aihub-video': '视频任务', 'aihub-audio': '音频任务',
  'aihub-music': '音乐任务', 'aihub-understanding': '素材理解任务',
};
const INVESTIGATE = '由 Agent 核对原任务和已保存的请求证据；仍无法定位时，整理必要信息供服务管理员查询。';

/** Only current, structured evidence can explain the current outcome. Raw errors stay in the local report. */
function cause(output: RecordValue, events: readonly FailureEvent[], stages?: FailureEvent['stage'][]) {
  const failure = record(output.failure), error = record(output.error);
  const event = [...events].reverse().find(item => !stages || stages.includes(item.stage));
  const direct = failure.code !== undefined || failure.http_status !== undefined || error.code !== undefined;
  const code = failure.code ?? error.code ?? (direct ? undefined : event?.code);
  const http = failure.http_status ?? (direct ? undefined : event?.http_status);
  if (code === 'invalid_api_key' || code === 'authentication_error' || http === 401) return {
    reason: '服务拒绝了当前密钥的认证。',
    advice: '由 Agent 核对实际配置来源；需要更换密钥时，请你在配置中心修复，再核对原任务状态。',
  };
  if (code === 'insufficient_quota') return {
    reason: '服务明确返回可用额度不足。', advice: '请你核对 AIhub 账号的可用额度；由 Agent 在修复后核对原任务，避免重复提交。',
  };
  if (http === 402) return {
    reason: '服务因账号付费或额度问题拒绝了请求，具体限制尚未确认。',
    advice: '请你核对账号状态或向服务管理员确认限制；由 Agent 保留并核对原任务。',
  };
  if (code === 'permission_denied' || http === 403) return {
    reason: '服务拒绝了本次操作的访问权限。', advice: '由 Agent 核对账号和操作范围；需要开通权限时，请你联系服务管理员。',
  };
  if (code === 'requested_options_unavailable' || code === 'unsupported_parameters') return {
    reason: '服务无法满足本次请求中的部分选项。',
    advice: '由 Agent 说明受影响的要求，请你选择保留要求稍后处理，或明确修改要求后新建请求。',
  };
  if (code === 'content_policy_violation') return {
    reason: '服务因内容规则拒绝了本次请求。', advice: '由 Agent 解释受影响的内容，请你决定是否调整需求；不自动改写后重发。',
  };
  if (code === 'model_unavailable' || code === 'model_not_support_capability') return {
    reason: '服务提示当前模型或所需能力不可用。',
    advice: '由 Agent 按已保存的模型策略判断能否继续；需要改变型号或要求时，请你选择。',
  };
  if (code === 'rate_limit_exceeded' || http === 429) return {
    reason: '服务提示请求过于频繁或已达到当前限额。', advice: '由 Agent 按服务给出的等待时间和原任务恢复规则继续处理。',
  };
  if (code === 'timeout') return { reason: '等待服务响应时超时，具体原因尚未确认。', advice: INVESTIGATE };
  if (code === 'network_error') return { reason: '本次与服务的连接未完成，具体原因尚未确认。', advice: INVESTIGATE };
  if (code === 'invalid_response') return { reason: '本次未收到可用的服务响应，具体原因尚未确认。', advice: INVESTIGATE };
  return { reason: '具体原因尚未确认。', advice: INVESTIGATE };
}

export interface UserFeedback { user_notice: string; advice: string }

/** Presentation only: never executes a retry, changes a request, or treats saved errors as current failures. */
export function summarizeFeedback(output: RecordValue, events: readonly FailureEvent[], skill?: string): UserFeedback | undefined {
  const task = TASK_NAMES[skill ?? ''] ?? '本次任务';
  const detail = record(output.result);
  const topStatus = String(output.status ?? 'unknown');
  const status = topStatus === 'failed' && detail.status ? String(detail.status) : topStatus;
  const current = Object.keys(detail).length ? detail : output;
  const finish = (outcome: string, advice: string, reason = '') => ({
    user_notice: [outcome, reason, advice].filter(Boolean).join(''), advice,
  });

  // A check can fail after successful delivery. Its outcome must not invalidate the generated files.
  const review = output.delivery_status === 'delivered' ? output : record(output.result_check);
  if (status === 'delivered' || output.delivery_status === 'delivered') {
    const reviewStatus = String(review.status ?? '');
    if (reviewStatus === 'matched') return finish(`${task}已完成，结果检查通过。`, '由 Agent 交付已有结果。');
    if (reviewStatus === 'mismatched') return finish(`${task}已有结果，但检查发现与要求不符。`, '由 Agent 交付已有结果并说明具体差异，请你决定是否修改或重做。');
    if (reviewStatus === 'inconclusive') return finish(`${task}已有结果，但检查证据不足，尚不能确认符合要求。`, '由 Agent 交付已有结果并说明已检查的范围和未确认的部分。');
    if (reviewStatus === 'pending') return finish(`${task}已有结果，尚待检查是否符合要求。`, '由 Agent 查看实际结果，完成仍可执行的检查后交付。');
    if (reviewStatus === 'checking' || reviewStatus === 'unavailable') {
      const check = record(record(review.external).result);
      const explanation = cause(check, Object.keys(check).length ? events : [], ['registry', 'upload', 'submission', 'query', 'remote_execution']);
      const advice = check.status === 'submission_unknown' || check.status === 'upload_unknown'
        ? '由 Agent 先核对原检查请求是否已被接受；保留已有生成结果，避免重复提交检查或生成任务。'
        : reviewStatus === 'checking'
          ? '由 Agent 继续查询原检查任务，并交付已有生成结果。'
          : '由 Agent 交付已有结果并说明检查范围；先排查原检查记录，需要新检查请求时沿用现有确认规则。';
      return finish(`${task}已有结果，但本次结果检查尚未完成。`, advice, explanation.reason);
    }
    return finish(`${task}已完成。`, reviewStatus === 'disabled'
      ? '由 Agent 交付已有结果；本次未进行内容检查。'
      : '由 Agent 交付已有结果；是否符合要求，以实际结果检查为准。');
  }

  if (status === 'availability_unknown') {
    const explanation = cause(current, events, ['registry']);
    return finish(`${task}的可用模型清单未能查到，当前可用范围尚未确认。`,
      (explanation.advice === INVESTIGATE ? '' : explanation.advice) + '由 Agent 核对本次模型查询的请求证据，按原查询规则继续处理；不能据此认定所有模型都不可用。', explanation.reason);
  }
  if (status === 'submission_unknown' || status === 'upload_unknown' || (status === 'not_submitted' && record(current.failure).ambiguous === true)) {
    const action = status === 'upload_unknown' ? '素材上传' : '任务提交';
    const explanation = cause(current, events, [status === 'upload_unknown' ? 'upload' : 'submission']);
    const knownTask = typeof output.task_id === 'string' || typeof current.task_id === 'string';
    return finish(`${task}的${action}结果尚未确认，服务可能已接收请求。`, knownTask
      ? '由 Agent 使用已取得的任务编号查询原任务，避免重复提交；目前不能确认是否计费。'
      : '由 Agent 核对已有请求记录；没有可用任务编号时，需服务管理员协助确认原请求结果，避免重复提交。目前不能确认是否计费。', explanation.reason);
  }
  if (status === 'query_failed') {
    const explanation = cause(current, events, ['query']);
    return finish(`${task}的最新进度未能查到，当前是否完成尚未确认。`,
      (explanation.advice === INVESTIGATE ? '' : explanation.advice) + '由 Agent 按原任务恢复规则继续查询原任务，保留已取得的结果；不创建替代任务。', explanation.reason);
  }
  if (status === 'download_failed' || status === 'download_pending') return finish(
    `${task}的服务处理已完成，但结果尚未成功保存到本机。`,
    '由 Agent 核对原任务的结果地址、本地存储和文件状态，只继续取得缺失文件；不重新生成。',
    '下载或保存未完成的具体原因，以本地文件检查和下载证据为准。');
  if (status === 'partial') {
    const explanation = cause(current, events);
    return finish(`${task}只完成了一部分；已取得的结果会保留。`,
      '由 Agent 交付可用部分，说明缺失内容及其影响，并按原任务恢复规则继续处理未完成部分。' +
      (explanation.advice === INVESTIGATE ? '' : explanation.advice), explanation.reason);
  }
  if (['waiting', 'submitted', 'in_progress'].includes(status)) return finish(`${task}尚未完成，目前没有可交付的完整结果。`,
    '由 Agent 核对最近进度并按原任务继续查询；等待结束不代表任务失败。');
  if (status === 'confirmation_required') return finish(`${task}尚未完成，继续使用下一候选模型需要你的选择。`,
    '由 Agent 展示下一模型、参数和可能的费用影响，等你确认后继续。');
  if (status === 'persistence_failed') return finish(`${task}的本地恢复记录未能保存完整；这不代表远端任务失败。`,
    '由 Agent 保留已知任务编号和已有结果，修复存储后查询原任务，避免重复提交。');
  if (status === 'recovery_failed') {
    const explanation = cause(current, events);
    return finish(`${task}本次续接未完成，原任务结果仍需核对。`,
      '由 Agent 检查原记录、账号及已有任务编号，修复后继续原任务，避免重新提交。' +
      (explanation.advice === INVESTIGATE ? '' : explanation.advice), explanation.reason);
  }
  if (['ok', 'ready', 'disabled'].includes(status)) {
    if (!events.length) return;
    return finish(status === 'ready' ? '本次任务准备已完成。' : status === 'disabled' ? '本次检查已关闭。' : '本次操作已完成。',
      '由 Agent 使用当前返回结果继续处理原任务；此前请求错误保留在本地记录中。');
  }

  const stages: FailureEvent['stage'][] | undefined = status === 'remote_failed' ? ['remote_execution']
    : status === 'preflight_failed' ? ['registry'] : status === 'upload_rejected' ? ['upload'] : undefined;
  const explanation = cause(current, events, stages);
  const outcomes: Record<string, string> = {
    remote_failed: `${task}已被服务标记为执行失败，未取得完整结果。`,
    preflight_failed: `${task}在提交前的检查阶段未完成。`,
    not_submitted: `${task}本次未成功提交。`,
    upload_rejected: `${task}的素材上传被拒绝，后续处理尚未完成。`,
    preprocessing_failed: `${task}的素材准备未完成。`,
    transcription_failed: `${task}未能完成转写；已取得的片段会保留。`,
    no_compatible_model: `${task}未找到满足当前要求的可用模型。`,
    attempt_limit: `${task}已达到本次允许的模型尝试次数，尚未取得完整结果。`,
  };
  return finish(outcomes[status] ?? `${task}尚未完成，需要核对当前结果。`, explanation.advice, explanation.reason);
}
