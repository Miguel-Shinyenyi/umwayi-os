// The High ground, rock and water (12.R16.3). The Standard look stays the base: the same colours of dry gold and green grass,
// red laterite soil, gravel and rock from the same height, slope and noise. High adds what code alone could not give up close:
// real surface detail from three CC0 photographs (site/high-assets.json), laid on the ground in two scales so the repeat does
// not show, faded out with distance so far ground never shimmers, and real relief from their normal maps. Rock gets the same
// rock photograph in three planes, so a boulder or a wall stone has grain, cracks and strata. The river gets a finer ripple.
import * as THREE from 'three';
import { heightAt } from '../world/height.js';
import { NOISE } from '../world/glsl.js';

// shared GLSL: a texture sampled in two scales and turned, so a 1k image covers the valley without a visible repeat; and the
// average colour of a texture from its last mip level, so the photograph adds detail around the scene's own colour
const DETAIL = /* glsl */ `
vec4 twoScale(sampler2D t, vec2 p, float s1, float s2) {
  vec2 q = mat2(0.8, -0.6, 0.6, 0.8) * p;
  return mix(texture(t, p * s1), texture(t, q * s2 + 0.37), 0.42);
}
vec3 twoScaleN(sampler2D t, vec2 p, float s1, float s2) {
  mat2 R = mat2(0.8, -0.6, 0.6, 0.8);
  vec3 a = texture(t, p * s1).xyz * 2.0 - 1.0;
  vec3 b = texture(t, (R * p) * s2 + 0.37).xyz * 2.0 - 1.0;
  b.xy = transpose(R) * b.xy; // the second sample is turned; turn its slope back
  return normalize(mix(a, b, 0.42));
}
float lum(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
vec3 avgOf(sampler2D t) { return textureLod(t, vec2(0.5), 12.0).rgb; }
// a normal from a tangent space normal map on the ground plane (u along +x, v along +z), in world space
vec3 groundNormal(vec3 n, vec3 m) {
  vec3 t = normalize(vec3(1.0, 0.0, 0.0) - n * n.x);
  vec3 b = normalize(vec3(0.0, 0.0, 1.0) - n * n.z);
  return normalize(t * m.x + b * m.y + n * m.z);
}
`;

export const HIGH_TERRAIN_SEG = 480;

