// W6.9 (tests first): the page client, ui/src/api/client.js. It is the one place that sends a request. Every test runs it
// against a fake request function, so no network is touched. The tests check: the origin it will run on, the requests it makes
// against the route table of umwayi/servegate.py (read from the file, so the two cannot drift), the token in one variable and
// one header, every kind of bad answer (the client stops and sends nothing more), and the words.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createClient, readEnvelope, ROUTES, SENTENCES, SHAPE_MESSAGE, UNAVAILABLE_MESSAGE, NO_TOKEN_MESSAGE, STOPPED_MESSAGE } from '../src/api/client.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const CLIENT_SRC = readFileSync(join(HERE, '..', 'src', 'api', 'client.js'), 'utf8');
const ORIGIN = 'http://127.0.0.1:8765';
const TOKEN = 'umt1_u8jzPde0IgxLd6GncfBAepfJBd0Kh8oOOL8dKLzd-oc';
const TOKEN2 = 'umt1_J2isAjIhKtJ0RlgLKOmxgJTeKdNnFRIBXuDL7DxtpYl';
const JSON_TYPE = 'application/json; charset=utf-8';

// ---- the words of the server, as the server defines them
const WORDS_SRC = readFileSync(join(REPO, 'umwayi', 'serve.py'), 'utf8');
const GATE_SRC = readFileSync(join(REPO, 'umwayi', 'servegate.py'), 'utf8');
const SERVER_WORDS = {};
for (const m of WORDS_SRC.slice(WORDS_SRC.indexOf('WORDS = {'), WORDS_SRC.indexOf('_REASON')).matchAll(/"(\w+)": \((\d+), (\d+)\)/g)) SERVER_WORDS[m[1]] = [[Number(m[2])], Number(m[3])];
const GATE_CODES = {};
for (const m of GATE_SRC.slice(GATE_SRC.indexOf('WORD_CODE = {'), GATE_SRC.indexOf('GATE_WORDS')).matchAll(/"(\w+)": (\d+)/g)) GATE_CODES[m[1]] = Number(m[2]);
// the statuses a gate word is sent with: every _no(STATUS, "word" ...) in the gate and parse_body
const GATE_STATUS = {};
for (const m of GATE_SRC.matchAll(/_no\((\d+), "(\w+)"/g)) (GATE_STATUS[m[2]] ||= new Set()).add(Number(m[1]));

// ---- a fake request function. respond(url, init, n) returns { status, type, text, ... } or throws.
function fake(respond) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    const r = await respond(url, init, calls.length);
    if (r instanceof Error) throw r;
    if (r === null) return null;
    const headers = { get: (k) => (k.toLowerCase() === 'content-type' ? (r.type === undefined ? JSON_TYPE : r.type) : null) };
    return { status: r.status, redirected: r.redirected === true, type: r.responseType || 'basic', headers: r.noHeaders ? undefined : headers, text: async () => { if (r.textFails) throw new Error('read'); return r.text; } };
  };
  fn.calls = calls;
  return fn;
}

const REQ = 'R-0a1b2c3d';
const env = (word, over = {}, data) => {
  const ok = word === 'done';
  const code = (SERVER_WORDS[word] || [0, GATE_CODES[word]])[1];
  const e = { schema: 1, ok, code: word === 'done' ? 0 : code, word, request: REQ, logged: true, ...over };
  if (data !== undefined) e.data = data;
  return e;
};
const reply = (status, e) => ({ status, text: typeof e === 'string' ? e : JSON.stringify(e) });
const DATA = {
  status: { kill_switch: 'off', token: { id: 'T-91ab02cd', created: '2026-11-12', expires: '2026-12-12', days_left: 30 }, degraded: false },
  'queue.list': { rows: [{ id: 'Q-0001', kind: 'task', status: 'open', answered: '', title: 'Write the notes', recommendation: 'Do it', answer: '' }], more: false },
  'queue.add': { id: 'Q-0002', added: true },
  'queue.answer': { id: 'Q-0001', answered: '2026-11-12' },
  'queue.close': { id: 'Q-0001', status: 'closed' },
  'kill.on': { kill_switch: 'on' },
};
const ARGS = {
  status: undefined,
  'queue.list': { query: { status: 'open', kind: 'task' } },
  'queue.add': { body: { kind: 'task', title: 'A title', recommendation: 'A recommendation', if_not_open: true } },
  'queue.answer': { id: 'Q-0001', body: { answer: 'Yes', revisit_if: 'It changes' } },
  'queue.close': { id: 'Q-0001' },
  'kill.on': { body: { reason: 'testing' } },
};
const row = (i) => ({ id: `Q-${String(i + 1).padStart(4, '0')}`, kind: 'task', status: 'open', answered: '', title: 'x'.repeat(4096), recommendation: '', answer: '' });
const good = (id) => reply(200, env('done', {}, DATA[id]));
const ready = (respond) => {
  const f = fake(respond);
  const c = createClient({ location: { origin: ORIGIN }, fetchImpl: f });
  assert.equal(c.setToken(TOKEN), true);
  return { c, f };
};

