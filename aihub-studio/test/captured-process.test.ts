import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { runCaptured } from '../src/capturedProcess.js';
import { runLocalTool } from '../src/localProcess.js';
import { createPrivateFile } from '../src/privateFile.js';
import { writePrivateRecord } from '../src/state.js';

async function workspace(run: (cwd: string) => Promise<void>): Promise<void> {
  const base = resolve(process.env.AIHUB_CAPTURE_TEST_ROOT ?? 'tmp/aihub-studio-tests/capture');
  await mkdir(base, { recursive: true });
  const cwd = await mkdtemp(join(base, 'case-'));
  try {
    await run(cwd);
    if (process.platform === 'win32') {
      const entries = await readdir(join(cwd, 'tmp/aihub-studio-process')).catch((error: NodeJS.ErrnoException) => {
        if (error.code === 'ENOENT') return [];
        throw error;
      });
      assert.deepEqual(entries, []);
    }
  } finally { await rm(cwd, { recursive: true, force: true }); }
}
const nodeArgs = (source: string, ...args: string[]): string[] => ['--preserve-symlinks', '--preserve-symlinks-main', '-e', source, ...args];

test('capture preserves argv, UTF-8 and binary stdout without shell expansion', async () => workspace(async cwd => {
  const args = ['two words', '中文🙂', 'literal "quote"', '$(`literal`)', 'line\nbreak', ''];
  const result = await runCaptured(process.execPath, nodeArgs('process.stdout.write(JSON.stringify(process.argv.slice(1))); process.stderr.write("错误🙂")', ...args), { cwd });
  assert.deepEqual(JSON.parse(result.stdout), args); assert.equal(result.stderr, '错误🙂');
  const binary = await runCaptured(process.execPath, nodeArgs('process.stdout.write(Buffer.from([0,255,128,10]))'), { cwd, encoding: 'buffer' });
  assert.deepEqual(binary.stdout, Buffer.from([0,255,128,10]));
}));

test('capture retains nonzero exit diagnostics and original spawn error fields', async () => workspace(async cwd => {
  await assert.rejects(runCaptured(process.execPath, nodeArgs('process.stdout.write("before"); process.stderr.write("original context"); process.exitCode=7'), { cwd }), error => {
    const e = error as Error & { code: number; stdout: string; stderr: string };
    assert.equal(e.code, 7); assert.equal(e.stdout, 'before'); assert.equal(e.stderr, 'original context'); return true;
  });
  await assert.rejects(runCaptured(join(cwd, 'missing-program'), [], { cwd }), error => {
    const e = error as NodeJS.ErrnoException; assert.equal(e.code, 'ENOENT'); assert.match(e.syscall!, /^spawn/); return true;
  });
}));

test('timeouts and AbortSignal stop the actual child and retain partial output', async () => workspace(async cwd => {
  const program = nodeArgs('process.stdout.write(String(process.pid)); setInterval(()=>{},100)');
  for (const abort of [false, true]) {
    const controller = new AbortController();
    const timer = abort ? setTimeout(() => controller.abort(), 1000) : undefined;
    try {
      await assert.rejects(runCaptured(process.execPath, program, { cwd, timeout: abort ? 10000 : 1000, signal: controller.signal }), error => {
        const e = error as Error & { code: string; stdout: string; killed?: boolean };
        assert.ok(abort ? e.name === 'AbortError' : e.killed);
        const pid = Number(e.stdout); assert.ok(pid > 0);
        assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' }); return true;
      });
    } finally { clearTimeout(timer); }
  }
  const controller = new AbortController(); controller.abort();
  await assert.rejects(runCaptured(process.execPath, program, { cwd, signal: controller.signal }), { name: 'AbortError' });
}));

