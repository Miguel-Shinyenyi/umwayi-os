// W1 (mobile first): the public site, built and served by next start on 127.0.0.1, rendered by a real browser at the four phone
// sizes in portrait and on its side. The same audit as the live view (ui/test/phone.test.mjs): no overlapping text or controls
// anywhere, nothing past the left or right edge, no sideways scroll, controls of 44 pixels, the header drawn in the order Tab
// takes. The site also has the High button, so its header is the widest. Needs a Chromium (ui/tools/browser.mjs); with none it
// skips and says how to run it by hand. It builds into site/.next (ignored by git) and talks to 127.0.0.1 only.
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findBrowser, launch, HOW_TO_RUN } from '../../ui/tools/browser.mjs';
import { PHONES, PHONES_LANDSCAPE, runPhones, problemsOf } from '../../ui/tools/phone-audit.mjs';
import { scenario } from '../../ui/tools/phone-scenario.mjs';

const SITE = join(dirname(fileURLToPath(import.meta.url)), '..');
const exe = findBrowser();
const skip = exe ? false : HOW_TO_RUN;
if (!exe && process.env.UMWAYI_REQUIRE_BROWSER) throw new Error(HOW_TO_RUN);

const freePort = () => new Promise((resolve, reject) => {
  const s = createServer();
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
  s.on('error', reject);
});

let browser = null, server = null, url = null;
test.before(async () => {
  if (!exe) return;
  const built = spawnSync(process.execPath, ['scripts/next.mjs', 'build'], { cwd: SITE, encoding: 'utf8' });
  assert.equal(built.status, 0, `next build failed: ${built.stdout.slice(-600)} ${built.stderr.slice(-600)}`);
  const port = await freePort();
  server = spawn(process.execPath, ['scripts/next.mjs', 'start', '-H', '127.0.0.1', '-p', String(port)], { cwd: SITE, stdio: 'ignore' });
  url = `http://127.0.0.1:${port}/`;
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(url)).ok) break; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  browser = await launch(exe);
});
test.after(async () => {
  if (browser) await browser.close();
  if (server) server.kill('SIGKILL');
});

for (const [name, phones] of [['portrait', PHONES], ['landscape', PHONES_LANDSCAPE]]) {
  test(`the public site on a phone in ${name}: no overlapping text, no sideways overflow, touch targets of 44 pixels, header in Tab order`, { skip, timeout: 240000 }, async (t) => {
    const { results, extras } = await runPhones(browser, url, scenario, { phones });
    for (const e of extras) for (const n of e.notes) t.diagnostic(n);
    t.diagnostic(`${results.length} states audited in ${await browser.version()}`);
    assert.deepEqual(problemsOf(results), []);
    for (const r of results) assert.deepEqual(r.order.visual, r.order.dom, `${r.phone} ${r.state}: the header is drawn in a different order from Tab`);
    for (const e of extras) {
      assert.deepEqual(e.visited.slice(0, 4), ['list', 'standard', 'high', 'checks-open'], `${e.phone}: Tab order of the header`);
      assert.equal(e.visited[4], 'calm-toggle', `${e.phone}: Tab order of the header`);
      assert.equal(e.tabAfterChecksOpen, 'checks-title', `${e.phone}: the owner checks panel takes the focus when it opens`);
      assert.equal(e.focusAfterClose, 'checks-open', `${e.phone}: and gives it back to the button that opened it`);
    }
  });
}
