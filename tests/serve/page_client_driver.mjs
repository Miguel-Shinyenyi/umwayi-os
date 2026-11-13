// A test helper (W6.10), not shipped: runs the REAL page client (ui/src/api/client.js) in Node against a running
// `umwayi serve`, and prints what happened as one JSON object. Used by tests/serve/test_scenarios.py.
//
// Node's fetch adds no Origin and no fetch metadata, which a browser always adds to a same-origin request. The wrapper below
// adds them (the page client itself does not, and cannot, set them), and records every path the client asked for.
//
// Environment: UMWAYI_PORT, UMWAYI_TOKEN, UMWAYI_SCRIPT (session, wrong or foreign).
import { createClient } from '../../ui/src/api/client.js';

const port = process.env.UMWAYI_PORT;
const token = process.env.UMWAYI_TOKEN;
const script = process.env.UMWAYI_SCRIPT;
const origin = `http://127.0.0.1:${port}`;
const paths = [];

const browserFetch = (path, init) => {
  paths.push(path);
  const headers = { ...init.headers, 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'same-origin', 'Sec-Fetch-Dest': 'empty' };
  if (init.method !== 'GET') headers.Origin = origin;
  return fetch(origin + path, { ...init, headers });
};

const plain = (r) => ({ ok: r.ok, kind: r.kind, word: r.word, request: r.request, data: r.data });
const steps = {};

async function session() {
  const c = createClient({ location: { origin }, fetchImpl: browserFetch });
  if (!c.available || !c.setToken(token)) throw new Error('the client did not accept the token');
  steps.status = plain(await c.call('status'));
  steps.add = plain(await c.call('queue.add', { body: { kind: 'task', title: 'From the page client', recommendation: 'Yes' } }));
  const id = steps.add.data.id;
  steps.list = plain(await c.call('queue.list', { query: { status: 'open', kind: 'task' } }));
  steps.answer = plain(await c.call('queue.answer', { id, body: { answer: 'Done by the page client' } }));
  steps.close = plain(await c.call('queue.close', { id }));
  steps.kill = plain(await c.call('kill.on', { body: { reason: 'Stop everything' } }));
  const after = await c.call('queue.add', { body: { kind: 'task', title: 'Blocked by the switch' } });
  steps.after_kill = { ...plain(after), stopped: c.stopped() };
  steps.status_after = plain(await c.call('status'));
}

async function wrong() {
  const c = createClient({ location: { origin }, fetchImpl: browserFetch });
  c.setToken(token);
  steps.first = plain(await c.call('status'));
  steps.second = plain(await c.call('status'));
}

async function foreign() {
  for (const [name, o] of [['file', 'file://'], ['other_host', 'http://192.168.1.5:8765'], ['localhost', `http://localhost:${port}`]]) {
    const before = paths.length;
    const c = createClient({ location: { origin: o }, fetchImpl: browserFetch });
    c.setToken(token);
    await c.call('status');
    steps[name] = { available: c.available, sent: paths.length - before };
  }
}

await { session, wrong, foreign }[script]();
process.stdout.write(JSON.stringify({ steps, paths }));
