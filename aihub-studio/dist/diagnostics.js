import { AsyncLocalStorage } from 'node:async_hooks';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, stat } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { credentialId } from './config.js';
import { assertOutsideInstallation, withJobLock, writePrivateRecord, writePrivateText } from './state.js';
import { jsonBlock, localLink, redactEvidence, upstreamEvidence } from './diagnosticEvidence.js';
const context = new AsyncLocalStorage();
export function collectRequestErrors(run) {
    const capture = { events: [], exchanges: [] };
    return context.run(capture, () => run(capture.events));
}
export function configureDiagnostics(cfg) { const c = context.getStore(); if (c)
    c.cfg = cfg; }
/** Bind before the first request. A run owns its child attempts and review requests. */
export async function bindDiagnosticRecord(cfg, record, taskContext, root = false) {
    const c = context.getStore();
    if (!c || (c.root && !root))
        return;
    c.cfg = cfg;
    c.record = resolve(record);
    c.root = root;
    if (taskContext !== undefined)
        c.taskContext = redactEvidence(taskContext, [cfg.apiKey]);
    if (!c.loaded) {
        c.loaded = true;
        try {
            const saved = JSON.parse(await readFile(join(dirname(c.record), 'request-context.json'), 'utf8'));
            if (saved.kind !== 'aihub-request-context' || !Array.isArray(saved.exchanges))
                throw new Error('Invalid request context');
            c.exchanges = [...saved.exchanges, ...c.exchanges];
            c.taskContext ??= saved.task_context;
        }
        catch (error) {
            if (error.code !== 'ENOENT')
                c.warning = '已有请求上下文无法读取；本轮证据仍会尝试保存。';
        }
    }
}
function directory(c, output) {
    const record = c?.record ?? [output.run_record, output.source_record, output.record].find(v => typeof v === 'string');
    if (typeof record === 'string')
        return dirname(resolve(record));
    const dir = resolve('data/aihub', `diagnostic-${randomUUID()}`);
    if (c)
        c.record = join(dir, 'request-context.json');
    return dir;
}
async function saveContext(c) {
    if (!c.cfg)
        return;
    await writePrivateRecord(join(directory(c, {}), 'request-context.json'), {
        schema_version: 1, kind: 'aihub-request-context', task_context: c.taskContext ?? null, exchanges: c.exchanges,
    });
}
export async function observeExchange(evidence) {
    const c = context.getStore();
    const safe = redactEvidence(evidence, c?.cfg ? [c.cfg.apiKey, credentialId(c.cfg.apiKey)] : []);
    if (c) {
        c.exchanges.push(safe);
        try {
            await saveContext(c);
        }
        catch {
            c.warning = '无法保存请求上下文；保留原任务结果与已知任务 ID。';
        }
    }
    return safe;
}
async function persistFailure() {
    const c = context.getStore();
    if (!c?.cfg)
        return;
    try {
        await feedback(c.cfg, { status: 'in_progress' }, c.events);
    }
    catch {
        c.warning = '无法保存错误报告；保留原任务结果与已知任务 ID，不要因此重新提交。';
    }
}
function stageFor(method, path) {
    return path.startsWith('/v1/tasks/') ? 'query' : method === 'GET' && (path.includes('/models') || path.includes('/configs/') || path === '/api/pricing') ? 'registry'
        : path.startsWith('/v1/files/') ? 'upload' : method === 'POST' ? 'submission' : 'other';
}
export async function observeRequestError(error, method, path, evidence) {
    const c = context.getStore();
    if (!c || error.type === 'validation' || error.code === 'deadline_exceeded')
        return;
    const stage = stageFor(method, path);
    const taskId = stage === 'query' ? decodeURIComponent(path.split('?')[0].split('/').at(-1)) : undefined;
    c.events.push({ id: evidence?.id ?? randomUUID(), at: evidence?.at ?? new Date().toISOString(), stage,
        http_status: evidence?.response.http_status ?? null, http_status_source: evidence?.response.http_status ? 'client_response' : 'not_observed',
        code: error.code ?? 'unknown_error', message: error.message, ambiguous: error.ambiguous,
        request_id: error.requestId ?? evidence?.response.headers['x-request-id'] ?? null,
        ...(taskId ? { task_id: taskId } : {}),
        ...(evidence ? { exchange_id: evidence.id } : {}), upstream: upstreamEvidence(evidence?.response.body) });
    await persistFailure();
}
export async function observeTerminalTask(task, evidence) {
    if (task.status !== 'failed')
        return;
    const c = context.getStore();
    if (!c)
        return;
    const id = 'task-' + createHash('sha256').update(task.id).digest('hex');
    c.events.push({ id, at: evidence?.at ?? new Date().toISOString(), stage: 'remote_execution',
        http_status: evidence?.response.http_status ?? null, http_status_source: evidence?.response.http_status ? 'client_response' : 'not_observed',
        code: task.error?.code ?? 'unknown_error', message: task.error?.message ?? null,
        ambiguous: false, task_id: task.id, task_status: task.status,
        request_id: evidence?.response.headers['x-request-id'] ?? null,
        ...(evidence ? { exchange_id: evidence.id } : {}), upstream: upstreamEvidence(evidence?.response.body ?? task) });
    await persistFailure();
}
export const ISSUE_URL = 'https://github.com/cookaihq/aihub-marketplace/issues/new';
const PUBLIC_CODES = new Set(['model_unavailable', 'model_not_support_capability', 'content_policy_violation', 'timeout',
    'service_unavailable', 'network_error', 'ambiguous', 'invalid_response', 'insufficient_quota', 'invalid_api_key',
    'rate_limit_exceeded', 'authentication_error', 'permission_denied']);
