import { cp, readdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
await cp(new URL('../catalog/', import.meta.url), new URL('../.test-build/catalog/', import.meta.url), { recursive: true });
await cp(new URL('../package.json', import.meta.url), new URL('../.test-build/package.json', import.meta.url));
await cp(new URL('../references/', import.meta.url), new URL('../.test-build/references/', import.meta.url), { recursive: true });
await cp(new URL('../test/fixtures/', import.meta.url), new URL('../.test-build/test/fixtures/', import.meta.url), { recursive: true });
const tests = (await readdir(new URL('../.test-build/test/', import.meta.url))).filter(name => name.endsWith('.test.js')).map(name => `.test-build/test/${name}`);
// Windows private-record checks launch PowerShell; unbounded file concurrency
// can starve unrelated CLI timeout tests. Keep the suite bounded on that host.
const run = spawnSync(process.execPath, ['--test', ...(process.platform === 'win32' ? ['--test-concurrency=2'] : []), ...tests],
  { stdio: 'inherit', timeout: process.platform === 'win32' ? 900_000 : 180_000 });
if (run.error) console.error(run.error.message);
process.exit(run.status ?? 1);
