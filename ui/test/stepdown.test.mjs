// UI.8 (tests first): the High tier steps down to Standard by itself after slow frames (12.R16, KNOWN-LIMITS 156).
// Three layers, each tested on its own and then joined: the pure window (detail.js), the frame reader of the stage (stage.js,
// driven with a fake stage because WebGL is not needed to count frames), and the page (boot.js, with the fake page of
// boot.test.mjs). A fast run never steps down; a slow run steps down once, with one notice, and nothing but the visitor's own
// choice of High puts it back in the same session.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { boot } from '../src/boot.js';
import { SLOW_MS, SLOW_FRAMES, HIGH_WINDOW, shouldLeaveHigh, createHighWatch } from '../src/engine/detail.js';
import { frameNotes } from '../src/engine/stage.js';

// the helpers below are the ones of boot.test.mjs (that file is not changed), with the fake app returned too
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r)); };

function fakePage({ hash = '', renderer = 'ANGLE (NVIDIA GeForce RTX 4060)', connection = { effectiveType: '4g', downlink: 50, saveData: false }, webgl = true } = {}) {
  const els = {};
  const el = (id) => (els[id] ||= { id, attrs: {}, textContent: '', hidden: false, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] ?? null; }, addEventListener() {}, removeEventListener() {} });
  const buttons = ['list', 'standard', 'high'].map((t) => ({ ...el(`tier-${t}`), dataset: { tier: t }, listeners: [], addEventListener(_e, f) { this.listeners.push(f); }, removeEventListener() {}, click() { this.listeners.forEach((f) => f()); } }));
  const timers = [];
  const doc = {
    documentElement: el('html'),
    // the owner checks panel (UI.4) is not on this page; it does nothing without its section
    getElementById: (id) => (id === 'checks' || id === 'checks-list' ? null : el(id)),
    addEventListener() {}, removeEventListener() {}, // the snapshot file picker and drop (UI.3)
    querySelectorAll: (q) => (q === '#tiers button[data-tier]' ? buttons : []),
    createElement: () => ({ getContext: () => (webgl ? { getExtension: (n) => (n === 'WEBGL_debug_renderer_info' ? { UNMASKED_RENDERER_WEBGL: 1 } : null), getParameter: () => renderer, RENDERER: 2 } : null) }),
  };
  const win = {
    document: doc,
    navigator: { hardwareConcurrency: 12, deviceMemory: 16, connection },
    screen: { width: 1920, height: 1080 },
    matchMedia: () => ({ matches: false }),
    location: { hash },
    history: { replaceState(_s, _t, h) { win.location.hash = h; } },
    setTimeout(f, ms) { timers.push({ f, ms }); return timers.length; },
    clearTimeout(i) { if (timers[i - 1]) timers[i - 1].f = null; },
  };
  const log = [];
  const app = { start() { log.push('start'); }, setFlat(f) { log.push(f ? 'flat' : 'draw'); }, setData() {} };
  const loadApp = () => Promise.resolve(() => { log.push('createApp'); return app; });
  const fire = () => { for (const t of timers.splice(0)) if (t.f) t.f(); };
  const pressed = () => buttons.filter((b) => b.attrs['aria-pressed'] === 'true').map((b) => b.dataset.tier);
  return { app, win, doc, els, buttons, log, loadApp, fire, timers, pressed, tier: () => doc.documentElement.attrs['data-tier'], high: () => doc.documentElement.attrs['data-high'], notice: () => el('notice').textContent };
}

// a High module that resolves when told to
function highModule(page, { fail = false, failLoad = false } = {}) {
  const ctl = { calls: 0, removed: 0, resolve: null, reject: null };
  const mod = {
    upgrade(app) {
      ctl.calls++;
      page.log.push('upgrade');
      return new Promise((res, rej) => { ctl.resolve = () => res({ remove() { ctl.removed++; page.log.push('remove'); } }); ctl.reject = rej; if (fail) rej(new Error('an asset failed')); });
    },
  };
  ctl.load = () => (failLoad ? Promise.reject(new Error('the chunk failed')) : Promise.resolve(mod));
  return ctl;
}
const SITE = (ctl) => ({ maxTier: 3, local: false, loadHigh: ctl.load });

// ---- the pure window
test('the window is short, shorter than the ladder, and its measure is the ladder measure', () => {
  assert.ok(HIGH_WINDOW >= 10 && HIGH_WINDOW < SLOW_FRAMES);
  assert.equal(SLOW_MS, 34);
});

test('slow frames over the window leave High; fast frames, too few frames and bad numbers do not', () => {
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW).fill(80)), true);
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW).fill(SLOW_MS + 1)), true);
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW).fill(SLOW_MS)), false, 'at the threshold is not slow');
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW).fill(16)), false);
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW - 1).fill(500)), false, 'a window must be full');
  assert.equal(shouldLeaveHigh([]), false);
  assert.equal(shouldLeaveHigh(undefined), false);
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW).fill(NaN)), false);
  assert.equal(shouldLeaveHigh(Array(HIGH_WINDOW).fill(-80)), false);
  assert.equal(shouldLeaveHigh([...Array(5).fill(10), ...Array(HIGH_WINDOW).fill(80)]), true, 'the last window counts');
});

