// UI.1.2: the engine. Pure logic, no DOM and no WebGL: tweens, following, the loop, settings and the pose player.
import test from 'node:test';
import assert from 'node:assert/strict';
import { easeOut, clamp, lerp } from '../src/engine/ease.js';
import { Follow } from '../src/engine/follow.js';
import { Motion } from '../src/engine/motion.js';
import { createLoop } from '../src/engine/loop.js';
import { createSettings } from '../src/engine/settings.js';
import { moveMs, actionMs, ACTION_DELAY, createPlayer, mixParams } from '../src/engine/poses.js';

const run = (motion, ms, dt = 16) => { for (let t = 0; t < ms; t += dt) motion.step(dt); };

test('easeOut starts at 0, ends at 1, only rises and slows down', () => {
  assert.equal(easeOut(0), 0);
  assert.equal(easeOut(1), 1);
  let prevValue = 0, prevStep = Infinity;
  for (let i = 1; i <= 100; i++) {
    const v = easeOut(i / 100), step = v - prevValue;
    assert.ok(v >= prevValue);
    assert.ok(step <= prevStep + 1e-12, 'the speed never grows');
    prevValue = v; prevStep = step;
  }
  assert.equal(clamp(5), 1); assert.equal(lerp(2, 4, 0.5), 3);
});

test('a tween ends in its time and then nothing is active', () => {
  const m = new Motion();
  const seen = []; let done = 0;
  m.add({ ms: 1000, update: (t) => seen.push(t), done: () => done++ });
  assert.equal(m.active, true);
  run(m, 990); assert.equal(m.active, true); assert.equal(done, 0);
  run(m, 40); assert.equal(m.active, false); assert.equal(done, 1);
  assert.equal(seen[seen.length - 1], 1);
  const n = seen.length; run(m, 500); assert.equal(seen.length, n, 'no update after the end');
});

test('a delayed tween waits, then runs', () => {
  const m = new Motion(); const seen = [];
  m.add({ ms: 200, delay: 500, update: (t) => seen.push(t) });
  run(m, 400); assert.equal(seen.length, 0);
  run(m, 400); assert.ok(seen.length > 0); run(m, 100); assert.equal(m.active, false);
});

test('slow (calm) lengthens every tween and its delay', () => {
  for (const slow of [1, 1.6]) {
    const m = new Motion({ slow }); let end = null; let t = 0;
    m.add({ ms: 1000, delay: 500, update: () => {}, done: () => { end = t; } });
    while (m.active && t < 10000) { m.step(10); t += 10; }
    assert.ok(Math.abs(end - 1500 * slow) <= 20, `slow ${slow} ended at ${end}`);
  }
});

test('with reduced motion a tween jumps to its end and nothing is scheduled', () => {
  const m = new Motion({ reduced: true }); const seen = []; let done = 0;
  m.add({ ms: 5000, delay: 500, update: (t) => seen.push(t), done: () => done++ });
  assert.deepEqual(seen, [1]); assert.equal(done, 1); assert.equal(m.active, false);
});

test('switching reduced motion on during a move completes it at once', () => {
  const m = new Motion(); const seen = [];
  m.add({ ms: 3000, update: (t) => seen.push(t), done: () => seen.push('done') });
  run(m, 300); m.setReduced(true);
  assert.equal(seen[seen.length - 2], 1); assert.equal(seen[seen.length - 1], 'done'); assert.equal(m.active, false);
});

test('cancel by tag stops a group of tweens without finishing them', () => {
  const m = new Motion(); let ran = 0;
  m.add({ ms: 1000, tag: 'a', update: () => ran++ }); m.add({ ms: 1000, tag: 'b', update: () => ran++ });
  m.cancel('a'); run(m, 100); assert.equal(m.active, true);
  m.cancel('b'); assert.equal(m.active, false);
});

test('wake is called once when the first tween starts an idle motion', () => {
  let wakes = 0; const m = new Motion({ wake: () => wakes++ });
  m.add({ ms: 100, update: () => {} }); m.add({ ms: 100, update: () => {} });
  assert.equal(wakes, 1); run(m, 400); m.add({ ms: 100, update: () => {} }); assert.equal(wakes, 2);
});

test('following comes to rest within 3 s, and within 5 s in calm mode, from the largest move', () => {
  for (const [tau, limit] of [[140, 3000], [140 * 1.6, 5000]]) {
    const f = new Follow({ tau, eps: 0.0005 }); f.target = 1; let t = 0;
    while (f.active && t < 20000) { f.step(16); t += 16; }
    assert.equal(f.active, false); assert.equal(f.value, 1); assert.ok(t <= limit, `tau ${tau} took ${t} ms`);
  }
});

test('following never overshoots', () => {
  const f = new Follow({ tau: 140, eps: 0.0005 }); f.target = 1;
  for (let i = 0; i < 400; i++) { f.step(16); assert.ok(f.value <= 1); }
});

test('with reduced motion following jumps', () => {
  const f = new Follow({ tau: 140, eps: 0.0005, reduced: true }); f.target = 0.7;
  assert.equal(f.value, 0.7); assert.equal(f.active, false);
});

function fakeRaf() {
  const q = []; let now = 0;
  return { raf: (cb) => { q.push(cb); return q.length; }, pending: () => q.length,
    tick: (dt = 16) => { now += dt; const cbs = q.splice(0); cbs.forEach((cb) => cb(now)); } };
}

