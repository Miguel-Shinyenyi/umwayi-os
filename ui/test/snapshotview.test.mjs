// UI.3 (tests first): the page part of reading a snapshot. The file picker and the drop, the one message, what the page
// shows once a snapshot is loaded (the strip, the date next to the scene, the footer), and the rule that no text from the
// file is ever set as markup. A stub document stands in for the browser; the real browser pass is in docs/interface.md.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initSnapshot } from '../src/ui/snapshot.js';
import { NOT_A_SNAPSHOT } from '../src/data/snapshot.js';
import { SAMPLE } from '../src/data/sample.js';
import { statusStrip } from '../src/data/home.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const FIXTURE = readFileSync(join(HERE, 'fixtures', 'snapshot.json'), 'utf8');
const good = () => JSON.parse(FIXTURE);
const walk = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));

// ---- a stub page. Any write of markup throws, so a test finds it at once.
function el(name = 'div') {
  const handlers = {};
  const o = {
    name, attrs: {}, handlers, hidden: false, value: 'picked', files: [], clicked: 0, textContent: '',
    addEventListener(t, fn) { (handlers[t] ||= []).push(fn); },
    removeEventListener(t, fn) { handlers[t] = (handlers[t] || []).filter((f) => f !== fn); },
    setAttribute(k, v) { o.attrs[k] = String(v); }, removeAttribute(k) { delete o.attrs[k]; },
    click() { o.clicked++; },
  };
  for (const sink of ['innerHTML', 'outerHTML']) {
    Object.defineProperty(o, sink, { set() { throw new Error(`${sink} was set`); }, get() { return ''; } });
  }
  o.insertAdjacentHTML = () => { throw new Error('insertAdjacentHTML was called'); };
  return o;
}
function page() {
  const ids = ['snapshot-file', 'snapshot-open', 'snapshot-msg', 'sample-tag', 'foot-note'];
  const els = Object.fromEntries(ids.map((id) => [id, el(id)]));
  els['sample-tag'].textContent = 'sample';
  els['foot-note'].textContent = 'A sample world. The picture shows made up counts until you load your own.';
  const strip = {};
  const initial = statusStrip(SAMPLE, { sample: true, date: SAMPLE.date });
  for (const s of initial) {
    const li = el('li'), v = el('v'), t = el('t');
    v.textContent = s.value; t.textContent = s.tag;
    li.querySelector = (q) => (q === '.v' ? v : q === '.t' ? t : null);
    strip[s.id] = { li, v, t };
  }
  const doc = {
    handlers: {},
    getElementById: (id) => els[id] || null,
    querySelector: (q) => { const m = /data-strip="([a-z]+)"/.exec(q); return m && strip[m[1]] ? strip[m[1]].li : null; },
    addEventListener(t, fn) { (doc.handlers[t] ||= []).push(fn); },
    removeEventListener(t, fn) { doc.handlers[t] = (doc.handlers[t] || []).filter((f) => f !== fn); },
  };
  return { doc, els, strip };
}
const fire = (target, type, ev = {}) => { const e = { type, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...ev }; (target.handlers[type] || []).forEach((f) => f(e)); return e; };
const flush = () => new Promise((r) => setTimeout(r, 0));

// a FileReader that answers from a map of file -> text, at a time the test chooses
function readerFor(texts, { delay = {} } = {}) {
  return class {
    readAsText(file) {
      const finish = () => { this.result = texts.get(file); if (this.result === undefined) this.onerror(new Error('x')); else this.onload(); };
      const ms = delay[file.name];
      if (ms) setTimeout(finish, ms); else Promise.resolve().then(finish);
    }
  };
}
const fileOf = (name, text) => ({ name, size: Buffer.byteLength(text), text });
function setup(opts = {}) {
  const p = page();
  const views = [];
  const files = new Map();
  const win = { FileReader: null };
  const api = {
    add(name, text) { const f = fileOf(name, text); files.set(f, text); win.FileReader = readerFor(files, opts); return f; },
  };
  win.FileReader = readerFor(files, opts);
  const h = initSnapshot(p.doc, win, { onView: (v) => views.push(v) });
  return { ...p, views, h, win, files, ...api };
}
const stripValues = (p) => Object.values(p.strip).map((s) => s.v.textContent);
const stripTags = (p) => Object.values(p.strip).map((s) => s.t.textContent);

test('before any file: nothing is changed, the label says sample and the message is empty', () => {
  const p = setup();
  assert.equal(p.els['sample-tag'].textContent, 'sample');
  assert.deepEqual(stripTags(p), ['sample', 'sample', 'sample', 'sample']);
  assert.equal(p.els['snapshot-msg'].textContent, '');
  assert.deepEqual(p.views, []);
});

