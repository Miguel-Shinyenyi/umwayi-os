/*! umwayi-client:begin */
// The page client (W6.9, W6.R2.5). It is the ONLY module of the page that sends a request, and the only place where the
// word for it appears. It talks to `umwayi serve`, which serves this page from http://127.0.0.1:PORT, and to nothing else:
//
//   - It works only when location.origin is exactly http://127.0.0.1: and a port. On any other origin (a file on disk, the
//     public site, another address) it is a frozen object with available false and it never sends anything.
//   - It builds each request from the table ROUTES below (the same ids and paths as umwayi/servegate.py), never from text.
//     Every path is relative and starts with /v1/. A parameter that does not fit its pattern is refused before sending.
//   - The token is held in ONE variable of this closure. It is written to nothing else: no storage, no address, no history
//     entry, no message, no log, no element. It goes out in the Authorization header and nowhere else. A reload forgets it.
//   - The answer is read strictly (exact keys, schema 1, a word with its own status and code, a request id of the right
//     shape, data only when ok and with the exact shape of the route). Anything else is one failure, and the client
//     FAILS CLOSED: it forgets the token and sends nothing more until the page is loaded again.
//   - A request without a token is not sent.
//
// Nothing here touches the page: the panel (ui/backend.js) shows what this returns, as text.

const ORIGIN = /^http:\/\/127\.0\.0\.1:([0-9]{2,5})$/;
const TOKEN = /^umt1_[A-Za-z0-9_-]{43}$/;
const REQUEST = /^R-[0-9a-f]{8}$/;
const ID = /^Q-[0-9]{4,}$/;
const TOKEN_ID = /^T-[0-9a-f]{8}$/;
const DATE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const QUERY_VALUE = /^[a-z0-9_-]{0,16}$/;
const MAX_TEXT = 2000000; // characters of an answer that are read
const MAX_STRING = 4096; // a string of a request body or of a row
const MAX_ROWS = 500;

export const SHAPE_MESSAGE = 'umwayi did not answer in the expected shape';
export const UNAVAILABLE_MESSAGE = 'Open this page with umwayi serve';
export const NO_TOKEN_MESSAGE = 'Paste the token first. Nothing was sent';
export const STOPPED_MESSAGE = 'This page stopped talking to umwayi. Nothing more is sent. Reload the page to start again';
export const NO_ANSWER_MESSAGE = 'umwayi did not answer';

// The closed table of routes the page may use (a subset of the server's table). A field is [name, kind]; kind is str or bool.
// A POST always sends a JSON object, as the server requires.
export const ROUTES = Object.freeze({
  status: Object.freeze({ method: 'GET', path: '/v1/status', query: [], fields: [], required: [] }),
  'queue.list': Object.freeze({ method: 'GET', path: '/v1/queue', query: ['status', 'kind'], fields: [], required: [] }),
  'queue.add': Object.freeze({
    method: 'POST', path: '/v1/queue', query: [], required: ['kind', 'title'],
    fields: [['kind', 'str'], ['title', 'str'], ['recommendation', 'str'], ['if_not_open', 'bool']],
  }),
  'queue.answer': Object.freeze({
    method: 'POST', path: '/v1/queue/{id}/answer', query: [], required: ['answer'],
    fields: [['answer', 'str'], ['revisit_if', 'str']],
  }),
  'queue.close': Object.freeze({ method: 'POST', path: '/v1/queue/{id}/close', query: [], fields: [], required: [] }),
  'kill.on': Object.freeze({ method: 'POST', path: '/v1/kill/on', query: [], fields: [['reason', 'str']], required: [] }),
});

// word -> [HTTP statuses it comes with, exit code]. The same words as umwayi/serve.py (WORDS) and umwayi/servegate.py (WORD_CODE).
const WORDS = Object.freeze({
  done: [[200], 0], refused: [[409], 1], usage: [[400], 64], error: [[500], 2], ask: [[403], 3], kill: [[403], 3],
  budget: [[403], 3], rules: [[403], 2], logbook: [[500], 2], busy: [[503], 2], page: [[503], 2], body: [[400], 64],
  method: [[405], 2], peer: [[403], 2], header: [[403], 2], host: [[403], 2], target: [[403], 2], token: [[401], 2],
  origin: [[403], 2], route: [[404], 2], length: [[411, 413], 2], type: [[415], 2], rate: [[429], 2],
});
// the words that are an ordinary answer to a good request. Any other word means the page sent something the server does not
// accept, so the client stops.
const ORDINARY = new Set(['done', 'refused', 'usage', 'error', 'ask', 'kill', 'budget', 'rules', 'logbook', 'busy', 'body', 'rate', 'token']);

