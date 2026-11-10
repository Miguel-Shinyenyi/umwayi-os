// The whole scene: sky, mountains, land, grass, trees, the lantern, eleven stations on a ring, lights.
import * as THREE from 'three';
import { makeKit } from '../stations/kit.js';
import { buildStation, stationDefs, ANCHOR_HEIGHT } from '../stations/index.js';
import { ringPositions } from '../engine/layout.js';
import { lerp } from '../engine/ease.js';
import { buildSky } from './sky.js';
import { buildMountains } from './mountains.js';
import { buildTerrain } from './terrain.js';
import { buildGrass } from './grass.js';
import { buildTrees } from './trees.js';
import { buildLantern } from './lantern.js';
import { buildArcs } from './arcs.js';
import { CALM } from './palette.js';

export function buildWorld() {
  const kit = makeKit();
  const scene = new THREE.Scene();
  const fogColor = new THREE.Color(0x141d1d);
  scene.fog = new THREE.FogExp2(fogColor, 0.0085);
  scene.background = fogColor;

  const defs = stationDefs();
  const positions = ringPositions(defs.length);
  const sky = buildSky();
  const terrain = buildTerrain();
  const lantern = buildLantern();
  const arcs = buildArcs();
  scene.add(sky.group, buildMountains(), terrain.mesh, buildGrass(positions), buildTrees(), lantern.group, arcs.group);

  const stations = defs.map((def, i) => {
    const st = buildStation(def, kit);
    const pos = positions[i];
    st.pos = pos;
    st.group.position.set(pos.x, 0, pos.z);
    st.group.rotation.y = pos.angle; // the front of a station faces away from the lantern
    st.anchor = new THREE.Vector3(pos.x, ANCHOR_HEIGHT, pos.z);
    scene.add(st.group);
    return st;
  });
  const byId = Object.fromEntries(stations.map((s) => [s.id, s]));

  // light: cool moonlight and sky from above, the warm lantern, and one small warm light that lifts the selected station
  const hemi = new THREE.HemisphereLight(0x7390ac, 0x2a4033, 1.6);
  const moon = new THREE.DirectionalLight(0xc8d8f0, 2.2);
  moon.position.set(-15, 22, 13);
  moon.castShadow = true;
  moon.shadow.mapSize.set(2048, 2048);
  Object.assign(moon.shadow.camera, { left: -19, right: 19, top: 19, bottom: -19, near: 5, far: 70 });
  moon.shadow.bias = -0.0006;
  moon.shadow.normalBias = 0.04;
  const lift = new THREE.PointLight(0xffd9a8, 0, 16, 2);
  scene.add(hemi, moon, lift);

  const base = { hemi: hemi.intensity, moon: moon.intensity, lantern: lantern.baseIntensity, bloom: 0.42, exposure: 1.05 };
  const world = {
    scene, kit, stations, byId, positions, sky, terrain, lantern, arcs, lift, defs,
    base,
    // c goes 0 (normal) to 1 (Calm mode). Same hues, lower strength. Returns what the stage needs.
    look(c) {
      kit.setGlowScale(lerp(1, CALM.glow, c));
      terrain.uniforms.uContour.value = lerp(0.35, CALM.contour, c);
      hemi.intensity = base.hemi * lerp(1, 0.9, c);
      moon.intensity = base.moon * lerp(1, 0.8, c);
      lantern.light.intensity = base.lantern * lerp(1, 0.75, c);
      lantern.lampMat.emissiveIntensity = lantern.baseEmissive * lerp(1, 0.7, c);
      lantern.halo.material.opacity = lerp(0.4, 0.22, c);
      sky.uniforms.glow.value = lerp(0.45, 0.25, c);
      sky.starMat.opacity = lerp(0.5, 0.25, c);
      scene.fog.density = 0.0085 * lerp(1, CALM.fogBoost, c);
      world.calm = c;
      arcs.mat.opacity = Math.min(arcs.mat.opacity, 0.3 * (1 - c));
      return { bloom: base.bloom * lerp(1, CALM.bloom, c), exposure: base.exposure * lerp(1, CALM.exposure, c) };
    },
    calm: 0,
  };
  return world;
}
