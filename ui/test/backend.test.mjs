// W6.9 (tests first): the panel of the local backend, ui/src/ui/backend.js (live view only). A small fake document stands in for
// the browser; its elements throw if text is ever set as markup, and it records every attribute, so a token that reached the
// page would be found. The client is the real one, on a fake request function. The real browser pass is the owner's (W6.10).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initBackend } from '../src/ui/backend.js';
import { createClient, SENTENCES, SHAPE_MESSAGE, UNAVAILABLE_MESSAGE, NO_TOKEN_MESSAGE, STOPPED_MESSAGE } from '../src/api/client.js';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const PANEL_SRC = readFileSync(join(SRC, 'ui', 'backend.js'), 'utf8');
const TEMPLATE = readFileSync(join(SRC, 'index.html'), 'utf8');
const ORIGIN = 'http://127.0.0.1:8765';
const TOKEN = 'umt1_u8jzPde0IgxLd6GncfBAepfJBd0Kh8oOOL8dKLzd-oc';
const TOKEN2 = 'umt1_J2isAjIhKtJ0RlgLKOmxgJTeKdNnFRIBXuDL7DxtpYl';
const JSON_TYPE = 'application/json; charset=utf-8';
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };

// ---- a fake document
class Text { constructor(t) { this.text = String(t); } get textContent() { return this.text; } }
class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.hidden = false; this.value = ''; this.disabled = false; this.className = '';
    this.log = []; // every attribute ever set, for the token scan
    for (const sink of ['innerHTML', 'outerHTML']) Object.defineProperty(this, sink, { set() { throw new Error(`${sink} was set`); }, get() { return ''; } });
    this.insertAdjacentHTML = () => { throw new Error('insertAdjacentHTML was called'); };
  }
  append(...nodes) { for (const n of nodes) this.children.push(typeof n === 'string' ? new Text(n) : n); }
  appendChild(n) { this.append(n); return n; }
  replaceChildren(...n) { this.children = []; this.append(...n); }
  get textContent() { return this.text !== undefined ? this.text : this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { this.text = undefined; this.children = [new Text(v)]; }
  setAttribute(k, v) { this.attrs[k] = String(v); this.log.push([k, String(v)]); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); }
  focus() { this.focused = true; }
  async click() { if (this.disabled) return; await this.fire('click'); }
  async fire(type, extra = {}) { const ev = { type, target: this, key: extra.key, preventDefault() {}, ...extra }; for (const f of this.listeners[type] || []) await f(ev); await flush(); }
  walk(fn) { fn(this); for (const c of this.children) if (c instanceof El) c.walk(fn); }
  all(pred) { const out = []; this.walk((e) => { if (pred(e)) out.push(e); }); return out; }
  byId(id) { return this.all((e) => e.attrs.id === id)[0] || null; }
}
function page() {
  const main = new El('main');
  const start = new El('section'); start.setAttribute('id', 'start');
  main.append(start); start.parentNode = main;
  main.insertBefore = (n, ref) => { main.children.splice(main.children.indexOf(ref), 0, n); n.parentNode = main; };
  const doc = { createElement: (t) => new El(t), createTextNode: (t) => new Text(t), getElementById: (id) => main.byId(id) };
  const find = (id) => main.byId(id);
  return { doc, main, find, get section() { return find('backend'); }, get note() { return find('backend-note'); }, get body() { return find('backend-body'); }, get msg() { return find('backend-msg'); } };
}
const everything = (p) => { const out = []; if (p.section) p.section.walk((e) => out.push(e)); return out; };
const allText = (p) => [p.note, p.body, p.msg].map((e) => e.textContent).join('\n');
const allAttrs = (p) => JSON.stringify(everything(p).map((e) => [e.log, e.value, e.className, e.textContent]));

