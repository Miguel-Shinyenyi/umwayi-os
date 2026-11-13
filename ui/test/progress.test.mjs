// W8 slice: the progress page. The parser is checked on small texts of its own, the built page is checked against a fresh render of
// the three source files (so a page older than its sources fails), and the page rules are checked on the built file.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { model, render, taskGroups, statusRows, highestLimit, firstSentence } from '../src/data/progress.js';

const ui = join(dirname(fileURLToPath(import.meta.url)), '..');
const repo = join(ui, '..');
const read = (p) => readFileSync(join(repo, p), 'utf8');
const html = readFileSync(join(ui, 'dist/progress.html'), 'utf8');

test('tasks are counted per group, and ### stays inside its group', () => {
  const g = taskGroups('# T\n\n## Status\n\n| a |\n\n## Layer 1: Memory (done, PR 1)\n- [x] 1.1 a\n- [ ] 1.2 b\n### Part 2\n- [X] 1.3 c\n  - [ ] 1.4 nested\n\n## Empty\ntext\n');
  assert.deepEqual(g, [{ name: 'Layer 1: Memory', done: 2, open: 2 }]);
});

test('status rows are read in file order and the header is not a row', () => {
  const r = statusRows('| date | PR | what | tests |\n| --- | --- | --- | --- |\n| 2026-11-13 | 85 | W2: map. More. | x |\n| 2026-11-12 | see the pull request | other | y |\n');
  assert.deepEqual(r.map((x) => [x.date, x.pr]), [['2026-11-13', '85'], ['2026-11-12', 'see the pull request']]);
});

test('the highest limit number is the largest, not the last', () => {
  assert.equal(highestLimit('### 9. a\n\n### 264. b\n\n### 12. c\n'), 264);
  assert.equal(highestLimit('nothing'), 0);
});

test('a first sentence drops code marks and is cut short', () => {
  assert.equal(firstSentence('W2: a `map` page. More text.'), 'W2: a map page.');
  assert.ok(firstSentence('word '.repeat(100)).length <= 240);
});

test('the page shows html safely', () => {
  const out = render({ groups: [{ name: 'A <b>', done: 1, open: 1 }], rows: [{ date: '2026-01-01', pr: '1', what: '<i>x</i>.' }], limit: 3 }, '2026-01-02');
  assert.ok(!out.groups.includes('<b>') && !out.rows.includes('<i>'));
});

test('the built page is what the three source files give now (date aside)', () => {
  const m = model({ statusLog: read('docs/status-log.md'), tasks: read('.kiro/specs/umwayi-os/tasks.md'), limits: read('docs/KNOWN-LIMITS.md') });
  const date = (html.match(/Built on (\d{4}-\d{2}-\d{2})\./) || [])[1];
  assert.ok(date, 'the page says the date it was built');
  const want = render(m, date);
  for (const key of ['groups', 'rows']) assert.ok(html.includes(want[key]), `stale: the ${key} differ from the sources (run node build.mjs in ui)`);
  assert.ok(html.includes(want.totals), 'stale: the totals differ');
  assert.ok(html.includes(`Highest known limit number: ${want.limit}`), 'stale: the highest limit differs');
  assert.equal(m.rows.length, 10);
  assert.equal((html.match(/<li data-group=/g) || []).length, m.groups.length);
});

test('the page has no http fetch, no form and no script src', () => {
  assert.ok(!/fetch\(|XMLHttpRequest|https?:\/\//i.test(html));
  assert.ok(!/<form|<input|<button|<textarea|<select/i.test(html));
  assert.ok(!/<script/i.test(html));
  assert.ok(!/\bsrc\s*=|\bhref\s*=|<link|<img|<iframe|@import|url\(/i.test(html));
  assert.ok(!html.includes('\u2014'));
  assert.ok(/default-src 'none'; style-src 'sha256-[^']+'; base-uri 'none'; form-action 'none'/.test(html));
});

test('the page code reads nothing of the logbook or .umwayi', () => {
  const code = readFileSync(join(ui, 'src/data/progress.js'), 'utf8');
  assert.ok(!/logbook|\.umwayi|readFile|fetch|import\(/i.test(code.replace(/^\/\/.*$/gm, '')));
});