// One plain sentence for each word. No word reaches the page as markup (the panel sets all of it as text).
export const SENTENCES = Object.freeze({
  done: 'Done',
  refused: 'umwayi refused this: it was checked and found wrong, and nothing was changed',
  usage: 'umwayi did not accept what was typed. Check the fields',
  error: 'umwayi stopped with an error. Nothing was changed',
  ask: 'Ask me first. The rules want you to decide; an item was added to the queue',
  kill: 'The kill switch is on',
  budget: 'The budget stops this',
  rules: 'The rules say No',
  logbook: 'The logbook could not be written, so umwayi gave no answer',
  busy: 'umwayi is busy. Try again in a moment',
  page: 'The page file did not pass its check',
  body: 'umwayi did not accept what was typed. Check the fields',
  rate: 'Too many requests. Wait a moment',
  token: 'The token is wrong or has run out',
  method: SHAPE_MESSAGE, peer: SHAPE_MESSAGE, header: SHAPE_MESSAGE, host: SHAPE_MESSAGE, target: SHAPE_MESSAGE,
  origin: SHAPE_MESSAGE, route: SHAPE_MESSAGE, length: SHAPE_MESSAGE, type: SHAPE_MESSAGE,
});

const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const plain = (v) => v !== null && typeof v === 'object' && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
const exact = (o, keys) => plain(o) && Object.keys(o).length === keys.length && keys.every((k) => own(o, k));
const str = (v, max = MAX_STRING) => typeof v === 'string' && v.length <= max;
const day = (v) => typeof v === 'string' && DATE.test(v);

// the exact shape of the data of each route when the word is done
const DATA = {
  status: (d) => exact(d, ['kill_switch', 'token', 'degraded']) && ['on', 'off', 'unknown'].includes(d.kill_switch) && typeof d.degraded === 'boolean'
    && (d.token === null || (exact(d.token, ['id', 'created', 'expires', 'days_left']) && TOKEN_ID.test(d.token.id) && day(d.token.created)
      && day(d.token.expires) && Number.isSafeInteger(d.token.days_left))),
  'queue.list': (d) => exact(d, ['rows', 'more']) && typeof d.more === 'boolean' && Array.isArray(d.rows) && d.rows.length <= MAX_ROWS
    && d.rows.every((r) => exact(r, ['id', 'kind', 'status', 'answered', 'title', 'recommendation', 'answer']) && ID.test(r.id)
      && ['task', 'decision'].includes(r.kind) && ['open', 'answered', 'closed'].includes(r.status) && (r.answered === '' || day(r.answered))
      && str(r.title) && str(r.recommendation) && str(r.answer)),
  'queue.add': (d) => exact(d, ['id', 'added']) && ID.test(d.id) && typeof d.added === 'boolean',
  'queue.answer': (d) => exact(d, ['id', 'answered']) && ID.test(d.id) && day(d.answered),
  'queue.close': (d) => exact(d, ['id', 'status']) && ID.test(d.id) && d.status === 'closed',
  'kill.on': (d) => exact(d, ['kill_switch']) && d.kill_switch === 'on',
};

const failure = (kind, message, word = null, request = null) => Object.freeze({ ok: false, kind, word, message, request });

// Reads an answer. Returns { ok: true, data, request }, or { ok: false, word, stop } for a refusal that is a valid answer (stop is
// true when the word means the page sent something the server does not accept), or null when the answer is not exactly an answer
// of umwayi (the caller then stops).
export function readEnvelope(status, text, routeId) {
  if (typeof status !== 'number' || typeof text !== 'string' || text.length > MAX_TEXT || !own(DATA, routeId)) return null;
  let env;
  try { env = JSON.parse(text); } catch (e) { return null; }
  if (!plain(env)) return null;
  const has = (k) => own(env, k);
  if (!has('schema') || !has('ok') || !has('code') || !has('word') || !has('request') || !has('logged')) return null;
  if (Object.keys(env).length !== (has('data') ? 7 : 6)) return null;
  if (env.schema !== 1 || typeof env.ok !== 'boolean' || typeof env.logged !== 'boolean' || typeof env.word !== 'string') return null;
  if (!own(WORDS, env.word)) return null;
  const [statuses, code] = WORDS[env.word];
  if (!statuses.includes(status) || env.code !== code) return null;
  if (env.request !== null && !(typeof env.request === 'string' && REQUEST.test(env.request))) return null;
  if (env.ok !== (env.word === 'done')) return null;
  if (env.ok) {
    if (env.request === null || env.logged !== true || !has('data') || !DATA[routeId](env.data)) return null;
    return { ok: true, data: env.data, request: env.request };
  }
  if (has('data') && !(env.word === 'logbook' && exact(env.data, ['changed']) && env.data.changed === true)) return null;
  return { ok: false, word: env.word, stop: !ORDINARY.has(env.word), request: env.request };
}