// ---- a fake backend
const REQ = 'R-0a1b2c3d';
const code = { done: 0, refused: 1, usage: 64, error: 2, ask: 3, kill: 3, budget: 3, rules: 2, logbook: 2, busy: 2, body: 64, rate: 2, token: 2 };
const statusOf = { done: 200, refused: 409, usage: 400, error: 500, ask: 403, kill: 403, budget: 403, rules: 403, logbook: 500, busy: 503, body: 400, rate: 429, token: 401 };
const answer = (word, data) => {
  const gate = ['rate', 'token'].includes(word);
  const e = { schema: 1, ok: word === 'done', code: code[word], word, request: gate ? null : REQ, logged: !gate && word === 'done' };
  if (data !== undefined) e.data = data;
  return { status: statusOf[word], text: JSON.stringify(e) };
};
const row = (over = {}) => ({ id: 'Q-0001', kind: 'task', status: 'open', answered: '', title: 'Write the notes', recommendation: 'Do it', answer: '', ...over });
function backend(opts = {}) {
  const state = { kill: opts.kill || 'off', rows: opts.rows || [row()], days: 30, next: 2 };
  const seen = [];
  const fn = async (url, init) => {
    const body = init.body ? JSON.parse(init.body) : null;
    seen.push({ url, method: init.method, body, auth: init.headers.Authorization });
    if (opts.respond) { const r = await opts.respond(url, init, seen.length); if (r) return reply(r); }
    const path = url.split('?')[0];
    if (path === '/v1/status') return reply(answer('done', { kill_switch: state.kill, token: { id: 'T-91ab02cd', created: '2026-11-12', expires: '2026-12-12', days_left: state.days }, degraded: false }));
    if (path === '/v1/queue' && init.method === 'GET') return reply(answer('done', { rows: state.rows, more: false }));
    if (path === '/v1/queue' && init.method === 'POST') {
      const id = `Q-${String(state.next++).padStart(4, '0')}`;
      state.rows = [...state.rows, row({ id, kind: body.kind, title: body.title, recommendation: body.recommendation || '' })];
      return reply(answer('done', { id, added: true }));
    }
    let m = /^\/v1\/queue\/(Q-\d+)\/answer$/.exec(path);
    if (m) { state.rows = state.rows.map((r) => (r.id === m[1] ? { ...r, status: 'answered', answered: '2026-11-12', answer: body.answer } : r)); return reply(answer('done', { id: m[1], answered: '2026-11-12' })); }
    m = /^\/v1\/queue\/(Q-\d+)\/close$/.exec(path);
    if (m) { state.rows = state.rows.map((r) => (r.id === m[1] ? { ...r, status: 'closed' } : r)); return reply(answer('done', { id: m[1], status: 'closed' })); }
    if (path === '/v1/kill/on') { state.kill = 'on'; return reply(answer('done', { kill_switch: 'on' })); }
    throw new Error(`unexpected ${url}`);
  };
  return { fn, seen, state };
}
const reply = (r) => ({ status: r.status, redirected: false, type: 'basic', headers: { get: (k) => (k.toLowerCase() === 'content-type' ? JSON_TYPE : null) }, text: async () => r.text });

async function open(opts = {}, origin = ORIGIN) {
  const p = page();
  const b = backend(opts);
  const client = createClient({ location: { origin }, fetchImpl: b.fn });
  const panel = initBackend(p.doc, { location: { origin } }, { client });
  return { p, b, client, panel };
}
async function connect(ctx, token = TOKEN) {
  const field = ctx.p.find('backend-token');
  field.value = token;
  await ctx.p.find('backend-connect').click();
  return field;
}
const rowsText = (ctx) => ctx.p.find('backend-queue').textContent;

