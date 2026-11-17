import { runCaptured } from './capturedProcess.js';
import { createPrivateFile } from './privateFile.js';
export function runLocalTool(file, args, options = {}) {
    const capture = { ...options, prepareCapture: createPrivateFile };
    return options.encoding === 'buffer' ? runCaptured(file, args, { ...capture, encoding: 'buffer' }) : runCaptured(file, args, capture);
}
