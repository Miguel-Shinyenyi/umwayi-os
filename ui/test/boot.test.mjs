// UI.7 (tests first): the start of a page with High (12.R16.3, 12.R16.4). boot() is the one device query and switch of both
// pages. On the public site High draws Standard first and replaces it when the High scene is ready; a failed or slow High start
// leaves Standard and says so in words. The owner's live view has no High at all. A fake page stands in for the browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import { boot, HIGH_TIMEOUT_MS } from '../src/boot.js';

const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r)); };

function fakePage({ hash = '', renderer = 'ANGLE (NVIDIA GeForce RTX 4060)', connection = { effectiveType: '4g', downlink: 50, saveData: false }, webgl = true } = {}) {
  const els = {};
  const el = (id) => (els[id] ||= { id, attrs: {}, textContent: '', hidden: false, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] ?? null; }, addEventListener() {}, removeEventListener() {} });
  const buttons = ['list', 'standard', 'high'].map((t) => ({ ...el(`tier-${t}`), dataset: { tier: t }, listeners: [], addEventListener(_e, f) { this.listeners.push(f); }, removeEventListener() {}, click() { this.listeners.forEach((f) => f()); } }));
  const timers = [];
  const doc = {
    documentElement: el('html'),
    getElementById: (id) => el(id),
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
  return { win, doc, els, buttons, log, loadApp, fire, timers, pressed, tier: () => doc.documentElement.attrs['data-tier'], high: () => doc.documentElement.attrs['data-high'], notice: () => el('notice').textContent };
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

test('on a capable device the site draws Standard first, then High replaces it', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  assert.deepEqual(p.log, ['createApp', 'start', 'draw', 'upgrade'], 'Standard is drawn before High is asked for');
  assert.equal(p.tier(), 'high');
  assert.equal(p.high(), 'loading');
  assert.match(p.notice(), /Loading High/);
  ctl.resolve();
  await flush();
  assert.equal(p.high(), 'on');
  assert.equal(p.tier(), 'high');
  assert.deepEqual(p.pressed(), ['high']);
  assert.equal(p.notice(), '');
});

test('a High module that fails to load leaves Standard, drawn, and says why', async () => {
  const p = fakePage();
  const ctl = highModule(p, { failLoad: true });
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  assert.equal(p.tier(), 'standard');
  assert.equal(p.high(), 'failed');
  assert.match(p.notice(), /High could not start/);
  assert.equal(p.log.at(-1), 'draw');
  assert.deepEqual(p.pressed(), ['standard']);
});

test('a failed asset (the upgrade rejects) leaves Standard', async () => {
  const p = fakePage();
  const ctl = highModule(p, { fail: true });
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  assert.equal(p.tier(), 'standard');
  assert.equal(p.high(), 'failed');
  assert.match(p.notice(), /High could not start/);
});

test('a slow High start gives Standard after the time limit, and a High that is ready later is taken away again', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  assert.ok(p.timers.some((t) => t.ms === HIGH_TIMEOUT_MS), 'no time limit was set');
  assert.ok(HIGH_TIMEOUT_MS >= 5000 && HIGH_TIMEOUT_MS <= 30000);
  p.fire();
  await flush();
  assert.equal(p.tier(), 'standard');
  assert.equal(p.high(), 'failed');
  assert.match(p.notice(), /took too long/);
  ctl.resolve();
  await flush();
  assert.equal(ctl.removed, 1, 'the late High scene was not removed');
  assert.equal(p.tier(), 'standard');
});

test('the switch: High to Standard removes the High scene, List keeps nothing drawn, High again builds it again', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush(); ctl.resolve(); await flush();
  const b = Object.fromEntries(p.buttons.map((x) => [x.dataset.tier, x]));
  b.standard.click(); await flush();
  assert.equal(p.tier(), 'standard');
  assert.equal(ctl.removed, 1);
  assert.equal(p.high(), 'off');
  assert.equal(p.win.location.hash, '#tier=standard');
  b.list.click(); await flush();
  assert.equal(p.tier(), 'list');
  assert.equal(p.log.at(-1), 'flat');
  b.high.click(); await flush();
  assert.equal(ctl.calls, 2);
  ctl.resolve(); await flush();
  assert.equal(p.tier(), 'high');
  assert.equal(p.high(), 'on');
  assert.equal(p.win.location.hash, '#tier=high');
});

test('High chosen above the automatic choice works and warns in words; the rule for the automatic choice is unchanged', async () => {
  // no Network Information API (Safari, Firefox): the automatic choice is Standard
  const p = fakePage({ connection: null });
  const ctl = highModule(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  assert.equal(p.tier(), 'standard', 'High was chosen by itself without a known fast network');
  assert.equal(ctl.calls, 0);
  p.buttons.find((x) => x.dataset.tier === 'high').click();
  await flush(); ctl.resolve(); await flush();
  assert.equal(p.tier(), 'high');
  assert.match(p.notice(), /You chose High/);
  // a software renderer is never High by itself either
  const q = fakePage({ renderer: 'Google SwiftShader' });
  const c2 = highModule(q);
  boot(q.win, SITE(c2), q.loadApp);
  await flush();
  assert.equal(q.tier(), 'standard');
  assert.equal(c2.calls, 0);
});

test('#tier=high in the address asks for High; with no WebGL it is List, and High is never started', async () => {
  const p = fakePage({ hash: '#tier=high', connection: null });
  const ctl = highModule(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush();
  assert.equal(ctl.calls, 1);
  const q = fakePage({ hash: '#tier=high', webgl: false });
  const c2 = highModule(q);
  boot(q.win, SITE(c2), q.loadApp);
  await flush();
  assert.equal(q.tier(), 'list');
  assert.equal(c2.calls, 0);
  assert.deepEqual(q.log, []);
});

test('the owner\'s live view has no High: a strong device and #tier=high give Standard, and no High state is written', async () => {
  for (const hash of ['', '#tier=high']) {
    const p = fakePage({ hash });
    boot(p.win, { maxTier: 2, local: true }, p.loadApp);
    await flush();
    assert.equal(p.tier(), 'standard');
    assert.equal(p.high(), undefined, 'the live view writes a data-high attribute');
    assert.deepEqual(p.log, ['createApp', 'start', 'draw']);
    assert.equal(p.notice(), '');
  }
});

test('nothing but the tier name is ever written to the address', async () => {
  const p = fakePage();
  const ctl = highModule(p);
  boot(p.win, SITE(ctl), p.loadApp);
  await flush(); ctl.resolve(); await flush();
  for (const t of ['list', 'standard', 'high', 'standard']) { p.buttons.find((x) => x.dataset.tier === t).click(); await flush(); }
  assert.match(p.win.location.hash, /^#tier=(list|standard|high)$/);
});
