import { randomUUID } from 'node:crypto';
import { observeExchange, observeRequestError, observeTerminalTask } from './diagnostics.js';
import { redactEvidence } from './diagnosticEvidence.js';
/** ambiguous=true means the caller must not submit the same write again automatically. */
export class ApiError extends Error {
    status;
    type;
    code;
    requestId;
    ambiguous;
    retryable;
    constructor(message, status, type, code, requestId, ambiguous = false, retryable = false) {
        super(message);
        this.status = status;
        this.type = type;
        this.code = code;
        this.requestId = requestId;
        this.ambiguous = ambiguous;
        this.retryable = retryable;
        this.name = "ApiError";
    }
}
/** Polling expiry preserves the paid task handle and its latest known response. */
export class PollBudgetExceededError extends ApiError {
    taskId;
    lastTask;
    constructor(taskId, lastTask) {
        super(`任务 ${taskId} 已达到等待时限；任务可能仍在运行，请用 task_id 查询，勿重新提交。`, 0, "polling", "poll_budget_exhausted");
        this.taskId = taskId;
        this.lastTask = lastTask;
        this.name = "PollBudgetExceededError";
    }
}
const MAX_ATTEMPTS = 3;
const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_RETRY_AFTER_MS = 60_000;
const POLL_INTERVAL_MS = 5_000;
const TASK_QUERY_TIMEOUT_MS = 15_000;
const MAX_POLL_FAILURES = 3;
const IDEMPOTENT_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const TASK_STATUSES = new Set(["pending", "processing", "completed", "failed"]);
const TRANSIENT_CODES = new Set([
    "ENOTFOUND", "EAI_AGAIN", "ECONNREFUSED", "ECONNRESET", "EPIPE", "ETIMEDOUT",
    "UND_ERR_CONNECT_TIMEOUT", "UND_ERR_HEADERS_TIMEOUT", "UND_ERR_BODY_TIMEOUT", "UND_ERR_SOCKET",
]);
function errorChain(error) {
    const chain = [];
    for (let current = error, depth = 0; current && typeof current === "object" && depth < 8; depth++) {
        const detail = current;
        chain.push(detail);
        current = detail.cause;
    }
    return chain;
}
function isPreSendNetworkError(error) {
    // A timeout during connect does not prove that no bytes reached the service.
    // ADR 0006 only permits DNS resolution failure and connection refusal here.
    return errorChain(error).some(({ code }) => code === "ENOTFOUND" || code === "EAI_AGAIN" || code === "ECONNREFUSED");
}
function isTransientNetworkError(error) {
    return errorChain(error).some(({ name, code, message }) => name === "TimeoutError" || name === "AbortError" || (code !== undefined && TRANSIENT_CODES.has(code)) ||
        (name === "TypeError" && (message === "fetch failed" || message === "terminated")));
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
function retryDelayMs(response, failedAttempt) {
    const fallback = 1_000 * 2 ** failedAttempt;
    if (response?.status !== 429)
        return fallback;
    const raw = response.headers.get("retry-after")?.trim();
    if (!raw)
        return fallback;
    const seconds = Number(raw);
    if (!Number.isNaN(seconds)) {
        return Number.isFinite(seconds) && seconds >= 0
            ? Math.min(seconds * 1_000, MAX_RETRY_AFTER_MS)
            : fallback;
    }
    // HTTP-date form, while rejecting nonfinite numeric spellings such as NaN.
    if (!/[A-Za-z]{3},/.test(raw))
        return fallback;
    const date = Date.parse(raw);
    return Number.isFinite(date) ? Math.min(Math.max(0, date - Date.now()), MAX_RETRY_AFTER_MS) : fallback;
}
export class AihubmaxClient {
    cfg;
    evidence = new WeakMap();
    constructor(cfg) {
        this.cfg = cfg;
    }
    evidenceFor(value) {
        return value && typeof value === 'object' ? this.evidence.get(value) : undefined;
    }
    async request(method, path, body, opts = {}) {
        const timeout = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
        if (!Number.isFinite(timeout) || timeout <= 0 || timeout > 2_147_483_647) {
            throw new ApiError("timeoutMs 必须是大于 0 且不超过 2147483647 的毫秒数。", 0, "validation", "invalid_timeout");
        }
        if (opts.deadline !== undefined && !Number.isFinite(opts.deadline)) {
            throw new ApiError("deadline 必须是有限的绝对毫秒时间戳。", 0, "validation", "invalid_deadline");
        }
        // Serialize before sending. Circular JSON and invalid parameters are local errors.
        const serializedBody = body === undefined ? undefined : JSON.stringify(body);
        const policy = opts.retry ?? (IDEMPOTENT_METHODS.has(method.toUpperCase()) ? "idempotent" : "non-idempotent");
        const isWrite = policy === "non-idempotent";
        const url = `${this.cfg.baseUrl}${path}`;
        for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            const remaining = opts.deadline === undefined ? timeout : opts.deadline - Date.now();
            if (remaining <= 0)
                throw this.deadlineError(method, path);
            const timeoutMs = Math.max(1, Math.floor(Math.min(timeout, remaining)));
            let response;
            let text;
            const started = Date.now();
            const headers = { Authorization: `Bearer ${this.cfg.apiKey}`,
                ...(serializedBody !== undefined ? { 'Content-Type': 'application/json' } : {}) };
            const capture = async (responseBody, retry = false, timeoutStage = null) => {
                const delay = retry ? retryDelayMs(response, attempt) : null;
                const scheduled = retry && (opts.deadline === undefined || delay < opts.deadline - Date.now());
                return observeExchange(redactEvidence({ id: randomUUID(), at: new Date(started).toISOString(), method, url,
                    elapsed_ms: Date.now() - started, attempt: attempt + 1, max_attempts: MAX_ATTEMPTS, retry_policy: policy,
                    retry_scheduled: scheduled, retry_delay_ms: scheduled ? delay : null, timeout_ms: timeoutMs, timeout_stage: timeoutStage,
                    request: { headers, body: body ?? null, query: Object.fromEntries([...new URL(url).searchParams.keys()].map(key => [key, new URL(url).searchParams.getAll(key)])) }, response: { http_status: response?.status ?? null,
                        headers: response ? Object.fromEntries(response.headers.entries()) : {}, body: responseBody },
                }, [this.cfg.apiKey]));
            };
            try {
                response = await fetch(url, {
                    method,
                    headers,
                    ...(serializedBody !== undefined ? { body: serializedBody } : {}),
                    signal: AbortSignal.timeout(timeoutMs),
                });
                text = await response.text();
            }
            catch (cause) {
                // A known deterministic HTTP rejection stays terminal even if its body disconnects.
                if (response && response.status >= 400 && response.status < 500 && response.status !== 429) {
                    const error = this.toApiError(response.status, "服务端拒绝请求，错误响应体未完整收到。", false);
                    await observeRequestError(error, method, path, await capture(null));
                    throw error;
                }
                const definitelyNotSent = !response && isPreSendNetworkError(cause);
                const ambiguous = isWrite && !definitelyNotSent;
                const retryable = isTransientNetworkError(cause) && (!isWrite || definitelyNotSent);
                const detail = errorChain(cause).map((item) => item.code ?? item.message).filter(Boolean).join("; ");
                const error = new ApiError(this.redact(`网络请求失败（${method} ${path}）：${detail || "未收到完整响应"}。` +
                    (ambiguous ? "写入结果不明，请勿自动重新提交。" : "")), response?.status ?? 0, "network", ambiguous ? "ambiguous" : "network_error", undefined, ambiguous, retryable);
                const timeoutStage = errorChain(cause).some(item => /timeout|abort/i.test(`${item.name} ${item.code}`))
                    ? (response ? 'response_body' : 'request_before_response_headers') : null;
                await observeRequestError(error, method, path, await capture(null, retryable && attempt + 1 < MAX_ATTEMPTS, timeoutStage));
                if (retryable && attempt + 1 < MAX_ATTEMPTS) {
                    await this.waitForRetry(retryDelayMs(response, attempt), attempt, error, opts);
                    continue;
                }
                throw error;
            }
            if (response.ok) {
                let parsed;
                try {
                    if (!text)
                        throw new Error("empty response");
                    parsed = JSON.parse(text);
                }
                catch {
                    const error = new ApiError(this.redact(`服务端返回了非 JSON 响应（HTTP ${response.status}，${method} ${path}）。` +
                        "请检查 AIHUB_BASE_URL 是否指向 API 网关。" +
                        (isWrite ? "写入结果不明，请勿自动重新提交。" : "")), response.status, "protocol", "invalid_response", undefined, isWrite);
                    await observeRequestError(error, method, path, await capture(text));
                    throw error;
                }
                const evidence = await capture(parsed);
                if (parsed && typeof parsed === 'object')
                    this.evidence.set(parsed, evidence);
                return parsed;
            }
            // No verified idempotency or rejection guarantee exists for AIhub generation POSTs.
            // In particular, HTTP 429 does not justify automatically repeating a paid submission.
            const error = this.toApiError(response.status, text, isWrite && (response.status >= 500 || response.status === 429), response.headers.get('x-request-id') ?? undefined);
            let responseBody = text;
            try {
                responseBody = JSON.parse(text);
            }
            catch { /* Preserve non-JSON response as text. */ }
            await observeRequestError(error, method, path, await capture(responseBody, error.retryable && !isWrite && attempt + 1 < MAX_ATTEMPTS));
            if (error.retryable && !isWrite && attempt + 1 < MAX_ATTEMPTS) {
                await this.waitForRetry(retryDelayMs(response, attempt), attempt, error, opts);
                continue;
            }
            throw error;
        }
        throw new ApiError("请求尝试次数已耗尽。", 0);
    }
    deadlineError(method, path) {
        return new ApiError(this.redact(`请求已达到截止时间（${method} ${path}）。`), 0, "timeout", "deadline_exceeded");
    }
    async waitForRetry(ms, failedAttempt, error, opts) {
        const remaining = opts.deadline === undefined ? Number.POSITIVE_INFINITY : opts.deadline - Date.now();
        // Do not shorten Retry-After and then issue an early request. If there is no time
        // for the full delay plus a request, hand the existing failure back to the caller.
        if (ms >= remaining)
            throw error;
        console.error(this.redact(`[aihub] 重试 ${failedAttempt + 2}/${MAX_ATTEMPTS}，等待 ${ms / 1000}s；${error.message}`));
        await sleep(ms);
    }
    redact(value) {
        return redactEvidence(value, [this.cfg.apiKey]);
    }
    toApiError(status, text, ambiguous, headerRequestId) {
        // Redact before truncating: slicing through a key would otherwise leave a
        // secret fragment that no longer matches the full configured key.
        let message = this.redact(text).slice(0, 400);
        let type;
        let code;
        let requestId = headerRequestId;
        try {
            const parsed = JSON.parse(text);
            if (parsed?.error) {
                if (typeof parsed.error.message === "string")
                    message = this.redact(parsed.error.message).slice(0, 400);
                if (typeof parsed.error.type === "string")
                    type = this.redact(parsed.error.type);
                if (typeof parsed.error.code === "string")
                    code = this.redact(parsed.error.code);
                requestId ??= /request_id:\s*([\w-]+)/.exec(message)?.[1];
            }
        }
        catch { /* A non-JSON rejection still retains its HTTP status. */ }
        const hints = {
            401: "API Key 无效或缺失，请检查 AIHUB_API_KEY。",
            402: "余额不足，请检查 AIhub 控制台额度。",
            403: "当前 API Key 无权执行该操作。",
            404: "请求资源不存在。",
            422: "参数或模型不可用，请重新查询模型与参数说明。",
            429: "服务端限流。",
        };
        return new ApiError(this.redact(`请求失败（HTTP ${status}）：${hints[status] ?? ""}${message}` +
            (ambiguous ? " 写入结果不明，请勿自动重新提交。" : "")), status, type, code, requestId ? this.redact(requestId) : undefined, ambiguous, !ambiguous && (status === 429 || status >= 500));
    }
    async submitGeneration(path, params, opts) {
        const result = await this.request("POST", path, params, opts);
        if (!result || typeof result.id !== "string" || !result.id || !TASK_STATUSES.has(result.status)) {
            const error = new ApiError("生成请求未返回有效的任务 ID 与状态；写入结果不明，请勿自动重新提交。", this.evidenceFor(result)?.response.http_status ?? 0, "protocol", "invalid_response", undefined, true);
            await observeRequestError(error, 'POST', path, this.evidenceFor(result));
            throw error;
        }
        await observeTerminalTask(result, this.evidenceFor(result));
        return result;
    }
    async getTask(taskId, syncUpstream = false, opts) {
        const suffix = syncUpstream ? "?sync_upstream=true" : "";
        const task = await this.request("GET", `/v1/tasks/${encodeURIComponent(taskId)}${suffix}`, undefined, opts);
        if (!task || task.id !== taskId || !TASK_STATUSES.has(task.status)) {
            const error = new ApiError("任务查询响应缺少有效 ID 或状态，请保留原 task_id 后再次查询。", this.evidenceFor(task)?.response.http_status ?? 0, "protocol", "invalid_response");
            await observeRequestError(error, 'GET', `/v1/tasks/${encodeURIComponent(taskId)}`, this.evidenceFor(task));
            throw error;
        }
        await observeTerminalTask(task, this.evidenceFor(task));
        return task;
    }
    async pollTask(taskId, waitSeconds, syncUpstream = false, onPoll) {
        if (!Number.isFinite(waitSeconds) || waitSeconds < 0) {
            throw new ApiError("waitSeconds 必须是大于或等于 0 的有限秒数。", 0, "validation", "invalid_wait");
        }
        const deadline = Date.now() + waitSeconds * 1000;
        if (!Number.isFinite(deadline)) {
            throw new ApiError("waitSeconds 超出可表示的时间范围。", 0, "validation", "invalid_wait");
        }
        let lastTask;
        let failures = 0;
        while (Date.now() < deadline) {
            try {
                lastTask = await this.getTask(taskId, syncUpstream, { timeoutMs: TASK_QUERY_TIMEOUT_MS, deadline });
                failures = 0;
                await onPoll?.(lastTask);
                if (lastTask.status === "completed" || lastTask.status === "failed")
                    return lastTask;
            }
            catch (error) {
                if (Date.now() >= deadline)
                    break;
                if (!(error instanceof ApiError) || !error.retryable || ++failures >= MAX_POLL_FAILURES)
                    throw error;
            }
            const remaining = deadline - Date.now();
            if (remaining <= 0)
                break;
            await sleep(Math.min(POLL_INTERVAL_MS, remaining));
        }
        throw new PollBudgetExceededError(taskId, lastTask);
    }
    uploadBase64(fileData, fileName) {
        return this.request("POST", "/v1/files/upload/base64", {
            file_data: fileData, ...(fileName ? { file_name: fileName } : {}),
        });
    }
    uploadUrl(url, fileName) {
        return this.request("POST", "/v1/files/upload/url", { url, ...(fileName ? { file_name: fileName } : {}) });
    }
    async listLiveModels() {
        const result = await this.request("GET", "/v1/models");
        if (!result || !Array.isArray(result.data) || result.data.some((model) => !model || typeof model.id !== "string")) {
            const error = new ApiError("模型清单响应格式无效，无法确认模型可用性。", this.evidenceFor(result)?.response.http_status ?? 0, "protocol", "invalid_response");
            await observeRequestError(error, 'GET', '/v1/models', this.evidenceFor(result));
            throw error;
        }
        return new Map(result.data.map((model) => [model.id, model]));
    }
    /** LLM Custom registry is separate from GET /v1/models. */
    async listLlmModels() {
        const result = await this.request("GET", "/v1/configs/llm_generations_models");
        if (!result || !Array.isArray(result.data) || result.data.some((model) => !model || typeof model.id !== "string")) {
            const error = new ApiError("LLM 模型清单响应格式无效，无法确认理解模型能力。", this.evidenceFor(result)?.response.http_status ?? 0, "protocol", "invalid_response");
            await observeRequestError(error, 'GET', '/v1/configs/llm_generations_models', this.evidenceFor(result));
            throw error;
        }
        return result.data;
    }
    /** Gemini native music uses a different endpoint and cannot share async task submission. */
    async generateGeminiMusic(model, body) {
        const path = `/v1beta/models/${encodeURIComponent(model)}:generateContent`;
        const response = await this.request("POST", path, body, { retry: "non-idempotent" });
        if (!response || !Array.isArray(response.candidates)) {
            const error = new ApiError("Gemini 音乐响应缺少 candidates；原生请求结果不明，请勿自动重试。", this.evidenceFor(response)?.response.http_status ?? 0, "protocol", "invalid_response", undefined, true);
            await observeRequestError(error, 'POST', path, this.evidenceFor(response));
            throw error;
        }
        return response;
    }
    /** Preserve published raw pricing fields; callers must not invent derived prices. */
    async getPricing() {
        const result = await this.request("GET", "/api/pricing");
        if (!result || !Array.isArray(result.data)) {
            const error = new ApiError("定价清单响应格式无效。", this.evidenceFor(result)?.response.http_status ?? 0, "protocol", "invalid_response");
            await observeRequestError(error, 'GET', '/api/pricing', this.evidenceFor(result));
            throw error;
        }
        return { models: new Map(result.data.map((entry) => [entry.model_name, entry])), groupRatio: result.group_ratio ?? {} };
    }
}
