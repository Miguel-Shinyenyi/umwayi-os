// UI.6 (tests first): the scene code is one module, ui/src/scene.js, used by the owner's live view (app.js) and by the
// public site (12.R18.3). These tests need no browser: they check the entry's contract and the source of both users.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createScene, CONTROLS } from '../src/scene.js';

const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const read = (name) => readFileSync(join(src, name), 'utf8');
const imports = (text) => [...text.matchAll(/^import\s+(?:[^'"]*?from\s+)?['"]([^'"]+)['"]/gm)].map((m) => m[1]);
const walk = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));

// A canvas that cannot draw: createScene must refuse it before it touches anything else.
const noGl = () => ({ getContext: () => null, addEventListener() {}, removeEventListener() {} });
const win = { devicePixelRatio: 1, requestAnimationFrame: () => 0, navigator: {}, location: { hash: '' } };

test('createScene is exported, with the controls the design names', () => {
  assert.equal(typeof createScene, 'function');
  for (const name of ['select', 'overview', 'setNeeds', 'setCalm', 'setReducedMotion', 'dispose']) assert.ok(CONTROLS.includes(name), name);
});

test('createScene draws Standard only: List draws no scene and High is not built yet', () => {
  assert.throws(() => createScene(noGl(), { tier: 1, win }), RangeError);
  assert.throws(() => createScene(noGl(), { tier: 3, win }), RangeError);
  assert.throws(() => createScene(noGl(), { tier: 'standard', win }), RangeError);
});

test('createScene with no WebGL throws, so the caller can show List', () => {
  assert.throws(() => createScene(noGl(), { tier: 2, win }), /no webgl2/);
  assert.throws(() => createScene(noGl(), { win }), /no webgl2/, 'the default tier is Standard');
});

test('the scene module reads no page: no document, no element lookup, no storage, no request', () => {
  const text = read('scene.js');
  for (const bad of ['document', 'getElementById', 'querySelector', 'localStorage', 'sessionStorage', 'fetch(', 'XMLHttpRequest', 'navigator.sendBeacon', 'document.cookie']) {
    assert.ok(!text.includes(bad), `scene.js contains ${bad}`);
  }
});

test('app.js, the live view, gets all of its scene code from scene.js and builds no world of its own', () => {
  const list = imports(read('app.js'));
  assert.ok(list.includes('./scene.js'), 'app.js does not import scene.js');
  const mine = list.filter((p) => /^\.\/(world|engine\/(stage|rig|motion|loop|poses|flow|placement|detail))/.test(p));
  assert.deepEqual(mine, [], 'app.js still imports scene code');
  assert.ok(!list.includes('three'), 'app.js still imports three');
  assert.ok(!/buildWorld|createStage|new Rig\(|createLoop|createPlayer/.test(read('app.js')), 'app.js still builds the scene');
});

test('the one scene module is the only place that builds the world, the stage, the rig and the loop', () => {
  const owners = walk(src).filter((f) => f.endsWith('.js') && /=\s*buildWorld\(|=\s*createStage\(|new Rig\(|=\s*createLoop\(/.test(readFileSync(f, 'utf8')));
  assert.deepEqual(owners.map((f) => f.slice(src.length + 1)).sort(), ['scene.js']);
});

test('the device query is one module for both pages: boot.js decides the tier and starts the scene, main.js only sets the live view options', () => {
  const boot = read('boot.js'), main = read('main.js');
  assert.ok(/chooseTier\(/.test(boot) && /readEnv\(/.test(boot), 'boot.js does not run the device query');
  assert.ok(imports(main).includes('./boot.js'), 'main.js does not use boot.js');
  assert.ok(!/chooseTier\(/.test(main), 'main.js has its own copy of the tier choice');
  assert.ok(/maxTier:\s*2/.test(main) && /local:\s*true/.test(main), 'the live view must pass a highest tier of Standard and ignore the network');
});

test('the device hints are read in one place and go nowhere: no request, no storage, no address write of a hint', () => {
  for (const name of ['boot.js', 'engine/env.js', 'scene.js']) {
    const text = read(name);
    for (const bad of ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage', 'sessionStorage', 'document.cookie', 'indexedDB', 'WebSocket']) {
      assert.ok(!text.includes(bad), `${name} contains ${bad}`);
    }
  }
  // the address fragment is written with the tier name only, through tierHash
  const boot = read('boot.js');
  const writes = [...boot.matchAll(/replaceState\(([^)]*)\)/g)].map((m) => m[1]);
  assert.ok(writes.length >= 1 && writes.every((w) => /tierHash\(/.test(w)), `address writes: ${writes}`);
});
