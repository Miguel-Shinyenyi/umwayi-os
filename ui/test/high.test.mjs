// UI.7 (tests first): the High scene (12.R16.3, 12.R16.4). It is added on top of a Standard world that is already drawn, and
// remove() puts the Standard world back exactly as it was, so a failed or dropped High always leaves Standard. The world is
// built in Node (no WebGL), with a fake 2D canvas for the two glows that are drawn in code.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three';

const g2d = new Proxy({}, { get: (t, k) => (k === 'createRadialGradient' || k === 'createLinearGradient' ? () => ({ addColorStop() {} }) : k in t ? t[k] : () => {}), set: (t, k, v) => { t[k] = v; return true; } });
globalThis.document ||= { createElement: () => ({ width: 0, height: 0, getContext: () => g2d }) };
const { buildWorld } = await import('../src/world/index.js');
const { Motion } = await import('../src/engine/motion.js');
const { waterShared } = await import('../src/world/water.js');
const { FOREST_COUNT } = await import('../src/world/forest.js');
const { applyHigh, HIGH_GRASS } = await import('../src/high/build.js');
const { ASSETS, loadTextures } = await import('../src/high/assets.js');
const { upgrade } = await import('../src/high/index.js');
const { birdPose, antelopePose, BIRDS, ANTELOPE_SCALE, ANTELOPE_REACH, ANTELOPE_GRAZE } = await import('../src/high/wildlife.js');

const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const walk = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));
const fakeTextures = () => Object.fromEntries(ASSETS.map((a) => [a.key, new THREE.DataTexture(new Uint8Array([128, 128, 255, 255]), 1, 1)]));

// everything about the scene that High could change: which objects are there, shown, where, and with what geometry and material
function snapshot(world) {
  const out = [];
  world.scene.traverse((o) => out.push([o.uuid, o.visible, o.parent && o.parent.uuid, o.position.toArray().join(), o.isMesh ? o.geometry.uuid : '', o.isMesh ? (Array.isArray(o.material) ? o.material.map((m) => m.uuid).join() : o.material.uuid) : '', o.isInstancedMesh ? o.count : '', o.onBeforeRender === THREE.Object3D.prototype.onBeforeRender]));
  return out;
}
const world = buildWorld(new Motion({ reduced: true, wake() {} }));
const before = snapshot(world);
const grassStd = world.grass.count;
const high = applyHigh(world, fakeTextures());
const named = (name) => { let f = null; world.scene.traverse((o) => { if (o.name === name) f = o; }); return f; };

test('High adds the wildlife: the birds and the antelope', () => {
  const birds = named('high:birds'), antelope = named('high:antelope');
  assert.ok(birds && antelope);
  assert.equal(birds.children.length, BIRDS.length);
});

test('the antelope is drawn at ANTELOPE_SCALE times the real model, and its keep out reach covers it at that size', async () => {
  const { buildAntelope } = await import('../src/high/figures.js');
  const antelope = named('high:antelope');
  for (const k of ['x', 'y', 'z']) assert.equal(antelope.scale[k], ANTELOPE_SCALE, `scale ${k}`);
  // the model itself is a real impala (see the size test below); the farthest a corner of its box is from its centre, on the ground, with the head down
  const model = buildAntelope();
  model.userData.neck.rotation.x = 1.15; // the head down to graze: the farthest it reaches
  model.updateMatrixWorld(true);
  const real = new THREE.Box3().setFromObject(model);
  const radius = Math.max(...[real.min.x, real.max.x].flatMap((x) => [real.min.z, real.max.z].map((z) => Math.hypot(x, z))));
  assert.ok(radius * ANTELOPE_SCALE <= ANTELOPE_REACH, `the antelope reaches ${(radius * ANTELOPE_SCALE).toFixed(2)} m, the keep out reach is ${ANTELOPE_REACH}`);
});

test('High draws more: a denser forest, much more grass, a finer ground', () => {
  const forest = named('high:forest'), grass = named('high:grass'), ground = named('high:terrain');
  assert.ok(forest && grass && ground);
  let trees = 0;
  forest.traverse((o) => { if (o.isInstancedMesh && o.name === 'high:trunks') trees = o.count; });
  assert.ok(trees >= FOREST_COUNT.high * 0.9, `${trees} trees`);
  assert.ok(grass.count >= grassStd * 2.5 && grass.count <= HIGH_GRASS, `${grass.count} blades against ${grassStd}`);
  assert.ok(ground.geometry.attributes.position.count > world.terrain.mesh.geometry.attributes.position.count * 3);
  assert.equal(world.forest.visible, false, 'the Standard forest is still drawn under the High one');
  assert.equal(world.grass.visible, false);
  assert.equal(world.terrain.mesh.visible, false);
});