// ---------------------------------------------------------------------------------------------------- not available
test('opened from disk or from another address: the section says to open the page with umwayi serve, has no field or button, and sends nothing', async () => {
  for (const origin of ['null', 'file://', 'http://localhost:8765', 'https://umwayi.example']) {
    const ctx = await open({}, origin);
    assert.ok(ctx.p.section, 'the section is made so the owner can read why');
    assert.equal(ctx.p.section.hidden, false);
    assert.equal(ctx.p.main.children[0], ctx.p.section, 'it stands before the Start section');
    assert.equal(ctx.p.note.textContent, UNAVAILABLE_MESSAGE);
    assert.equal(everything(ctx.p).filter((e) => ['input', 'button', 'select', 'textarea'].includes(e.tag)).length, 0);
    assert.equal(ctx.b.seen.length, 0);
  }
});

test('a page without the section does not throw, and the panel makes the client itself when none is given', async () => {
  const doc = { createElement: () => new El('x'), createTextNode: (t) => new Text(t), getElementById: () => null };
  assert.doesNotThrow(() => initBackend(doc, { location: { origin: 'null' } }).stop());
  const p = page();
  const panel = initBackend(p.doc, { location: { origin: 'null' } });
  assert.equal(p.note.textContent, UNAVAILABLE_MESSAGE);
  panel.stop();
});

// ---------------------------------------------------------------------------------------------------- the token field
test('on the right address the panel shows a password field for the token and sends nothing until a token is pasted', async () => {
  const ctx = await open();
  assert.equal(ctx.p.section.hidden, false);
  const field = ctx.p.find('backend-token');
  assert.equal(field.attrs.type, 'password');
  assert.equal(field.attrs.autocomplete, 'off');
  assert.equal(field.attrs.spellcheck, 'false');
  assert.ok(field.attrs['aria-label']);
  assert.ok(ctx.p.find('backend-connect'));
  assert.equal(ctx.b.seen.length, 0, 'nothing is sent when the page opens');
  assert.match(ctx.p.note.textContent, /umwayi serve token create/);
  await ctx.p.find('backend-connect').click();
  assert.equal(ctx.p.msg.textContent, NO_TOKEN_MESSAGE);
  assert.equal(ctx.b.seen.length, 0, 'an empty field sends nothing');
});

test('a pasted token is copied to the client and the field is cleared at once; a token of the wrong shape is refused and cleared too', async () => {
  const ctx = await open();
  const field = await connect(ctx, 'not a token');
  assert.equal(field.value, '');
  assert.equal(ctx.p.msg.textContent, NO_TOKEN_MESSAGE);
  assert.equal(ctx.b.seen.length, 0);
  await connect(ctx, TOKEN);
  assert.equal(field.value, '', 'the field is cleared');
  assert.ok(ctx.b.seen.length >= 2, 'the status and the queue were asked');
  assert.deepEqual(ctx.b.seen.map((s) => s.url).slice(0, 2), ['/v1/status', '/v1/queue']);
  assert.ok(ctx.b.seen.every((s) => s.auth === `Bearer ${TOKEN}`));
});

test('the token is nowhere in the page: no text, no attribute, no value, at any step', async () => {
  const ctx = await open({ respond: (url, init, n) => (n === 5 ? answer('ask') : null) });
  await connect(ctx);
  await ctx.p.find('backend-add-title').fire('input', {});
  ctx.p.find('backend-add-title').value = 'A title';
  await ctx.p.find('backend-add').click();
  await ctx.p.find('backend-refresh').click();
  await ctx.p.find('backend-kill').click();
  for (const text of [allText(ctx.p), allAttrs(ctx.p)]) {
    assert.ok(!text.includes(TOKEN), 'the token is in the page');
    assert.ok(!text.includes('umt1_'), 'a part of a token is in the page');
  }
  assert.ok(ctx.b.seen.length > 4);
});