test('the open button opens the picker, and the picker takes one json file', () => {
  const p = setup();
  fire(p.els['snapshot-open'], 'click');
  assert.equal(p.els['snapshot-file'].clicked, 1);
  fire(p.els['snapshot-open'], 'click');
  assert.equal(p.els['snapshot-file'].clicked, 2);
});

test('a picked file that is the fixture loads: the strip, the date by the scene and the footer show it, and sample is gone', async () => {
  const p = setup();
  const f = p.add('snapshot.json', FIXTURE);
  p.els['snapshot-file'].files = [f];
  fire(p.els['snapshot-file'], 'change');
  await flush();
  assert.equal(p.views.length, 1);
  assert.equal(p.views[0].sample, false);
  assert.deepEqual(p.views[0].counts, good());
  assert.deepEqual(stripValues(p), ['off', '105 UU', '2', '8 linked entries']);
  assert.deepEqual(stripTags(p), Array(4).fill('as of 2026-11-11'));
  assert.match(p.els['sample-tag'].textContent, /2026-11-11/);
  assert.doesNotMatch(p.els['sample-tag'].textContent, /sample/i);
  assert.doesNotMatch(p.els['foot-note'].textContent, /sample/i);
  assert.match(p.els['foot-note'].textContent, /2026-11-11/);
  assert.equal(p.els['snapshot-msg'].textContent, 'Loaded the snapshot of 2026-11-11.');
  assert.equal(p.els['snapshot-file'].value, '', 'the picker is cleared, so the same file can be picked again');
});

test('the same file picked again loads again (a refreshed snapshot of the same name)', async () => {
  const p = setup();
  const f = p.add('snapshot.json', FIXTURE);
  for (let i = 0; i < 2; i++) { p.els['snapshot-file'].files = [f]; fire(p.els['snapshot-file'], 'change'); await flush(); }
  assert.equal(p.views.length, 2);
});

test('a bad file shows the one message and loads nothing: strip, label, footer and the scene stay as they were', async () => {
  const p = setup();
  const before = { v: stripValues(p), t: stripTags(p), tag: p.els['sample-tag'].textContent, foot: p.els['foot-note'].textContent };
  const bads = [
    ['extra.json', JSON.stringify({ ...good(), extra: 1 })], ['text.json', 'not json'], ['schema2.json', JSON.stringify({ ...good(), schema: 2 })],
    ['big.json', FIXTURE + ' '.repeat(5000)], ['float.json', FIXTURE.replace('"open": 2', '"open": 2.5')], ['empty.json', ''],
  ];
  for (const [name, text] of bads) {
    p.els['snapshot-file'].files = [p.add(name, text)];
    p.els['snapshot-msg'].textContent = '';
    fire(p.els['snapshot-file'], 'change');
    await flush();
    assert.equal(p.els['snapshot-msg'].textContent, NOT_A_SNAPSHOT, name);
    assert.equal(p.els['snapshot-msg'].textContent, 'This file is not a snapshot of this version');
    assert.deepEqual(stripValues(p), before.v, name);
    assert.deepEqual(stripTags(p), before.t, name);
    assert.equal(p.els['sample-tag'].textContent, before.tag, name);
    assert.equal(p.els['foot-note'].textContent, before.foot, name);
  }
  assert.deepEqual(p.views, [], 'the scene was never told');
});

test('a bad file after a good one leaves the good one loaded, with the message', async () => {
  const p = setup();
  p.els['snapshot-file'].files = [p.add('a.json', FIXTURE)]; fire(p.els['snapshot-file'], 'change'); await flush();
  const shown = stripValues(p);
  p.els['snapshot-file'].files = [p.add('b.json', '{"schema": 1}')]; fire(p.els['snapshot-file'], 'change'); await flush();
  assert.equal(p.views.length, 1);
  assert.deepEqual(stripValues(p), shown);
  assert.equal(p.els['snapshot-msg'].textContent, NOT_A_SNAPSHOT);
  assert.match(p.els['sample-tag'].textContent, /2026-11-11/);
});

test('a read error and a missing file give the same message', async () => {
  const p = setup();
  p.els['snapshot-file'].files = [{ name: 'gone.json', size: 10 }];
  fire(p.els['snapshot-file'], 'change'); await flush();
  assert.equal(p.els['snapshot-msg'].textContent, NOT_A_SNAPSHOT);
  p.els['snapshot-msg'].textContent = '';
  p.els['snapshot-file'].files = [];
  fire(p.els['snapshot-file'], 'change'); await flush();
  assert.equal(p.els['snapshot-msg'].textContent, '', 'choosing nothing (cancel) says nothing and changes nothing');
  assert.deepEqual(p.views, []);
});

