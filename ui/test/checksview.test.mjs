// UI.4 (tests first): the owner checks panel in the page (12.R7). A small fake document stands in for the browser: its elements
// throw if text is ever set as markup. The panel is built from checks.js with createElement and textContent only, works with
// no scene and no WebGL, keeps its state in memory and makes no request. The real browser pass is in docs/interface.md.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initChecks } from '../src/ui/checks.js';
import { CHECKS } from '../src/data/checks.js';
import { END_LINE, MEMORY_NOTICE, RECORD_RULE, EXPORT_FILE } from '../src/data/notes.js';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const TEMPLATE = readFileSync(join(SRC, 'index.html'), 'utf8');
const walk = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));

// ---- a fake document
class Text { constructor(t) { this.text = String(t); } get textContent() { return this.text; } }
class El {
  constructor(tag, opts = {}) {
    this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.hidden = false; this.value = ''; this.checked = false;
    this.className = ''; this.calls = []; this._text = null;
    if (opts.noDownload !== true && tag === 'a') this.download = '';
    for (const sink of ['innerHTML', 'outerHTML']) Object.defineProperty(this, sink, { set() { throw new Error(`${sink} was set`); }, get() { return ''; } });
    this.insertAdjacentHTML = () => { throw new Error('insertAdjacentHTML was called'); };
  }
  append(...nodes) { for (const n of nodes) this.children.push(typeof n === 'string' ? new Text(n) : n); }
  appendChild(n) { this.append(n); return n; }
  replaceChildren(...n) { this.children = []; this.append(...n); }
  get textContent() { return this._text !== null ? this._text : this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { this._text = null; this.children = [new Text(v)]; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); }
  focus() { this.calls.push('focus'); El.focused = this; }
  select() { this.calls.push('select'); }
  click() { this.calls.push('click'); }
  scrollIntoView() { this.calls.push('scrollIntoView'); }
  fire(type, extra = {}) { const ev = { type, target: this, preventDefault() {}, ...extra }; (this.listeners[type] || []).forEach((f) => f(ev)); }
  walk(fn) { fn(this); for (const c of this.children) if (c instanceof El) c.walk(fn); }
  all(pred) { const out = []; this.walk((e) => { if (pred(e)) out.push(e); }); return out; }
}
function page(opts = {}) {
  const ids = {};
  const mk = (id, tag = 'div', extra = {}) => { const e = new El(tag, opts); Object.assign(e, extra); ids[id] = e; return e; };
  const section = mk('checks', 'section', { hidden: true });
  mk('checks-title', 'h2'); mk('checks-list'); mk('checks-open', 'button'); mk('checks-open-list', 'button'); mk('checks-close', 'button');
  mk('checks-export-btn', 'button'); mk('checks-copy', 'button', { hidden: true }); mk('checks-download', 'button', { hidden: true });
  mk('checks-export', 'textarea', { hidden: true }); mk('checks-status', 'p'); mk('checks-copy-only', 'p', { hidden: true });
  ids['checks-open'].setAttribute('aria-expanded', 'false'); ids['checks-open-list'].setAttribute('aria-expanded', 'false');
  const doc = { createElement: (t) => new El(t, opts), createTextNode: (t) => new Text(t), getElementById: (id) => ids[id] || null, body: new El('body'), querySelector: () => null };
  return { doc, ids, section, list: ids['checks-list'] };
}
const boxes = (p) => p.list.all((e) => e.tag === 'input' && e.attrs.type === 'checkbox');
const texts = (p) => p.list.all((e) => e.tag === 'input' && e.attrs.type === 'text');
const articles = (p) => p.list.all((e) => e.tag === 'article');
const badge = (a) => a.all((e) => e.className === 'check-status')[0].textContent;
const tickAll = (p, check) => articles(p).find((a) => a.attrs['data-check'] === check).all((e) => e.tag === 'input' && e.attrs.type === 'checkbox').forEach((b) => { b.checked = true; b.fire('change'); });