// ---------------------------------------------------------------------------------------------------- what it shows
test('after connecting it shows the kill switch, the days left on the token, and the queue rows as text', async () => {
  const ctx = await open({ rows: [row(), row({ id: 'Q-0002', kind: 'decision', title: 'Pick a name', recommendation: 'Umwayi', status: 'answered', answered: '2026-11-11', answer: 'Yes' })] });
  await connect(ctx);
  const status = ctx.p.find('backend-status').textContent;
  assert.match(status, /Kill switch: off/);
  assert.match(status, /30 days left/);
  const q = rowsText(ctx);
  for (const w of ['Q-0001', 'Write the notes', 'Do it', 'Q-0002', 'Pick a name', 'decision', 'answered', 'Yes']) assert.ok(q.includes(w), w);
  assert.equal(ctx.p.msg.textContent, '');
});

test('text from a response is set as text: markup in a title is shown as typed and nothing builds an element from it', async () => {
  const evil = '<img src=x onerror=alert(1)><script>alert(2)</script>';
  const ctx = await open({ rows: [row({ title: evil, recommendation: evil })] });
  await connect(ctx);
  assert.ok(rowsText(ctx).includes(evil));
  assert.equal(everything(ctx.p).filter((e) => ['img', 'script'].includes(e.tag)).length, 0);
});

test('one day left, no days, and an unknown kill switch are told in plain words', async () => {
  for (const [days, kill, want] of [[1, 'off', /1 day left/], [0, 'off', /expires today/], [-2, 'off', /has run out/], [5, 'unknown', /Kill switch: unknown/], [5, 'on', /Kill switch: on/]]) {
    const ctx = await open({ kill });
    ctx.b.state.days = days;
    await connect(ctx);
    assert.match(ctx.p.find('backend-status').textContent, want);
  }
});

// ---------------------------------------------------------------------------------------------------- what it does
test('adding an item sends only the fields of the form, shows Done, and reloads the queue', async () => {
  const ctx = await open();
  await connect(ctx);
  ctx.p.find('backend-add-kind').value = 'decision';
  ctx.p.find('backend-add-title').value = 'A new decision';
  ctx.p.find('backend-add-rec').value = 'Say yes';
  const before = ctx.b.seen.length;
  await ctx.p.find('backend-add').click();
  const post = ctx.b.seen.slice(before).find((s) => s.method === 'POST');
  assert.equal(post.url, '/v1/queue');
  assert.deepEqual(post.body, { kind: 'decision', title: 'A new decision', recommendation: 'Say yes' });
  assert.ok(rowsText(ctx).includes('A new decision'));
  assert.equal(ctx.p.msg.textContent, SENTENCES.done);
  assert.equal(ctx.p.find('backend-add-title').value, '', 'the form is cleared after it was accepted');
});

test('adding with an empty title sends nothing and says what is missing', async () => {
  const ctx = await open();
  await connect(ctx);
  const before = ctx.b.seen.length;
  ctx.p.find('backend-add-title').value = '   ';
  await ctx.p.find('backend-add').click();
  assert.equal(ctx.b.seen.length, before);
  assert.match(ctx.p.msg.textContent, /title/i);
});

test('answering and closing use the id of the row and nothing typed into the address', async () => {
  const ctx = await open({ rows: [row(), row({ id: 'Q-0002', title: 'Second' })] });
  await connect(ctx);
  const rows = ctx.p.find('backend-queue').all((e) => e.attrs['data-id']);
  assert.deepEqual(rows.map((r) => r.attrs['data-id']), ['Q-0001', 'Q-0002']);
  const first = rows[0];
  first.all((e) => e.tag === 'input')[0].value = 'Go ahead';
  const before = ctx.b.seen.length;
  await first.all((e) => e.tag === 'button' && /Answer/.test(e.textContent))[0].click();
  const post = ctx.b.seen.slice(before).find((s) => s.method === 'POST');
  assert.equal(post.url, '/v1/queue/Q-0001/answer');
  assert.deepEqual(post.body, { answer: 'Go ahead' });
  assert.match(rowsText(ctx), /Go ahead/);
  const second = ctx.p.find('backend-queue').all((e) => e.attrs['data-id'] === 'Q-0002')[0];
  const mark = ctx.b.seen.length;
  await second.all((e) => e.tag === 'button' && /Close/.test(e.textContent))[0].click();
  assert.equal(ctx.b.seen[mark].url, '/v1/queue/Q-0002/close');
  assert.deepEqual(ctx.b.seen[mark].body, {});
});

