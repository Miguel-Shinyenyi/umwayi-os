// UI.1b.1 (tests first): the tier choice (12.R16.6) and the flow clock of the water (12.R20.2).
import test from 'node:test';
import assert from 'node:assert/strict';
import { chooseTier, parseTier, tierHash, TIERS } from '../src/engine/tier.js';
import { createFlow, FLOW_FRAME_MS } from '../src/engine/flow.js';

// a strong desktop on a fast network: every hint known and good
const strong = () => ({
  webgl: true, cores: 12, memory: 16, renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11)',
  connection: { effectiveType: '4g', downlink: 50, saveData: false }, screen: { w: 1920, h: 1080 }, reducedMotion: false,
});
const tierOf = (env, o) => chooseTier(env, o).tier;

test('the three tiers have the names of the switch', () => {
  assert.deepEqual(TIERS.map((t) => t.name), ['list', 'standard', 'high']);
  assert.deepEqual(TIERS.map((t) => t.label), ['List', 'Standard', 'High']);
});

test('a strong machine on a fast network gets High on the public site, and Standard in the live view', () => {
  assert.equal(tierOf(strong()), 3);
  assert.equal(tierOf(strong(), { maxTier: 2, local: true }), 2);
});

test('no WebGL gives List, whatever was asked for', () => {
  for (const requested of [null, 1, 2, 3]) {
    const c = chooseTier({ ...strong(), webgl: false }, { requested });
    assert.equal(c.tier, 1);
    assert.equal(c.reason, 'no-webgl');
  }
});

test('Save-Data and a slow effective type give List on the site; the live view ignores the network', () => {
  for (const connection of [{ effectiveType: '4g', downlink: 50, saveData: true }, { effectiveType: 'slow-2g' }, { effectiveType: '2g' }]) {
    assert.equal(tierOf({ ...strong(), connection }), 1, JSON.stringify(connection));
    assert.equal(tierOf({ ...strong(), connection }, { maxTier: 2, local: true }), 2, 'a file on disk is not slowed by the network');
  }
  assert.equal(tierOf({ ...strong(), connection: { effectiveType: '3g', downlink: 1.5 } }), 2, '3g is Standard');
});

test('High needs every hint known and good; a missing Network Information API gives Standard', () => {
  assert.equal(tierOf({ ...strong(), connection: null }), 2, 'Safari and Firefox');
  assert.equal(tierOf({ ...strong(), connection: { effectiveType: '4g', downlink: 6 } }), 2, 'downlink under 10');
  assert.equal(tierOf({ ...strong(), connection: { effectiveType: '4g' } }), 2, 'downlink not known');
  assert.equal(tierOf({ ...strong(), cores: 6 }), 2, 'fewer than 8 cores');
  assert.equal(tierOf({ ...strong(), cores: undefined }), 2, 'cores not known');
  assert.equal(tierOf({ ...strong(), memory: 4 }), 2, 'less than 8 GB');
  assert.equal(tierOf({ ...strong(), memory: undefined }), 3, 'memory is only held against the machine when it is reported');
  for (const renderer of ['Google SwiftShader', 'llvmpipe (LLVM 15.0.7, 256 bits)', 'softpipe', 'Microsoft Basic Render Driver', 'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)))']) {
    assert.equal(tierOf({ ...strong(), renderer }), 2, renderer);
  }
  assert.equal(tierOf({ ...strong(), renderer: '' }), 2, 'renderer not known');
  assert.equal(tierOf({ ...strong(), screen: { w: 390, h: 844 } }), 2, 'a phone screen');
  assert.equal(tierOf({ ...strong(), screen: { w: 1280, h: 700 } }), 2, 'the shorter side under 720');
  assert.equal(tierOf({ ...strong(), reducedMotion: true }), 2, 'reduced motion');
});

test('a weak machine is still Standard (the detail mode lowers detail inside the tier), never List', () => {
  assert.equal(tierOf({ webgl: true, cores: 2, memory: 1, renderer: 'Google SwiftShader', connection: { effectiveType: '4g', downlink: 10 }, screen: { w: 800, h: 600 }, reducedMotion: false }), 2);
  assert.equal(tierOf({ webgl: true }), 2, 'nothing else known');
  assert.equal(tierOf({}), 1, 'WebGL not known to work is no WebGL');
});

