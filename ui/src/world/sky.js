// The sky just after sunset: a deep blue top, a warm glow low in the west, soft cloud made once from noise (it never moves),
// a few faint stars, and Mount Kenya on the horizon, seen through haze with snow that holds the last light.
import * as THREE from 'three';
import { NOISE, SKY_FN } from './glsl.js';
import { SKY_UNIFORMS } from './skyuniforms.js';
import { mulberry32 } from './random.js';
import { ridged, fbm } from './noise.js';

export function buildSky() {
  const g = new THREE.Group();
  const uniforms = { ...SKY_UNIFORMS, cloudAmount: { value: 1 } };
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(800, 40, 24),
    new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false, fog: false, uniforms,
      vertexShader: 'varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `varying vec3 vDir; uniform float cloudAmount; ${SKY_FN} ${NOISE}
      void main(){
        vec3 d = normalize(vDir);
        vec3 c = skyColor(d);
        // soft cloud on a high plane: dark blue bodies, warm undersides towards the sunset
        vec2 q = d.xz / (d.y + 0.28) * 0.9;
        float cl = fbm(q * 1.15 + 3.0) * 0.75 + fbm(q * 3.1) * 0.25;
        float body = smoothstep(0.50, 0.72, cl) * smoothstep(0.02, 0.2, d.y) * (1.0 - smoothstep(0.7, 1.0, d.y));
        float toSun = max(dot(d, normalize(sunDir)), 0.0);
        vec3 lit = mix(skyMid * 0.9, skyGlow * 0.5, pow(toSun, 2.0) * smoothstep(0.62, 0.5, cl + 0.12));
        c = mix(c, lit, body * 0.7 * cloudAmount);
        gl_FragColor = vec4(c, 1.0);
      }`,
    })
  );
  dome.renderOrder = -10;
  g.add(dome);
  const rnd = mulberry32(7);
  const pts = [];
  for (let i = 0; i < 90; i++) {
    const a = rnd() * Math.PI * 2, e = 0.3 + rnd() * 1.1;
    pts.push(Math.cos(a) * Math.cos(e) * 700, Math.sin(e) * 700, Math.sin(a) * Math.cos(e) * 700);
  }
  const starMat = new THREE.PointsMaterial({ color: 0x9fb0c0, size: 1.4, sizeAttenuation: false, transparent: true, opacity: 0.45, fog: false, depthWrite: false });
  g.add(new THREE.Points(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pts, 3)), starMat));
  g.add(buildMountain());
  return { group: g, uniforms, starMat };
}

// Mount Kenya: an eroded old volcano whose two highest points, Batian and Nelion, are sharp rock. A displaced cone with
// two summits, a lower shoulder, rock below and snow above. The scene's haze softens it.
function buildMountain() {
  const N = 150, R = 190, H = 62;
  const geo = new THREE.PlaneGeometry(R * 2, R * 2, N, N).rotateX(-Math.PI / 2);
  const p = geo.attributes.position;
  const col = new Float32Array(p.count * 3);
  const rock = new THREE.Color(0x5a5f78), snow = new THREE.Color(0xe6d3d8), low = new THREE.Color(0x44536a), haze = new THREE.Color(0x56627c), c = new THREE.Color();
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i);
    const r = Math.hypot(x, z) / R;
    const a1 = Math.hypot(x + 9, z - 3) / 38, a2 = Math.hypot(x - 11, z + 5) / 30; // the two summits
    const peaks = Math.max(0, 1 - a1) ** 1.3 * 1.0 + Math.max(0, 1 - a2) ** 1.3 * 0.93;
    const body = Math.max(0, 1 - r) ** 1.7 * 0.55;
    const rough = ridged(x * 0.045 + 2, z * 0.045 - 3, 3) * 0.28 * Math.max(0, 1 - r) + fbm(x * 0.12, z * 0.12, 3) * 0.1 * Math.max(0, 1 - r);
    const h = (peaks * 0.62 + body + rough) * H;
    p.setY(i, h);
    const t = Math.min(1, Math.max(0, (h / H - 0.36) / 0.3));
    c.copy(low).lerp(rock, Math.min(1, h / (H * 0.4))).lerp(snow, t * (0.65 + 0.35 * fbm(x * 0.2, z * 0.2, 2)));
    c.lerp(haze, 0.3); // seen through a long stretch of air
    col.set([c.r, c.g, c.b], i * 3);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, emissive: 0x5a4452, emissiveIntensity: 0.38 });
  mat.fog = false;
  const m = new THREE.Mesh(geo, mat);
  m.position.set(95, -2, -400);
  m.rotation.y = 0.5;
  m.scale.set(1.25, 0.62, 1.25); // about 6 degrees above the horizon from the valley
  return m;
}
