// W1 (mobile first): the live view, rendered by a real browser at the four phone sizes, in portrait and on its side. It fails when
// two text boxes or controls overlap anywhere on the page (the header, the mode row, the hero text, the station panel, the owner
// checks panel, the sections below), when anything shows past the left or right edge, when the page scrolls sideways, when a
// control is under 44 pixels, or when the header is drawn in a different order from the order Tab takes (owner checks 1.11).
// It needs a Chromium; see ui/tools/browser.mjs. With none it skips and says how to run it by hand (UMWAYI_REQUIRE_BROWSER=1
// makes a missing browser a failure). It makes no network request: the page is opened from disk.
import test from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { findBrowser, launch, HOW_TO_RUN } from '../tools/browser.mjs';
import { PHONES, PHONES_LANDSCAPE, runPhones, problemsOf } from '../tools/phone-audit.mjs';
import { scenario } from '../tools/phone-scenario.mjs';

const PAGE = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'index.html')).href;
const exe = findBrowser();
const skip = exe ? false : HOW_TO_RUN;
if (!exe && process.env.UMWAYI_REQUIRE_BROWSER) throw new Error(HOW_TO_RUN);

let browser = null;
test.before(async () => { if (exe) browser = await launch(exe); });
test.after(async () => { if (browser) await browser.close(); });

for (const [name, phones] of [['portrait', PHONES], ['landscape', PHONES_LANDSCAPE]]) {
  test(`the live view on a phone in ${name}: no overlapping text, no sideways overflow, touch targets of 44 pixels, header in Tab order`, { skip, timeout: 240000 }, async (t) => {
    const { results, extras } = await runPhones(browser, PAGE, scenario, { phones });
    for (const e of extras) for (const n of e.notes) t.diagnostic(n);
    t.diagnostic(`${results.length} states audited in ${await browser.version()}`);
    assert.deepEqual(problemsOf(results), []);
    for (const r of results) assert.deepEqual(r.order.visual, r.order.dom, `${r.phone} ${r.state}: the header is drawn in a different order from Tab`);
    for (const e of extras) {
      assert.deepEqual(e.visited.slice(0, 3), ['list', 'standard', 'checks-open'], `${e.phone}: Tab order of the header`);
      assert.equal(e.visited[3], 'calm-toggle', `${e.phone}: Tab order of the header`);
      assert.equal(e.tabAfterChecksOpen, 'checks-title', `${e.phone}: the owner checks panel takes the focus when it opens`);
      assert.equal(e.focusAfterClose, 'checks-open', `${e.phone}: and gives it back to the button that opened it`);
      assert.equal(e.expandedAfterClose, 'false');
    }
  });
}