test('a drop of one file loads it, and the page does not let the browser open the file', async () => {
  const p = setup();
  const f = p.add('snapshot.json', FIXTURE);
  const over = fire(p.doc, 'dragover', { dataTransfer: { types: ['Files'] } });
  assert.equal(over.defaultPrevented, true, 'the page takes the drag');
  const drop = fire(p.doc, 'drop', { dataTransfer: { types: ['Files'], files: [f] } });
  assert.equal(drop.defaultPrevented, true);
  await flush();
  assert.equal(p.views.length, 1);
  assert.deepEqual(stripValues(p), ['off', '105 UU', '2', '8 linked entries']);
});

test('a drop of text, a link or nothing is left alone; a drop of two files, or a folder, is the one message', async () => {
  const p = setup();
  const text = fire(p.doc, 'dragover', { dataTransfer: { types: ['text/plain'] } });
  assert.equal(text.defaultPrevented, false, 'dragging text over the page is not ours');
  const none = fire(p.doc, 'drop', { dataTransfer: { types: ['text/plain'], files: [] } });
  assert.equal(none.defaultPrevented, false);
  assert.equal(p.els['snapshot-msg'].textContent, '');
  const a = p.add('a.json', FIXTURE), b = p.add('b.json', FIXTURE);
  fire(p.doc, 'drop', { dataTransfer: { types: ['Files'], files: [a, b] } });
  await flush();
  assert.equal(p.els['snapshot-msg'].textContent, NOT_A_SNAPSHOT, 'two files: nothing is loaded');
  p.els['snapshot-msg'].textContent = '';
  fire(p.doc, 'drop', { dataTransfer: { types: ['Files'], files: [{ name: 'folder', size: 0 }] } });
  await flush();
  assert.equal(p.els['snapshot-msg'].textContent, NOT_A_SNAPSHOT, 'a folder reads as nothing');
  fire(p.doc, 'drop', { dataTransfer: null });
  fire(p.doc, 'drop', {});
  assert.deepEqual(p.views, []);
});

test('the newest choice wins: a slow older file that finishes last does not replace the newer one', async () => {
  const p = setup({ delay: { 'slow.json': 30 } });
  const other = { ...good(), queue: { open: 5, answered: 1 } };
  p.els['snapshot-file'].files = [p.add('slow.json', FIXTURE)]; fire(p.els['snapshot-file'], 'change');
  p.els['snapshot-file'].files = [p.add('fast.json', JSON.stringify(other, null, 2))]; fire(p.els['snapshot-file'], 'change');
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(p.views.length, 1);
  assert.equal(p.views[0].counts.queue.open, 5);
  assert.equal(p.strip.queue.v.textContent, '5');
});