test('answering with an empty answer sends nothing; a closed row has no buttons', async () => {
  const ctx = await open({ rows: [row(), row({ id: 'Q-0002', status: 'closed' })] });
  await connect(ctx);
  const first = ctx.p.find('backend-queue').all((e) => e.attrs['data-id'] === 'Q-0001')[0];
  const before = ctx.b.seen.length;
  await first.all((e) => e.tag === 'button' && /Answer/.test(e.textContent))[0].click();
  assert.equal(ctx.b.seen.length, before);
  assert.match(ctx.p.msg.textContent, /answer/i);
  const closed = ctx.p.find('backend-queue').all((e) => e.attrs['data-id'] === 'Q-0002')[0];
  assert.equal(closed.all((e) => e.tag === 'button').length, 0);
});

test('Stop everything turns the kill switch on and shows it; there is no button for anything else that changes the state', async () => {
  const ctx = await open();
  await connect(ctx);
  const kill = ctx.p.find('backend-kill');
  assert.equal(kill.textContent, 'Stop everything');
  const before = ctx.b.seen.length;
  await kill.click();
  const post = ctx.b.seen.slice(before).find((s) => s.method === 'POST');
  assert.equal(post.url, '/v1/kill/on');
  assert.match(ctx.p.find('backend-status').textContent, /Kill switch: on/);
  const names = everything(ctx.p).filter((e) => e.tag === 'button').map((e) => e.textContent);
  assert.deepEqual([...new Set(names)].sort(), ['Add', 'Answer', 'Close', 'Refresh', 'Stop everything', 'Use token']);
});

test('Refresh asks again, by hand; the panel sets no timer and never asks by itself', async () => {
  const ctx = await open();
  await connect(ctx);
  const n = ctx.b.seen.length;
  await flush();
  assert.equal(ctx.b.seen.length, n, 'nothing is asked without a click');
  await ctx.p.find('backend-refresh').click();
  assert.deepEqual(ctx.b.seen.slice(n).map((s) => s.url), ['/v1/status', '/v1/queue']);
  for (const bad of ['setTimeout', 'setInterval', 'requestAnimationFrame', 'requestIdleCallback', 'Worker', 'EventSource']) assert.ok(!PANEL_SRC.includes(bad), bad);
});

// ---------------------------------------------------------------------------------------------------- refusals and failure
test('an ordinary refusal is shown in its own words and the panel goes on', async () => {
  for (const word of ['ask', 'kill', 'budget', 'rules', 'refused', 'usage', 'busy', 'rate', 'error']) {
    const ctx = await open({ respond: (url, init) => (init.method === 'POST' ? answer(word) : null) });
    await connect(ctx);
    ctx.p.find('backend-add-title').value = 'A title';
    await ctx.p.find('backend-add').click();
    assert.equal(ctx.p.msg.textContent, SENTENCES[word], word);
    assert.equal(ctx.p.find('backend-add').disabled, false, `${word}: the panel stopped`);
    assert.equal(ctx.client.stopped(), false);
    assert.ok(ctx.p.find('backend-add-title').value === 'A title', 'what was typed is kept after a refusal');
  }
  assert.match(SENTENCES.ask, /^Ask me first/);
});