test('High gives the shepherd a finer figure and every sheep and goat a short coat, and leaves the lantern, its light and its glow as they were', () => {
  assert.ok(named('high:shepherd'));
  assert.ok(world.shepherd.light.visible && world.shepherd.halo.visible);
  world.shepherd.group.children.slice(0, 8).forEach((o) => assert.equal(o.visible, false, 'a Standard part of the figure is still drawn'));
  let coats = 0, animals = 0;
  world.scene.traverse((o) => { if (o.name === 'high:coat') coats++; if (o.userData && ['dorper', 'redmaasai', 'goat'].includes(o.userData.kind)) animals++; });
  assert.ok(animals >= 5 && coats === animals, `${coats} coats for ${animals} animals`);
});

test('High gives every stone the rock photograph and the river a finer ripple on the same uniforms', () => {
  const stones = [];
  world.scene.traverse((o) => { if (o.isMesh && (o.material === world.kit.M.stone || o.material === world.kit.M.stoneDark)) stones.push(o); });
  assert.deepEqual(stones, [], 'a stone keeps the Standard material');
  assert.equal(world.river.material.name, 'high:water');
  assert.equal(world.river.material.uniforms.flowTime, waterShared.flowTime, 'the High water has its own clock');
  assert.match(world.river.material.fragmentShader, /q3/);
});

test('High never moves a station or changes what a station shows', () => {
  for (const st of world.stations) {
    const b = before.find((r) => r[0] === st.group.uuid);
    assert.equal(st.group.position.toArray().join(), b[3], st.id);
    assert.equal(st.group.visible, b[1], st.id);
  }
});

test('the wildlife is drawn where the pure functions say, at the time of the flow clock, and stays still when the clock stays', () => {
  const birds = named('high:birds'), antelope = named('high:antelope');
  for (const t of [0, 7.5, 31]) {
    waterShared.flowTime.value = t;
    birds.onBeforeRender(); antelope.onBeforeRender();
    birds.children.forEach((b, i) => {
      const p = birdPose(i, t);
      assert.ok(Math.hypot(b.position.x - p.x, b.position.y - p.y, b.position.z - p.z) < 1e-6, `bird ${i} at ${t}`);
    });
    const a = antelopePose(t);
    assert.ok(Math.hypot(antelope.position.x - a.x, antelope.position.z - a.z) < 1e-6);
  }
  const at = antelope.position.clone();
  birds.onBeforeRender(); antelope.onBeforeRender();
  assert.ok(antelope.position.equals(at), 'the antelope moved with no time passing');
  waterShared.flowTime.value = 0;
});

// Found by the mutation pass of UI.7.
test('High hides the Standard acacia crowns and cedars it replaces, so no tree is drawn twice', () => {
  for (const group of [world.acacia, world.cedar]) {
    const leaves = group.children.filter((o) => o.isInstancedMesh && o.geometry.type !== 'CylinderGeometry');
    assert.ok(leaves.length >= 1);
    for (const o of leaves) assert.equal(o.visible, false, `${group.name || 'a tree group'}: the Standard crown is still drawn`);
  }
});

