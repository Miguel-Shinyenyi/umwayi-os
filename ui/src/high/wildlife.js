// Wildlife at the edge of the scene, High only (12.R20.5): a few distant birds that glide in loops over the far valley, and an
// antelope (an impala) that walks slowly along a ridge on the skyline and stops to graze. Pure: no three.js, no clock of its
// own. The time t is the flow clock of the water (engine/flow.js), so the wildlife stops whenever the water stops: with reduced
// motion, in Calm mode, off screen, hidden and in List. Nothing of it comes within 25 m of a station, wherever a station stands.
import { heightAt } from '../world/height.js';

export const KEEP_FROM_STATIONS = 25; // metres from the edge of a station to the edge of an animal
export const BIRD_REACH = 0.9; // half the wingspan
export const ANTELOPE_REACH = 1.0; // half the body length, nose to tail

// The birds: black kites, gliding in loops over the far hills behind the forest, right of the middle of the default view, low enough to be under the top bar.
// cx, cz: the centre of the loop; r: its radius; y: the height of the glide; v: metres a second; dir: +1 or -1; phase: radians
const LOOP = { cx: 32, cz: -118 };
export const BIRDS = [
  { r: 15, y: 28.6, v: 7.5, dir: 1, phase: 0.0 },
  { r: 17, y: 29.4, v: 8.2, dir: 1, phase: 0.55 },
  { r: 13, y: 28.8, v: 7.0, dir: 1, phase: 1.3 },
  { r: 18, y: 30.2, v: 8.6, dir: 1, phase: 2.2 },
  { r: 11, y: 29.0, v: 6.6, dir: -1, phase: 3.1 },
  { r: 16, y: 28.7, v: 7.8, dir: -1, phase: 4.0 },
  { r: 14, y: 30.6, v: 7.2, dir: 1, phase: 5.1 },
].map((b) => ({ ...LOOP, ...b }));

const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

// { x, y, z, heading (radians, 0 is +z), bank (radians), wing (radians of the wing beat) }
export function birdPose(i, t) {
  const b = BIRDS[i];
  const a = b.phase + (b.dir * b.v * t) / b.r;
  // the loop breathes a little, so the flock never looks like a wheel
  const rr = b.r * (1 + 0.12 * Math.sin(a * 2 + b.phase * 3));
  const x = b.cx + Math.cos(a) * rr, z = b.cz + Math.sin(a) * rr;
  const y = b.y + 1.4 * Math.sin(t * 0.21 + b.phase * 2);
  // the direction of travel: the derivative of the loop
  const dx = -Math.sin(a) * b.dir, dz = Math.cos(a) * b.dir;
  const heading = Math.atan2(dx, dz);
  // mostly a glide; every few seconds a short run of wing beats
  const beat = smooth(0.55, 0.8, Math.sin(t * 0.37 + b.phase * 1.7));
  const wing = 0.08 + beat * 0.42 * Math.sin(t * 6.5 + b.phase * 5);
  return { x, y, z, heading, bank: -b.dir * 0.32, wing };
}

// The antelope's path: a few metres along a crest right of the middle of the default view, about 150 m off, where it stands on
// the skyline and no tree of the forest is in front of it (ui/test/wildlife.test.mjs, ui/test/high.test.mjs).
export const ANTELOPE_PATH = [{ x: 11, z: -90 }, { x: 12, z: -90.6 }, { x: 13, z: -91 }, { x: 14, z: -91 }];
const SEG = ANTELOPE_PATH.slice(1).map((p, i) => Math.hypot(p.x - ANTELOPE_PATH[i].x, p.z - ANTELOPE_PATH[i].z));
const LENGTH = SEG.reduce((a, b) => a + b, 0);
const SPEED = 0.45; // a slow walk, metres a second
const WALK = LENGTH / SPEED, GRAZE = 14; // seconds walking one way, seconds grazing at each end
const PERIOD = 2 * (WALK + GRAZE);
const STEP = 1.1; // metres per stride

function along(s) {
  let k = 0;
  while (k < SEG.length - 1 && s > SEG[k]) { s -= SEG[k]; k++; }
  const a = ANTELOPE_PATH[k], b = ANTELOPE_PATH[k + 1], f = Math.min(1, Math.max(0, s / SEG[k]));
  return { x: a.x + (b.x - a.x) * f, z: a.z + (b.z - a.z) * f, heading: Math.atan2(b.x - a.x, b.z - a.z) };
}

// { x, y, z, heading, stride (radians of the leg swing), graze (0 head up to 1 head down) }
export function antelopePose(t) {
  const u = ((t % PERIOD) + PERIOD) % PERIOD;
  let s, back = false, graze = 0, walking = true;
  if (u < GRAZE) { s = 0; walking = false; graze = smooth(0, 2.5, u) * (1 - smooth(GRAZE - 2.5, GRAZE, u)); }
  else if (u < GRAZE + WALK) s = (u - GRAZE) * SPEED;
  else if (u < 2 * GRAZE + WALK) { s = LENGTH; walking = false; const w = u - GRAZE - WALK; graze = smooth(0, 2.5, w) * (1 - smooth(GRAZE - 2.5, GRAZE, w)); back = true; }
  else { s = LENGTH - (u - 2 * GRAZE - WALK) * SPEED; back = true; }
  const p = along(Math.min(LENGTH, Math.max(0, s)));
  const heading = back ? p.heading + Math.PI : p.heading;
  // it faces the way it will walk next while it grazes at an end
  const stride = walking ? ((s / STEP) * Math.PI * 2) % (Math.PI * 2) : 0;
  return { x: p.x, y: heightAt(p.x, p.z), z: p.z, heading, stride, graze };
}

// Every place the wildlife can be, over a time longer than every loop and the antelope's walk, for the keep out test.
export function wildlifeSamples(seconds = 2 * PERIOD + 60, step = 0.5) {
  const out = [];
  for (let t = 0; t <= seconds; t += step) {
    for (let i = 0; i < BIRDS.length; i++) { const p = birdPose(i, t); out.push({ kind: 'bird', x: p.x, y: p.y, z: p.z, reach: BIRD_REACH }); }
    const a = antelopePose(t);
    out.push({ kind: 'antelope', x: a.x, y: a.y, z: a.z, reach: ANTELOPE_REACH });
  }
  return out;
}
