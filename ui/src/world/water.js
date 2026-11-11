// Water. The river flows (the owner, Nov 11 round 2): two layers of noise move down the river at different speeds for the
// moving highlights, and foam gathers at the rocks of the rapids and trails downstream from them. The time comes from the flow
// clock (engine/flow.js), which stops with reduced motion, in Calm mode, off screen and hidden; then the water is a still picture.
// The pools have no flow direction, so they stay still. Nothing in the water flashes: foam and highlights drift.
import * as THREE from 'three';
import { NOISE, SKY_FN } from './glsl.js';
import { SKY_UNIFORMS } from './skyuniforms.js';
import { SAMPLES, RIVER_HALF_WIDTH, riverPoint } from './river.js';
import { reachable } from './layout.js';
import { WATER_LEVEL } from './height.js';
import { mulberry32 } from './random.js';

export const WATER_COLORS = { deep: new THREE.Color(0x10222b), shallow: new THREE.Color(0x2c4d55) };
export const FLOW_SPEED = 0.9; // metres a second along the river
export const RAPIDS_AT = [2.6, 4.4, 5.5, 7.3, 9.2, 10.6]; // where on the river (u) the rapids are
const MAX_ROCKS = 40;

// the rocks of the rapids: a broken line across the river at each rapid, a few gaps for the water. Pure and seeded.
export function rapidRocks() {
  const rnd = mulberry32(77), out = [], keep = reachable();
  for (const u of RAPIDS_AT) {
    const c = riverPoint(u), a = riverPoint(u - 0.04), b = riverPoint(u + 0.04);
    let tx = b.x - a.x, tz = b.z - a.z; const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
    const n = 6 + Math.floor(rnd() * 2);
    for (let i = 0; i < n && out.length < MAX_ROCKS; i++) {
      if (rnd() < 0.22) continue; // a gap
      const across = (i / (n - 1) - 0.5) * RIVER_HALF_WIDTH * 1.8 + (rnd() - 0.5) * 0.5;
      const along = (rnd() - 0.5) * 1.6;
      const x = c.x - tz * across + tx * along, z = c.z + tx * across + tz * along, r = 0.28 + rnd() * 0.42;
      if (keep.some((k) => Math.hypot(x - k.x, z - k.z) < k.r + r)) continue; // clear of every place a river station can stand
      out.push({ x, z, r });
    }
  }
  return out;
}

const ROCKS = rapidRocks();
const shared = {
  waterDeep: { value: WATER_COLORS.deep }, waterShallow: { value: WATER_COLORS.shallow }, waterLevel: { value: 1 }, flowTime: { value: 0 },
  rocks: { value: Array.from({ length: MAX_ROCKS }, (_, i) => (ROCKS[i] ? new THREE.Vector3(ROCKS[i].x, ROCKS[i].z, ROCKS[i].r) : new THREE.Vector3(1e4, 1e4, 0))) },
};

