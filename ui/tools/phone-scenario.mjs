// What a visitor does on a phone, in order, for the layout audit (W1). The same walk is used for the live view (ui/dist/index.html)
// and for the public site's HTML. Each `check(name, prepare)` renders the state and audits it.
import { STATIONS } from '../src/stations/meta.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (page, selector) => page.evaluate((s) => { const e = document.querySelector(s); if (e) e.click(); return !!e; }, selector);

export async function scenario(page, check, phone) {
  const notes = [];
  // List first: it needs no WebGL
  await check('List', async () => { await click(page, '[data-tier="list"]'); await sleep(200); });
  await check('List, Owner checks open', async () => { await click(page, '#checks-open-list'); await sleep(300); });
  await click(page, '#checks-close');
  await page.evaluate(() => window.scrollTo(0, 0));

  // Standard: the picture, the hint, the sample tag and the panel of each station
  const standard = await (async () => {
    await click(page, '[data-tier="standard"]');
    for (let i = 0; i < 40; i++) {
      if (await page.evaluate(() => document.documentElement.dataset.tier === 'standard' && !!document.querySelector('#scene').getContext)) break;
      await sleep(250);
    }
    return page.evaluate(() => document.documentElement.dataset.tier === 'standard');
  })();
  if (!standard) {
    // no WebGL in this browser: the page fell back to List with words. The layout rules are keyed on data-tier, so the Standard
    // layout is still audited with the attribute set by hand, and the stations' panels are skipped.
    notes.push(`${phone.name}: no WebGL here, Standard layout audited with data-tier set by hand`);
    await page.evaluate(() => { document.documentElement.dataset.tier = 'standard'; });
  }
  await check('Standard', null);
  await check('Standard, Calm mode', async () => { await click(page, '#calm-toggle'); await sleep(200); });
  await click(page, '#calm-toggle');
  await check('Standard, Owner checks open', async () => { await click(page, '#checks-open'); await sleep(300); });
  const tab = await page.evaluate(() => ({ focus: document.activeElement && document.activeElement.id }));
  await click(page, '#checks-close');
  const back = await page.evaluate(() => ({ focus: document.activeElement && document.activeElement.id, expanded: document.getElementById('checks-open').getAttribute('aria-expanded') }));
  await page.evaluate(() => window.scrollTo(0, 0));
  if (standard) {
    // the panels with the most text are the hardest to fit: the three longest are audited
    const size = (s) => [s.name, ...s.lines, s.note || '', s.command].join(' ').length;
    for (const s of [...STATIONS].sort((a, b) => size(b) - size(a)).slice(0, 3)) {
      await check(`Standard, ${s.name} panel`, async () => { await click(page, `.label[data-station="${s.id}"]`); await sleep(300); });
      await click(page, '#back');
      await page.evaluate(() => window.scrollTo(0, 0));
      await sleep(100);
    }
  }
  // the keyboard: Tab from the top visits the header in the order it is drawn
  await page.evaluate(() => { window.scrollTo(0, 0); document.activeElement && document.activeElement.blur(); });
  const visited = [];
  for (let i = 0; i < 5; i++) {
    await page.key('Tab');
    visited.push(await page.evaluate(() => { const e = document.activeElement; return e ? (e.dataset.tier || e.id || e.tagName.toLowerCase()) : null; }));
  }
  return { notes, tabAfterChecksOpen: tab.focus, focusAfterClose: back.focus, expandedAfterClose: back.expanded, visited, standard };
}