// ---------------------------------------------------------------------------------------------------- the origin
test('the client runs only on http://127.0.0.1 and a port; anywhere else it is closed, says so and sends nothing', async () => {
  const bad = ['file://', 'null', '', 'http://localhost:8765', 'http://127.0.0.1', 'http://127.0.0.1:', 'https://127.0.0.1:8765', 'http://127.0.0.1:8765/',
    'http://127.0.0.1:80', 'http://127.0.0.1:1023', 'http://127.0.0.1:65536', 'http://127.0.0.1:999999', 'http://127.0.0.1:8765@evil.example', 'http://127.0.0.1.evil.example:8765',
    'http://0.0.0.0:8765', 'http://[::1]:8765', 'http://127.0.0.2:8765', 'http://127.0.0.1:87a5', 'HTTP://127.0.0.1:8765', 'http://127.0.0.1:8765 ', ' http://127.0.0.1:8765',
    'https://umwayi.example', 'http://127.0.0.1:8765\n', 'http://127.0.0.1:+8765'];
  for (const origin of bad) {
    const f = fake(() => good('status'));
    const c = createClient({ location: { origin }, fetchImpl: f });
    assert.equal(c.available, false, JSON.stringify(origin));
    assert.ok(Object.isFrozen(c));
    assert.equal(c.setToken(TOKEN), false);
    assert.equal(c.hasToken(), false);
    const r = await c.call('status');
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'unavailable');
    assert.equal(r.message, UNAVAILABLE_MESSAGE);
    assert.equal(f.calls.length, 0, `${origin} sent a request`);
  }
  for (const loc of [undefined, null, {}, { origin: 5 }, { origin: null }]) {
    const c = createClient({ location: loc, fetchImpl: fake(() => good('status')) });
    assert.equal(c.available, false);
  }
  assert.equal(createClient().available, false);
  assert.equal(UNAVAILABLE_MESSAGE, 'Open this page with umwayi serve');
});

test('on the right origin the client is available, frozen, and has only the listed members', () => {
  for (const origin of ['http://127.0.0.1:8765', 'http://127.0.0.1:1024', 'http://127.0.0.1:65535', 'http://127.0.0.1:54321']) {
    const c = createClient({ location: { origin }, fetchImpl: fake(() => good('status')) });
    assert.equal(c.available, true, origin);
    assert.ok(Object.isFrozen(c));
    assert.deepEqual(Object.keys(c).sort(), ['available', 'call', 'clearToken', 'hasToken', 'setToken', 'stopped']);
  }
});

test('without a request function of its own the client uses the global one, with a relative path', async () => {
  const f = fake(() => good('status'));
  const saved = globalThis.fetch;
  globalThis.fetch = f;
  try {
    const c = createClient({ location: { origin: ORIGIN } });
    c.setToken(TOKEN);
    const r = await c.call('status');
    assert.equal(r.ok, true);
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].url, '/v1/status');
  } finally { globalThis.fetch = saved; }
});

// ---------------------------------------------------------------------------------------------------- the route table
function serverRoutes() {
  const body = GATE_SRC.slice(GATE_SRC.indexOf('ROUTES = ('), GATE_SRC.indexOf('_BY_ID'));
  const out = {};
  for (const chunk of body.split('\n    Route(').slice(1)) {
    const m = /^"([^"]+)", "([A-Z]+)", "([^"]+)", "(\w+)", (\d+)/.exec(chunk);
    assert.ok(m, chunk);
    const q = /query=\(([^)]*)\)/.exec(chunk);
    const fi = chunk.indexOf('fields=');
    const fieldText = fi < 0 ? '' : chunk.slice(fi, chunk.indexOf('required=') < 0 ? undefined : chunk.indexOf('required='));
    const rq = /required=\(([^)]*)\)/.exec(chunk);
    out[m[1]] = {
      method: m[2], path: m[3], cls: m[4], cap: Number(m[5]),
      query: q ? [...q[1].matchAll(/"(\w+)"/g)].map((x) => x[1]) : [],
      fields: [...fieldText.matchAll(/\("(\w+)", "(\w+)"\)/g)].map((x) => [x[1], x[2]]),
      required: rq ? [...rq[1].matchAll(/"(\w+)"/g)].map((x) => x[1]) : [],
    };
  }
  return out;
}

test('the client table is a subset of the closed route table of the server, with the same method, path, query and fields', () => {
  const server = serverRoutes();
  assert.ok(Object.keys(server).length >= 12, 'the server table was read');
  assert.deepEqual(Object.keys(ROUTES).sort(), ['kill.on', 'queue.add', 'queue.answer', 'queue.close', 'queue.list', 'status']);
  for (const [id, r] of Object.entries(ROUTES)) {
    const s = server[id];
    assert.ok(s, `${id} is not a route of the server`);
    assert.equal(r.method, s.method, id);
    assert.equal(r.path, s.path, id);
    assert.deepEqual([...r.query], s.query, id);
    assert.deepEqual(r.fields.map((f) => [...f]), s.fields, id);
    assert.deepEqual([...r.required], s.required, id);
    assert.ok(r.path.startsWith('/v1/'), id);
    assert.notEqual(s.cls, 'page', id);
  }
  assert.ok(Object.isFrozen(ROUTES));
});