export function buildHighTerrain(tex) {
  const size = 320, seg = HIGH_TERRAIN_SEG;
  const geo = new THREE.PlaneGeometry(size, size, seg, seg).rotateX(-Math.PI / 2);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) p.setY(i, heightAt(p.getX(i), p.getZ(i)));
  geo.computeVertexNormals();
  geo.deleteAttribute('uv');
  const mat = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0 });
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, { tGrass: { value: tex.grass }, tGrassN: { value: tex.grassNormal }, tSoil: { value: tex.soil }, tRock: { value: tex.rock }, tRockN: { value: tex.rockNormal } });
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWp;\nvarying vec3 vNo;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWp = (modelMatrix * vec4(position, 1.0)).xyz;\nvNo = normal;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        varying vec3 vWp; varying vec3 vNo;
        uniform sampler2D tGrass; uniform sampler2D tGrassN; uniform sampler2D tSoil; uniform sampler2D tRock; uniform sampler2D tRockN;
        ${NOISE}
        ${DETAIL}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec2 xz = vWp.xz;
        vec3 nG = normalize(vNo);
        float slope = 1.0 - clamp(nG.y, 0.0, 1.0);
        float dist = length(vViewPosition);
        float nearK = 1.0 - smoothstep(14.0, 85.0, dist); // the photographs show up close and fade out with distance
        float dry = clamp(fbm(xz * 0.045 + 4.0) * 1.5 - 0.15 + 0.2, 0.0, 1.0);
        float soilN = fbm(xz * 0.31 + 9.0);
        vec3 gold = vec3(0.46, 0.34, 0.15), olive = vec3(0.15, 0.2, 0.085);
        vec3 grassC = mix(olive, gold, smoothstep(0.25, 0.75, dry));
        vec3 g = twoScale(tGrass, xz, 0.55, 0.17).rgb;
        vec3 gd = g / max(avgOf(tGrass), vec3(0.02));
        gd = pow(gd, vec3(1.35)); // a little more contrast than the photograph, so the dry stalks and the soil between them read at dusk
        grassC *= mix(vec3(1.0), gd, 0.95 * nearK);
        grassC *= 0.8 + 0.4 * mix(0.5, fbm(xz * 0.7), 1.0 - nearK);
        // red laterite soil in patches and on the paths of the flock, from the soil photograph tinted to the scene
        float soilK = smoothstep(0.66, 0.85, soilN) * 0.4; // the same patches as Standard
        vec3 s = twoScale(tSoil, xz, 0.5, 0.17).rgb;
        vec3 soilC = mix(vec3(0.33, 0.18, 0.1), s * vec3(0.33, 0.18, 0.1) / max(lum(avgOf(tSoil)), 0.02), nearK * 0.9);
        grassC = mix(grassC, soilC, soilK);
        // rock on the steep ground and high up: the rock photograph, mapped on the two vertical planes so a cliff is not stretched
        vec3 w = pow(abs(nG), vec3(4.0)); w /= (w.x + w.y + w.z);
        vec3 r = texture(tRock, vWp.zy * 0.22).rgb * w.x + texture(tRock, xz * 0.22).rgb * w.y + texture(tRock, vWp.xy * 0.22).rgb * w.z;
        vec3 rockC = vec3(0.27, 0.25, 0.24) * mix(vec3(0.75 + 0.6 * fbm(xz * 0.8 + vWp.y * 0.5)), r / max(avgOf(tRock), vec3(0.02)), 0.4 + 0.5 * nearK);
        float rockMix = smoothstep(0.28, 0.5, slope + 0.1 * (fbm(xz * 0.2) - 0.5)) + smoothstep(32.0, 60.0, vWp.y) * 0.5;
        float wet = 1.0 - smoothstep(-1.4, 0.35, vWp.y);
        vec3 gravel = vec3(0.25, 0.22, 0.18) * mix(vec3(0.75 + 0.5 * fbm(xz * 0.7)), s / max(avgOf(tSoil), vec3(0.02)) * 0.85, nearK);
        vec3 col = mix(grassC, rockC, clamp(rockMix, 0.0, 1.0));
        col = mix(col, gravel, wet * 0.9);
        col = mix(col, vec3(0.12, 0.15, 0.22), smoothstep(70.0, 300.0, dist) * 0.8); // the distance goes blue
        diffuseColor.rgb = col;
        float hiRock = clamp(rockMix, 0.0, 1.0);`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        {
          float nk = 1.0 - smoothstep(10.0, 60.0, length(vViewPosition));
          vec3 mg = twoScaleN(tGrassN, vWp.xz, 0.42, 0.13);
          vec3 mr = texture(tRockN, vWp.xz * 0.22).xyz * 2.0 - 1.0;
          vec3 m = normalize(mix(mg, mr, hiRock));
          m.xy *= 1.4 * nk;
          vec3 nW = groundNormal(normalize(vNo), normalize(m));
          normal = normalize(mat3(viewMatrix) * nW);
        }`);
  };
  mat.customProgramCacheKey = () => 'high-terrain';
  const mesh = new THREE.Mesh(geo, mat);
  mesh.receiveShadow = true;
  mesh.name = 'high:terrain';
  return mesh;
}

