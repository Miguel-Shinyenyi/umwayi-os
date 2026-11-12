// UI.3 (tests first): the snapshot joins the scene. A snapshot that is accepted reaches the scene as counts and as needs, in
// the one way the position code has (setNeeds, 12.R3.6), whether it was loaded before the scene started or after; the same code
// serves the live view and the public site (boot.js); a refused file reaches nothing.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { boot } from '../src/boot.js';
import { feedScene, viewOf, parseSnapshot, needsFrom } from '../src/data/snapshot.js';
import { SAMPLE } from '../src/data/sample.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const FIXTURE = readFileSync(join(HERE, 'fixtures', 'snapshot.json'), 'utf8');
const read = (name) => readFileSync(join(SRC, name), 'utf8');
const flush = () => new Promise((r) => setTimeout(r, 5));

test('feedScene gives the scene the counts, the sample flag and the needs, and nothing else', () => {
  const calls = [];
  const scene = { setCounts: (...a) => calls.push(['setCounts', ...a]), setNeeds: (...a) => calls.push(['setNeeds', ...a]), select() { calls.push(['select']); }, overview() { calls.push(['overview']); } };
  const snap = parseSnapshot(FIXTURE).snapshot;
  feedScene(scene, viewOf(snap));
  assert.deepEqual(calls, [['setCounts', snap, false], ['setNeeds', needsFrom(snap)]]);
  assert.equal(calls[1][1].queue, needsFrom(snap).queue);
});

test('feedScene on the sample world keeps the stations where they stand by default', () => {
  const calls = [];
  feedScene({ setCounts: (...a) => calls.push(['setCounts', ...a]), setNeeds: (...a) => calls.push(['setNeeds', ...a]) }, viewOf(null));
  assert.deepEqual(calls, [['setCounts', SAMPLE, true], ['setNeeds', {}]]);
});

// ---- boot: the page script both pages share
function el() {
  const o = { handlers: {}, attrs: {}, textContent: '', hidden: false, files: [], value: '', dataset: {},
    addEventListener(t, f) { (o.handlers[t] ||= []).push(f); }, removeEventListener() {}, setAttribute(k, v) { o.attrs[k] = v; }, click() {} };
  return o;
}
function stage({ webgl = true, hash = '' } = {}) {
  const els = {};
  const get = (id) => (els[id] ||= el());
  const gl = { getExtension: () => null, getParameter: () => '' };
  const doc = {
    documentElement: el(), handlers: {},
    getElementById: (id) => (id.startsWith('checks') ? null : get(id)), querySelector: () => null, querySelectorAll: () => [],
    addEventListener(t, f) { (doc.handlers[t] ||= []).push(f); }, removeEventListener() {},
    createElement: () => ({ getContext: () => (webgl ? gl : null) }),
  };
  get('sample-tag').textContent = 'sample';
  const reads = new Map();
  const win = {
    document: doc, navigator: {}, location: { hash }, history: { replaceState() {} }, screen: { width: 1440, height: 900 },
    FileReader: class { readAsText(f) { Promise.resolve().then(() => { this.result = reads.get(f); this.onload(); }); } },
  };
  return { win, doc, get, reads };
}
const pick = (st, name, text) => {
  const f = { name, size: Buffer.byteLength(text) };
  st.reads.set(f, text);
  const input = st.get('snapshot-file');
  input.files = [f];
  input.handlers.change.forEach((h) => h({}));
};
function fakeApp() {
  const log = { created: [], started: 0, data: [] };
  const createApp = (win, view) => {
    log.created.push(view);
    return { start() { log.started++; }, setFlat() {}, setData(v) { log.data.push(v); }, onLost: null };
  };
  return { log, loadApp: () => Promise.resolve(createApp) };
}

test('boot: a snapshot picked after the scene started goes to the scene with setData', async () => {
  const st = stage(); const { log, loadApp } = fakeApp();
  boot(st.win, { maxTier: 2, local: true }, loadApp);
  await flush();
  assert.equal(log.started, 1);
  assert.equal(log.created[0].sample, true, 'the scene starts with the sample world');
  pick(st, 'snapshot.json', FIXTURE);
  await flush();
  assert.equal(log.data.length, 1);
  assert.equal(log.data[0].sample, false);
  assert.equal(log.data[0].counts.queue.open, 2);
  assert.match(st.get('sample-tag').textContent, /2026-11-11/);
});

test('boot: a refused file reaches nothing; the scene is not told and the label stays sample', async () => {
  const st = stage(); const { log, loadApp } = fakeApp();
  boot(st.win, { maxTier: 2, local: true }, loadApp);
  await flush();
  pick(st, 'bad.json', FIXTURE.replace('"schema": 1', '"schema": 2'));
  await flush();
  assert.deepEqual(log.data, []);
  assert.equal(st.get('sample-tag').textContent, 'sample');
  assert.equal(st.get('snapshot-msg').textContent, 'This file is not a snapshot of this version');
});

test('boot: a snapshot loaded while the page is List (no scene yet) is what the scene starts with', async () => {
  const st = stage({ hash: '#tier=list' }); const { log, loadApp } = fakeApp();
  boot(st.win, { maxTier: 2, local: true }, loadApp);
  await flush();
  assert.equal(log.started, 0, 'List draws no scene');
  pick(st, 'snapshot.json', FIXTURE);
  await flush();
  assert.match(st.get('sample-tag').textContent, /2026-11-11/, 'the page shows it in List too');
  assert.equal(log.created.length, 0);
});

test('boot: the snapshot is read on a page with no WebGL as well (the List page shows the strip)', async () => {
  const st = stage({ webgl: false }); const { log, loadApp } = fakeApp();
  boot(st.win, { maxTier: 2, local: true }, loadApp);
  await flush();
  pick(st, 'snapshot.json', FIXTURE);
  await flush();
  assert.equal(log.started, 0);
  assert.match(st.get('foot-note').textContent, /2026-11-11/);
});

test('the shared script wires the snapshot once, for both pages, and the scene is told in the one way', () => {
  const boot_ = read('boot.js');
  assert.match(boot_, /initSnapshot\(/);
  assert.match(boot_, /createApp\(win, view\)/);
  assert.match(boot_, /setData\(/);
  assert.ok(!/initSnapshot/.test(read('main.js')) && !/initSnapshot/.test(read('app.js')), 'the wiring is not copied into a page of its own');
  const app = read('app.js');
  assert.match(app, /feedScene\(scene/);
  assert.match(app, /export function createApp\(win, view/);
});

test('scene.js has setCounts, keeps the current counts for the panel, and still reads no page', () => {
  const text = read('scene.js');
  assert.match(text, /setCounts\(/);
  assert.match(text, /st\.setCounts\(/);
  assert.match(text, /isSample: \(\) => sample/);
  assert.match(text, /hooks\.onSelect\(id, \{ prev, def: st\.def, counts, sample \}\)/, 'the panel gets the counts now in use');
  assert.match(text, /let counts\b|counts = /, 'counts can change');
});

test('the position code is untouched: setNeeds is still the placement\'s own, and the placement and the layout import nothing of the snapshot', () => {
  assert.match(read('scene.js'), /setNeeds: \(needs\) => world\.placement\.setNeeds\(needs\)/);
  for (const name of ['engine/placement.js', 'world/layout.js']) assert.ok(!/from '[^']*data\/snapshot|sceneNumbers|needsFrom|viewOf|feedScene/.test(read(name)), name);
});