test('a bad answer shows the one message, empties the queue, disables every control, and nothing more is sent', async () => {
  const bads = [
    () => ({ status: 200, text: 'not json' }), () => ({ status: 500, text: answer('done', {}).text }),
    () => ({ status: 200, text: JSON.stringify({ schema: 1, ok: true, code: 0, word: 'done', request: REQ, logged: true, data: { surprise: 1 } }) }),
    () => { throw new Error('offline'); },
  ];
  for (const bad of bads) {
    for (const when of [1, 2]) {
      const ctx = await open({ respond: (url, init, n) => (n === when ? bad() : null) });
      await connect(ctx);
      const sent = ctx.b.seen.length;
      const text = ctx.p.msg.textContent;
      assert.ok(text === SHAPE_MESSAGE || text === 'umwayi did not answer', text);
      assert.equal(ctx.client.stopped(), true);
      for (const e of everything(ctx.p).filter((x) => ['input', 'button', 'select'].includes(x.tag))) assert.equal(e.disabled, true, `${e.attrs.id || e.textContent} is still on`);
      assert.equal(ctx.p.find('backend-queue').textContent, '', 'no rows are left on show');
      for (const id of ['backend-connect', 'backend-refresh', 'backend-kill', 'backend-add']) { const b = ctx.p.find(id); if (b) await b.click(); }
      await ctx.p.find('backend-token')?.fire('keydown', { key: 'Enter' });
      assert.equal(ctx.b.seen.length, sent, 'a click after the failure sent something');
      assert.ok(!allText(ctx.p).includes(TOKEN) && !allAttrs(ctx.p).includes('umt1_'));
    }
  }
});

test('data that was shown is removed when a later answer is bad, or the token turns out wrong; a bad answer locks every control', async () => {
  for (const [name, later, locked] of [['a bad answer', () => ({ status: 200, text: 'not json' }), true], ['a wrong token', () => answer('token'), false]]) {
    let from = 1000;
    const ctx = await open({ respond: (url, init, n) => (n >= from ? later() : null) });
    await connect(ctx);
    assert.ok(rowsText(ctx).includes('Write the notes'), 'the rows are shown first');
    assert.match(ctx.p.find('backend-status').textContent, /Kill switch/);
    from = ctx.b.seen.length + 1;
    await ctx.p.find('backend-refresh').click();
    assert.equal(rowsText(ctx), '', `${name}: the rows stayed on show`);
    assert.equal(ctx.p.find('backend-status').textContent, '', `${name}: the status stayed on show`);
    assert.equal(ctx.p.find('backend-area').hidden, true, `${name}: the area stayed shown`);
    const off = everything(ctx.p).filter((e) => ['input', 'button', 'select'].includes(e.tag) && e.disabled).length;
    assert.equal(off > 0, locked, `${name}: controls disabled ${off}`);
  }
});

test('Enter in the token field after a failure sends nothing and leaves the message as it was', async () => {
  const ctx = await open({ respond: (url, init, n) => (n === 1 ? { status: 200, text: 'not json' } : null) });
  await connect(ctx);
  const text = ctx.p.msg.textContent;
  assert.equal(text, SHAPE_MESSAGE);
  const sent = ctx.b.seen.length;
  const field = ctx.p.find('backend-token');
  field.value = TOKEN2;
  await field.fire('keydown', { key: 'Enter' });
  assert.equal(ctx.b.seen.length, sent);
  assert.equal(ctx.p.msg.textContent, text);
});

test('a new item takes the kind task when the owner did not choose one', async () => {
  const ctx = await open();
  await connect(ctx);
  ctx.p.find('backend-add-title').value = 'Plain';
  const before = ctx.b.seen.length;
  await ctx.p.find('backend-add').click();
  assert.equal(ctx.b.seen.slice(before).find((x) => x.method === 'POST').body.kind, 'task');
  ctx.p.find('backend-add-kind').value = 'agent';
  ctx.p.find('backend-add-title').value = 'Odd';
  const mark = ctx.b.seen.length;
  await ctx.p.find('backend-add').click();
  assert.equal(ctx.b.seen.slice(mark).find((x) => x.method === 'POST').body.kind, 'task', 'only task and decision can be sent');
});