test('each bird faces the way it flies and is drawn there at once; the antelope trots on diagonal pairs of legs', () => {
  const birds = named('high:birds'), antelope = named('high:antelope');
  const t = 17.3; // walking: after the first pause of 14 s, before the walk of about 7 s ends
  assert.ok(antelopePose(t).stride !== 0);
  waterShared.flowTime.value = t;
  birds.onBeforeRender(); antelope.onBeforeRender();
  const v = new THREE.Vector3();
  birds.children.forEach((b, i) => {
    const p = birdPose(i, t);
    assert.ok(Math.abs(b.rotation.y - p.heading) < 1e-9 && Math.abs(b.rotation.z - p.bank) < 1e-9, `bird ${i} is not turned to its heading`);
    v.setFromMatrixPosition(b.matrixWorld);
    assert.ok(v.distanceTo(new THREE.Vector3(p.x, p.y, p.z)) < 1e-6, `bird ${i} is drawn where it was a frame ago`);
  });
  v.setFromMatrixPosition(antelope.matrixWorld);
  const a = antelopePose(t);
  assert.ok(v.distanceTo(new THREE.Vector3(a.x, a.y, a.z)) < 1e-6);
  const leg = (front, side) => antelope.userData.legs.find((l) => l.userData.front === front && l.userData.side === side).rotation.x;
  assert.ok(Math.abs(leg(1, -1)) > 0.01, 'the legs do not swing while walking');
  for (const l of antelope.userData.legs) assert.ok(Math.abs(l.rotation.x) <= 0.38 + 1e-9, 'a leg swings too far');
  assert.ok(Math.abs(leg(1, -1) - leg(0, 1)) < 1e-9 && Math.abs(leg(1, -1) + leg(0, -1)) < 1e-9 && Math.abs(leg(1, 1) - leg(0, -1)) < 1e-9);
  waterShared.flowTime.value = 0;
  birds.onBeforeRender();
});

test('while it grazes the antelope puts its head all the way down and keeps its legs still; walking, the head is up', () => {
  const antelope = named('high:antelope');
  waterShared.flowTime.value = ANTELOPE_GRAZE / 2; // the middle of the first pause
  antelope.onBeforeRender();
  assert.ok(Math.abs(antelope.userData.neck.rotation.x - 1.15) < 1e-6, `the head is at ${antelope.userData.neck.rotation.x}`);
  for (const l of antelope.userData.legs) assert.ok(l.rotation.x === 0, 'a leg swings while grazing'); // 0 and -0 are both still
  waterShared.flowTime.value = ANTELOPE_GRAZE + 2; // walking
  antelope.onBeforeRender();
  assert.equal(antelope.userData.neck.rotation.x, 0, 'the head is down while walking');
  waterShared.flowTime.value = 0;
  antelope.onBeforeRender();
});

test('when High fails part way through its build, what it did is undone and the error goes on', () => {
  const mat = world.river.material, shader = mat.fragmentShader;
  const now = snapshot(world);
  try {
    // the High water refuses a Standard water shader it does not know, after the rocks, the ground and the plants were done
    mat.fragmentShader = 'void main() {}';
    assert.throws(() => applyHigh(world, fakeTextures()));
    assert.deepEqual(snapshot(world), now, 'a failed High left something in the scene');
  } finally {
    mat.fragmentShader = shader;
  }
});

test('remove() puts the Standard world back exactly: the same objects, shown or hidden, with the same geometry and materials', () => {
  high.remove();
  assert.deepEqual(snapshot(world), before);
  assert.equal(world.grass.count, grassStd);
  high.remove(); // a second remove changes nothing
  assert.deepEqual(snapshot(world), before);
});

// (placed after the remove() test above, so that the world is the Standard world again and this High is the only one)
test('remove() frees the rock materials High made, and the geometry of the ground it added', () => {
  const h = applyHigh(world, fakeTextures());
  const used = new Set();
  world.scene.traverse((o) => { if (o.isMesh && o.material && o.material.name !== 'high:water' && o.material.customProgramCacheKey?.() === 'high-rock') used.add(o.material); });
  assert.ok(used.size >= 2, `${used.size} High rock materials`);
  const freed = new Set();
  for (const m of used) m.addEventListener('dispose', () => freed.add(m));
  const ground = named('high:terrain'), disposedGeo = [];
  ground.geometry.addEventListener('dispose', () => disposedGeo.push('ground'));
  h.remove();
  assert.equal(freed.size, used.size, 'a High rock material was not freed');
  assert.deepEqual(disposedGeo, ['ground'], 'the High ground geometry was not freed');
});

test('the detail ladder still thins the grass in High', () => {
  const h = applyHigh(world, fakeTextures());
  const grass = named('high:grass');
  const full = grass.count;
  world.setPlants(0.5);
  assert.ok(grass.count <= Math.ceil(full * 0.5) + 1);
  world.setPlants(1);
  assert.equal(grass.count, full);
  h.remove();
  assert.deepEqual(snapshot(world), before);
});

