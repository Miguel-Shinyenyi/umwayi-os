// UI.7 (tests first): wildlife at the edge, High only (12.R20.5). Distant birds and an antelope on the ridge. They are the only
// things besides the river that move by themselves, they move on the flow clock (so they stop with reduced motion, in Calm
// mode, off screen and hidden), and nothing of them is ever within 25 m of a station, wherever the stations stand.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { birdPose, antelopePose, BIRDS, ANTELOPE_PATH, ANTELOPE_REACH, BIRD_REACH, KEEP_FROM_STATIONS, wildlifeSamples } from '../src/high/wildlife.js';
import { stationPositions, TABLE } from '../src/world/layout.js';
import { heightAt } from '../src/world/height.js';
import { overviewShot } from '../src/world/shots.js';
import { mulberry32 } from '../src/world/random.js';
import { IDS } from '../src/stations/meta.js';

const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

// every place the wildlife can be: the path of every bird and of the antelope over a long time, sampled finely
const SAMPLES = wildlifeSamples();

function nearest(pos, s) {
  let best = Infinity, who = null;
  for (const row of TABLE) {
    const p = pos[row.id], dx = s.x - p.x, dz = s.z - p.z;
    const d = Math.sqrt(dx * dx + dz * dz) - row.footprint - s.reach;
    if (d < best) { best = d; who = row.id; }
  }
  return { d: best, who };
}

test('the keep out distance is 25 m, from the edge of a station to the edge of an animal', () => {
  assert.equal(KEEP_FROM_STATIONS, 25);
  assert.ok(BIRD_REACH > 0.5 && ANTELOPE_REACH > 0.5);
  assert.ok(SAMPLES.length > 1000, `${SAMPLES.length} samples`);
  assert.ok(SAMPLES.some((s) => s.kind === 'bird') && SAMPLES.some((s) => s.kind === 'antelope'));
});

test('no animal is ever within 25 m of a station: at the defaults, all quiet, all needing, each station alone at 0 and 1, and 2000 random need sets', () => {
  const sets = [{}, Object.fromEntries(IDS.map((id) => [id, 0])), Object.fromEntries(IDS.map((id) => [id, 1]))];
  for (const id of IDS) for (const v of [0, 1]) sets.push({ [id]: v });
  const rnd = mulberry32(2027);
  for (let n = 0; n < 2000; n++) sets.push(Object.fromEntries(IDS.map((id) => [id, rnd()])));
  let closest = Infinity;
  for (const needs of sets) {
    const pos = stationPositions(needs);
    for (const s of SAMPLES) {
      const { d, who } = nearest(pos, s);
      closest = Math.min(closest, d);
      if (d < KEEP_FROM_STATIONS) assert.fail(`${s.kind} at (${s.x.toFixed(1)}, ${s.z.toFixed(1)}) is ${d.toFixed(1)} m from ${who} for ${JSON.stringify(needs)}`);
    }
  }
  assert.ok(Number.isFinite(closest));
});

test('the antelope walks on the ground of the ridge and the birds fly well above it', () => {
  for (const s of SAMPLES) {
    const g = heightAt(s.x, s.z);
    if (s.kind === 'antelope') assert.ok(Math.abs(s.y - g) < 1e-6, `the antelope floats at (${s.x}, ${s.z})`);
    else assert.ok(s.y - g >= 8, `a bird is ${(s.y - g).toFixed(1)} m above the ground`);
  }
  for (const p of ANTELOPE_PATH) assert.ok(heightAt(p.x, p.z) > 14, 'the antelope path is up on the hills');
});

test('the antelope is on the skyline of the default view at 1440 by 900: in sight, with the sky behind it', () => {
  const s = overviewShot(1440 / 750);
  const cam = { x: 0, y: s.ty + s.dist * Math.sin(s.pitch), z: s.tz + s.dist * Math.cos(s.pitch) };
  for (const p of ANTELOPE_PATH) {
    const dx = p.x - cam.x, dz = p.z - cam.z, d = Math.hypot(dx, dz);
    const top = Math.atan2(heightAt(p.x, p.z) + 1.0 - cam.y, d);
    let front = -9, back = -9;
    for (let t = 3; t < 300; t += 0.5) {
      const x = cam.x + (dx / d) * t, z = cam.z + (dz / d) * t;
      if (Math.abs(x) > 158 || Math.abs(z) > 158) break;
      const e = Math.atan2(heightAt(x, z) - cam.y, t);
      if (t < d - 1.5) front = Math.max(front, e); else if (t > d + 1.5) back = Math.max(back, e);
    }
    assert.ok(top > front, `the antelope at (${p.x}, ${p.z}) is hidden by the ground in front`);
    assert.ok(top > back, `the antelope at (${p.x}, ${p.z}) has the hill behind it, not the sky`);
    // inside the picture: the horizontal half angle of the overview at 1440 by 750 is about 36 degrees
    assert.ok(Math.abs(Math.atan2(dx, -dz)) < (32 * Math.PI) / 180, 'the antelope is outside the picture');
  }
});

