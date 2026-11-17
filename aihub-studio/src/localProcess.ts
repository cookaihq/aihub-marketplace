import { runCaptured, type CaptureOptions, type CaptureResult } from './capturedProcess.js';
import { createPrivateFile } from './privateFile.js';

type LocalOptions = Omit<CaptureOptions, 'prepareCapture'>;
export function runLocalTool(file: string, args: readonly string[], options: LocalOptions & { encoding: 'buffer' }): Promise<CaptureResult<Buffer>>;
export function runLocalTool(file: string, args: readonly string[], options?: LocalOptions): Promise<CaptureResult<string>>;
export function runLocalTool(file: string, args: readonly string[], options: LocalOptions = {}): Promise<CaptureResult<string | Buffer>> {
  const capture = { ...options, prepareCapture: createPrivateFile };
  return options.encoding === 'buffer' ? runCaptured(file, args, { ...capture, encoding: 'buffer' }) : runCaptured(file, args, capture);
}
