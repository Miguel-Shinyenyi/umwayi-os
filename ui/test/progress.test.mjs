// W8 slice: the progress page. The parser is checked on small texts of its own, the built page is checked against itself, and the page rules are checked on the built file.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { model, shown, render, taskGroups, statusRows, highestLimit, firstSentence } from '../src/data/progress.js';

const ui = join(dirname(fileURLToPath(import.meta.url)), '..');
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

test('the built page agrees with itself: the totals are the sum of the groups and ten rows are shown', () => {
  // staleness against the three source files is checked without npm by tests/test_progress_page.py (hashes in dist/build.json)
  assert.ok(/Built on \d{4}-\d{2}-\d{2}\./.test(html), 'the page says the date it was built');
  const groups = [...html.matchAll(/<li data-group="[^"]*">.*?<span class="done">(\d+) done<\/span><span class="open">(\d+) open<\/span>/g)];
  assert.ok(groups.length > 0);
  const done = groups.reduce((a, g) => a + Number(g[1]), 0);
  const open = groups.reduce((a, g) => a + Number(g[2]), 0);
  assert.ok(html.includes(`${done} tasks done and ${open} open, in ${groups.length} groups.`));
  assert.equal((html.match(/<span class="when">/g) || []).length, 10);
  assert.ok(/Highest known limit number: \d+/.test(html));
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

test('shown() changes with what the page shows and not with other lines of the sources', () => {
  const src = { statusLog: '| 2026-11-13 | 1 | a. b | x |\n', tasks: '## G\n- [x] 1\n- [ ] 2\n', limits: '### 5. t\n' };
  const base = shown(model(src));
  assert.equal(shown(model({ statusLog: `words\n${src.statusLog}`, tasks: `intro\n${src.tasks}text\n`, limits: `${src.limits}\nmore words\n` })), base);
  assert.notEqual(shown(model({ ...src, statusLog: '| 2026-11-13 | 1 | changed | x |\n' })), base);
  assert.notEqual(shown(model({ ...src, tasks: '## G\n- [x] 1\n- [x] 2\n' })), base);
  assert.notEqual(shown(model({ ...src, limits: '### 6. t\n' })), base);
});
