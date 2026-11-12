// UI.1.3: the eleven stations. Models are built in Node (no WebGL needed) and every pose is applied.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { STATIONS, IDS } from '../src/stations/meta.js';
import { stationDefs, buildStation } from '../src/stations/index.js';
import { makeKit } from '../src/stations/kit.js';
import { actionMs } from '../src/engine/poses.js';
import { SAMPLE } from '../src/data/sample.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const files = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : [join(dir, n)]));

test('there are eleven stations in the ring order of UI-Q8', () => {
  assert.deepEqual(IDS, ['memory', 'rules', 'queue', 'archive', 'logbook', 'automation', 'helpers', 'workflows', 'adapters', 'killswitch', 'budget']);
  assert.deepEqual(STATIONS.map((s) => s.name), ['Memory', 'Rules', 'Queue', 'Archive', 'Logbook', 'Automation', 'AI helpers', 'Workflows', 'Adapters', 'Kill switch', 'Budget']);
});

test('Budget is a built station, and every station is built', () => {
  for (const s of STATIONS) assert.equal(s.state, 'built', s.id);
  assert.match(STATIONS.find((s) => s.id === 'budget').note, /B\.10/);
});

test('every station has at least two poses, with the same numeric parameters, and a move between each pair', () => {
  const kit = makeKit();
  for (const def of stationDefs()) {
    assert.ok(def.poses.length >= 2, def.id);
    assert.ok(actionMs(def.poses.length) <= 2900, `${def.id} action is too long`);
    const keys = Object.keys(def.poses[0].params).sort();
    for (const p of def.poses) {
      assert.deepEqual(Object.keys(p.params).sort(), keys, `${def.id} pose ${p.id}`);
      for (const v of Object.values(p.params)) assert.ok(Number.isFinite(v), `${def.id} pose ${p.id}`);
      assert.ok(p.caption && p.caption.length > 5);
    }
    const st = buildStation(def, kit);
    st.setCounts(SAMPLE);
    for (const p of def.poses) st.apply(p.params);
    for (let i = 1; i < def.poses.length; i++) {
      for (const t of [0, 0.5, 1]) {
        const mid = {};
        for (const k of keys) mid[k] = def.poses[i - 1].params[k] + (def.poses[i].params[k] - def.poses[i - 1].params[k]) * t;
        st.apply(mid); // a move is every value in between
      }
    }
    if (st.rest) for (const v of Object.values(st.rest())) assert.ok(Number.isFinite(v), `${def.id} rest`);
    assert.ok(st.hit.userData.station === def.id);
  }
});

test('stations also build and apply with no counts at all', () => {
  const kit = makeKit();
  for (const def of stationDefs()) {
    const st = buildStation(def, kit);
    st.setCounts(null);
    st.apply(def.poses[0].params);
  }
});

test('the words are the product words: short, no em dash, every station has two lines and a command', () => {
  const dash = /[\u2014\u2013]/;
  for (const s of STATIONS) {
    assert.equal(s.lines.length, 2, s.id);
    assert.match(s.command, /^umwayi [a-z]/);
    for (const text of [s.name, ...s.lines, s.note ?? '', ...s.poses.map((p) => p.caption)]) {
      assert.ok(!dash.test(text), `${s.id}: ${text}`);
    }
    for (const line of s.lines) assert.ok(line.split(/\s+/).length <= 14 && line.endsWith('.'), `${s.id}: ${line}`);
  }
  const all = JSON.stringify(STATIONS);
  assert.ok(all.includes('Ask me first') && all.includes('AI helpers') && all.includes('logbook'));
});

test('no module loads a file, keeps a timer or draws by itself', () => {
  const banned = [/\bfetch\s*\(/, /XMLHttpRequest/, /WebSocket/, /sendBeacon/, /\bLoader\b/, /TextureLoader/, /localStorage/, /sessionStorage/,
    /indexedDB/, /document\.cookie/, /setInterval/, /new Worker/, /import\s*\(/, /\bnew Image\b/, /\bImage\s*\(/];
  for (const f of files(ROOT).filter((n) => n.endsWith('.js'))) {
    const text = readFileSync(f, 'utf8');
    // the one exception (UI.7, 12.R16.4): the High asset module of the public site loads its photographs as images from the
    // site's own host. The owner's live view never imports it (ui/test/high.test.mjs checks the import graph).
    let own = f.endsWith(join('src', 'high', 'assets.js')) ? banned.filter((re) => !/Image/.test(re.source)) : banned;
    // the other exception (W6.9, W6.R2.5): the page client sends the page's requests to the backend that served it, and is the one
    // file that may. It may name the request function and nothing else in this list (ui/test/client.test.mjs, tests/test_ui_package.py).
    if (f.endsWith(join('src', 'api', 'client.js'))) own = own.filter((re) => !/fetch/.test(re.source));
    for (const re of own) assert.ok(!re.test(text), `${f}: ${re}`);
    // only scene.js names it, to hand it to the on demand loop (it was app.js before the scene moved to a module of its own); no other module asks for a frame
    if (!f.endsWith(join('src', 'scene.js'))) assert.ok(!/requestAnimationFrame/.test(text), `${f} asks for frames by itself`);
  }
});

import { describe as describeCounts } from '../src/data/counts.js';
test('counts text: real numbers, unknown is never zero, and stations without a count say nothing', () => {
  assert.equal(describeCounts('queue', SAMPLE), '6 open, 5 answered');
  assert.equal(describeCounts('rules', SAMPLE), '7 Yes, 6 No, 2 Ask me first');
  assert.equal(describeCounts('killswitch', { kill_switch: 'on' }), 'on');
  assert.equal(describeCounts('killswitch', { kill_switch: 'unknown' }), 'unknown, drawn as on');
  assert.equal(describeCounts('rules', { rules: null }), 'unknown, drawn as Ask me first');
  assert.equal(describeCounts('queue', { queue: null }), 'unknown');
  assert.equal(describeCounts('queue', { queue: { open: null, answered: 3 } }), 'unknown open, 3 answered');
  for (const id of ['memory', 'archive', 'helpers', 'workflows', 'adapters']) assert.equal(describeCounts(id, SAMPLE), null);
  assert.equal(describeCounts('queue', null), null);
});