test('each call is one request as the table says: method, relative path, headers, body, and the safe options', async () => {
  const server = serverRoutes();
  for (const id of Object.keys(ROUTES)) {
    const { c, f } = ready(() => good(id));
    const r = await c.call(id, ARGS[id]);
    assert.equal(r.ok, true, id);
    assert.equal(f.calls.length, 1, id);
    const { url, init } = f.calls[0];
    const s = server[id];
    const want = s.path.replace('{id}', 'Q-0001') + (id === 'queue.list' ? '?status=open&kind=task' : '');
    assert.equal(url, want, id);
    assert.ok(url.startsWith('/v1/') && !/^[a-z]+:/i.test(url) && !url.includes('//'), url);
    assert.equal(init.method, s.method, id);
    assert.equal(init.credentials, 'omit');
    assert.equal(init.cache, 'no-store');
    assert.equal(init.redirect, 'error');
    assert.equal(init.referrerPolicy, 'no-referrer');
    assert.equal(init.mode, 'same-origin');
    assert.deepEqual(Object.keys(init).sort(), s.method === 'POST' ? ['body', 'cache', 'credentials', 'headers', 'method', 'mode', 'redirect', 'referrerPolicy'] : ['cache', 'credentials', 'headers', 'method', 'mode', 'redirect', 'referrerPolicy']);
    if (s.method === 'POST') {
      assert.deepEqual(Object.keys(init.headers).sort(), ['Authorization', 'Content-Type'], id);
      assert.equal(init.headers['Content-Type'], 'application/json');
      const body = JSON.parse(init.body);
      assert.ok(Object.keys(body).every((k) => s.fields.some((x) => x[0] === k)), id);
      assert.ok(s.required.every((k) => k in body), id);
      assert.ok(init.body.length <= s.cap, id);
      assert.equal(init.body, JSON.stringify(ARGS[id] && ARGS[id].body ? ARGS[id].body : {}));
    } else {
      assert.deepEqual(Object.keys(init.headers), ['Authorization'], id);
      assert.equal('body' in init, false, id);
    }
  }
});

test('a POST without fields still sends a JSON object, as the server requires', async () => {
  const { c, f } = ready(() => good('queue.close'));
  await c.call('queue.close', { id: 'Q-0001' });
  assert.equal(f.calls[0].init.body, '{}');
  assert.equal(f.calls[0].init.headers['Content-Type'], 'application/json');
});

test('a query value that is empty or missing is left out; the keys follow the table order', async () => {
  const { c, f } = ready(() => good('queue.list'));
  await c.call('queue.list', { query: { kind: 'decision', status: '' } });
  await c.call('queue.list');
  assert.equal(f.calls[0].url, '/v1/queue?kind=decision');
  assert.equal(f.calls[1].url, '/v1/queue');
});

test('arguments that do not fit the table are refused before anything is sent, and the client goes on', async () => {
  const cases = [
    ['page'], ['agents.check', { id: 'Q-0001' }], ['__proto__'], ['constructor'], ['toString'], ['hasOwnProperty'], [''], [undefined], [null], [5], ['Status'], ['status '],
    ['queue.close'], ['queue.close', { id: 'Q-1' }], ['queue.close', { id: '../x' }], ['queue.close', { id: 'Q-0001/answer' }], ['queue.close', { id: 'Q-0001?x=1' }], ['queue.close', { id: 'q-0001' }],
    ['queue.close', { id: 5 }], ['queue.close', { id: 'Q-0001\n' }], ['queue.close', { id: ['Q-0001'] }], ['queue.answer', { id: 'Q-0001' }],
    ['status', { id: 'Q-0001' }], ['status', { body: {} }], ['status', { x: 1 }], ['status', 5], ['status', []], ['status', { query: { status: 'open' } }],
    ['queue.list', { query: { status: 'open now' } }], ['queue.list', { query: { status: 'x'.repeat(17) } }], ['queue.list', { query: { status: 'OPEN' } }], ['queue.list', { query: { status: 'a&b=c' } }],
    ['queue.list', { query: { other: 'a' } }], ['queue.list', { query: { status: 5 } }], ['queue.list', { body: {} }], ['queue.list', { query: [] }],
    ['queue.add', { body: { kind: 'task' } }], ['queue.add', { body: { title: 'x' } }], ['queue.add', { body: { kind: 'task', title: 5 } }], ['queue.add', { body: { kind: 'task', title: 'x', extra: 'y' } }],
    ['queue.add', { body: { kind: 'task', title: 'x', if_not_open: 'yes' } }], ['queue.add', { body: { kind: 'task', title: 'x'.repeat(4097) } }], ['queue.add', { body: [] }], ['queue.add', { body: null }],
    ['queue.add', { body: { kind: 'task', title: 'x', recommendation: true } }], ['queue.answer', { id: 'Q-0001', body: { answer: 1 } }], ['queue.answer', { id: 'Q-0001', body: {} }],
    ['kill.on', { body: { reason: 5 } }], ['kill.on', { body: { why: 'x' } }], ['kill.on', { id: 'Q-0001' }],
  ];
  for (const [id, args] of cases) {
    const { c, f } = ready(() => good('status'));
    const r = await c.call(id, args);
    assert.equal(r.ok, false, JSON.stringify([id, args]));
    assert.equal(r.kind, 'usage');
    assert.equal(f.calls.length, 0, `${JSON.stringify([id, args])} was sent`);
    assert.equal(c.stopped(), false);
    assert.equal(c.hasToken(), true);
    assert.equal((await c.call('status')).ok, true, 'the client goes on');
  }
});