test('no text from the file is ever set as markup: a file full of markup is refused, and an accepted one shows only numbers, a word and a date', async () => {
  const p = setup(); // any write of innerHTML, outerHTML or insertAdjacentHTML in the stub throws
  const attacks = [
    JSON.stringify({ ...good(), date: '<img src=x onerror=alert(1)>' }),
    JSON.stringify({ ...good(), kill_switch: '<script>alert(1)</script>' }),
    JSON.stringify({ ...good(), extra: '<svg onload=alert(1)>' }),
    JSON.stringify({ ...good(), queue: { open: '<b>6</b>', answered: 1 } }),
    JSON.stringify({ ...good(), budget: { days: good().budget.days.map((d) => ({ ...d, date: '"><script>' })) } }),
  ];
  for (const [i, t] of attacks.entries()) {
    p.els['snapshot-file'].files = [p.add(`attack${i}.json`, t)];
    fire(p.els['snapshot-file'], 'change');
    await flush();
    assert.equal(p.els['snapshot-msg'].textContent, NOT_A_SNAPSHOT, `attack ${i}`);
  }
  p.els['snapshot-file'].files = [p.add('ok.json', FIXTURE)]; fire(p.els['snapshot-file'], 'change'); await flush();
  for (const t of [...stripValues(p), ...stripTags(p), p.els['sample-tag'].textContent, p.els['foot-note'].textContent, p.els['snapshot-msg'].textContent]) {
    assert.doesNotMatch(t, /[<>"`]/, t);
  }
});

test('the sources never write markup, run text or read a file any other way', () => {
  const banned = [/\.innerHTML/, /\.outerHTML/, /insertAdjacentHTML/, /insertAdjacentElement/, /document\.write/, /DOMParser/, /createContextualFragment/, /\.srcdoc/,
    /\beval\s*\(/, /new Function/, /\bFunction\s*\(/, /readAsDataURL/, /readAsArrayBuffer/, /readAsBinaryString/, /createObjectURL/,
    /setAttribute\(\s*['"]on/, /setTimeout\(\s*['"]/, /setInterval/];
  for (const f of walk(SRC).filter((n) => n.endsWith('.js'))) {
    const text = readFileSync(f, 'utf8');
    for (const re of banned) assert.ok(!re.test(text), `${f.slice(SRC.length + 1)}: ${re}`);
  }
});

test('the file is read with readAsText in the one data module and only there; the page hands it its FileReader and makes none of its own', () => {
  const users = walk(SRC).filter((f) => f.endsWith('.js') && /readAsText|new FileReader/.test(readFileSync(f, 'utf8')));
  assert.deepEqual(users.map((f) => f.slice(SRC.length + 1).split('\\').join('/')), ['data/snapshot.js']);
  assert.equal((readFileSync(join(SRC, 'data', 'snapshot.js'), 'utf8').match(/readAsText\(/g) || []).length, 1);
  assert.ok(!/new FileReader/.test(readFileSync(join(SRC, 'data', 'snapshot.js'), 'utf8')), 'the reader comes in as an argument, so a test can stand in for it');
});

test('the snapshot path makes no request, keeps nothing and sends nothing', () => {
  for (const name of ['data/snapshot.js', 'ui/snapshot.js']) {
    const text = readFileSync(join(SRC, name), 'utf8');
    for (const bad of ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'localStorage', 'sessionStorage', 'indexedDB', 'document.cookie',
      'history.', 'location.', 'navigator.', 'import(', 'Worker', 'postMessage', 'Image(', 'new URL', 'URL.']) {
      assert.ok(!text.includes(bad), `${name} contains ${bad}`);
    }
  }
});

test('the page works without a picker in it (the List page before its script, a page that has no strip): it does not throw', async () => {
  const doc = { getElementById: () => null, querySelector: () => null, addEventListener() {}, removeEventListener() {} };
  const h = initSnapshot(doc, { FileReader: null }, { onView() {} });
  assert.equal(typeof h.stop, 'function');
  h.stop();
});

test('stop takes every listener off again', () => {
  const p = setup();
  p.h.stop();
  assert.deepEqual(p.doc.handlers.drop, []);
  assert.deepEqual(p.doc.handlers.dragover, []);
  assert.deepEqual(p.els['snapshot-file'].handlers.change, []);
  assert.deepEqual(p.els['snapshot-open'].handlers.click, []);
});

// ---- the page template: what the page says before any file is opened
import { SAMPLE_LABEL, SAMPLE_FOOTER } from '../src/data/snapshot.js';
const TEMPLATE = readFileSync(join(SRC, 'index.html'), 'utf8');

test('the template says sample before any file, with the same words the code puts back for the sample', () => {
  assert.match(TEMPLATE, new RegExp(`<p id="sample-tag">${SAMPLE_LABEL}</p>`));
  assert.ok(TEMPLATE.includes(`<p id="foot-note">${SAMPLE_FOOTER}</p>`));
  assert.equal(SAMPLE_LABEL, 'sample');
});

test('the template has one file picker for json, read in the page: no form, no upload, no second input', () => {
  const inputs = [...TEMPLATE.matchAll(/<input\b([^>]*)>/g)].map((m) => m[1]);
  assert.equal(inputs.length, 1);
  assert.match(inputs[0], /type="file"/);
  assert.match(inputs[0], /id="snapshot-file"/);
  assert.match(inputs[0], /accept="\.json,application\/json"/);
  assert.ok(!/multiple|capture|webkitdirectory|name=/.test(inputs[0]));
  assert.ok(!/<form\b|action=|formaction/i.test(TEMPLATE));
  assert.match(TEMPLATE, /id="snapshot-open"/);
  assert.match(TEMPLATE, /id="snapshot-msg"[^>]*role="status"/);
  assert.match(TEMPLATE, /It is not uploaded, sent or kept\./);
});

test('the picker comes after the status strip, so the top of the strip stays in the first screen', () => {
  assert.ok(TEMPLATE.indexOf('<!--@strip-->') < TEMPLATE.indexOf('id="snapshot-open"'));
  assert.ok(TEMPLATE.indexOf('id="snapshot-open"') < TEMPLATE.indexOf('id="list-view"'));
});

test('without a script the picker is not shown (it would do nothing)', () => {
  const css = readFileSync(join(SRC, 'style.css'), 'utf8');
  assert.match(css, /html:not\(\[data-js\]\) :is\([^)]*#snapshot[^)]*\)\s*\{\s*display:\s*none/);
});
