// The whole scene: sky and Mount Kenya, hills, the valley with its river, plants, rocks, the shepherd with the lantern, the
// eleven stations where the layout puts them, and the light. Nothing in it moves by itself.
import * as THREE from 'three';
import { makeKit } from '../stations/kit.js';
import { buildStation, stationDefs } from '../stations/index.js';
import { createPlacement } from '../engine/placement.js';
import { lerp } from '../engine/ease.js';
import { buildSky } from './sky.js';
import { buildTerrain, buildFarHills } from './terrain.js';
import { buildRiver } from './water.js';
import { buildGrass, buildAcacia, buildCedar, buildBoulders, buildForest, buildGroundDetail } from './plants.js';
import { forestSpots } from './forest.js';
import { rapidRocks } from './water.js';
import { WATER_LEVEL } from './height.js';
import { buildShepherd } from './lantern.js';
import { buildTrails } from './trails.js';
import { SUN_DIR, FOG, CALM } from './palette.js';
import { SKY_UNIFORMS } from './skyuniforms.js';
import { waterShared } from './water.js';

export function buildWorld(motion) {
  const kit = makeKit();
  const scene = new THREE.Scene();
  const fogColor = new THREE.Color(FOG);
  scene.fog = new THREE.FogExp2(fogColor, 0.0075);
  scene.background = fogColor;

  const sky = buildSky();
  const terrain = buildTerrain();
  const hills = buildFarHills();
  hills.traverse((o) => { if (o.material) o.material.fog = false; });
  const river = buildRiver();
  const grass = buildGrass(9000);
  const acacia = buildAcacia(), cedar = buildCedar();
  const boulders = buildBoulders((r, seed, x, y, z) => kit.rock(r, seed % 2 ? kit.M.stone : kit.M.stoneDark, x, y, z, seed, 1.2, 0.8, 1), 70);
  const forest = buildForest(forestSpots());
  const ground = buildGroundDetail(kit.M.stoneDark);
  const rapids = new THREE.Group(); // the rocks the river runs over
  rapidRocks().forEach((r, i) => rapids.add(kit.rock(r.r, i % 3 ? kit.M.stoneDark : kit.M.stone, r.x, WATER_LEVEL + r.r * 0.12, r.z, i + 90, 1.25, 0.6, 1)));
  const shepherd = buildShepherd((s) => kit.dog(s));
  const trails = buildTrails();
  const restTrails = buildTrails(24, 90, { size: 0.34, spacing: 0.9 });
  for (const o of [terrain.mesh, grass]) o.receiveShadow = true;
  scene.add(sky.group, hills, terrain.mesh, river, grass, acacia, cedar, boulders, forest, rapids, ground, shepherd.group, trails.group, restTrails.group);

  const defs = stationDefs();
  const stations = defs.map((def) => {
    const st = buildStation(def, kit);
    scene.add(st.group);
    return st;
  });
  const byId = Object.fromEntries(stations.map((s) => [s.id, s]));
  const placement = createPlacement({ stations, motion });
  placement.place({});

  // light: a dim warm glow from the west behind the hills, a blue fill from the sky, the lantern, and one small warm light that lifts the focused feature
  const hemi = new THREE.HemisphereLight(0x7a96c4, 0x4a3b2c, 1.15);
  const glow = new THREE.DirectionalLight(0xffa268, 2.1);
  const sunDir = new THREE.Vector3(...SUN_DIR).normalize();
  glow.position.copy(sunDir).multiplyScalar(120);
  glow.target.position.set(0, 0, 0);
  glow.castShadow = true;
  glow.shadow.mapSize.set(2048, 2048);
  Object.assign(glow.shadow.camera, { left: -46, right: 46, top: 46, bottom: -46, near: 20, far: 260 });
  glow.shadow.bias = -0.0004;
  glow.shadow.normalBias = 0.05;
  const lift = new THREE.PointLight(0xffd7a0, 0, 14, 2);
  scene.add(hemi, glow, glow.target, lift);

  const base = { hemi: hemi.intensity, glow: glow.intensity, lantern: shepherd.baseLight, bloom: 0.5, exposure: 1.15, fog: scene.fog.density };
  const world = {
    scene, kit, stations, byId, sky, terrain, river, grass, acacia, cedar, boulders, forest, rapids, shepherd, trails, restTrails, lift, glow, hemi, placement, base, calm: 0,
    // c goes 0 (normal) to 1 (Calm mode): the same hues at lower strength. Returns what the stage needs.
    look(c) {
      kit.setGlowScale(lerp(1, CALM.glow, c));
      hemi.intensity = base.hemi * lerp(1, 0.9, c);
      glow.intensity = base.glow * lerp(1, 0.8, c);
      shepherd.light.intensity = base.lantern * lerp(1, 0.8, c);
      shepherd.flameMat.emissiveIntensity = shepherd.baseEmissive * lerp(1, 0.75, c);
      shepherd.halo.material.opacity = lerp(0.5, 0.3, c);
      SKY_UNIFORMS.glowAmount.value = lerp(1, 0.6, c);
      waterShared.waterLevel.value = lerp(1, 0.8, c);
      sky.uniforms.cloudAmount.value = lerp(1, 0.6, c);
      sky.starMat.opacity = lerp(0.45, 0.25, c);
      scene.fog.density = base.fog * lerp(1, CALM.haze, c);
      world.calm = c;
      return { bloom: base.bloom * lerp(1, CALM.bloom, c), exposure: base.exposure * lerp(1, CALM.exposure, c) };
    },
    // the detail ladder: how many plants are drawn (the stage handles pixel ratio, bloom and shadows)
    setPlants(f) {
      grass.count = Math.floor(grass.userData.total * f);
    },
  };
  return world;
}