// A rock material: the colour of the stone it replaces, with the rock photograph in three planes in the stone's own frame (so a
// stone that moves in a pose keeps its grain) and its normal map. One material per stone colour.
export function highRockMaterial(base, tex) {
  const mat = new THREE.MeshStandardMaterial({ color: base.color.clone(), roughness: 0.95, metalness: 0 });
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, { tRock: { value: tex.rock }, tRockN: { value: tex.rockNormal } });
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vTp;\nvarying vec3 vTn;')
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        #ifdef USE_INSTANCING
          mat4 rm = modelMatrix * instanceMatrix;
        #else
          mat4 rm = modelMatrix;
        #endif
        vTp = mat3(rm) * position + vec3(fract(rm[3].x * 0.137) * 9.0, fract(rm[3].z * 0.173) * 9.0, fract(rm[3].y * 0.21) * 9.0);
        vTn = normalize(mat3(rm) * normal);`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying vec3 vTp;\nvarying vec3 vTn;\nuniform sampler2D tRock;\nuniform sampler2D tRockN;\n${DETAIL}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec3 tw = pow(abs(vTn), vec3(4.0)); tw /= (tw.x + tw.y + tw.z);
        const float rs = 0.9;
        vec3 rc = texture(tRock, vTp.zy * rs).rgb * tw.x + texture(tRock, vTp.xz * rs).rgb * tw.y + texture(tRock, vTp.xy * rs).rgb * tw.z;
        diffuseColor.rgb *= mix(vec3(1.0), rc / max(avgOf(tRock), vec3(0.02)), 0.9);`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        {
          // whiteout blend of the three planes, in world space
          vec3 n = normalize(vTn);
          vec3 a = texture(tRockN, vTp.zy * rs).xyz * 2.0 - 1.0;
          vec3 b = texture(tRockN, vTp.xz * rs).xyz * 2.0 - 1.0;
          vec3 c = texture(tRockN, vTp.xy * rs).xyz * 2.0 - 1.0;
          a = vec3(a.xy + n.zy, abs(a.z) * n.x);
          b = vec3(b.xy + n.xz, abs(b.z) * n.y);
          c = vec3(c.xy + n.xy, abs(c.z) * n.z);
          vec3 nW = normalize(a.zyx * tw.x + b.xzy * tw.y + c.xyz * tw.z);
          float nk = 1.0 - smoothstep(12.0, 70.0, length(vViewPosition));
          normal = normalize(mix(normal, mat3(viewMatrix) * nW, nk));
        }`);
  };
  mat.customProgramCacheKey = () => 'high-rock';
  return mat;
}

// The river with a finer ripple: a third, small layer of moving noise and a sharper glint on top of the Standard water. It keeps
// the Standard uniforms (the same objects), so the flow clock, the Calm look and the rocks of the rapids drive it as before.
// Throws if the Standard water shader is not the one this was written for, so High falls back to Standard.
export function highWaterMaterial(standard) {
  const from = 'vec2 slope = vec2(n1 * 0.2 + n2 * 0.1, m1 * 0.2 + m2 * 0.1);';
  const glint = 'float glint = pow(max(dot(r, normalize(sunDir)), 0.0), 60.0);';
  if (!standard.fragmentShader.includes(from) || !standard.fragmentShader.includes(glint)) throw new Error('the Standard water shader changed');
  const fragmentShader = standard.fragmentShader
    .replace(from, `${from}
        vec2 q3 = flows > 0.5 ? vec2((vAlong - flowTime * 2.1 * flows) * 3.1, across * 5.5 + 9.0) : vW.xz * 6.0;
        slope += vec2(fbm(q3) - 0.5, fbm(q3 + 4.1) - 0.5) * 0.06 * (1.0 - smoothstep(10.0, 60.0, length(cameraPosition - vW)));`)
    .replace(glint, `${glint}
        glint += pow(max(dot(r, normalize(sunDir)), 0.0), 380.0) * 2.2;`);
  const mat = new THREE.ShaderMaterial({
    transparent: standard.transparent, depthWrite: standard.depthWrite, fog: standard.fog,
    uniforms: standard.uniforms, vertexShader: standard.vertexShader, fragmentShader,
  });
  mat.name = 'high:water';
  return mat;
}
