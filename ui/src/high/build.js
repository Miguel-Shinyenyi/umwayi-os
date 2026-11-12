// The High scene (12.R16.3): built on top of a Standard world that is already drawn. applyHigh hides the Standard parts it
// replaces, adds the High ones and returns remove(), which puts the Standard world back exactly as it was. If anything throws
// while High is being built, what was done is undone before the error goes on, so the caller is left with Standard.
// The wildlife moves on the flow clock of the water (waterShared.flowTime, set by the scene before each draw): there is no clock
// here, so it stops whenever the water stops.
import * as THREE from 'three';
import { waterShared } from '../world/water.js';
import { buildHighTerrain, highRockMaterial, highWaterMaterial } from './ground.js';
import { buildHighGrass, buildHighForest, buildHighAcaciaCrowns, buildHighCedars, HIGH_GRASS } from './plants.js';
import { buildHighShepherd, makeCoat, disposeCoats, buildBird, buildAntelope } from './figures.js';
import { BIRDS, birdPose, antelopePose, ANTELOPE_SCALE } from './wildlife.js';

export { HIGH_GRASS };
const SHEPHERD_FIGURE = 8; // the first eight children of the Standard shepherd are the figure (legs, cloth, arm, neck, collar, head)

// textures: { grass, grassNormal, soil, rock, rockNormal } (assets.js)
export function applyHigh(world, textures) {
  const undo = [], made = [];
  const add = (parent, obj) => { parent.add(obj); made.push(obj); undo.push(() => parent.remove(obj)); return obj; };
  const hide = (obj) => { const was = obj.visible; obj.visible = false; undo.push(() => { obj.visible = was; }); };
  const setMat = (mesh, mat) => { const was = mesh.material; mesh.material = mat; undo.push(() => { mesh.material = was; }); };
  const undoAll = () => { while (undo.length) undo.pop()(); };
  const { scene } = world;
  try {
    // the rocks first, so nothing High is touched: every stone of the scene and the stations gets the rock photograph
    const rockMats = new Map([[world.kit.M.stone, highRockMaterial(world.kit.M.stone, textures)], [world.kit.M.stoneDark, highRockMaterial(world.kit.M.stoneDark, textures)]]);
    const stones = [];
    scene.traverse((o) => { if (o.isMesh && rockMats.has(o.material)) stones.push(o); });
    for (const o of stones) setMat(o, rockMats.get(o.material));
    made.push(...rockMats.values());

    // the ground, the grass, the forest, the acacias and the cedars
    hide(world.terrain.mesh);
    add(scene, buildHighTerrain(textures));
    hide(world.grass);
    const grass = add(scene, buildHighGrass());
    const setPlants = world.setPlants;
    world.setPlants = (f) => { setPlants(f); grass.count = Math.floor(grass.userData.total * f); };
    undo.push(() => { world.setPlants = setPlants; });
    hide(world.forest);
    add(scene, buildHighForest());
    const crown = world.acacia.children.find((o) => o.isInstancedMesh && o.geometry.type !== 'CylinderGeometry');
    hide(crown);
    add(scene, buildHighAcaciaCrowns(crown));
    const cedar = world.cedar.children.find((o) => o.isInstancedMesh && o.geometry.type !== 'CylinderGeometry');
    hide(cedar);
    add(scene, buildHighCedars(cedar));

    // the river: a finer ripple on the same water
    const water = highWaterMaterial(world.river.material);
    setMat(world.river, water);
    made.push(water);

    // the shepherd: a finer figure in place of the Standard one; the staff, the lantern, its light and its glow stay
    world.shepherd.group.children.slice(0, SHEPHERD_FIGURE).forEach(hide);
    add(world.shepherd.group, buildHighShepherd());

    // a short coat on every sheep and goat, the stations' flocks included
    const animals = [];
    scene.traverse((o) => { if (o.userData && o.userData.kind && !o.name) animals.push(o); });
    for (const a of animals) { const coat = makeCoat(a.userData.kind); if (coat) add(a, coat); }

    // the wildlife, at the edge
    const birdMat = new THREE.MeshStandardMaterial({ color: 0x1b1612, roughness: 0.9, side: THREE.DoubleSide });
    made.push(birdMat);
    const birds = new THREE.Group();
    birds.name = 'high:birds';
    for (let i = 0; i < BIRDS.length; i++) birds.add(buildBird(birdMat));
    add(scene, birds);
    const antelope = add(scene, buildAntelope());
    antelope.scale.setScalar(ANTELOPE_SCALE); // larger than life so that it shows at 130 m (wildlife.js)
    const step = () => {
      const t = waterShared.flowTime.value;
      birds.children.forEach((b, i) => {
        const p = birdPose(i, t);
        b.position.set(p.x, p.y, p.z);
        b.rotation.set(0, p.heading, p.bank, 'YXZ');
        for (const w of b.userData.wings) w.rotation.z = w.userData.side * p.wing;
      });
      const a = antelopePose(t);
      antelope.position.set(a.x, a.y, a.z);
      antelope.rotation.y = a.heading;
      for (const leg of antelope.userData.legs) {
        const phase = a.stride + (leg.userData.front ? 0 : Math.PI) + (leg.userData.side > 0 ? Math.PI : 0);
        leg.rotation.x = Math.sin(phase) * 0.38 * (a.stride === 0 ? 0 : 1);
      }
      antelope.userData.neck.rotation.x = a.graze * 1.15;
      birds.updateMatrixWorld(true);
      antelope.updateMatrixWorld(true);
    };
    birds.onBeforeRender = step;
    antelope.onBeforeRender = step;
    const before = scene.onBeforeRender;
    scene.onBeforeRender = function (...args) { step(); return before.apply(this, args); };
    undo.push(() => { scene.onBeforeRender = before; });
    step();
  } catch (e) {
    undoAll();
    dispose(made);
    throw e;
  }
  let removed = false;
  return {
    remove() {
      if (removed) return;
      removed = true;
      undoAll();
      dispose(made);
    },
  };
}

function dispose(objects) {
  for (const o of objects) {
    if (o.isMaterial) { o.dispose(); continue; }
    o.traverse?.((c) => {
      if (c.isMesh) {
        if (c.name !== 'high:coat') c.geometry.dispose();
        for (const m of [].concat(c.material)) if (c.name !== 'high:coat') m.dispose();
      }
    });
  }
  disposeCoats();
}
