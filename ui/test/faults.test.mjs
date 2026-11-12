// UI.5 (tests first): the planted faults of 12.R10.6 that live in the page, and the map from each fault to the named test that
// kills it. The map is checked: every test it names must exist. docs/interface.md has the same table with the counts of the
// mutation pass. The faults of UI.2 (a title or path in the snapshot, a wrong count, the tamper check or the entry skipped,
// --out over rules.yaml) are killed by tests/test_view.py (PR 41: 23 planted, 20 killed, 3 equivalent).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const walk = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));
const srcFiles = walk(join(ROOT, 'src')).filter((f) => /\.(js|css|html)$/.test(f));
const read = (f) => readFileSync(f, 'utf8');

test('no style, font, script or image comes from an address: the template, the style and the sources hold no link element, no @import and no remote url()', () => {
  const template = read(join(ROOT, 'src', 'index.html')), css = read(join(ROOT, 'src', 'style.css'));
  assert.ok(!/<link\b/i.test(template), 'a link element would load a file');
  assert.ok(!/<script[^>]*\bsrc=/i.test(template) && !/<img\b|<iframe\b|<object\b|<embed\b/i.test(template));
  assert.ok(!/@import|@font-face/.test(css), 'a font or style import');
  for (const m of css.matchAll(/url\(([^)]*)\)/g)) assert.match(m[1].replace(/['"]/g, ''), /^data:/, `url(${m[1]})`);
  for (const f of srcFiles) {
    const t = read(f);
    for (const m of t.matchAll(/https?:\/\/[^\s"'`)<>\\]+/g)) {
      // the repo and docs addresses of the home page, the XML namespace three.js carries, and the addresses of sources named in comments
      assert.ok(/github\.com\/Miguel-Shinyenyi\/umwayi-os|www\.w3\.org\/1999\/xhtml/.test(m[0]) || /^\s*(\/\/|\/\*|\*)/.test(t.slice(t.lastIndexOf('\n', m.index) + 1, m.index)), `${f}: ${m[0]}`);
    }
  }
});

test('nothing in the sources asks for an animation frame or sets a timer outside the one loop and the Copy label', () => {
  const raf = srcFiles.filter((f) => f.endsWith('.js') && /requestAnimationFrame/.test(read(f))).map((f) => f.slice(ROOT.length + 5));
  assert.deepEqual(raf, ['scene.js'].map((x) => x), 'only the scene hands the loop its frame request');
  const timers = srcFiles.filter((f) => f.endsWith('.js') && /setInterval|setTimeout|requestIdleCallback/.test(read(f))).map((f) => f.slice(ROOT.length + 5).split('\\').join('/'));
  // The one exception (UI.7, 12.R16.4): boot.js keeps a single one-shot timer, HIGH_TIMEOUT_MS, that gives up on High after 15 s
  // and leaves Standard. It never redraws and never repeats, it is cleared as soon as High arrives or fails, and it runs only on
  // the public site (the live view passes no loadHigh, so boot() never starts it). Anything else in boot.js, or any other file, fails.
  assert.deepEqual(timers, ['boot.js', 'ui/home.js'], 'the only timers are the High time limit in boot.js and the one that puts the word Copy back on a button');
  const boot = read(srcFiles.find((f) => f.endsWith('boot.js')));
  assert.equal((boot.match(/\bset(Timeout|Interval)\(/g) || []).length, 1, 'boot.js sets exactly one timer');
  assert.ok(/setTimeout\([\s\S]{0,400}?HIGH_TIMEOUT_MS\)/.test(boot), 'the one timer in boot.js is the High time limit');
  assert.ok(!/setInterval|requestIdleCallback/.test(boot), 'boot.js repeats nothing');
});

// ---- the map: a fault of 12.R10.6 or of this slice, and the tests that kill it (file: test title)
export const MAP = [
  ['a fetch added to the page', ['ui/test/stations.test.mjs: no module loads a file, keeps a timer or draws by itself', 'tests/test_ui_package.py: test_a_fetch_in_the_page']],
  ['a second place in the page that sends a request, or the client called from the public site', ['ui/test/stations.test.mjs: no module loads a file, keeps a timer or draws by itself', 'tests/test_ui_package.py: test_a_fetch_before_or_after_the_region_or_in_the_markup', 'tests/test_ui_package.py: test_a_second_fetch_inside_the_region_or_none']],
  ['the page client runs on an address that is not http://127.0.0.1 and a port', ['ui/test/client.test.mjs: the client runs only on http://127.0.0.1 and a port; anywhere else it is closed, says so and sends nothing']],
  ['the token kept in a second place or shown in the page', ['ui/test/client.test.mjs: the token is held in one variable of the source: one let, one Bearer, and no place it could be kept', 'ui/test/backend.test.mjs: the token is nowhere in the page: no text, no attribute, no value, at any step', 'tests/test_ui_package.py: test_the_authorization_header_made_in_a_second_place']],
  ['a bad answer that does not stop the client', ['ui/test/client.test.mjs: every bad envelope or wrong status gives one message, forgets the token and stops all sending', 'ui/test/backend.test.mjs: a bad answer shows the one message, empties the queue, disables every control, and nothing more is sent']],
  ['a request sent without a token', ['ui/test/client.test.mjs: a call without a token sends nothing, for every route']],
  ['a policy that allows more than its own origin for connections', ['tests/test_ui_package.py: test_a_policy_without_connect_src_or_with_more_than_self']],
  ['text of a response set as markup in the panel', ['ui/test/backend.test.mjs: text from a response is set as text: markup in a title is shown as typed and nothing builds an element from it']],
  ['the panel asking by itself', ['ui/test/backend.test.mjs: Refresh asks again, by hand; the panel sets no timer and never asks by itself']],
  ['a font loaded from a CDN', ['ui/test/faults.test.mjs: no style, font, script or image comes from an address: the template, the style and the sources hold no link element, no @import and no remote url()', 'tests/test_ui_package.py: test_a_font_from_a_cdn']],
  ['a setInterval that redraws at rest', ['ui/test/stations.test.mjs: no module loads a file, keeps a timer or draws by itself', 'ui/test/faults.test.mjs: nothing in the sources asks for an animation frame or sets a timer outside the one loop and the Copy label']],
  ['an infinite animation loop in the style', ['ui/test/access.test.mjs: reduced motion removes every transition and animation, and nothing in the style loops']],
  ['a free running frame loop', ['ui/test/engine.test.mjs: invalidate draws exactly one frame when nothing moves']],
  ['reduced motion ignored by the tweens', ['ui/test/engine.test.mjs: with reduced motion a tween jumps to its end and nothing is scheduled']],
  ['reduced motion ignored when the page starts', ['ui/test/engine.test.mjs: reduced motion that is already on when the page starts is read at start (12.R5.4), and so is less contrast for Calm mode']],
  ['reduced motion ignored by the style', ['ui/test/access.test.mjs: reduced motion removes every transition and animation, and nothing in the style loops']],
  ['a page written by hand without a rebuild', ['tests/test_ui_package.py: test_a_page_edited_by_hand', 'tests/test_ui_package.py: test_a_source_changed_without_a_rebuild']],
  ['"passed" shown for a ticked check', ['ui/test/notes.test.mjs: a check is "not done" until every step is ticked, then "ticked by you", never "passed" or "verified"', 'ui/test/checksview.test.mjs: the word passed or verified is never the status of a check, in any state']],
  ['a value-looking result not warned', ['ui/test/notes.test.mjs: warning: an email address', 'ui/test/checksview.test.mjs: typing an email, a URL, a token or a hex string in a result shows a warning on that field; a plain exit code does not']],
  ['no text alternative for the picture', ['ui/test/access.test.mjs: the picture has a text alternative that says what it shows and where the list view is']],
  ['no language, title or landmark', ['ui/test/access.test.mjs: the page has a language, a title, a viewport and one main landmark, one banner and one footer']],
  ['a tick box under 24 pixels', ['ui/test/access.test.mjs: every control is at least 24 by 24 CSS pixels (WCAG 2.2, 2.5.8): buttons, the tick boxes and the text fields']],
  ['the focus ring removed', ["ui/test/access.test.mjs: a visible focus on everything: a 2px outline, and the only outline removed is the panel\\'s own, which has its own focus-visible"]],
  ['the placeholder left to the browser default', ['ui/test/contrast.test.mjs: UI.5: the placeholder of a result field is coloured on purpose (the browser default is too faint) and keeps 4.5 to 1']],
  ['a faint field border', ['ui/test/contrast.test.mjs: UI.5: the border of a result field and of the notes box keeps 3 to 1 against what is inside and what is around it (WCAG 1.4.11)']],
  ['Calm text below the 4.5 to 1 floor', ['ui/test/contrast.test.mjs: UI.5: ink and muted text keep 4.5 to 1 on every ground the CSS puts them on, in normal and in Calm mode']],
  ['a positive tabindex', ['ui/test/access.test.mjs: no positive tabindex, and the only tabindex values are 0 and -1']],
  ['a button without a name', ['ui/test/access.test.mjs: every button has a name, and a button that only says Copy or Replay is told apart by its aria-label or its place']],
  ['a live region lost', ['ui/test/access.test.mjs: each message the page gives is in a live region that a screen reader announces']],
  ['a landmark without a name', ['ui/test/access.test.mjs: every section, nav and aside is a named landmark, and every name points at a heading or label that exists']],
  ['a heading level skipped', ['ui/test/access.test.mjs: headings go down one level at a time, from the one h1']],
  ['the checks panel wider than a phone', ['ui/test/access.test.mjs: the owner checks panel fits a phone: its grid may shrink, long words wrap, a code block scrolls inside its own box']],
  ['the station panel not a bottom sheet on a phone', ['ui/test/access.test.mjs: the station panel is a bottom sheet on a phone: full width at the bottom, scrolls inside itself and leaves the picture its top half']],
  ['the top bar over the checks title', ['ui/test/access.test.mjs: the fixed top bar does not cover the title of the owner checks panel when it is scrolled into view']],
  ['the list view order changed', ['ui/test/placement.test.mjs: the default positions equal the table of the design']],
];

test('every test the map names exists', () => {
  const py = {};
  for (const [, tests] of MAP) {
    for (const t of tests) {
      const i = t.indexOf(': '), file = t.slice(0, i), title = t.slice(i + 2);
      const text = readFileSync(join(ROOT, '..', file), 'utf8');
      if (file.endsWith('.py')) assert.ok(new RegExp(`def ${title}\\(`).test(text), t);
      else assert.ok(text.includes(`test('${title}'`), t);
      py[file] = true;
    }
  }
  assert.ok(MAP.length >= 25);
});