// location: the page's location (only .origin is read). fetchImpl: for a test; the page passes nothing and the browser's
// own request function is used.
export function createClient({ location, fetchImpl } = {}) {
  const origin = location && typeof location.origin === 'string' ? location.origin : '';
  const m = ORIGIN.exec(origin);
  if (!m || Number(m[1]) < 1024 || Number(m[1]) > 65535) {
    const closed = () => Promise.resolve(failure('unavailable', UNAVAILABLE_MESSAGE));
    return Object.freeze({ available: false, hasToken: () => false, stopped: () => false, setToken: () => false, clearToken() {}, call: closed });
  }
  const send = typeof fetchImpl === 'function' ? fetchImpl : (...args) => globalThis.fetch(...args);

  let token = null; // THE one variable that holds the token
  let halted = false; // set when an answer was wrong: nothing more is sent

  function halt() {
    halted = true;
    token = null;
  }

  // the request for a route id and its parameters, or null when they do not fit the table
  function build(routeId, args) {
    if (!own(ROUTES, routeId)) return null;
    const route = ROUTES[routeId];
    const a = args === undefined ? {} : args;
    if (!plain(a) || Object.keys(a).some((k) => !['id', 'query', 'body'].includes(k))) return null;
    let path = route.path;
    if (path.includes('{id}')) {
      if (typeof a.id !== 'string' || !ID.test(a.id)) return null;
      path = path.replace('{id}', a.id);
    } else if (a.id !== undefined) return null;
    const q = a.query === undefined ? {} : a.query;
    if (!plain(q) || Object.keys(q).some((k) => !route.query.includes(k))) return null;
    const pairs = [];
    for (const k of route.query) {
      if (!own(q, k) || q[k] === null || q[k] === undefined || q[k] === '') continue;
      if (typeof q[k] !== 'string' || !QUERY_VALUE.test(q[k])) return null;
      pairs.push(`${k}=${q[k]}`);
    }
    if (pairs.length) path += `?${pairs.join('&')}`;
    let body = null;
    if (route.method === 'POST') {
      const b = a.body === undefined ? {} : a.body;
      if (!plain(b)) return null;
      const kinds = new Map(route.fields);
      if (Object.keys(b).some((k) => !kinds.has(k)) || !route.required.every((k) => own(b, k))) return null;
      for (const [k, v] of Object.entries(b)) {
        if (kinds.get(k) === 'bool' ? typeof v !== 'boolean' : !str(v)) return null;
      }
      body = JSON.stringify(b);
    } else if (a.body !== undefined) return null;
    return { route, path, body };
  }

  async function call(routeId, args) {
    if (halted) return failure('stopped', STOPPED_MESSAGE);
    if (token === null) return failure('notoken', NO_TOKEN_MESSAGE);
    const req = build(routeId, args);
    if (req === null) return failure('usage', SENTENCES.usage);
    const headers = { Authorization: `Bearer ${token}` };
    if (req.body !== null) headers['Content-Type'] = 'application/json';
    const init = {
      method: req.route.method, headers, credentials: 'omit', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer', mode: 'same-origin',
    };
    if (req.body !== null) init.body = req.body;
    let res, text;
    try {
      res = await send(req.path, init);
      if (!res || res.redirected === true || res.type === 'opaque' || res.type === 'opaqueredirect' || res.type === 'error') throw new Error('shape');
      const type = res.headers && typeof res.headers.get === 'function' ? res.headers.get('content-type') : null;
      if (type !== 'application/json; charset=utf-8') throw new Error('shape');
      text = await res.text();
    } catch (e) {
      halt();
      return failure('network', NO_ANSWER_MESSAGE);
    }
    const got = readEnvelope(res.status, text, routeId);
    if (got === null) {
      halt();
      return failure('shape', SHAPE_MESSAGE);
    }
    if (got.ok) return Object.freeze({ ok: true, kind: 'done', word: 'done', message: SENTENCES.done, request: got.request, data: got.data });
    if (got.stop) halt();
    else if (got.word === 'token') token = null; // the owner pastes a new one; until then nothing is sent
    return failure(got.word === 'token' ? 'token' : 'word', SENTENCES[got.word], got.word, got.request);
  }

  return Object.freeze({
    available: true,
    hasToken: () => token !== null,
    stopped: () => halted,
    // the token as the owner pasted it; false (and nothing is kept) when it does not have the shape of a token
    setToken(value) {
      if (halted || typeof value !== 'string' || !TOKEN.test(value)) return false;
      token = value;
      return true;
    },
    clearToken() { token = null; },
    call,
  });
}
/*! umwayi-client:end */
