// W2: the command map page. The data file comes from the real command line (ui/tools/cli_map.py; tests/test_cli_map.py compares it
// with the parser). Here: the file is well formed, and the built page lists every command and group in it, with one line each.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ui = join(dirname(fileURLToPath(import.meta.url)), '..');
const data = JSON.parse(readFileSync(join(ui, 'src/data/cli-map.json'), 'utf8'));
const html = readFileSync(join(ui, 'dist/cli-map.html'), 'utf8');
const flat = (nodes) => nodes.flatMap((n) => [n, ...flat(n.children)]);
const all = flat(data.children);

test('the data file is well formed', () => {
  assert.equal(data.schema, 1);
  assert.equal(data.program, 'umwayi');
  assert.ok(all.length > 0);
  const seen = new Set();
  for (const n of all) {
    assert.deepEqual(Object.keys(n).sort(), ['children', 'help', 'line', 'name', 'path']);
    assert.equal(n.path[n.path.length - 1], n.name);
    assert.ok(!seen.has(n.path.join(' ')), `twice: ${n.path.join(' ')}`);
    seen.add(n.path.join(' '));
    assert.equal(n.line === null, n.help === null);
    if (n.line !== null) {
      assert.ok(n.help.startsWith(n.line), `${n.path.join(' ')}: the line is the start of the help`);
      assert.ok(!/[;]/.test(n.line.replace(/\([^)]*\)/g, '')), `${n.path.join(' ')}: the line is one sentence`);
    }
  }
});

test('the page lists every command and group once, each with a line', () => {
  for (const n of all) {
    const at = html.indexOf(`<li data-path="${n.path.join(' ')}">`);
    assert.ok(at >= 0, `not in the page: ${n.path.join(' ')}`);
    assert.equal(html.indexOf(`<li data-path="${n.path.join(' ')}">`, at + 1), -1);
  }
  assert.equal((html.match(/<li data-path=/g) || []).length, all.length);
  const groups = all.filter((n) => n.children.length).length;
  assert.equal((html.match(/<summary /g) || []).length, groups);
  assert.ok(html.includes(`${groups} groups and ${all.length - groups} commands.`));
});

test('a command with no help line is listed and says so', () => {
  const plain = data.children.length ? all.filter((n) => n.line === null) : [];
  assert.equal((html.match(/no help line yet/g) || []).length, plain.length + 0);
});

test('the page has no script, no link, no request and no em dash', () => {
  assert.ok(!/<script|<link|<img|<iframe|<form|<input|\bsrc\s*=|\bhref\s*=|fetch\(|XMLHttpRequest|@import|url\(/i.test(html));
  assert.ok(!html.includes('\u2014'));
  assert.ok(/default-src 'none'; style-src 'sha256-[^']+'; base-uri 'none'; form-action 'none'/.test(html));
});