// ---------------------------------------------------------------------------------------------------- the token
test('the token goes out in the Authorization header and nowhere else, and is never in a result or in the client', async () => {
  const { c, f } = ready((url, init, n) => (n === 3 ? reply(403, env('ask')) : good(n === 1 ? 'status' : 'queue.add')));
  const results = [await c.call('status'), await c.call('queue.add', ARGS['queue.add']), await c.call('queue.close', { id: 'Q-0001' })];
  for (const { url, init } of f.calls) {
    assert.equal(init.headers.Authorization, `Bearer ${TOKEN}`);
    assert.ok(!url.includes(TOKEN) && !url.includes('umt1_'));
    const { Authorization, ...rest } = init.headers;
    assert.ok(!JSON.stringify([rest, { ...init, headers: null }]).includes('umt1_'));
    assert.deepEqual(Object.keys(init.headers).filter((k) => init.headers[k].includes('umt1_')), ['Authorization']);
  }
  for (const text of [JSON.stringify(results), JSON.stringify(Object.keys(c)), String(Object.values(c).map((v) => String(v)).join('|')), JSON.stringify(c)]) {
    assert.ok(!text.includes(TOKEN), 'the token leaked');
    assert.ok(!text.includes('umt1_u8'), 'a part of the token leaked');
  }
  assert.equal(c.hasToken(), true);
  assert.equal(Object.getOwnPropertyNames(c).some((k) => typeof c[k] === 'string' && c[k].includes('umt1_')), false);
});

test('a whole session writes nothing to the console and leaves no new global, and no global holds the token', async () => {
  const names = ['log', 'info', 'warn', 'error', 'debug', 'trace'];
  const saved = Object.fromEntries(names.map((n) => [n, console[n]]));
  const printed = [];
  for (const n of names) console[n] = (...a) => printed.push(a.map(String).join(' '));
  const before = new Set(Object.getOwnPropertyNames(globalThis));
  try {
    const { c } = ready((url, init, n) => (n === 4 ? { status: 200, text: 'not json' } : good(n % 2 ? 'status' : 'queue.list')));
    for (let i = 0; i < 6; i++) await c.call(i % 2 ? 'queue.list' : 'status');
    await c.call('queue.close', { id: 'Q-0001' });
    c.setToken(TOKEN2);
    c.clearToken();
  } finally { for (const n of names) console[n] = saved[n]; }
  assert.deepEqual(printed, [], 'something was written to the console');
  const added = Object.getOwnPropertyNames(globalThis).filter((k) => !before.has(k));
  assert.deepEqual(added, [], 'a global was made');
  for (const k of Object.getOwnPropertyNames(globalThis)) {
    let v; try { v = globalThis[k]; } catch (e) { continue; }
    if (typeof v === 'string') assert.ok(!v.includes('umt1_'), `global ${k} holds a token`);
  }
});

test('a token with the wrong shape is not kept; a good one replaces the old one; clearToken forgets it', async () => {
  const f = fake(() => good('status'));
  const c = createClient({ location: { origin: ORIGIN }, fetchImpl: f });
  for (const bad of ['', 'umt1_', TOKEN.slice(1), `${TOKEN} `, ` ${TOKEN}`, `${TOKEN}\n`, `${TOKEN}A`, TOKEN.replace('umt1_', 'umt2_'), TOKEN.slice(0, -1), TOKEN.slice(0, 10) + '!' + TOKEN.slice(11), null, undefined, 5, {}, [TOKEN], { toString: () => TOKEN }]) {
    assert.equal(c.setToken(bad), false, String(bad));
    assert.equal(c.hasToken(), false);
  }
  assert.equal(f.calls.length, 0);
  assert.equal(c.setToken(TOKEN), true);
  assert.equal(c.setToken(TOKEN2), true);
  await c.call('status');
  assert.equal(f.calls[0].init.headers.Authorization, `Bearer ${TOKEN2}`);
  c.clearToken();
  assert.equal(c.hasToken(), false);
  const r = await c.call('status');
  assert.equal(r.kind, 'notoken');
  assert.equal(r.message, NO_TOKEN_MESSAGE);
  assert.equal(f.calls.length, 1, 'nothing was sent without a token');
});