export function waterMaterial({ soft = true } = {}) {
  return new THREE.ShaderMaterial({
    transparent: soft, depthWrite: !soft, fog: true,
    uniforms: { ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog), ...SKY_UNIFORMS, ...shared },
    vertexShader: `attribute float edge; attribute float along; attribute vec2 tang; varying vec3 vW; varying float vEdge; varying float vAlong; varying vec2 vT;
      #include <fog_pars_vertex>
      void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vEdge = edge; vAlong = along; vT = tang; vec4 mvPosition = viewMatrix * w; gl_Position = projectionMatrix * mvPosition;
      #include <fog_vertex>
      }`,
    fragmentShader: `varying vec3 vW; varying float vEdge; varying float vAlong; varying vec2 vT;
      uniform vec3 waterDeep; uniform vec3 waterShallow; uniform float waterLevel; uniform float flowTime; uniform vec3 rocks[${MAX_ROCKS}];
      ${SKY_FN} ${NOISE}
      #include <fog_pars_fragment>
      void main(){
        vec3 v = normalize(cameraPosition - vW);
        float flows = step(0.01, length(vT));
        vec2 t = flows > 0.5 ? normalize(vT) : vec2(1.0, 0.0);
        vec2 nr = vec2(-t.y, t.x);
        float across = dot(vW.xz, nr);
        // two layers moving down the river at different speeds, stretched along it
        vec2 q1 = vec2((vAlong - flowTime * ${FLOW_SPEED.toFixed(2)} * flows) * 0.55, across * 1.3);
        vec2 q2 = vec2((vAlong - flowTime * ${(FLOW_SPEED * 1.7).toFixed(2)} * flows) * 1.3, across * 2.6 + 5.0);
        vec2 qs = flows > 0.5 ? q1 : vW.xz * 0.9;
        float n1 = fbm(qs) - 0.5, n2 = fbm(flows > 0.5 ? q2 : vW.xz * 2.8) - 0.5;
        float m1 = fbm(qs + 7.3) - 0.5, m2 = fbm((flows > 0.5 ? q2 : vW.xz * 2.8) + 2.0) - 0.5;
        vec2 slope = vec2(n1 * 0.2 + n2 * 0.1, m1 * 0.2 + m2 * 0.1);
        // foam: a ring at each rock and a tail downstream, broken up by the moving noise
        float foam = 0.0;
        for (int i = 0; i < ${MAX_ROCKS}; i++) {
          vec2 d = vW.xz - rocks[i].xy;
          float r = rocks[i].z;
          float dl = length(d);
          if (dl > r + 6.0) continue;
          float ring = exp(-pow(max(dl - r, 0.0) / 0.32, 2.0));
          float a = dot(d, t), c = dot(d, nr);
          float tail = a > 0.0 ? exp(-a / 2.6) * exp(-(c * c) / (r * r * 1.6 + 0.05)) : 0.0;
          foam += ring + 0.85 * tail;
        }
        foam *= flows;
        float broken = fbm(vec2((vAlong - flowTime * ${(FLOW_SPEED * 1.3).toFixed(2)}) * 1.6, across * 3.4) + 3.0);
        foam = smoothstep(0.32, 0.95, foam * (0.45 + 0.75 * broken));
        slope *= 1.0 + foam * 1.5;
        vec3 n = normalize(vec3(slope.x, 1.0, slope.y));
        vec3 r = reflect(-v, n); r.y = abs(r.y);
        float fres = 0.04 + 0.96 * pow(1.0 - max(dot(n, v), 0.0), 5.0);
        vec3 body = mix(waterDeep, waterShallow, smoothstep(0.55, 1.0, vEdge));
        vec3 c = mix(body, skyColor(r), clamp(fres * 1.2 + 0.16, 0.0, 1.0) * waterLevel);
        float glint = pow(max(dot(r, normalize(sunDir)), 0.0), 60.0);
        c += skyGlow * glint * 0.8 * glowAmount * waterLevel;
        vec3 foamC = mix(vec3(0.34, 0.36, 0.38), skyGlow * 0.42 + vec3(0.18), 0.35) * waterLevel;
        c = mix(c, foamC, foam * 0.8);
        float a = ${soft ? 'smoothstep(1.0, 0.72, vEdge)' : '1.0'};
        gl_FragColor = vec4(c, a);
        #include <fog_fragment>
      }`,
  });
}

// the river: a ribbon along the centre line at the water level, wider than the water so the banks cover its edges.
// along: metres down the river; tang: the river's direction (the foam trails and the flow follow it)
export function buildRiver() {
  const half = RIVER_HALF_WIDTH + 2.4;
  const pts = SAMPLES.filter((_, i) => i % 2 === 0);
  const geo = new THREE.BufferGeometry();
  const P = [], E = [], A = [], T = [], I = [];
  let run = 0;
  pts.forEach((s, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let tx = b.x - a.x, tz = b.z - a.z; const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
    if (i) run += Math.hypot(s.x - pts[i - 1].x, s.z - pts[i - 1].z);
    P.push(s.x - tz * half, WATER_LEVEL, s.z + tx * half, s.x, WATER_LEVEL, s.z, s.x + tz * half, WATER_LEVEL, s.z - tx * half);
    E.push(1, 0, 1);
    A.push(run, run, run);
    T.push(tx, tz, tx, tz, tx, tz);
    // wound so the surface faces up (the earlier winding faced down, so the river was culled and only its bed showed)
    if (i < pts.length - 1) { const k = i * 3; I.push(k, k + 3, k + 1, k + 1, k + 3, k + 4, k + 1, k + 4, k + 2, k + 2, k + 4, k + 5); }
  });
  geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3));
  geo.setAttribute('edge', new THREE.Float32BufferAttribute(E, 1));
  geo.setAttribute('along', new THREE.Float32BufferAttribute(A, 1));
  geo.setAttribute('tang', new THREE.Float32BufferAttribute(T, 2));
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
  geo.setAttribute('along', new THREE.BufferAttribute(new Float32Array(p.count), 1));
  geo.setAttribute('tang', new THREE.BufferAttribute(new Float32Array(p.count * 2), 2)); // no direction: a pool does not flow
  const m = new THREE.Mesh(geo, material);
  m.renderOrder = 2;
  m.userData.noShadow = true;
  return m;
}
export { shared as waterShared };

// one material shared by every pool
let poolMat = null;
export const sharedPoolMaterial = () => (poolMat ||= waterMaterial({ soft: false }));
