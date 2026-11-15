// W51a: one `next build` for one `node --test` run. The test files of site/test run as separate processes at the same time, and
// two of them need the built site (the phone layout test serves it, the icon test reads its head). Two builds into the same .next
// at once can break each other, so the first file to get here builds and the others wait for it. A run is the parent process of
// the test files (node --test), so every file of one run shares one build, and a later run builds again.
// Only the tests use this; the owner and Vercel build with `npm run build` as before.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = join(dirname(fileURLToPath(import.meta.url)), '..');
const LOCK = join(SITE, '.next-build-lock');
const MARK = join(SITE, '.next', 'umwayi-test-run');
const STALE_MS = 15 * 60 * 1000;
const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
const run = String(process.ppid);
const built = () => existsSync(MARK) && readFileSync(MARK, 'utf8') === run;

// returns { status, out }: status 0 when the site is built for this run
export function buildOnce({ timeoutMs = 10 * 60 * 1000 } = {}) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (built()) return { status: 0, out: 'built by another test file of this run' };
    try {
      mkdirSync(LOCK);
    } catch {
      try { if (Date.now() - statSync(LOCK).mtimeMs > STALE_MS) rmSync(LOCK, { recursive: true, force: true }); } catch { /* gone */ }
      sleep(500);
      continue;
    }
    try {
      if (built()) return { status: 0, out: 'built by another test file of this run' };
      const r = spawnSync(process.execPath, ['scripts/next.mjs', 'build'], { cwd: SITE, encoding: 'utf8' });
      if (r.status === 0) writeFileSync(MARK, run);
      return { status: r.status, out: `${(r.stdout || '').slice(-600)} ${(r.stderr || '').slice(-600)}` };
    } finally {
      rmSync(LOCK, { recursive: true, force: true });
    }
  }
  return { status: null, out: 'no build within the time limit' };
}