test('a call without a token sends nothing, for every route', async () => {
  for (const id of Object.keys(ROUTES)) {
    const f = fake(() => good(id));
    const c = createClient({ location: { origin: ORIGIN }, fetchImpl: f });
    const r = await c.call(id, ARGS[id]);
    assert.equal(r.ok, false);
    assert.equal(r.kind, 'notoken');
    assert.equal(f.calls.length, 0, id);
    assert.equal(c.stopped(), false, 'a missing token is not a failure of umwayi');
  }
});

test('the token is held in one variable of the source: one let, one Bearer, and no place it could be kept', () => {
  const CODE = CLIENT_SRC.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/ \/\/ .*$/gm, '');
  assert.equal((CODE.match(/\blet token\b/g) || []).length, 1, 'exactly one variable named token');
  const assigned = [...CODE.matchAll(/\btoken\s*=[^=]\s*(\w+)/g)].map((m) => m[1]);
  assert.deepEqual(assigned.sort(), ['null', 'null', 'null', 'null', 'value'], 'the token is set from the pasted value and otherwise only cleared');
  assert.equal((CODE.match(/Bearer/g) || []).length, 1, 'the header is made in one place');
  assert.equal((CODE.match(/`Bearer \$\{token\}`/g) || []).length, 1);
  for (const bad of ['localStorage', 'sessionStorage', 'indexedDB', 'document', 'cookie', 'history.', 'postMessage', 'console', 'location.href', 'location.hash', 'location.search', 'window', 'navigator',
    'XMLHttpRequest', 'WebSocket', 'EventSource', 'sendBeacon', 'import(', 'setTimeout', 'setInterval', 'innerHTML', 'eval(', 'new Function', 'Blob', 'FormData', 'URLSearchParams', 'new URL', 'Date', 'Math.random']) {
    assert.ok(!CODE.includes(bad), `client.js contains ${bad}`);
  }
  assert.ok(!/[\u2014\u2013]/.test(CLIENT_SRC), 'no dash');
  assert.deepEqual([...CODE.matchAll(/\bfetch\s*\(/g)].length, 1, 'the request function is called by name in one place only');
  assert.ok(/location\.origin/.test(CODE) && (CODE.match(/\blocation\./g) || []).length === 2, 'only location.origin is read');
});