test('the panel builds the six checks in order, each "not done", with a checkbox and a text field for every step, from checks.js', () => {
  const p = page();
  initChecks(p.doc, {});
  const a = articles(p);
  assert.deepEqual(a.map((x) => x.attrs['data-check']), ['10.21', '10.31', '11.6', 'B.10', '10.37', 'UI.5']);
  assert.deepEqual(a.map(badge), Array(6).fill('not done'));
  const steps = CHECKS.reduce((s, c) => s + c.steps.length, 0);
  assert.equal(steps, 67);
  assert.equal(boxes(p).length, steps);
  assert.equal(texts(p).length, steps);
  assert.ok(boxes(p).every((b) => b.checked === false));
  assert.ok(texts(p).every((t) => t.value === '' && t.attrs.maxlength === '500' && t.attrs.autocomplete === 'off'));
  assert.equal(p.section.hidden, true, 'closed until the owner opens it');
});

test('each check shows its id and name, why it is open, where its steps come from, and its steps in order', () => {
  const p = page();
  initChecks(p.doc, {});
  articles(p).forEach((art, i) => {
    const c = CHECKS[i];
    const t = art.textContent;
    assert.ok(t.includes(c.id) && t.includes(c.name), c.id);
    assert.ok(t.includes(c.reason), `${c.id} reason`);
    assert.ok(t.includes(c.notes), `${c.id} source`);
    let at = 0;
    for (const s of c.steps) {
      const label = art.all((e) => e.attrs['data-step'] === s.id)[0];
      assert.ok(label, `${c.id} ${s.id}`);
      const k = t.indexOf(s.text.split('`')[0].slice(0, 20), at);
      assert.ok(k >= 0, `${c.id} ${s.id} in order`);
    }
  });
});

test('every command is in a code block, word for word, and so is every code block of the NOTES', () => {
  const p = page();
  initChecks(p.doc, {});
  const pre = p.list.all((e) => e.tag === 'pre');
  const shown = pre.map((e) => e.textContent);
  const want = CHECKS.flatMap((c) => c.steps.flatMap((s) => [...(s.commands || []), ...(s.block ? [s.block] : [])]));
  assert.deepEqual(shown, want);
  assert.ok(pre.every((e) => e.children.length === 1 && e.children[0].tag === 'code'));
});

test('a step\'s words keep their inline code: text between backticks is a code element, the rest is text', () => {
  const p = page();
  initChecks(p.doc, {});
  const step = p.list.all((e) => e.attrs['data-step'] === '0.1')[0];
  const code = step.all((e) => e.tag === 'code' && e.parent !== 'pre').map((e) => e.textContent);
  assert.ok(code.includes('node --version'));
  assert.ok(step.textContent.includes('prints'));
  assert.ok(!step.textContent.includes('`'), 'the backticks are not shown');
});

test('opening shows the panel, moves focus to its title and tells the opener; closing hides it and gives the focus back', () => {
  const p = page();
  const h = initChecks(p.doc, {});
  p.ids['checks-open'].fire('click');
  assert.equal(p.section.hidden, false);
  assert.equal(p.ids['checks-open'].attrs['aria-expanded'], 'true');
  assert.equal(El.focused, p.ids['checks-title']);
  assert.ok(p.section.calls.includes('scrollIntoView'));
  p.ids['checks-close'].fire('click');
  assert.equal(p.section.hidden, true);
  assert.equal(p.ids['checks-open'].attrs['aria-expanded'], 'false');
  assert.equal(El.focused, p.ids['checks-open']);
  p.ids['checks-open-list'].fire('click');
  assert.equal(p.section.hidden, false);
  assert.equal(p.ids['checks-open-list'].attrs['aria-expanded'], 'true');
  p.ids['checks-close'].fire('click');
  assert.equal(El.focused, p.ids['checks-open-list'], 'back to the button that opened it');
  h.stop();
});

test('a check says "ticked by you" only when every step is ticked, and "not done" again when one is unticked; others do not change', () => {
  const p = page();
  initChecks(p.doc, {});
  const first = articles(p)[0];
  const bs = first.all((e) => e.tag === 'input' && e.attrs.type === 'checkbox');
  bs.slice(0, -1).forEach((b) => { b.checked = true; b.fire('change'); });
  assert.equal(badge(first), 'not done');
  bs[bs.length - 1].checked = true; bs[bs.length - 1].fire('change');
  assert.equal(badge(first), 'ticked by you');
  assert.deepEqual(articles(p).slice(1).map(badge), Array(5).fill('not done'));
  assert.match(p.ids['checks-status'].textContent, /10\.21.*ticked by you/);
  bs[1].checked = false; bs[1].fire('change');
  assert.equal(badge(first), 'not done');
  const all = p.section.textContent + p.list.textContent;
  assert.doesNotMatch(badge(first), /passed|verified/i);
});