test('the loop draws nothing and asks for no frame while idle', () => {
  const r = fakeRaf(); const motion = new Motion(); let renders = 0;
  createLoop({ render: () => renders++, motion, follows: [], raf: r.raf });
  assert.equal(r.pending(), 0); assert.equal(renders, 0);
});

test('invalidate draws exactly one frame when nothing moves', () => {
  const r = fakeRaf(); const motion = new Motion(); let renders = 0;
  const loop = createLoop({ render: () => renders++, motion, follows: [], raf: r.raf });
  loop.invalidate(); loop.invalidate(); assert.equal(r.pending(), 1);
  r.tick(); assert.equal(renders, 1); assert.equal(r.pending(), 0); r.tick(); assert.equal(renders, 1);
});

test('the loop keeps drawing while a tween runs and stops the frame after it ends', () => {
  const r = fakeRaf(); const motion = new Motion({ wake: () => loop.invalidate() }); let renders = 0;
  const loop = createLoop({ render: () => renders++, motion, follows: [], raf: r.raf });
  motion.add({ ms: 320, update: () => {} });
  let guard = 0; while (r.pending() && guard++ < 200) r.tick(16);
  assert.ok(renders >= 19 && renders <= 22, `renders ${renders}`); assert.equal(r.pending(), 0);
  const before = renders; r.tick(); r.tick(); assert.equal(renders, before);
});

test('the loop keeps drawing while a follow has not come to rest, and then stops', () => {
  const r = fakeRaf(); const motion = new Motion(); const f = new Follow({ tau: 140, eps: 0.0005 });
  const loop = createLoop({ render: () => {}, motion, follows: [f], raf: r.raf });
  f.target = 1; loop.invalidate(); let frames = 0;
  while (r.pending() && frames < 1000) { r.tick(16); frames++; }
  assert.equal(f.value, 1); assert.ok(frames * 16 <= 3000); assert.equal(r.pending(), 0);
});

test('settings read reduced motion, start calm on less contrast, and follow changes', () => {
  const listeners = {}; const state = { reduce: false, less: false };
  const mm = (q) => ({ get matches() { return q.includes('reduced-motion') ? state.reduce : state.less; },
    addEventListener: (_e, cb) => { listeners[q] = cb; } });
  const s = createSettings({ matchMedia: mm }); const log = [];
  s.onChange((k, v) => log.push([k, v]));
  assert.equal(s.reduced, false); assert.equal(s.calm, false);
  state.reduce = true; listeners['(prefers-reduced-motion: reduce)']({ matches: true });
  assert.equal(s.reduced, true); assert.deepEqual(log.pop(), ['reduced', true]);
  s.setCalm(true); assert.equal(s.calm, true); assert.deepEqual(log.pop(), ['calm', true]);
  state.less = true; assert.equal(createSettings({ matchMedia: mm }).calm, true);
  assert.equal(createSettings({ matchMedia: undefined }).reduced, false);
});

test('the action of any station ends within 3 s, and within 5 s in calm mode', () => {
  for (let n = 2; n <= 6; n++) {
    assert.ok(moveMs(n) <= 1200);
    assert.ok(actionMs(n) <= 3000, `${n} poses: ${actionMs(n)}`);
    assert.ok(actionMs(n) * 1.6 <= 5000);
    assert.equal(actionMs(n), ACTION_DELAY + moveMs(n) * (n - 1));
  }
});

const stub = () => {
  const applied = [];
  const station = { poses: [{ params: { a: 0, b: 0 } }, { params: { a: 1, b: 2 } }, { params: { a: 2, b: 0 } }], restIndex: 2,
    apply: (p) => applied.push({ ...p }) };
  return { station, applied };
};

test('mixParams interpolates every key', () => {
  assert.deepEqual(mixParams({ a: 0, b: 2 }, { a: 1, b: 4 }, 0.5), { a: 0.5, b: 3 });
});

test('the pose player plays the poses once, ends on the last one, and then asks for nothing', () => {
  const { station, applied } = stub(); const motion = new Motion();
  const player = createPlayer({ station, motion });
  player.play(); assert.deepEqual(applied[0], { a: 0, b: 0 }, 'starts on the first pose');
  run(motion, actionMs(3) + 100);
  assert.deepEqual(applied[applied.length - 1], { a: 2, b: 0 }); assert.equal(motion.active, false);
  assert.equal(player.index, 2);
});

test('with reduced motion play shows the rest pose and the stepper jumps between poses', () => {
  const { station, applied } = stub(); const motion = new Motion({ reduced: true });
  const player = createPlayer({ station, motion });
  player.showRest(); assert.deepEqual(applied.pop(), { a: 2, b: 0 }); assert.equal(player.index, 2);
  player.prev(); assert.deepEqual(applied.pop(), { a: 1, b: 2 }); assert.equal(player.index, 1);
  player.prev(); player.prev(); assert.equal(player.index, 0, 'does not go before the first');
  player.next(); player.next(); player.next(); assert.equal(player.index, 2, 'does not go past the last');
  assert.equal(motion.active, false);
});

test('settleToRest eases back to the rest pose and jumps with reduced motion', () => {
  const { station, applied } = stub(); const motion = new Motion();
  const player = createPlayer({ station, motion }); player.goto(0);
  player.settleToRest(); run(motion, 1500);
  assert.deepEqual(applied[applied.length - 1], { a: 2, b: 0 }); assert.equal(motion.active, false);
  const r = stub(); const m2 = new Motion({ reduced: true }); const p2 = createPlayer({ station: r.station, motion: m2 });
  p2.goto(0); p2.settleToRest(); assert.deepEqual(r.applied[r.applied.length - 1], { a: 2, b: 0 });
});