// ---------------------------------------------------------------------------------------------------- bad answers
const valid = () => env('done', {}, DATA.status);
const MUT = [
  ['not json', () => 'not json'], ['empty', () => ''], ['html', () => '<html></html>'], ['array', () => '[]'], ['null', () => 'null'], ['string', () => '"done"'], ['number', () => '1'],
  ['an extra key', () => ({ ...valid(), extra: 1 })], ['an extra key named __proto__', () => JSON.stringify(valid()).replace('{', '{"__proto__":{"x":1},')],
  ...['schema', 'ok', 'code', 'word', 'request', 'logged', 'data'].map((k) => [`missing ${k}`, () => { const e = valid(); delete e[k]; return e; }]),
  ['schema 2', () => ({ ...valid(), schema: 2 })], ['schema as text', () => ({ ...valid(), schema: '1' })], ['schema 1.5', () => ({ ...valid(), schema: 1.5 })],
  ['ok as text', () => ({ ...valid(), ok: 'true' })], ['ok as 1', () => ({ ...valid(), ok: 1 })], ['ok false for done', () => ({ ...valid(), ok: false })],
  ['ok true for refused', () => ({ ...env('refused'), ok: true })], ['code 1 for done', () => ({ ...valid(), code: 1 })], ['code as text', () => ({ ...valid(), code: '0' })],
  ['code of another word', () => ({ ...env('refused'), code: 3 })],
  ['word in capitals', () => ({ ...valid(), word: 'Done' })], ['unknown word', () => ({ ...valid(), word: 'fine' })], ['word __proto__', () => ({ ...valid(), word: '__proto__' })],
  ['word constructor', () => ({ ...valid(), word: 'constructor' })], ['word toString', () => ({ ...valid(), word: 'toString' })], ['word as number', () => ({ ...valid(), word: 5 })],
  ['word with a space', () => ({ ...valid(), word: 'done ' })], ['word as markup', () => ({ ...valid(), word: '<img src=x>' })],
  ...['R-1234', 'r-0a1b2c3d', 'R-0A1B2C3D', 'R-0a1b2c3g', 'R-0a1b2c3d4', ' R-0a1b2c3d', 'R-0a1b2c3d\n', '', 5, true].map((r) => [`request ${JSON.stringify(r)}`, () => ({ ...valid(), request: r })]),
  ['done without a request', () => ({ ...valid(), request: null })], ['done not logged', () => ({ ...valid(), logged: false })], ['logged as text', () => ({ ...valid(), logged: 'yes' })],
  ['done with data null', () => ({ ...valid(), data: null })], ['done with data as text', () => ({ ...valid(), data: 'x' })], ['done with data as array', () => ({ ...valid(), data: [] })],
  ['data with an extra key', () => ({ ...valid(), data: { ...DATA.status, extra: 1 } })], ['data missing a key', () => { const d = { ...DATA.status }; delete d.degraded; return { ...valid(), data: d }; }],
  ['kill_switch in capitals', () => ({ ...valid(), data: { ...DATA.status, kill_switch: 'ON' } })], ['kill_switch as bool', () => ({ ...valid(), data: { ...DATA.status, kill_switch: true } })],
  ['degraded as text', () => ({ ...valid(), data: { ...DATA.status, degraded: 'no' } })], ['token as text', () => ({ ...valid(), data: { ...DATA.status, token: 'umt1_x' } })],
  ['token id wrong', () => ({ ...valid(), data: { ...DATA.status, token: { ...DATA.status.token, id: 'T-1' } } })], ['token date wrong', () => ({ ...valid(), data: { ...DATA.status, token: { ...DATA.status.token, expires: '12/12/2026' } } })],
  ['days_left as text', () => ({ ...valid(), data: { ...DATA.status, token: { ...DATA.status.token, days_left: '30' } } })], ['token with an extra key', () => ({ ...valid(), data: { ...DATA.status, token: { ...DATA.status.token, sha256: 'x' } } })],
  ['ok false for done, with data', () => ({ ...valid(), ok: false })], ['ok false for done, without data', () => { const e = { ...valid(), ok: false }; delete e.data; return e; }],
  ['ok true for refused, with data', () => ({ ...env('refused'), ok: true, data: DATA.status })], ['ok true for ask, with data', () => ({ ...env('ask'), ok: true, data: DATA.status })],
  ['a refusal with data', () => ({ ...env('refused'), data: { x: 1 } })], ['a refusal with a status shaped data', () => ({ ...env('ask'), data: DATA.status })], ['a refusal with data null', () => ({ ...env('refused'), data: null })],
  ['logbook with the wrong note', () => ({ ...env('logbook'), data: { changed: false } })], ['logbook with an extra note key', () => ({ ...env('logbook'), data: { changed: true, x: 1 } })],
  ['ask with a status of 200', 'status:200:ask'], ['done with a status of 500', 'status:500:done'], ['done with a status of 201', 'status:201:done'], ['token with a status of 403', 'status:403:token'],
  ['refused with a status of 400', 'status:400:refused'], ['rate with a status of 503', 'status:503:rate'], ['usage with a status of 409', 'status:409:usage'],
];

// the status a word is sent with, so that a mutation is refused for the fault it plants and not for a wrong status
const statusFor = (word) => (typeof word === 'string' && Object.hasOwn(SERVER_WORDS, word) ? SERVER_WORDS[word][0][0] : typeof word === 'string' && Object.hasOwn(GATE_STATUS, word) ? [...GATE_STATUS[word]][0] : 200);
function mutated(m) {
  if (typeof m === 'string' && m.startsWith('status:')) {
    const [, status, word] = m.split(':');
    return reply(Number(status), word === 'done' ? valid() : env(word));
  }
  const v = m();
  return reply(v && typeof v === 'object' ? statusFor(v.word) : 200, v);
}

test('every bad envelope or wrong status gives one message, forgets the token and stops all sending', async () => {
  for (const [name, m] of MUT) {
    const { c, f } = ready(() => mutated(m));
    const r = await c.call('status');
    assert.equal(r.ok, false, name);
    assert.equal(r.kind, 'shape', name);
    assert.equal(r.message, SHAPE_MESSAGE, name);
    assert.equal(r.message, 'umwayi did not answer in the expected shape');
    assert.equal(c.stopped(), true, name);
    assert.equal(c.hasToken(), false, `${name}: the token was kept`);
    assert.equal(c.setToken(TOKEN2), false, `${name}: a new token was taken`);
    for (const id of Object.keys(ROUTES)) {
      const again = await c.call(id, ARGS[id]);
      assert.equal(again.kind, 'stopped', `${name} ${id}`);
      assert.equal(again.message, STOPPED_MESSAGE);
    }
    assert.equal(f.calls.length, 1, `${name}: something was sent after the bad answer`);
    assert.ok(!JSON.stringify(r).includes(TOKEN));
  }
});