test('every asset is a file of the site\'s own host under /high/, and one that fails makes the whole load fail', async () => {
  assert.ok(ASSETS.length >= 1);
  for (const a of ASSETS) {
    assert.match(a.file, /^[a-z0-9_]+\.jpg$/);
    assert.ok(!/\/\/|:/.test(a.file));
    // a photograph's colours are sRGB; a normal map holds directions, not colours
    assert.equal(a.colour, !a.file.includes('_nor_'), `${a.file}: the wrong colour space`);
  }
  const urls = [];
  const ok = { load(url, onLoad) { urls.push(url); onLoad(new THREE.Texture()); } };
  const got = await loadTextures('/high/', ok);
  assert.deepEqual(Object.keys(got).sort(), ASSETS.map((a) => a.key).sort());
  assert.deepEqual(urls, ASSETS.map((a) => `/high/${a.file}`));
  const bad = { load(url, onLoad, _p, onError) { if (url.endsWith(ASSETS[0].file)) onError(new Error('404')); else onLoad(new THREE.Texture()); } };
  await assert.rejects(loadTextures('/high/', bad));
  await assert.rejects(loadTextures('https://cdn.example.invalid/', ok), /own host/);
  await assert.rejects(loadTextures('high/', ok), /own host/);
  await assert.rejects(loadTextures('/high//cdn.example.invalid/', ok), /own host/);
  for (const tex of Object.values(got)) {
    assert.equal(tex.generateMipmaps, true);
    assert.equal(tex.minFilter, THREE.LinearMipmapLinearFilter, 'a far photograph would shimmer');
  }
});

test('with no loader given, the photographs load as images of the site\'s own host, made into textures', async () => {
  const seen = [];
  const saved = globalThis.Image;
  globalThis.Image = class {
    set src(u) { seen.push(u); this.url = u; queueMicrotask(() => (u.includes('fail') ? this.onerror(new Error('404')) : this.onload())); }
  };
  try {
    const got = await loadTextures('/high/');
    assert.deepEqual(seen, ASSETS.map((a) => `/high/${a.file}`));
    for (const a of ASSETS) {
      const tex = got[a.key];
      assert.ok(tex.isTexture && tex.image && tex.image.url === `/high/${a.file}`);
      assert.equal(tex.colorSpace, a.colour ? THREE.SRGBColorSpace : THREE.NoColorSpace);
      assert.equal(tex.wrapS, THREE.RepeatWrapping);
      assert.equal(tex.version > 0, true, 'the texture is not marked for upload');
    }
    await assert.rejects(loadTextures('/fail/'), /did not load/);
  } finally {
    globalThis.Image = saved;
  }
});

