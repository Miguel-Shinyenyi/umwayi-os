import * as THREE from 'three';
import { mulberry32 } from './random.js';

// A dusk sky: a gradient, a warm glow behind the mountains, a still moon and a few faint stars. Nothing moves.
export function buildSky() {
  const g = new THREE.Group();
  const uniforms = {
    top: { value: new THREE.Color(0x0a1015) }, mid: { value: new THREE.Color(0x182730) },
    horizon: { value: new THREE.Color(0x30383a) }, glowColor: { value: new THREE.Color(0x70502f) }, glow: { value: 0.45 },
  };
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(320, 32, 20),
    new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false, fog: false, uniforms,
      vertexShader: 'varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `varying vec3 vDir; uniform vec3 top; uniform vec3 mid; uniform vec3 horizon; uniform vec3 glowColor; uniform float glow;
      void main(){
        vec3 d = normalize(vDir); float h = d.y;
        vec3 c = mix(horizon, mid, smoothstep(0.0, 0.2, h));
        c = mix(c, top, smoothstep(0.15, 0.75, h));
        float gl = pow(max(dot(d, normalize(vec3(0.3, 0.05, -1.0))), 0.0), 5.0);
        c += glowColor * gl * glow * (1.0 - smoothstep(0.0, 0.45, h));
        c = mix(c, horizon * 0.8, smoothstep(0.0, -0.12, h));
        gl_FragColor = vec4(c, 1.0);
      }`,
    })
  );
  dome.renderOrder = -10;
  g.add(dome);
  const moon = new THREE.Mesh(new THREE.SphereGeometry(5, 24, 16), new THREE.MeshBasicMaterial({ color: 0xa9ada0, fog: false }));
  moon.position.set(-150, 118, -255);
  g.add(moon);
  const halo = new THREE.Mesh(new THREE.SphereGeometry(14, 24, 16), new THREE.MeshBasicMaterial({ color: 0x6f7f86, transparent: true, opacity: 0.07, fog: false, depthWrite: false }));
  halo.position.copy(moon.position);
  g.add(halo);
  const rnd = mulberry32(7);
  const pts = [];
  for (let i = 0; i < 110; i++) {
    const a = rnd() * Math.PI * 2, e = 0.22 + rnd() * 1.15;
    pts.push(Math.cos(a) * Math.cos(e) * 300, Math.sin(e) * 300, Math.sin(a) * Math.cos(e) * 300);
  }
  const starGeo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  const starMat = new THREE.PointsMaterial({ color: 0x8fa09a, size: 1.5, sizeAttenuation: false, transparent: true, opacity: 0.5, fog: false, depthWrite: false });
  g.add(new THREE.Points(starGeo, starMat));
  return { group: g, uniforms, starMat };
}
