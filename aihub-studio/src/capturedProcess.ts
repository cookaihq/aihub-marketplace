import { execFile, spawn } from 'node:child_process';
import { mkdir, mkdtemp, open, rm, type FileHandle } from 'node:fs/promises';
import { join, resolve, toNamespacedPath } from 'node:path';
import { promisify } from 'node:util';

const exec = promisify(execFile);
export interface CaptureOptions {
  cwd?: string; env?: NodeJS.ProcessEnv; timeout?: number; maxBuffer?: number;
  killSignal?: NodeJS.Signals; signal?: AbortSignal; windowsHide?: boolean;
  encoding?: BufferEncoding | 'buffer';
  prepareCapture?: (stdout: string, stderr: string, signal: AbortSignal) => Promise<void>;
}
export interface CaptureResult<T> { stdout: T; stderr: T }
type ProcessError = Error & {
  code?: string | number; killed?: boolean; signal?: NodeJS.Signals | null;
  stdout?: string | Buffer; stderr?: string | Buffer;
};
function abortError(signal: AbortSignal): ProcessError {
  return Object.assign(new Error('The operation was aborted', { cause: signal.reason }), { name: 'AbortError', code: 'ABORT_ERR' });
}

/** Regular file handles avoid libuv's Windows named-pipe creation under restricted tokens.
 * No shell, retry, identity change or sandbox exception is involved. Only the ACL
 * bootstrap uses this directly; media calls protect both empty captures first.
 */