test('both output streams enforce their own budget, including quick exit and a running producer', async () => workspace(async cwd => {
  for (const stream of ['stdout', 'stderr']) for (const running of [false, true]) {
    const source = running ? `setInterval(()=>process.${stream}.write(Buffer.alloc(4096)),1)` : `process.${stream}.write(Buffer.alloc(4096))`;
    await assert.rejects(runCaptured(process.execPath, nodeArgs(source), { cwd, maxBuffer: 64, timeout: 10000, encoding: 'buffer' }), error => {
      const e = error as Error & { code: string; stdout: Buffer; stderr: Buffer };
      assert.equal(e.code, 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER'); assert.ok(e.stdout.length <= 64); assert.ok(e.stderr.length <= 64); return true;
    });
  }
}));

test('concurrent captures keep output isolated and remove temporary files', async () => workspace(async cwd => {
  const results = await Promise.all(Array.from({ length: 8 }, (_, i) => runCaptured(process.execPath,
    nodeArgs('setTimeout(()=>{process.stdout.write(process.argv[1]);process.stderr.write(process.argv[1]+"!")},Math.random()*20)', `job-${i}`), { cwd })));
  results.forEach((r, i) => { assert.equal(r.stdout, `job-${i}`); assert.equal(r.stderr, `job-${i}!`); });
}));

test('private creation refuses existing files; protected captures and atomic records remain readable', async () => workspace(async cwd => {
  // Private creation uses the current project identity; all paths stay within it.
  const existing = join(cwd, 'existing'); await writeFile(existing, 'keep');
  await assert.rejects(createPrivateFile(existing)); assert.equal(await readFile(existing, 'utf8'), 'keep');
  const record = join(cwd, 'record.json');
  await writePrivateRecord(record, { revision: 1 }); await writePrivateRecord(record, { revision: 2 });
  assert.equal(JSON.parse(await readFile(record, 'utf8')).revision, 2);
  const result = await runLocalTool(process.execPath, nodeArgs('process.stdout.write("private output")'), { cwd });
  assert.equal(result.stdout, 'private output');
}));

test('private files, atomic records and protected captures work in deep Unicode paths', async () => workspace(async cwd => {
  let deep = cwd;
  while (deep.length < 310) deep = join(deep, '中文 space deep segment');
  await mkdir(deep, { recursive: true });
  const file = join(deep, 'private 文件.json');
  await createPrivateFile(file);
  await writeFile(file, 'private');
  assert.equal(await readFile(file, 'utf8'), 'private');
  const record = join(deep, 'record.json');
  await writePrivateRecord(record, { revision: 1 });
  await writePrivateRecord(record, { revision: 2 });
  assert.equal(JSON.parse(await readFile(record, 'utf8')).revision, 2);
  const result = await runLocalTool(process.execPath, nodeArgs('process.stdout.write(process.argv[1])', 'deep 中文 output'), { cwd: deep });
  assert.equal(result.stdout, 'deep 中文 output');
  if (process.platform === 'win32') assert.deepEqual(await readdir(join(deep, 'tmp/aihub-studio-process')), []);
}));

test('Windows time and cancellation budgets include private capture preparation', { skip: process.platform !== 'win32' }, async () => workspace(async cwd => {
  const marker = join(cwd, 'must-not-start');
  const args = nodeArgs('require("node:fs").writeFileSync(process.argv[1],"started")', marker);
  await assert.rejects(runLocalTool(process.execPath, args, { cwd, timeout: 1 }), { code: 'ETIMEDOUT' });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('stop during setup'), 1);
  try { await assert.rejects(runLocalTool(process.execPath, args, { cwd, signal: controller.signal }), { name: 'AbortError' }); }
  finally { clearTimeout(timer); }
  await assert.rejects(readFile(marker), { code: 'ENOENT' });
}));

test('failed capture preparation retains its original error and cleans partial files', { skip: process.platform !== 'win32' }, async () => workspace(async cwd => {
  const original = new Error('private preparation failed');
  await assert.rejects(runCaptured(process.execPath, nodeArgs('process.exit(0)'), {
    cwd, prepareCapture: async stdout => { await writeFile(stdout, ''); throw original; },
  }), error => error === original);
}));