test('the wildlife moves only with the clock: the same time gives the same pose, a later time another, and time 0 is a rest pose', () => {
  for (let i = 0; i < BIRDS.length; i++) {
    assert.deepEqual(birdPose(i, 12.5), birdPose(i, 12.5));
    const a = birdPose(i, 10), b = birdPose(i, 11);
    assert.ok(Math.hypot(a.x - b.x, a.z - b.z) > 1, 'a bird does not move');
    assert.ok(Math.hypot(a.x - b.x, a.z - b.z) < 30, 'a bird jumps');
    for (const k of ['x', 'y', 'z', 'heading', 'wing']) assert.ok(Number.isFinite(a[k]), k);
  }
  assert.deepEqual(antelopePose(40), antelopePose(40));
  const moved = [0, 30, 60, 90, 120].map((t) => antelopePose(t)).some((p, _, all) => Math.hypot(p.x - all[0].x, p.z - all[0].z) > 2);
  assert.ok(moved, 'the antelope never walks');
  for (const t of [0, 5, 50, 500]) {
    const p = antelopePose(t);
    for (const k of ['x', 'y', 'z', 'heading', 'stride', 'graze']) assert.ok(Number.isFinite(p[k]), k);
    assert.ok(p.graze >= 0 && p.graze <= 1);
  }
});

test('the antelope walks slowly and the birds glide: speeds a calm picture can carry', () => {
  for (let t = 0; t < 300; t += 0.5) {
    const a = antelopePose(t), b = antelopePose(t + 0.5);
    assert.ok(Math.hypot(a.x - b.x, a.z - b.z) / 0.5 <= 1.2, `the antelope runs at ${t}`);
  }
  for (let i = 0; i < BIRDS.length; i++) for (let t = 0; t < 200; t += 0.5) {
    const a = birdPose(i, t), b = birdPose(i, t + 0.5);
    assert.ok(Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) / 0.5 <= 14, `bird ${i} at ${t}`);
  }
});

test('the wildlife has no clock of its own: it reads the flow clock of the water, so it stops when the water stops', () => {
  const text = readFileSync(join(src, 'high', 'wildlife.js'), 'utf8') + readFileSync(join(src, 'high', 'build.js'), 'utf8');
  for (const bad of ['requestAnimationFrame', 'setInterval', 'setTimeout', 'performance.now', 'Date.now', 'new Date', 'Math.random']) {
    assert.ok(!text.includes(bad), `the wildlife uses ${bad}`);
  }
  assert.match(readFileSync(join(src, 'high', 'build.js'), 'utf8'), /flowTime/);
});

// Found by the mutation pass of UI.7: the look of the motion, which the keep out test does not see.
test('the antelope grazes still at each end of its path, head down in the middle of the pause, and walks the whole path between', () => {
  const end = ANTELOPE_PATH[ANTELOPE_PATH.length - 1], start = ANTELOPE_PATH[0];
  const length = ANTELOPE_PATH.slice(1).reduce((s, p, i) => s + Math.hypot(p.x - ANTELOPE_PATH[i].x, p.z - ANTELOPE_PATH[i].z), 0);
  const graze = 14, walk = length / 0.45;
  const at = (t) => antelopePose(t);
  // the first pause: in place at the start, legs still, the head up at both ends of the pause and down in its middle
  for (let t = 0.2; t < graze; t += 0.7) {
    const p = at(t);
    assert.ok(Math.abs(p.x - start.x) < 1e-9 && Math.abs(p.z - start.z) < 1e-9, `moved while grazing at ${t}`);
    assert.equal(p.stride, 0, `legs swing while grazing at ${t}`);
  }
  assert.ok(at(0).graze < 0.01 && at(graze - 0.01).graze < 0.05 && at(graze / 2).graze > 0.99);
  // walking: the head is up and the legs swing, and the end of the path is reached when the walk ends
  for (let t = graze + 0.5; t < graze + walk - 0.5; t += 0.9) assert.equal(at(t).graze, 0, `grazing while walking at ${t}`);
  assert.ok(at(graze + 1).stride !== 0);
  const arrived = at(graze + walk + 0.01);
  assert.ok(Math.hypot(arrived.x - end.x, arrived.z - end.z) < 1e-6, 'the walk does not end at the end of the path');
  const before = at(graze + walk - 1);
  assert.ok(Math.hypot(before.x - end.x, before.z - end.z) > 0.3, 'the end of the path was reached too early');
  // the second pause, at the far end, still too
  for (let t = graze + walk + 0.2; t < 2 * graze + walk; t += 0.7) assert.equal(at(t).stride, 0);
});

test('the birds keep to their loops, face the way they fly, and mostly glide with short runs of wing beats', () => {
  for (let i = 0; i < BIRDS.length; i++) {
    const b = BIRDS[i];
    let glide = 0, n = 0;
    for (let t = 0; t < 600; t += 0.37) {
      const p = birdPose(i, t);
      const r = Math.hypot(p.x - b.cx, p.z - b.cz);
      assert.ok(r >= b.r * 0.88 - 1e-9 && r <= b.r * 1.12 + 1e-9, `bird ${i} off its loop at ${t}: ${r}`);
      assert.ok(Math.abs(p.wing) <= 0.5 + 1e-9, `bird ${i} beats its wings too far at ${t}`);
      if (Math.abs(p.wing - 0.08) < 1e-6) glide++;
      n++;
      // the heading points along the direction of travel
      const q = birdPose(i, t + 0.01), dx = q.x - p.x, dz = q.z - p.z;
      const d = Math.atan2(dx, dz) - p.heading;
      assert.ok(Math.abs(Math.atan2(Math.sin(d), Math.cos(d))) < 0.35, `bird ${i} flies sideways at ${t}`);
    }
    assert.ok(glide / n > 0.6, `bird ${i} glides only ${Math.round((100 * glide) / n)}% of the time`);
  }
});