test('the word passed or verified is never the status of a check, in any state', () => {
  const p = page();
  initChecks(p.doc, {});
  for (const c of CHECKS) tickAll(p, c.id);
  const badges = p.list.all((e) => e.className === 'check-status').map((e) => e.textContent);
  assert.deepEqual(badges, Array(6).fill('ticked by you'));
  assert.ok(p.ids['checks-status'].textContent.length > 0);
  assert.doesNotMatch(p.ids['checks-status'].textContent, /passed|verified/i);
});

test('typing an email, a URL, a token or a hex string in a result shows a warning on that field; a plain exit code does not', () => {
  const p = page();
  initChecks(p.doc, {});
  const art = articles(p)[0];
  const field = art.all((e) => e.tag === 'input' && e.attrs.type === 'text')[0];
  const warn = art.all((e) => e.className === 'check-warning')[0];
  assert.equal(warn.hidden, true);
  for (const [v, shape] of [['me@example.com', 'email address'], ['https://example.com', 'URL'], ['abcdefghijklmnopqrstuvwxyz', 'token'], ['3b9f1c2d4e5a6b7c', 'long hex string']]) {
    field.value = v; field.fire('input');
    assert.equal(warn.hidden, false, v);
    assert.ok(warn.textContent.includes(shape), warn.textContent);
    assert.ok(warn.textContent.includes('never a value'));
    assert.equal(field.attrs['aria-invalid'], undefined, 'a hint, not an error');
  }
  field.value = 'exit 0'; field.fire('input');
  assert.equal(warn.hidden, true);
  field.value = ''; field.fire('input');
  assert.equal(warn.hidden, true);
});

test('a step that records an exit code warns when the result is not a plain number', () => {
  const p = page();
  initChecks(p.doc, {});
  const art = articles(p).find((a) => a.attrs['data-check'] === 'UI.5');
  const li = art.all((e) => e.attrs['data-step'] === '0.3')[0];
  const field = li.all((e) => e.tag === 'input' && e.attrs.type === 'text')[0];
  const warn = li.all((e) => e.className === 'check-warning')[0];
  field.value = 'it worked'; field.fire('input');
  assert.equal(warn.hidden, false);
  assert.equal(warn.textContent, 'This step records an exit code. Type the number only.');
  field.value = '0'; field.fire('input');
  assert.equal(warn.hidden, true);
});

test('a warning never stops a tick or the export', () => {
  const p = page();
  initChecks(p.doc, {});
  const li = p.list.all((e) => e.attrs['data-step'] === 'A3')[0];
  const f = li.all((e) => e.tag === 'input' && e.attrs.type === 'text')[0];
  const b = li.all((e) => e.tag === 'input' && e.attrs.type === 'checkbox')[0];
  f.value = 'me@example.com'; f.fire('input');
  b.checked = true; b.fire('change');
  p.ids['checks-export-btn'].fire('click');
  assert.ok(p.ids['checks-export'].value.includes('[x] A3.'));
  assert.ok(p.ids['checks-export'].value.includes('    Result: me@example.com'));
  assert.ok(p.ids['checks-export'].value.includes('Check this result: it looks like an email address.'));
});

test('export shows the text in the box, selected, with Copy and Download, and ends with the closing line', () => {
  const p = page();
  initChecks(p.doc, {});
  const box = p.ids['checks-export'];
  assert.equal(box.hidden, true);
  assert.equal(p.ids['checks-copy'].hidden, true);
  assert.equal(p.ids['checks-download'].hidden, true);
  tickAll(p, '10.21');
  p.ids['checks-export-btn'].fire('click');
  assert.equal(box.hidden, false);
  assert.equal(p.ids['checks-copy'].hidden, false);
  assert.equal(p.ids['checks-download'].hidden, false);
  assert.ok(box.calls.includes('select'));
  assert.ok(box.value.endsWith(`\n${END_LINE}\n`));
  assert.ok(box.value.includes('Status: ticked by you (4 of 4 steps ticked)'));
  assert.equal(box.textContent, box.value, 'the box and its default text agree, so a copy reads the same');
  assert.match(p.ids['checks-status'].textContent, /Copy|Download/);
});