/** An update error must not hide usable files from an earlier observation. Never link a missing file. */
export async function existingFeedback(output) {
    const c = context.getStore();
    if (!c?.record && ![output.run_record, output.source_record, output.record].some(v => typeof v === 'string'))
        return;
    const dir = directory(c, output), artifacts = {};
    for (const [key, name] of [['error_report', 'error-report.md'], ['diagnostic', 'diagnostic.json'],
        ['issue_draft', 'issue-draft.md'], ['request_context', 'request-context.json']]) {
        const path = join(dir, name);
        if (await stat(path).then(s => s.isFile()).catch(() => false))
            artifacts[key] = path;
    }
    const links = Object.values(artifacts).map(localLink);
    if (!links.length)
        return;
    return { ...artifacts, show_notice: true, artifact_links: links,
        user_notice: `本轮报告更新失败；以下为已存在的本地文件，内容可能未包含最新结果：\n\n${links.join('\n\n')}` };
}
export async function feedback(cfg, output, events) {
    const c = context.getStore();
    const hasRecord = c?.record || [output.run_record, output.source_record, output.record].some(v => typeof v === 'string');
    if (!events.length && !hasRecord)
        return;
    const dir = directory(c, output), path = join(dir, 'diagnostic.json');
    assertOutsideInstallation(path);
    await mkdir(dir, { recursive: true, mode: 0o700 });
    return withJobLock(path, async () => {
        const now = new Date().toISOString();
        let saved = { schema_version: 2, kind: 'aihub-diagnostic', events: [], created_at: now, updated_at: now, context: {}, exchanges: [] };
        try {
            const parsed = JSON.parse(await readFile(path, 'utf8'));
            if (parsed.kind !== 'aihub-diagnostic' || !Array.isArray(parsed.events) || ![1, 2].includes(parsed.schema_version))
                throw new Error('Invalid diagnostic record');
            if (parsed.schema_version === 1) {
                saved.legacy_note = '旧版 schema 1 的 remote_execution.http_status=200 是固定填充值，不是采集的 HTTP 证据；已改为未知。旧报告没有请求/响应正文，不能回填或推断供应商状态。';
                saved.events = parsed.events.map((e) => ({ ...e,
                    http_status: e.stage === 'remote_execution' || !e.http_status ? null : e.http_status,
                    http_status_source: e.stage === 'remote_execution' ? 'legacy_unverified' : 'legacy_client_error', message: null, upstream: [] }));
                saved.context = parsed.context ?? {};
            }
            else
                saved = parsed;
        }
        catch (error) {
            if (error.code !== 'ENOENT')
                throw error;
        }
        const secrets = [cfg.apiKey, credentialId(cfg.apiKey)];
        for (const raw of events) {
            const event = redactEvidence(raw, secrets);
            const old = saved.events.findIndex(e => e.id === event.id);
            if (old < 0)
                saved.events.push(event);
            else
                saved.events[old] = { ...saved.events[old], ...event, at: saved.events[old].at };
        }
        if (!saved.events.length)
            return;
        let taskContext = c?.taskContext, exchanges = c?.exchanges ?? [];
        if (!taskContext || !exchanges.length) {
            try {
                const snapshot = JSON.parse(await readFile(join(dir, 'request-context.json'), 'utf8'));
                taskContext ??= snapshot.task_context;
                if (!exchanges.length && Array.isArray(snapshot.exchanges))
                    exchanges = snapshot.exchanges;
            }
            catch { /* Old records can legitimately lack the new evidence file. */ }
        }
        for (const exchange of exchanges)
            if (!saved.exchanges.some(e => e.id === exchange.id))
                saved.exchanges.push(exchange);
        const version = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8')).version;
        saved.updated_at = now;
        saved.context = { ...saved.context, plugin: 'aihub-studio', plugin_version: version, skill: cfg.skill,
            task_status: output.status ?? 'unknown', service_url: cfg.baseUrl, task_context: taskContext ?? saved.context.task_context ?? null,
            attempted_models: output.attempted_models ?? saved.context.attempted_models ?? [], attempts: output.attempts ?? saved.context.attempts ?? [],
            original_request: taskContext?.original_request ?? saved.context.original_request ?? null,
            model: output.model ?? saved.context.model ?? null };
        // Each exchange is already bounded. Do not truncate the accumulated history on every save.
        saved.context = redactEvidence(saved.context, secrets);
        const reportPath = join(dir, 'error-report.md'), draftPath = join(dir, 'issue-draft.md');
        const contextPath = join(dir, 'request-context.json');
        const hasContext = await stat(contextPath).then(s => s.isFile()).catch(() => false);
        const links = [reportPath, path, draftPath, ...(hasContext ? [contextPath] : [])].map(localLink);
        const account = saved.events.some(e => [401, 402, 403].includes(e.http_status ?? 0));
        const advice = account ? '请核对实际服务地址、账号权限或余额；不要为生成报告重发请求。'
            : 'service_unavailable 仅是服务返回的错误分类，不能证明上游宕机。未暴露的供应商状态、路由和内部重试应由管理员按 task_id/request_id 查询后台日志。';
        const report = '# AIHub Studio 本地请求与错误汇总\n\n' +
            `首次记录：${saved.created_at}\n\n更新时间：${now}\n\n独立错误数：${saved.events.length}\n\n` +
            '本文件仅保存在本机，含私密需求、提示词及素材定位信息。凭证已脱敏；对外提交前请人工检查。公开 Issue 请使用另附草稿。\n\n' +
            'HTTP 表示客户端实际收到的 AIHub 响应，异步任务状态单独记录。上游字段仅按响应原字段及来源保留；null 表示未知或未记录。客户端耗时不代表供应商执行耗时。\n\n' +
            `${saved.legacy_note ? saved.legacy_note + '\n\n' : ''}${advice}\n\n` +
            `## 任务与模型切换\n\n${jsonBlock(saved.context)}\n\n## 错误证据\n\n${jsonBlock(saved.events)}\n\n` +
            `## 实际请求 / 响应 JSON（脱敏）\n\n${jsonBlock(saved.exchanges)}\n\n` +
            '上游原始 HTTP / 错误码 / request ID / trace ID / 供应商 / 路由 / 内部耗时 / 内部重试：仅以 upstream.source 及响应正文为准；未出现的字段均为未知。二进制、大型 Base64 与超限内容用明确省略标记表示。\n\n' +
            `## 关联文件\n\n${links.map(link => '- ' + link).join('\n')}\n`;
        // Public draft is an allowlist projection: no private input, URLs, IDs, paths or raw errors.
        const rows = saved.events.map((e, i) => `| ${i + 1} | ${e.at} | ${e.stage} | ${e.http_status ?? '未知'} | ${PUBLIC_CODES.has(e.code) ? e.code : 'unknown_error'} |`).join('\n');
        const publicStatus = ['delivered', 'failed', 'remote_failed', 'waiting', 'preflight_failed', 'query_failed',
            'submission_unknown', 'not_submitted', 'in_progress', 'attempt_limit', 'confirmation_required', 'download_failed',
            'partial', 'persistence_failed', 'submitted', 'matched', 'mismatched', 'inconclusive', 'checking', 'unavailable']
            .includes(String(output.status)) ? output.status : 'unknown';
        const draft = `# AIHub 错误反馈草稿\n\nPlugin: ${version}\nSkill: ${cfg.skill}\n运行平台: ${process.platform}; Node: ${process.version}\n任务状态: ${publicStatus}\n独立错误数: ${saved.events.length}\n\n` +
            '| # | UTC 时间 | 阶段 | 客户端 HTTP（不是供应商 HTTP） | 错误类别 |\n| --- | --- | --- | --- | --- |\n' + rows +
            `\n\n请补充不含私密输入的复现步骤，检查后手动提交：${ISSUE_URL}\n任务/请求 ID 仅留在本地报告；本草稿未自动发送。\n`;
        await writePrivateRecord(path, saved);
        await writePrivateText(draftPath, draft);
        await writePrivateText(reportPath, report);
        return { upstream_error_count: saved.events.length, report_required: true, show_notice: true,
            error_report: reportPath, diagnostic: path, issue_draft: draftPath, issue_url: ISSUE_URL, artifact_links: links,
            user_notice: `本地错误汇总（${saved.events.length} 个独立错误；当前状态 ${publicStatus}）：\n\n${links.join('\n\n')}`,
            advice, support: redactEvidence(cfg.feedback?.supportUrl ?? '联系当前 AIhub 服务管理员', secrets),
            ...(c?.warning ? { warning: c.warning } : {}),
            privacy_notice: '本地报告含私密请求与定位信息；公开反馈只使用检查后的 issue-draft.md，不自动发送。' };
    });
}
