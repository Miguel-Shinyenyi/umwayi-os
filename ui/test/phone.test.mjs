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

async function check(t, phones) {
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
}

test('the live view on a phone in portrait: no overlapping text, no sideways overflow, touch targets of 44 pixels, header in Tab order', { skip, timeout: 240000 }, (t) => check(t, PHONES));
test('the live view on a phone in landscape: no overlapping text, no sideways overflow, touch targets of 44 pixels, header in Tab order', { skip, timeout: 240000 }, (t) => check(t, PHONES_LANDSCAPE));

// The name of the selected feature is placed from the picture, so it can land where the station panel is. The page moves it out
// (src/app.js, panelBox). Fonts decide how close it comes by itself, so this test makes it certain: the panel is stretched over
// the place of the name and the page is asked to lay out again; the name must end up clear of the panel, left of a card at the
// side and above a sheet at the bottom.
test('the name of the selected feature moves out from under the station panel, beside a side card and above a bottom sheet', { skip, timeout: 120000 }, async () => {
  for (const [width, height, over] of [[640, 360, [['left', '150px'], ['width', 'auto'], ['right', '8px']]], [390, 844, [['top', '150px'], ['max-height', 'none']]]]) {
    const page = await browser.newPage();
    try {
      await page.emulate({ width, height });
      await page.goto(PAGE);
      await new Promise((r) => setTimeout(r, 600));
      await page.evaluate(() => document.querySelector('[data-tier="standard"]').click());
      for (let i = 0; i < 40 && !(await page.evaluate(() => document.documentElement.dataset.tier === 'standard')); i++) await new Promise((r) => setTimeout(r, 250));
      if (!(await page.evaluate(() => document.documentElement.dataset.tier === 'standard'))) continue; // no WebGL here: there is no picture to name
      await new Promise((r) => setTimeout(r, 2000));
      await page.evaluate((rules) => {
        const panel = document.querySelector('#panel');
        for (const [k, v] of rules) panel.style.setProperty(k, v, 'important'); // the CSSOM is allowed under the page's policy; a style element is not
        document.querySelector('.label[data-station="rules"]').click();
      }, over);
      await new Promise((r) => setTimeout(r, 500));
      await page.evaluate(() => window.dispatchEvent(new Event('resize')));
      await new Promise((r) => setTimeout(r, 600));
      const r = await page.evaluate(() => {
        const l = document.querySelector('.label.is-selected').getBoundingClientRect(), p = document.querySelector('#panel').getBoundingClientRect();
        return { w: Math.min(l.right, p.right) - Math.max(l.left, p.left), h: Math.min(l.bottom, p.bottom) - Math.max(l.top, p.top), l: [l.left, l.top], p: [p.left, p.top] };
      });
      assert.ok(!(r.w > 0 && r.h > 0), `${width}x${height}: the name still overlaps the panel by ${Math.round(r.w)} x ${Math.round(r.h)} px (name at ${r.l}, panel at ${r.p})`);
    } finally {
      await page.close();
    }
  }
});