export function runCaptured(file: string, args: readonly string[], options: CaptureOptions & { encoding: 'buffer' }): Promise<CaptureResult<Buffer>>;
export function runCaptured(file: string, args: readonly string[], options?: CaptureOptions): Promise<CaptureResult<string>>;
export async function runCaptured(file: string, args: readonly string[], options: CaptureOptions = {}): Promise<CaptureResult<string | Buffer>> {
  const maxBuffer = options.maxBuffer ?? 1024 * 1024;
  const timeout = options.timeout ?? 0;
  if (!Number.isSafeInteger(maxBuffer) || maxBuffer < 0 || !Number.isSafeInteger(timeout) || timeout < 0) {
    throw new RangeError('Subprocess output and time budgets must be nonnegative safe integers.');
  }
  if (options.signal?.aborted) throw abortError(options.signal);
  if (process.platform !== 'win32') {
    const { prepareCapture: _, ...native } = options;
    return exec(file, [...args], { ...native, encoding: options.encoding === 'buffer' ? 'buffer' : options.encoding ?? 'utf8', maxBuffer, timeout });
  }
  const parent = resolve(options.cwd ?? process.cwd(), 'tmp', 'aihub-studio-process');
  const cancellation = new AbortController();
  const onUserAbort = (): void => cancellation.abort(abortError(options.signal!));
  options.signal?.addEventListener('abort', onUserAbort, { once: true });
  const timer = timeout ? setTimeout(() => cancellation.abort(Object.assign(new Error('Subprocess timed out'), { code: 'ETIMEDOUT', killed: true })), timeout) : undefined;
  let directory: string | undefined;
  let failed = false;
  const handles: FileHandle[] = [];
  try {
    await mkdir(parent, { recursive: true });
    // mkdtemp needs an extended-length Windows path even when mkdir succeeds
    // with the same long parent. Preserve the actual project/cwd location.
    directory = await mkdtemp(join(toNamespacedPath(parent), 'capture-'));
    const paths = [join(directory, 'stdout'), join(directory, 'stderr')] as const;
    await options.prepareCapture?.(...paths, cancellation.signal);
    for (const path of paths) handles.push(await open(path, options.prepareCapture ? 'r+' : 'wx+', 0o600));
    if (cancellation.signal.aborted) throw cancellation.signal.reason;
    const stdoutHandle = handles[0]!; const stderrHandle = handles[1]!;
    const child = spawn(file, [...args], { cwd: options.cwd === undefined ? undefined : toNamespacedPath(resolve(options.cwd)), env: options.env,
      windowsHide: options.windowsHide ?? true, stdio: ['ignore', stdoutHandle.fd, stderrHandle.fd] });
    let failure: ProcessError | undefined;
    let closed = false;
    let escalation: ReturnType<typeof setTimeout> | undefined;
    const stop = (error: ProcessError): void => {
      if (failure || closed) return;
      failure = error;
      child.kill(options.killSignal ?? 'SIGTERM');
      escalation = setTimeout(() => child.kill('SIGKILL'), 1_000);
      escalation.unref();
    };
    const budgetError = (stream: string): ProcessError => Object.assign(
      new RangeError(`${stream} maxBuffer length exceeded`), { code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER', killed: true });
    let checking = false;
    // Reject oversized output even when a short process exits between checks.
    // Polling bounds retained bytes; disk use can briefly overshoot before kill.
    const checkBudget = async (): Promise<void> => {
      if (checking || failure) return;
      checking = true;
      try {
        for (let i = 0; i < handles.length; i++) {
          if ((await handles[i]!.stat()).size > maxBuffer) { stop(budgetError(i === 0 ? 'stdout' : 'stderr')); break; }
        }
      } catch (error) { stop(error as ProcessError); }
      finally { checking = false; }
    };
    const budgetTimer = setInterval(() => { void checkBudget(); }, 10);
    const onAbort = (): void => stop(cancellation.signal.reason as ProcessError);
    cancellation.signal.addEventListener('abort', onAbort, { once: true });
    // No await between spawning, installing listeners and subscribing to close.
    const result = await new Promise<{ code: number | null; signal: NodeJS.Signals | null }>(resolveClose => {
      child.once('error', error => { failure ??= error; });
      child.once('close', (code, signal) => resolveClose({ code, signal }));
    }).finally(() => {
      closed = true;
      clearInterval(budgetTimer); clearTimeout(escalation);
      cancellation.signal.removeEventListener('abort', onAbort);
    });
    // Await any in-flight stat before reading/closing the handles.
    while (checking) await new Promise<void>(done => setTimeout(done, 1));
    const buffers: Buffer[] = [];
    for (let i = 0; i < handles.length; i++) {
      const handle = handles[i]!; const size = (await handle.stat()).size;
      if (size > maxBuffer) failure ??= budgetError(i === 0 ? 'stdout' : 'stderr');
      const buffer = Buffer.alloc(Math.min(size, maxBuffer));
      let offset = 0;
      while (offset < buffer.length) {
        const { bytesRead } = await handle.read(buffer, offset, buffer.length - offset, offset);
        if (!bytesRead) break;
        offset += bytesRead;
      }
      buffers.push(buffer.subarray(0, offset));
    }
    const decode = (buffer: Buffer): string | Buffer => options.encoding === 'buffer' ? buffer : buffer.toString(options.encoding ?? 'utf8');
    const output = { stdout: decode(buffers[0]!), stderr: decode(buffers[1]!) };
    if (failure || result.code !== 0) {
      failure ??= Object.assign(new Error(`Command failed: ${file} (exit ${result.code ?? result.signal})`), { code: result.code ?? undefined });
      throw Object.assign(failure, output, { signal: result.signal });
    }
    return output;
  } catch (error) {
    failed = true;
    throw cancellation.signal.aborted ? cancellation.signal.reason : error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', onUserAbort);
    const cleanup = await Promise.allSettled(handles.map(handle => handle.close()));
    if (directory) cleanup.push(...await Promise.allSettled([rm(directory, { recursive: true, force: true })]));
    const cleanupFailure = cleanup.find(result => result.status === 'rejected');
    // A cleanup failure must not replace the actual launch/exit/timeout error.
    if (!failed && cleanupFailure?.status === 'rejected') throw cleanupFailure.reason;
  }
}