test('a wrong token says so, empties the page of data, and waits for a new token; then it goes on', async () => {
  let wrong = true;
  const ctx = await open({ respond: () => (wrong ? answer('token') : null) });
  await connect(ctx);
  assert.equal(ctx.p.msg.textContent, SENTENCES.token);
  assert.equal(ctx.client.hasToken(), false);
  assert.equal(ctx.p.find('backend-queue').textContent, '');
  assert.equal(ctx.p.find('backend-token').disabled, false);
  const n = ctx.b.seen.length;
  await ctx.p.find('backend-refresh').click();
  assert.equal(ctx.b.seen.length, n, 'no token, nothing sent');
  assert.equal(ctx.p.msg.textContent, NO_TOKEN_MESSAGE);
  wrong = false;
  await connect(ctx, TOKEN2);
  assert.match(ctx.p.find('backend-status').textContent, /Kill switch: off/);
  assert.ok(!allText(ctx.p).includes(TOKEN2));
});

test('a second click while a request is on its way does nothing, but Stop everything is never held back', async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const ctx = await open({ respond: async (url, init) => { if (init.method === 'POST' && url === '/v1/queue') await gate; return null; } });
  await connect(ctx);
  ctx.p.find('backend-add-title').value = 'Once';
  const before = ctx.b.seen.length;
  const first = ctx.p.find('backend-add').fire('click');
  await flush();
  await ctx.p.find('backend-add').fire('click');
  await ctx.p.find('backend-refresh').fire('click');
  await ctx.p.find('backend-kill').fire('click');
  const during = ctx.b.seen.slice(before).map((s) => `${s.method} ${s.url}`);
  assert.deepEqual(during, ['POST /v1/queue', 'POST /v1/kill/on', 'GET /v1/status', 'GET /v1/queue'].slice(0, during.length));
  assert.ok(during.includes('POST /v1/kill/on'), 'Stop everything went through');
  assert.equal(during.filter((x) => x === 'POST /v1/queue').length, 1, 'the second click on Add sent something');
  release();
  await first;
  await flush();
  assert.equal(ctx.b.seen.slice(before).filter((s) => s.method === 'POST' && s.url === '/v1/queue').length, 1);
});

test('Enter in the token field connects, as the button does', async () => {
  const ctx = await open();
  const field = ctx.p.find('backend-token');
  field.value = TOKEN;
  await field.fire('keydown', { key: 'Enter' });
  assert.equal(field.value, '');
  assert.ok(ctx.b.seen.length >= 2);
});

test('stop takes the listeners off', async () => {
  const ctx = await open();
  const btn = ctx.p.find('backend-connect');
  assert.ok((btn.listeners.click || []).length > 0);
  ctx.panel.stop();
  assert.equal((btn.listeners.click || []).length, 0);
});

// ---------------------------------------------------------------------------------------------------- the source and the template
test('the panel code sends nothing itself, builds no markup, keeps nothing and writes nowhere', () => {
  for (const bad of ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'import(', 'localStorage', 'sessionStorage', 'indexedDB', 'cookie', 'history', 'postMessage', 'console',
    '.innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'DOMParser', 'eval(', 'new Function', 'srcdoc', 'location.', 'navigator', 'Blob', 'createObjectURL', 'clipboard']) {
    assert.ok(!PANEL_SRC.includes(bad), `backend.js contains ${bad}`);
  }
  assert.ok(!/[\u2014\u2013]/.test(PANEL_SRC));
  assert.ok(/from '\.\.\/api\/client\.js'/.test(PANEL_SRC), 'the panel uses the one client');
  assert.ok(!/\.setAttribute\(\s*'value'/.test(PANEL_SRC) && !/\.defaultValue/.test(PANEL_SRC), 'a value is never written as an attribute');
});

test('the page template has no id of the panel: the public site shows the same template and has no place for it', () => {
  assert.ok(!/backend/.test(TEMPLATE), 'the template mentions the backend panel');
  assert.match(TEMPLATE, /<section[^>]*\bid="start"/, 'the panel is placed before this section');
});