test('every route has its own data shape: good data passes, a shape of another route is a bad answer', async () => {
  const ids = Object.keys(DATA);
  for (const id of ids) {
    const { c } = ready(() => good(id));
    const r = await c.call(id, ARGS[id]);
    assert.equal(r.ok, true, id);
    assert.deepEqual(r.data, DATA[id]);
    assert.equal(r.request, REQ);
    assert.ok(Object.isFrozen(r));
    for (const other of ids.filter((x) => x !== id)) {
      const w = ready(() => good(other));
      const bad = await w.c.call(id, ARGS[id]);
      assert.equal(bad.kind, 'shape', `${id} accepted the data of ${other}`);
    }
  }
  const rowMuts = [
    (r) => ({ ...r, id: 'Q-1' }), (r) => ({ ...r, kind: 'chat' }), (r) => ({ ...r, status: 'done' }), (r) => ({ ...r, answered: 'yesterday' }), (r) => ({ ...r, title: 5 }),
    (r) => ({ ...r, extra: 1 }), (r) => ({ ...r, answer: null }), (r) => ({ ...r, title: 'x'.repeat(4097) }),
  ];
  for (const mut of rowMuts) {
    const { c } = ready(() => reply(200, env('done', {}, { rows: [mut(DATA['queue.list'].rows[0])], more: false })));
    assert.equal((await c.call('queue.list')).kind, 'shape');
  }
  const { c } = ready(() => reply(200, env('done', {}, { rows: Array.from({ length: 501 }, () => DATA['queue.list'].rows[0]), more: false })));
  assert.equal((await c.call('queue.list')).kind, 'shape', 'more rows than the server sends');
  const w = ready(() => reply(200, env('done', {}, { rows: Array.from({ length: 500 }, () => DATA['queue.list'].rows[0]), more: true })));
  assert.equal((await w.c.call('queue.list')).ok, true);
});

test('a wrong content type, a redirect, an opaque or empty response, a response that cannot be read, and a failed request all stop the client', async () => {
  const cases = [
    ['text/html', () => ({ ...good('status'), type: 'text/html' })], ['no content type', () => ({ ...good('status'), type: null })], ['json without a charset', () => ({ ...good('status'), type: 'application/json' })],
    ['json in capitals', () => ({ ...good('status'), type: 'APPLICATION/JSON; CHARSET=UTF-8' })], ['redirected', () => ({ ...good('status'), redirected: true })],
    ['opaque', () => ({ ...good('status'), responseType: 'opaque' })], ['error type', () => ({ ...good('status'), responseType: 'error' })], ['opaqueredirect', () => ({ ...good('status'), responseType: 'opaqueredirect' })],
    ['no headers', () => ({ ...good('status'), noHeaders: true })], ['no response', () => null], ['the body cannot be read', () => ({ ...good('status'), textFails: true })],
    ['the request fails', () => new Error('offline')], ['a status that is not a number', () => ({ status: '200', text: JSON.stringify(valid()) })],
    ['an answer that is too long', () => reply(200, JSON.stringify({ ...valid(), pad: 'x'.repeat(2000001) }))],
    ['a huge number of rows', () => reply(200, 'x'.repeat(2000001))],
  ];
  for (const [name, respond] of cases) {
    const { c, f } = ready(respond);
    const r = await c.call('status');
    assert.equal(r.ok, false, name);
    assert.ok(r.kind === 'shape' || r.kind === 'network', `${name}: ${r.kind}`);
    assert.equal(c.stopped(), true, name);
    assert.equal(c.hasToken(), false, name);
    assert.equal((await c.call('status')).kind, 'stopped');
    assert.equal(f.calls.length, 1, name);
  }
});

test('an answer that is good in every way but longer than the client reads is a bad answer', async () => {
  const big = env('done', {}, { rows: Array.from({ length: 500 }, (_, i) => row(i)), more: false });
  const text = JSON.stringify(big);
  assert.ok(text.length > 2000000, `the test answer is ${text.length} characters`);
  const { c } = ready(() => reply(200, text));
  const r = await c.call('queue.list');
  assert.equal(r.kind, 'shape');
  assert.equal(c.stopped(), true);
  const small = ready(() => reply(200, JSON.stringify(env('done', {}, { rows: Array.from({ length: 200 }, (_, i) => row(i)), more: false }))));
  assert.equal((await small.c.call('queue.list')).ok, true, 'a long but allowed answer passes');
});

test('readEnvelope is strict on its own: it answers null for anything that is not an answer of umwayi', () => {
  assert.equal(readEnvelope(200, JSON.stringify(valid()), 'status').ok, true);
  assert.equal(readEnvelope(200, JSON.stringify(valid()), 'nope'), null);
  assert.equal(readEnvelope(200, JSON.stringify(valid()), '__proto__'), null);
  assert.equal(readEnvelope(undefined, JSON.stringify(valid()), 'status'), null);
  assert.equal(readEnvelope(200, 5, 'status'), null);
  assert.equal(readEnvelope(200, '{}', 'status'), null);
});

// ---------------------------------------------------------------------------------------------------- ordinary answers
const ORDINARY = ['refused', 'usage', 'error', 'ask', 'kill', 'budget', 'rules', 'logbook', 'busy', 'body', 'rate'];