test('the switch: a requested tier is used, capped by the highest tier, and warns when it is above the automatic choice', () => {
  const weak = { ...strong(), connection: null };
  assert.deepEqual(chooseTier(weak, { requested: 3 }), { tier: 3, name: 'high', reason: 'requested', warn: true });
  assert.deepEqual(chooseTier(strong(), { requested: 1 }), { tier: 1, name: 'list', reason: 'requested', warn: false });
  assert.equal(tierOf(strong(), { requested: 2 }), 2);
  assert.equal(tierOf(strong(), { requested: 3, maxTier: 2, local: true }), 2, 'the live view has no High');
  assert.equal(chooseTier({ ...strong(), connection: { saveData: true } }, { requested: 2 }).tier, 2, 'the owner may choose Standard on Save-Data');
  for (const bad of [0, 4, '2', NaN, {}]) assert.equal(chooseTier(strong(), { requested: bad }).reason === 'requested', false, String(bad));
});

test('the tier in the address fragment: read and written, other keys kept', () => {
  assert.equal(parseTier('#tier=list'), 1);
  assert.equal(parseTier('#tier=standard'), 2);
  assert.equal(parseTier('#detail=low&tier=high'), 3);
  for (const h of ['', '#', '#tier=', '#tier=ultra', '#tier=2', '#xtier=list', null, undefined]) assert.equal(parseTier(h), null, String(h));
  assert.equal(tierHash('', 1), '#tier=list');
  assert.equal(tierHash('#detail=low', 2), '#detail=low&tier=standard');
  assert.equal(tierHash('#detail=low&tier=list', 3), '#detail=low&tier=high');
});

test('the flow clock runs only when the water may move', () => {
  const f = createFlow();
  assert.equal(f.active, true);
  f.step(100);
  assert.ok(Math.abs(f.time - 0.1) < 1e-9);
  for (const key of ['reduced', 'calm', 'hidden', 'offscreen', 'flat']) {
    const g = createFlow();
    g.set({ [key]: true });
    assert.equal(g.active, false, key);
    g.step(1000);
    assert.equal(g.time, 0, `${key}: the water is still`);
    g.set({ [key]: false });
    assert.equal(g.active, true, `${key} off again`);
  }
});

test('the flow clock tells the loop when to draw: at most one frame in FLOW_FRAME_MS, and a wake when it starts again', () => {
  assert.ok(FLOW_FRAME_MS > 1000 / 33, 'at most 30 frames a second');
  let woke = 0;
  const f = createFlow({ wake: () => woke++ });
  assert.equal(f.due(10), true, 'the first frame');
  assert.equal(f.due(20), false);
  assert.equal(f.due(10 + FLOW_FRAME_MS), true);
  f.set({ calm: true });
  assert.equal(woke, 0);
  f.set({ calm: false });
  assert.equal(woke, 1);
  f.set({ calm: false });
  assert.equal(woke, 1, 'no wake when nothing changed');
});

import { createLoop } from '../src/engine/loop.js';
test('the loop: while only the water flows it draws at most one frame in FLOW_FRAME_MS, and with the water still it stops', () => {
  let queue = [], renders = 0, now = 0;
  const raf = (cb) => queue.push(cb);
  const run = (ms) => { for (const end = now + ms; now < end; now += 1000 / 60) { const q = queue; queue = []; q.forEach((cb) => cb(now)); } };
  const motion = { active: false, step() {} };
  const flow = createFlow({ wake: () => loop.wake() });
  const busy = [];
  const loop = createLoop({ render: () => renders++, motion, follows: [], flow, raf, onBusy: (b) => busy.push(b) });
  loop.invalidate();
  run(500);
  const r0 = renders;
  run(1000);
  assert.ok(renders - r0 >= 25 && renders - r0 <= 30, `${renders - r0} frames in a second`);
  assert.ok(flow.time > 0.9, 'the water moved');
  flow.set({ calm: true });
  run(100); const r = renders; run(1000);
  assert.equal(renders, r, 'still water: nothing is drawn');
  assert.equal(queue.length, 0, 'and no frame is asked for');
  flow.set({ calm: false });
  assert.equal(queue.length, 1, 'the water starts again');
  motion.active = true; loop.invalidate(); run(64); motion.active = false; run(64);
  assert.deepEqual(busy, [true, false], 'the page is told when it starts and stops moving');
});