test('one slow frame in a fast run is not a slow window (a hitch is not a weak machine)', () => {
  const times = Array(HIGH_WINDOW).fill(16);
  times[3] = 300;
  assert.equal(shouldLeaveHigh(times), false, 'the average is 30, under the threshold');
});

test('the watch calls onSlow once, on the frame that fills a slow window, and never again', () => {
  let calls = 0;
  const w = createHighWatch(() => calls++);
  for (let i = 0; i < HIGH_WINDOW - 1; i++) assert.equal(w.note(90), false);
  assert.equal(calls, 0);
  assert.equal(w.note(90), true);
  assert.equal(calls, 1);
  assert.equal(w.done, true);
  for (let i = 0; i < 200; i++) assert.equal(w.note(90), false);
  assert.equal(calls, 1, 'one call');
});

test('the watch keeps looking window after window while frames are fast', () => {
  let calls = 0;
  const w = createHighWatch(() => calls++);
  for (let i = 0; i < HIGH_WINDOW * 10; i++) w.note(12);
  assert.equal(calls, 0);
  assert.equal(w.done, false);
  for (let i = 0; i < HIGH_WINDOW; i++) w.note(70);
  assert.equal(calls, 1, 'then it still catches a machine that slowed down later');
});

// ---- the stage reader
function fakeStage(extra = {}) {
  const s = { pinned: false, world: {}, steps: [], stepped: [], step: 0,
    setStep(i) { s.steps.push(i); s.step = i; }, onStep(i) { s.stepped.push(i); }, ...extra };
  s.notes = frameNotes(s, () => s.step);
  return s;
}
const feed = (s, n, dt) => { for (let i = 0; i < n; i++) s.notes(dt); };

test('stage: High armed, slow frames: onSlow once, and the ladder is not touched by that', () => {
  const s = fakeStage();
  let slow = 0;
  s.notes.watchHigh(() => slow++);
  feed(s, HIGH_WINDOW, 90);
  assert.equal(slow, 1);
  assert.deepEqual(s.steps, [], 'the tier came off first, not a rung');
  feed(s, 500, 90);
  assert.equal(slow, 1, 'once');
});

test('stage: High armed, fast frames: no step down, ever, and no rung either', () => {
  const s = fakeStage();
  let slow = 0;
  s.notes.watchHigh(() => slow++);
  feed(s, 5000, 16);
  assert.equal(slow, 0);
  assert.deepEqual(s.steps, []);
  assert.deepEqual(s.stepped, []);
});

test('stage: not armed, the ladder is what it was: a rung after a slow window of its own, one at a time', () => {
  const s = fakeStage();
  feed(s, SLOW_FRAMES - 1, 90);
  assert.deepEqual(s.steps, []);
  feed(s, 1, 90);
  assert.deepEqual(s.steps, [1]);
  assert.deepEqual(s.stepped, [1]);
  feed(s, SLOW_FRAMES, 90);
  assert.deepEqual(s.steps, [1, 2]);
  feed(s, SLOW_FRAMES * 3, 90);
  assert.deepEqual(s.steps, [1, 2], 'the ladder ends at its last rung');
});

test('stage: a pinned detail mode (#detail=) is kept: no step down from High either', () => {
  const s = fakeStage({ pinned: true });
  let slow = 0;
  s.notes.watchHigh(() => slow++);
  feed(s, 500, 90);
  assert.equal(slow, 0);
  assert.deepEqual(s.steps, []);
});

test('stage: disarmed, or never armed, High is never reported; arming again starts a new window', () => {
  const s = fakeStage();
  let slow = 0;
  s.notes.watchHigh(() => slow++);
  feed(s, HIGH_WINDOW - 2, 90);
  s.notes.watchHigh(null);
  feed(s, 100, 90);
  assert.equal(slow, 0);
  s.notes.watchHigh(() => slow++);
  feed(s, HIGH_WINDOW - 1, 90);
  assert.equal(slow, 0, 'the old frames are not counted');
  feed(s, 1, 90);
  assert.equal(slow, 1);
  s.notes.watchHigh('not a function');
  feed(s, 100, 90);
  assert.equal(slow, 1);
});