test('an ordinary refusal shows its own plain sentence and the client goes on', async () => {
  for (const word of ORDINARY) {
    const status = (SERVER_WORDS[word] || [[...GATE_STATUS[word]]])[0][0];
    const { c, f } = ready((url, init, n) => (n === 1 ? reply(status, env(word, word === 'logbook' ? {} : {}, word === 'logbook' ? { changed: true } : undefined)) : good('status')));
    const r = await c.call('queue.add', ARGS['queue.add']);
    assert.equal(r.ok, false, word);
    assert.equal(r.kind, 'word');
    assert.equal(r.word, word);
    assert.equal(r.message, SENTENCES[word]);
    assert.ok(r.message.length > 5);
    assert.equal(c.stopped(), false, word);
    assert.equal(c.hasToken(), true, word);
    assert.equal((await c.call('status')).ok, true, `${word}: the client does not go on`);
    assert.equal(f.calls.length, 2);
  }
});

test('the sentences: Ask me first and the kill switch say what the design says, and no word is empty', () => {
  assert.equal(SENTENCES.ask, 'Ask me first. The rules want you to decide; an item was added to the queue');
  assert.equal(SENTENCES.kill, 'The kill switch is on');
  assert.equal(SENTENCES.budget, 'The budget stops this');
  assert.equal(SENTENCES.token, 'The token is wrong or has run out');
  for (const [w, s] of Object.entries(SENTENCES)) {
    assert.ok(typeof s === 'string' && s.length >= 4, w);
    assert.ok(!/[\u2014\u2013<>]/.test(s), w);
  }
  for (const w of ['done', ...ORDINARY, 'token', 'page', 'method', 'peer', 'header', 'host', 'target', 'origin', 'route', 'length', 'type']) assert.ok(w in SENTENCES, w);
});

test('the client knows exactly the words and statuses the server sends', async () => {
  // every word of the pipeline and of the gate, with the statuses it is sent with, is accepted by readEnvelope for a route; nothing else is
  const all = { ...Object.fromEntries(Object.entries(SERVER_WORDS).map(([w, [s, c]]) => [w, { s, c }])) };
  for (const [w, code] of Object.entries(GATE_CODES)) {
    if (w === 'error' || w === 'body') continue; // the same words as the pipeline's, same statuses and codes
    all[w] = { s: [...GATE_STATUS[w]], c: code };
  }
  assert.deepEqual(Object.keys(SENTENCES).sort(), Object.keys(all).sort(), 'the words of the client are the words of the server');
  for (const [w, { s, c }] of Object.entries(all)) {
    for (const status of s) {
      const e = { schema: 1, ok: w === 'done', code: c, word: w, request: w === 'done' ? REQ : null, logged: w === 'done' };
      if (w === 'done') e.data = DATA.status;
      const r = readEnvelope(status, JSON.stringify(e), 'status');
      assert.ok(r !== null, `${w} ${status} was refused`);
    }
    for (const wrong of [200, 201, 301, 404, 418, 500, 502].filter((x) => !s.includes(x))) {
      const e = { schema: 1, ok: w === 'done', code: c, word: w, request: null, logged: false };
      if (w === 'done') { e.data = DATA.status; e.request = REQ; e.logged = true; }
      assert.equal(readEnvelope(wrong, JSON.stringify(e), 'status'), null, `${w} with status ${wrong} was accepted`);
    }
  }
});

test('a word that means the page sent something the server does not accept stops the client at once', async () => {
  for (const word of ['method', 'peer', 'header', 'host', 'target', 'origin', 'route', 'length', 'type', 'page']) {
    const status = (SERVER_WORDS[word] || [[...GATE_STATUS[word]]])[0][0];
    const { c, f } = ready(() => reply(status, env(word, { request: null, logged: false })));
    const r = await c.call('status');
    assert.equal(r.ok, false);
    assert.equal(r.word, word);
    assert.equal(c.stopped(), true, word);
    assert.equal(c.hasToken(), false, word);
    assert.equal((await c.call('status')).kind, 'stopped');
    assert.equal(f.calls.length, 1, word);
  }
});

test('the word token forgets the token and sends nothing until a new one is pasted; then the client goes on', async () => {
  const { c, f } = ready((url, init, n) => (n === 1 ? reply(401, env('token', { request: null, logged: false })) : good('status')));
  const r = await c.call('status');
  assert.equal(r.kind, 'token');
  assert.equal(r.word, 'token');
  assert.equal(r.message, 'The token is wrong or has run out');
  assert.equal(c.hasToken(), false);
  assert.equal(c.stopped(), false);
  assert.equal((await c.call('status')).kind, 'notoken');
  assert.equal(f.calls.length, 1, 'a second wrong token was not tried');
  assert.equal(c.setToken(TOKEN2), true);
  assert.equal((await c.call('status')).ok, true);
  assert.equal(f.calls.length, 2);
  assert.equal(f.calls[1].init.headers.Authorization, `Bearer ${TOKEN2}`);
});
