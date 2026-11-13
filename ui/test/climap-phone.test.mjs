// W2: the command map on a phone, in a real Chromium, at the four phone sizes upright and on their side. It uses the same audit as
// the live view (ui/tools/phone-audit.mjs): no overlapping text, no sideways overflow, no control under 44 pixels. Each group is
// audited closed and then all opened. Needs a Chromium (UMWAYI_BROWSER names one); with none it skips like phone.test.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { findBrowser, launch, HOW_TO_RUN } from '../tools/browser.mjs';
import { PHONES, PHONES_LANDSCAPE, runPhones, problemsOf } from '../tools/phone-audit.mjs';

const PAGE = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'cli-map.html')).href;
const exe = findBrowser();
const skip = exe ? false : HOW_TO_RUN;
if (!exe && process.env.UMWAYI_REQUIRE_BROWSER) throw new Error(HOW_TO_RUN);

let browser = null;
test.before(async () => { if (exe) browser = await launch(exe); });
test.after(async () => { if (browser) await browser.close(); });

async function scenario(page, check) {
  await check('closed', null);
  await check('all groups open', () => page.evaluate(() => { for (const d of document.querySelectorAll('details')) d.open = true; }));
  return {};
}

for (const [name, phones] of [['portrait', PHONES], ['landscape', PHONES_LANDSCAPE]]) {
  test(`the command map on a phone in ${name}: no overlap, no sideways overflow, 44 pixel rows`, { skip, timeout: 120000 }, async () => {
    const { results } = await runPhones(browser, PAGE, scenario, { phones });
    assert.deepEqual(problemsOf(results), []);
  });
}