test('the exported text follows later changes, so a Copy after a tick copies the new state', () => {
  const p = page();
  initChecks(p.doc, {});
  p.ids['checks-export-btn'].fire('click');
  const before = p.ids['checks-export'].value;
  tickAll(p, '10.37');
  assert.notEqual(p.ids['checks-export'].value, before);
  assert.ok(p.ids['checks-export'].value.includes('== 10.37: '));
  const li = p.list.all((e) => e.attrs['data-step'] === 'B1')[0];
  const f = li.all((e) => e.tag === 'input' && e.attrs.type === 'text')[0];
  f.value = 'apiKeySource, loggedIn'; f.fire('input');
  assert.ok(p.ids['checks-export'].value.includes('    Result: apiKeySource, loggedIn'));
});

test('Download makes a link whose address holds the text (a data address), named umwayi-owner-checks.txt, and clicks it', () => {
  const p = page();
  initChecks(p.doc, {});
  p.ids['checks-export-btn'].fire('click');
  const made = [];
  const orig = p.doc.createElement;
  p.doc.createElement = (t) => { const e = orig(t); if (t === 'a') made.push(e); return e; };
  p.ids['checks-download'].fire('click');
  assert.equal(made.length, 1);
  const a = made[0];
  assert.ok(a.attrs.href.startsWith('data:text/plain;charset=utf-8,'));
  assert.equal(decodeURIComponent(a.attrs.href.slice('data:text/plain;charset=utf-8,'.length)), p.ids['checks-export'].value);
  assert.equal(a.download, EXPORT_FILE);
  assert.ok(a.calls.includes('click'));
  assert.match(p.ids['checks-status'].textContent, /Copy/);
  assert.equal(p.ids['checks-copy-only'].hidden, true);
});

test('where the browser cannot download, the panel says Copy only and hides Download', () => {
  const p = page({ noDownload: true });
  initChecks(p.doc, {});
  p.ids['checks-export-btn'].fire('click');
  assert.equal(p.ids['checks-download'].hidden, true);
  assert.equal(p.ids['checks-copy-only'].hidden, false);
  assert.equal(p.ids['checks-copy-only'].textContent, 'This browser cannot save a file from this page. Copy only.');
  assert.equal(p.ids['checks-copy'].hidden, false);
});

test('text typed or built into the panel is never set as markup (the fake elements throw if it is), also a result full of markup', () => {
  const p = page();
  initChecks(p.doc, {});
  const f = texts(p)[0];
  f.value = '<img src=x onerror=alert(1)><script>alert(2)</script>'; f.fire('input');
  p.ids['checks-export-btn'].fire('click');
  assert.ok(p.ids['checks-export'].value.includes('<img src=x onerror=alert(1)>'));
  assert.equal(p.list.all((e) => e.tag === 'img' || e.tag === 'script').length, 0);
});

test('the notes live in memory: the panel uses no window at all and nothing is written anywhere', () => {
  const p = page();
  const trap = new Proxy({}, { get(_, k) { throw new Error(`the panel read window.${String(k)}`); }, set() { throw new Error('the panel wrote to window'); } });
  initChecks(p.doc, trap);
  tickAll(p, '11.6');
  p.ids['checks-export-btn'].fire('click');
  p.ids['checks-download'].fire('click');
});

test('after stop, the buttons and fields do nothing', () => {
  const p = page();
  const h = initChecks(p.doc, {});
  h.stop();
  p.ids['checks-open'].fire('click');
  assert.equal(p.section.hidden, true);
  const b = boxes(p)[0];
  b.checked = true; b.fire('change');
  assert.equal(badge(articles(p)[0]), 'not done');
});

test('a page without the panel (no skeleton) does not throw', () => {
  const doc = { getElementById: () => null, createElement: () => new El('x'), createTextNode: (t) => new Text(t) };
  const h = initChecks(doc, {});
  h.stop();
});

