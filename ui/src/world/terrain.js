import * as THREE from 'three';
import { heightAt } from './height.js';
import { NOISE, BUMP } from './glsl.js';

// The ground: the height function as a mesh, and a shader that blends dry gold grass, green grass, red soil, gravel and
// rock by height, slope, wetness and noise, with a fine bump from noise (no texture).
export function buildTerrain() {
  const size = 320, seg = 256;
  const geo = new THREE.PlaneGeometry(size, size, seg, seg).rotateX(-Math.PI / 2);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) p.setY(i, heightAt(p.getX(i), p.getZ(i)));
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0 });
  const uniforms = { uDry: { value: 1 } };
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uDry = uniforms.uDry;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWp;\nvarying vec3 vNo;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWp = (modelMatrix * vec4(position, 1.0)).xyz;\nvNo = normal;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying vec3 vWp;\nvarying vec3 vNo;\nuniform float uDry;\n${NOISE}\n${BUMP}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec2 xz = vWp.xz;
        float slope = 1.0 - clamp(normalize(vNo).y, 0.0, 1.0);
        float dry = clamp(fbm(xz * 0.045 + 4.0) * 1.5 - 0.15 + 0.2 * uDry, 0.0, 1.0);
        float dist = length(vViewPosition);
        float nearK = 1.0 - smoothstep(10.0, 60.0, dist); // fine grain only up close, so the distance does not shimmer
        float fine = mix(0.5, fbm(xz * 0.7), nearK);
        float soilN = fbm(xz * 0.31 + 9.0);
        vec3 gold = vec3(0.46, 0.34, 0.15) * (0.8 + 0.5 * fine);
        vec3 olive = vec3(0.15, 0.2, 0.085) * (0.8 + 0.5 * fine);
        vec3 grassC = mix(olive, gold, smoothstep(0.25, 0.75, dry));
        grassC = mix(grassC, vec3(0.36, 0.19, 0.11) * (0.7 + 0.6 * fine), smoothstep(0.66, 0.85, soilN) * 0.4); // red laterite soil
        vec3 rockC = vec3(0.27, 0.25, 0.24) * (0.7 + 0.8 * fbm(xz * 0.8 + vWp.y * 0.5));
        vec3 gravel = vec3(0.25, 0.22, 0.18) * (0.7 + 0.7 * fine);
        float rockMix = smoothstep(0.28, 0.5, slope + 0.1 * (fbm(xz * 0.2) - 0.5)) + smoothstep(32.0, 60.0, vWp.y) * 0.5;
        float wet = 1.0 - smoothstep(-1.4, 0.35, vWp.y);
        vec3 col = mix(grassC, rockC, clamp(rockMix, 0.0, 1.0));
        col = mix(col, gravel, wet * 0.9);
        col = mix(col, vec3(0.12, 0.15, 0.22), smoothstep(70.0, 300.0, dist) * 0.8); // the distance goes blue
        diffuseColor.rgb = col;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        float nk = 1.0 - smoothstep(8.0, 45.0, length(vViewPosition));
        float bh = fbm(xz * 1.9);
        normal = bumpNormal(normal, -vViewPosition, bh, 0.28 * nk);`);
  };
  const mesh = new THREE.Mesh(geo, mat);
  mesh.receiveShadow = true;
  return { mesh, uniforms };
}

// Hills far behind the valley, so the horizon has more than one ridge between the valley and the mountain.
export function buildFarHills() {
  const g = new THREE.Group();
  const layers = [{ r: 250, h: 38, c: 0x3a4660, s: 1 }, { r: 320, h: 52, c: 0x4a5878, s: 2 }];
  for (const L of layers) {
    const n = 260, pos = [], idx = [];
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      const e = 0.5 + 0.3 * Math.sin(a * 3 + L.s) + 0.2 * Math.sin(a * 7 + L.s * 2) + 0.1 * Math.sin(a * 17 + L.s * 3);
      const hh = L.h * Math.max(0.2, e);
      pos.push(Math.sin(a) * L.r, -10, Math.cos(a) * L.r, Math.sin(a) * L.r, hh, Math.cos(a) * L.r);
      if (i < n) idx.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
    }
    const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setIndex(idx);
    g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: L.c, side: THREE.DoubleSide, fog: true })));
  }
  return g;
}