test('boot.js: a lost picture marks WebGL as gone, so the automatic path can never choose High again (UI.8)', () => {
  const text = readFileSync(new URL('../src/boot.js', import.meta.url), 'utf8');
  assert.match(text, /app\.onLost = \(\) => \{ env\.webgl = false; use\(chooseTier\(env, options\)/);
  assert.equal((text.match(/(?<!function )\buse\((first|choice|chooseTier)\b/g) || []).length, 3, 'three callers of use: the first choice, a lost picture and a click');
});

test('stage.js hands the frame reader to the stage and exposes watchHigh', () => {
  const text = readFileSync(new URL('../src/engine/stage.js', import.meta.url), 'utf8');
  assert.match(text, /stage\.noteFrame = notes/);
  assert.match(text, /stage\.watchHigh = notes\.watchHigh/);
  assert.match(text, /export function frameNotes/);
  const scene = readFileSync(new URL('../src/scene.js', import.meta.url), 'utf8');
  assert.match(scene, /watchHigh: \(onSlow\) => stage\.watchHigh\(onSlow\)/);
});

// ---- the page
// the fake app of the page gets the real frame reader, so the page, the reader and the window are tested joined
function joined(p) {
  const stage = fakeStage();
  p.app.watchHigh = stage.notes.watchHigh;
  p.stage = stage;
  return stage;
}
async function highOn(p, ctl) {
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  ctl.resolve();
  await flush();
}
const noticeLog = (p) => {
  const log = [];
  const notice = p.doc.getElementById('notice');
  let text = notice.textContent;
  Object.defineProperty(notice, 'textContent', { get: () => text, set: (v) => { text = v; log.push(v); } });
  return log;
};

test('page: slow frames while High is on take High off, once, with one plain notice, and the page stays Standard', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  joined(p);
  const notices = noticeLog(p);
  await highOn(p, ctl);
  assert.equal(p.tier(), 'high');
  assert.equal(p.high(), 'on');
  const before = notices.length;
  feed(p.stage, HIGH_WINDOW, 90);
  assert.equal(p.tier(), 'standard');
  assert.equal(p.high(), 'off');
  assert.equal(ctl.removed, 1, 'the High scene was removed');
  assert.deepEqual(p.pressed(), ['standard']);
  assert.equal(notices.length, before + 1, 'exactly one notice');
  assert.match(p.notice(), /High was slow on this device, so this is Standard now/);
  assert.equal(p.doc.getElementById('notice').hidden, false);
  assert.doesNotMatch(p.notice(), /[\u2014\u2013]/, 'plain words, no dash');
  feed(p.stage, 1000, 90);
  assert.equal(notices.length, before + 1, 'no second notice');
  assert.equal(ctl.removed, 1);
});

test('page: fast frames while High is on leave High on and say nothing', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  joined(p);
  const notices = noticeLog(p);
  await highOn(p, ctl);
  const before = notices.length;
  feed(p.stage, 3000, 16);
  assert.equal(p.tier(), 'high');
  assert.equal(p.high(), 'on');
  assert.equal(ctl.removed, 0);
  assert.equal(notices.length, before);
  assert.equal(p.notice(), '');
});

test('page: after the step down nothing puts High back by itself in the same session', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  joined(p);
  await highOn(p, ctl);
  feed(p.stage, HIGH_WINDOW, 90);
  assert.equal(p.tier(), 'standard');
  assert.equal(ctl.calls, 1);
  // the picture is lost and found again by the device query, which would offer High on this device
  p.app.onLost();
  await flush();
  assert.equal(ctl.calls, 1, 'High was not loaded again');
  assert.notEqual(p.tier(), 'high');
  assert.equal(p.high(), 'off');
  // time passes, frames are now fast: still not
  feed(p.stage, 3000, 8);
  await flush();
  assert.equal(ctl.calls, 1);
  assert.notEqual(p.tier(), 'high');
});

test('page: the visitor choosing High again is theirs: it loads, and it can step down again', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  joined(p);
  await highOn(p, ctl);
  feed(p.stage, HIGH_WINDOW, 90);
  assert.equal(p.tier(), 'standard');
  p.buttons.find((b) => b.dataset.tier === 'high').listeners[0]();
  await flush();
  assert.equal(ctl.calls, 2, 'the visitor asked for it');
  ctl.resolve();
  await flush();
  assert.equal(p.tier(), 'high');
  assert.equal(p.high(), 'on');
  feed(p.stage, HIGH_WINDOW, 90);
  assert.equal(p.tier(), 'standard', 'slow again, down again');
  assert.equal(ctl.removed, 2);
});

test('page: choosing Standard by hand while High is on disarms the watch (no notice for a choice the visitor made)', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  joined(p);
  await highOn(p, ctl);
  p.buttons.find((b) => b.dataset.tier === 'standard').listeners[0]();
  await flush();
  assert.equal(p.tier(), 'standard');
  assert.equal(p.notice(), '');
  feed(p.stage, 500, 90);
  assert.equal(p.notice(), '', 'no step down notice: High is already off');
  assert.equal(ctl.removed, 1);
});

test('page: the owner live view has no High, and a Standard page is never "stepped down"', async () => {
  const p = fakePage();
  joined(p);
  boot(p.win, { maxTier: 2, local: true }, p.loadApp);
  await flush();
  assert.equal(p.tier(), 'standard');
  feed(p.stage, 500, 90);
  assert.equal(p.tier(), 'standard');
  assert.equal(p.notice(), '');
});

test('page: a High that is still loading when the frames are slow is not reported as stepped down', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  joined(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  feed(p.stage, 500, 90); // Standard draws slowly while High loads: the watch is not armed yet
  assert.equal(p.high(), 'loading');
  ctl.resolve();
  await flush();
  assert.equal(p.high(), 'on', 'High is on and its own watch starts now');
});
