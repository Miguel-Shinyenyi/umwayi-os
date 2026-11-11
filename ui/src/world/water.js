// Water that does not flow: dark, with the sky reflected by a Fresnel curve and a warm streak where the sky glows.
// Used for the river, the spring pool and the pools of the stream. Still water: nothing in it moves.
import * as THREE from 'three';
import { NOISE, SKY_FN } from './glsl.js';
import { SKY_UNIFORMS } from './skyuniforms.js';
import { RIVER, SAMPLES, RIVER_HALF_WIDTH } from './river.js';
import { WATER_LEVEL } from './height.js';

export const WATER_COLORS = { deep: new THREE.Color(0x0d1c24), shallow: new THREE.Color(0x24424a) };
const shared = { waterDeep: { value: WATER_COLORS.deep }, waterShallow: { value: WATER_COLORS.shallow }, waterLevel: { value: 1 } };

export function waterMaterial({ soft = true } = {}) {
  return new THREE.ShaderMaterial({
    transparent: soft, depthWrite: !soft, fog: true,
    uniforms: { ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog), ...SKY_UNIFORMS, ...shared },
    vertexShader: `attribute float edge; varying vec3 vW; varying float vEdge;
      #include <fog_pars_vertex>
      void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vEdge = edge; vec4 mvPosition = viewMatrix * w; gl_Position = projectionMatrix * mvPosition;
      #include <fog_vertex>
      }`,
    fragmentShader: `varying vec3 vW; varying float vEdge; uniform vec3 waterDeep; uniform vec3 waterShallow; uniform float waterLevel; ${SKY_FN} ${NOISE}
      #include <fog_pars_fragment>
      void main(){
        vec3 v = normalize(cameraPosition - vW);
        vec2 q = vW.xz * 0.9;
        vec3 n = normalize(vec3((fbm(q) - 0.5) * 0.18 + (fbm(q * 3.1) - 0.5) * 0.08, 1.0, (fbm(q + 7.3) - 0.5) * 0.18 + (fbm(q * 3.1 + 2.0) - 0.5) * 0.08));
        vec3 r = reflect(-v, n); r.y = abs(r.y);
        float fres = 0.03 + 0.97 * pow(1.0 - max(dot(n, v), 0.0), 5.0);
        vec3 body = mix(waterDeep, waterShallow, smoothstep(0.55, 1.0, vEdge));
        vec3 c = mix(body, skyColor(r), clamp(fres * 1.15 + 0.12, 0.0, 1.0) * waterLevel);
        float glint = pow(max(dot(r, normalize(sunDir)), 0.0), 90.0);
        c += skyGlow * glint * 0.7 * glowAmount * waterLevel;
        float a = ${soft ? 'smoothstep(1.0, 0.72, vEdge)' : '1.0'};
        gl_FragColor = vec4(c, a);
        #include <fog_fragment>
      }`,
  });
}

// the river: a ribbon along the centre line at the water level, wider than the water so the banks cover its edges
export function buildRiver() {
  const half = RIVER_HALF_WIDTH + 2.4;
  const pts = SAMPLES.filter((_, i) => i % 2 === 0);
  // three rows (bank, centre, bank): the colour goes from the middle to the banks
  const geo = new THREE.BufferGeometry();
  const P = [], E = [], I = [];
  pts.forEach((s, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let tx = b.x - a.x, tz = b.z - a.z; const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
    P.push(s.x - tz * half, WATER_LEVEL, s.z + tx * half, s.x, WATER_LEVEL, s.z, s.x + tz * half, WATER_LEVEL, s.z - tx * half);
    E.push(1, 0, 1);
    if (i < pts.length - 1) { const k = i * 3; I.push(k, k + 1, k + 3, k + 1, k + 4, k + 3, k + 1, k + 2, k + 4, k + 2, k + 5, k + 4); }
  });
  geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3));
  geo.setAttribute('edge', new THREE.Float32BufferAttribute(E, 1));
  geo.setIndex(I);
  const m = new THREE.Mesh(geo, waterMaterial({ soft: true }));
  m.renderOrder = 2;
  return m;
}

// a round pool; the rim fades so it sits in the stones around it
export function poolMesh(radius, material = waterMaterial({ soft: false })) {
  const geo = new THREE.CircleGeometry(radius, 40).rotateX(-Math.PI / 2);
  const p = geo.attributes.position, e = new Float32Array(p.count);
  for (let i = 0; i < p.count; i++) e[i] = Math.hypot(p.getX(i), p.getZ(i)) / radius;
  geo.setAttribute('edge', new THREE.BufferAttribute(e, 1));
  const m = new THREE.Mesh(geo, material);
  m.renderOrder = 2;
  m.userData.noShadow = true;
  return m;
}
export { shared as waterShared };

// one material shared by every pool
let poolMat = null;
export const sharedPoolMaterial = () => (poolMat ||= waterMaterial({ soft: false }));