// ---- the template and the sources
test('the template has the panel: hidden, with the notice, the rule, the buttons and the box; the buttons to open it are in the top bar and the list view', () => {
  assert.match(TEMPLATE, /<section class="home" id="checks"[^>]*\bhidden\b/);
  assert.ok(TEMPLATE.includes(`<p class="checks-memory" id="checks-memory">${MEMORY_NOTICE}</p>`));
  assert.ok(TEMPLATE.includes(`<p class="checks-rule" id="checks-rule">${RECORD_RULE}</p>`));
  for (const id of ['checks-list', 'checks-export-btn', 'checks-copy', 'checks-download', 'checks-close', 'checks-export', 'checks-status', 'checks-copy-only', 'checks-open', 'checks-open-list']) {
    assert.ok(TEMPLATE.includes(`id="${id}"`), id);
  }
  assert.match(TEMPLATE, /<textarea[^>]*id="checks-export"[^>]*\breadonly\b[^>]*\bhidden\b/);
  assert.match(TEMPLATE, /id="checks-copy"[^>]*data-copy="checks-export"[^>]*\bhidden\b|data-copy="checks-export"[^>]*id="checks-copy"[^>]*\bhidden\b/);
  const bar = TEMPLATE.slice(TEMPLATE.indexOf('<header'), TEMPLATE.indexOf('</header>'));
  assert.ok(bar.includes('id="checks-open"'));
  const list = TEMPLATE.slice(TEMPLATE.indexOf('id="list-view"'), TEMPLATE.indexOf('id="start"'));
  assert.ok(list.includes('id="checks-open-list"'));
  assert.ok(TEMPLATE.indexOf('id="checks"') > TEMPLATE.indexOf('id="links"'), 'after the links, before the footer');
  assert.match(TEMPLATE, /html:not|<html/);
});

test('without a script the panel buttons are not shown (they would do nothing)', () => {
  const css = readFileSync(join(SRC, 'style.css'), 'utf8');
  assert.match(css, /html:not\(\[data-js\]\) :is\([^)]*#checks-open[^)]*#checks-open-list[^)]*\)\s*\{\s*display:\s*none/);
});

test('the panel is started by the shared script, so the live view and the site both have it, with or without a scene', () => {
  const boot = readFileSync(join(SRC, 'boot.js'), 'utf8');
  assert.match(boot, /initChecks\(doc, win\)/);
  assert.ok(boot.indexOf('initChecks(') < boot.indexOf('chooseTier('), 'before the tier is chosen, so List has it too');
  assert.match(boot, /stopChecks\(\)|checks\.stop\(\)/);
  for (const f of ['main.js', 'app.js', 'scene.js']) assert.ok(!/initChecks/.test(readFileSync(join(SRC, f), 'utf8')), f);
  const mod = readFileSync(join(SRC, 'ui', 'checks.js'), 'utf8');
  for (const bad of ["from '../scene", "from '../app", "from '../world", "from '../engine", "from 'three'", 'data/snapshot', 'ui/snapshot', 'env.js']) assert.ok(!mod.includes(bad), `ui/checks.js imports ${bad}`);
});

test('no source reads or writes a storage or a cookie, anywhere in ui/src', () => {
  const bad = ['localStorage', 'sessionStorage', 'indexedDB', 'document.cookie', 'openDatabase', 'caches.', 'serviceWorker'];
  for (const f of walk(SRC).filter((n) => n.endsWith('.js'))) {
    const t = readFileSync(f, 'utf8');
    for (const b of bad) assert.ok(!t.includes(b), `${f.slice(SRC.length + 1)} contains ${b}`);
    assert.ok(!/cookie/i.test(t), `${f.slice(SRC.length + 1)} mentions a cookie`);
  }
});

test('the panel code makes no request, sends nothing and builds no markup from text', () => {
  for (const name of ['data/checks.js', 'data/notes.js', 'ui/checks.js']) {
    const t = readFileSync(join(SRC, name), 'utf8');
    for (const b of ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'import(', 'Worker', 'postMessage', 'Blob', 'createObjectURL', 'navigator', 'location', 'history',
      '.innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'DOMParser', 'eval(', 'new Function', 'srcdoc', 'clipboard']) {
      assert.ok(!t.includes(b), `${name} contains ${b}`);
    }
  }
});

test('the clipboard is still written in one place only (ui/home.js), and it reads the box of the notes by value', () => {
  const home = readFileSync(join(SRC, 'ui', 'home.js'), 'utf8');
  assert.equal((home.match(/writeText\(/g) || []).length, 1);
  assert.match(home, /\.value/);
});