// The Standard scene and High share one copy of three.js, which the Standard visitor downloads. A three.js class that only
// High uses is kept in that copy, so it makes the Standard download bigger (UI.7: the Standard path keeps its size). High may
// use only what Standard already uses, apart from a few constants.
test('High uses no three.js class or add-on that Standard does not already use', () => {
  const highFiles = walk(join(src, 'high')).filter((f) => f.endsWith('.js'));
  const restFiles = walk(src).filter((f) => f.endsWith('.js') && !relative(src, f).startsWith('high'));
  const used = (fs) => new Set(fs.flatMap((f) => [...readFileSync(f, 'utf8').matchAll(/THREE\.([A-Za-z0-9_]+)/g)].map((m) => m[1])));
  const addons = (fs) => new Set(fs.flatMap((f) => [...readFileSync(f, 'utf8').matchAll(/from 'three\/addons\/([^']+)'/g)].map((m) => m[1])));
  // Texture is the base class of the CanvasTexture that Standard uses, so it is in the copy already
  const CONSTANTS = new Set(['LinearMipmapLinearFilter', 'NoColorSpace', 'RepeatWrapping', 'Texture']);
  const rest = used(restFiles);
  assert.deepEqual([...used(highFiles)].filter((n) => !rest.has(n) && !CONSTANTS.has(n)).sort(), []);
  const restAddons = addons(restFiles);
  assert.deepEqual([...addons(highFiles)].filter((n) => !restAddons.has(n)), []);
});

test('upgrade() keeps Standard when an asset fails, and gives a remove() when it works', async () => {
  const app = { world, loop: { invalidate() { app.drawn = (app.drawn || 0) + 1; } } };
  const fail = { load(url, onLoad, _p, onError) { onError(new Error('404')); } };
  await assert.rejects(upgrade(app, { base: '/high/', loader: fail }));
  assert.deepEqual(snapshot(world), before, 'a failed High left something in the scene');
  const ok = { load(url, onLoad) { onLoad(new THREE.Texture()); } };
  const h = await upgrade(app, { base: '/high/', loader: ok });
  assert.ok(named('high:birds'));
  assert.ok(app.drawn >= 1, 'the picture was not redrawn with High');
  const drawn = app.drawn;
  h.remove();
  assert.ok(app.drawn > drawn, 'the picture was not redrawn without High');
  assert.deepEqual(snapshot(world), before);
});

test('only the High asset module loads a file, and the owner\'s live view never reaches src/high', () => {
  const loaders = walk(src).filter((f) => f.endsWith('.js') && /TextureLoader|ImageLoader|FileLoader|ImageBitmapLoader|new Image\b|Image\s*\(/.test(readFileSync(f, 'utf8')));
  assert.deepEqual(loaders.map((f) => relative(src, f).split('\\').join('/')), ['high/assets.js']);
  const seen = new Set();
  const visit = (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    const text = readFileSync(file, 'utf8');
    for (const m of text.matchAll(/^(?:import|export)\s+(?:[^'"]*?from\s+)?['"](\.[^'"]+)['"]/gm)) visit(join(dirname(file), m[1]));
  };
  visit(join(src, 'main.js'));
  const reached = [...seen].map((f) => relative(src, f).split('\\').join('/'));
  assert.ok(reached.includes('scene.js') && reached.includes('boot.js'));
  assert.deepEqual(reached.filter((f) => f.startsWith('high/')), [], 'the live view bundles High');
});

const { highForestSpots } = await import('../src/high/plants.js');
const { forestSpots } = await import('../src/world/forest.js');
const { reachable, stationPositions, TABLE } = await import('../src/world/layout.js');
const { nearestOnRiver, RIVER_HALF_WIDTH } = await import('../src/world/river.js');
test('the High forest keeps every Standard tree where it stands and adds younger trees clear of every station and of the river', () => {
  const hi = highForestSpots(), std = forestSpots();
  assert.deepEqual(hi.slice(0, std.length), std);
  assert.ok(hi.length >= FOREST_COUNT.high * 0.9);
  const keep = reachable(), pos = stationPositions({});
  for (const s of hi.slice(std.length)) {
    for (const k of keep) if (Math.hypot(s.x - k.x, s.z - k.z) < k.r) assert.fail(`a tree in a station at (${k.x.toFixed(1)}, ${k.z.toFixed(1)})`);
    for (const row of TABLE) if (Math.hypot(s.x - pos[row.id].x, s.z - pos[row.id].z) < row.footprint + 1) assert.fail(row.id);
    if (nearestOnRiver(s).distance <= RIVER_HALF_WIDTH + 1) assert.fail('a tree in the river');
  }
});

const { blocksAntelope } = await import('../src/high/plants.js');
const { ANTELOPE_PATH } = await import('../src/high/wildlife.js');
test('no tree stands between the default view and the antelope: not the forest of either tier, not a cedar, not an acacia', () => {
  const trees = [...highForestSpots()];
  const m = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
  // a standalone cedar is about 8.3 m tall times its scale and 1.6 m wide; an acacia's crown tops out near 3.7 m and spreads 4 m
  for (const [group, height, radius] of [[world.cedar, 8.6, 1.9], [world.acacia, 3.9, 4.4]]) {
    const inst = group.children.find((o) => o.isInstancedMesh);
    for (let i = 0; i < inst.count; i++) { inst.getMatrixAt(i, m); m.decompose(p, q, s); trees.push({ x: p.x, z: p.z, y: p.y, r: radius * s.x + 0.5, top: p.y + height * s.y }); }
  }
  for (const a of ANTELOPE_PATH) for (const t of trees) if (blocksAntelope(t, a)) assert.fail(`a tree at (${t.x.toFixed(1)}, ${t.z.toFixed(1)}) hides the antelope at (${a.x}, ${a.z})`);
});

const { stationViews, inStationView } = await import('../src/high/plants.js');
test('no younger High tree stands in the view of a station, so the camera never starts inside a tree', () => {
  const views = stationViews();
  assert.ok(views.length >= TABLE.length * 6 * 2);
  for (const t of highForestSpots().slice(forestSpots().length)) if (inStationView(t, views)) assert.fail(`a tree at (${t.x.toFixed(1)}, ${t.z.toFixed(1)}) in a station view`);
});

// Found by the mutation pass of UI.7: no Node test can compile a shader, so this checks that every edit High makes to a
// three.js shader finds its place in the real three.js shader text, and that the photographs are bound to it.
const { buildHighTerrain, highRockMaterial } = await import('../src/high/ground.js');
test('every High shader edit finds its place in the three.js shader, and the photographs are bound', () => {
  const tex = fakeTextures();
  const compile = (mat) => {
    const sh = { uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.standard.uniforms), vertexShader: THREE.ShaderLib.standard.vertexShader, fragmentShader: THREE.ShaderLib.standard.fragmentShader };
    mat.onBeforeCompile(sh);
    return sh;
  };
  const terrain = buildHighTerrain(tex);
  assert.equal(terrain.receiveShadow, true, 'the High ground takes no shadow');
  const t = compile(terrain.material);
  assert.match(t.vertexShader, /varying vec3 vWp;[\s\S]*vWp = \(modelMatrix \* vec4\(position, 1\.0\)\)\.xyz;/);
  assert.match(t.fragmentShader, /uniform sampler2D tGrass;[\s\S]*#include <color_fragment>\s*\S/);
  for (const [u, k] of [['tGrass', 'grass'], ['tGrassN', 'grassNormal'], ['tSoil', 'soil'], ['tRock', 'rock'], ['tRockN', 'rockNormal']]) assert.equal(t.uniforms[u].value, tex[k], u);
  const rock = compile(highRockMaterial(new THREE.MeshStandardMaterial({ color: 0x777777 }), tex));
  assert.match(rock.vertexShader, /vTp = mat3\(rm\) \* position/);
  assert.match(rock.fragmentShader, /uniform sampler2D tRock;[\s\S]*diffuseColor\.rgb \*= mix[\s\S]*whiteout blend/);
  assert.equal(rock.uniforms.tRock.value, tex.rock);
  assert.equal(rock.uniforms.tRockN.value, tex.rockNormal);
  terrain.geometry.dispose();
});

const { VIEW_CLEAR } = await import('../src/high/plants.js');
test('the view line test measures the distance from a tree to the segment between the camera and the station', () => {
  const along = [{ ax: 0, az: 0, bx: 10, bz: 0 }], diagonal = [{ ax: 0, az: 0, bx: 10, bz: 10 }];
  const tree = (x, z) => ({ x, z, kind: 'broadleaf', k: 0 }); // a crown of no size: only VIEW_CLEAR counts
  assert.equal(inStationView(tree(5, VIEW_CLEAR - 0.1), along), true);
  assert.equal(inStationView(tree(5, VIEW_CLEAR + 0.1), along), false);
  assert.equal(inStationView(tree(-1.2, 0.5), along), true); // behind the camera: the distance to the camera
  assert.equal(inStationView(tree(-2, 0), along), false);
  assert.equal(inStationView(tree(5, 6), diagonal), true); // 0.71 m from the line
  assert.equal(inStationView(tree(4, 7), diagonal), false); // 2.1 m from the line
  assert.equal(inStationView(tree(12, 12), diagonal), false); // past the station: 2.8 m from it
});

// Found by the mutation pass of UI.7: the figures' sizes, which no other test sees. The numbers are real ones: a Maasai man of
// about 1.8 m, a black kite with a wingspan of about 1.5 to 1.9 m, an impala ram with its horns up, a hair coat over the body.
const { buildHighShepherd, buildAntelope, buildBird, makeCoat, disposeCoats } = await import('../src/high/figures.js');
const { buildHighGrass } = await import('../src/high/plants.js');
const { heightAt } = await import('../src/world/height.js');
const boxOf = (o) => { o.updateMatrixWorld(true); return new THREE.Box3().setFromObject(o); };
test('the High shepherd stands on the ground in the place of the Standard figure, at a man\'s height', () => {
  const std = new THREE.Group();
  world.shepherd.group.children.slice(0, 8).forEach((c) => std.add(c.clone()));
  const a = boxOf(std), b = boxOf(buildHighShepherd());
  assert.ok(b.min.y > -0.01 && b.min.y < 0.02, `the feet are at ${b.min.y}`);
  assert.ok(b.max.y > 1.75 && b.max.y < 1.9, `${b.max.y} m tall`);
  assert.ok(Math.abs(b.max.y - a.max.y) < 0.05, 'not the height of the Standard figure');
  for (const k of ['x', 'z']) assert.ok(b.min[k] > a.min[k] - 0.1 && b.max[k] < a.max[k] + 0.1, `wider than the Standard figure in ${k}`);
  assert.ok(b.max.x - b.min.x > 0.6, 'the arm does not reach out to the staff');
});

test('the wildlife has the size of the real animals', () => {
  const a = boxOf(buildAntelope());
  assert.ok(a.min.y > -0.01 && a.min.y < 0.02, 'the impala does not stand on the ground');
  assert.ok(a.max.y > 1.4 && a.max.y < 2.0, `the impala is ${a.max.y} m to the horn tips`);
  assert.ok(a.max.z - a.min.z > 1.2 && a.max.z - a.min.z < 1.8, 'the impala is not the length of one');
  assert.ok(a.max.x - a.min.x < 0.45, 'the impala is too wide');
  const b = boxOf(buildBird(new THREE.MeshBasicMaterial()));
  assert.ok(b.max.x - b.min.x > 1.5 && b.max.x - b.min.x < 2.0, `a wingspan of ${b.max.x - b.min.x} m`);
  assert.ok(b.max.y - b.min.y < 0.2, 'the kite is not flat in a glide');
  assert.ok(Math.abs(b.max.x + b.min.x) < 1e-6, 'the wings are not the same');
});

test('a coat sits on the body of its sheep or goat, not beside it or far outside it', () => {
  for (const kind of ['dorper', 'redmaasai', 'goat']) {
    let animal = null;
    world.scene.traverse((o) => { if (!animal && o.userData && o.userData.kind === kind) animal = o; });
    assert.ok(animal, kind);
    const a = animal.clone(); a.position.set(0, 0, 0); a.rotation.set(0, 0, 0); a.scale.set(1, 1, 1);
    const body = boxOf(a), coat = boxOf(makeCoat(kind));
    assert.ok(coat.min.y > 0.1, `${kind}: the coat reaches the ground`);
    for (const k of ['x', 'y', 'z']) assert.ok(coat.min[k] > body.min[k] - 0.05 && coat.max[k] < body.max[k] + 0.05, `${kind}: the coat sticks out in ${k}`);
    assert.ok(coat.max.x - coat.min.x > (body.max.x - body.min.x) * 0.8, `${kind}: the coat is thinner than the body`);
  }
  disposeCoats();
});

test('the High grass: every blade on the ground, none in the river, each with its own colour', () => {
  const grass = buildHighGrass();
  assert.equal(grass.count, HIGH_GRASS);
  assert.ok(grass.instanceColor && grass.geometry.attributes.color, 'the blades have no colour of their own');
  const m = new THREE.Matrix4(), p = new THREE.Vector3(), seen = new Set();
  for (let i = 0; i < grass.count; i += 7) {
    grass.getMatrixAt(i, m); p.setFromMatrixPosition(m);
    assert.ok(Math.abs(p.y - heightAt(p.x, p.z)) < 0.3, `a blade floats at (${p.x}, ${p.z})`);
    assert.ok(nearestOnRiver({ x: p.x, z: p.z }).distance >= RIVER_HALF_WIDTH, `a blade in the river at (${p.x}, ${p.z})`);
    seen.add(grass.instanceColor.getX(i).toFixed(2));
  }
  assert.ok(seen.size > 20, 'every blade has the same colour');
  grass.geometry.dispose();
});

test('the High ground covers the Standard ground, follows the same heights everywhere, and faces up', () => {
  const ground = buildHighTerrain(fakeTextures());
  const hi = boxOf(ground), std = boxOf(world.terrain.mesh.clone());
  for (const k of ['x', 'z']) assert.ok(hi.min[k] <= std.min[k] + 0.5 && hi.max[k] >= std.max[k] - 0.5 && hi.max[k] - hi.min[k] < (std.max[k] - std.min[k]) * 1.2, `the High ground is not the size of the Standard ground in ${k}`);
  const p = ground.geometry.attributes.position, n = ground.geometry.attributes.normal;
  for (const i of [0, 1, 2, p.count >> 1, p.count - 2, p.count - 1, 12345, 98765]) {
    assert.ok(Math.abs(p.getY(i) - heightAt(p.getX(i), p.getZ(i))) < 1e-4, `vertex ${i} is off the ground`);
    assert.ok(n.getY(i) > 0.3, `vertex ${i} faces down`);
  }
  assert.equal(ground.geometry.attributes.uv, undefined, 'the photographs are placed by world position, not by uv');
  assert.equal(ground.material.roughness, 1);
  ground.geometry.dispose();
});
