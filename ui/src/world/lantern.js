import * as THREE from 'three';
import { heightAt } from './height.js';

// The centre: a Maasai shepherd in silhouette on the knoll (12.R20.3), the staff with a lantern hanging from its hook, and a
// dog. Plain and respectful: a tall, slim standing figure, a shuka wrapped over the left shoulder and falling below the
// knee, a beaded collar only as a shape, no face detail. The lantern is the brightest point of the picture.
export function buildShepherd(makeDog) {
  const g = new THREE.Group();
  g.position.y = heightAt(0, 0);
  const skin = new THREE.MeshStandardMaterial({ color: 0x120d0b, roughness: 0.85 });
  const shuka = new THREE.MeshStandardMaterial({ color: 0x5c1610, roughness: 1 }); // the red cloth, deep in the dusk
  const shuka2 = new THREE.MeshStandardMaterial({ color: 0x3a1d3a, roughness: 1 }); // a second cloth, darker
  const beads = new THREE.MeshStandardMaterial({ color: 0x4a3a2a, roughness: 0.7 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x1d2024, roughness: 0.5, metalness: 0.6 });
  const smooth = (pts, mat, seg = 22) => new THREE.Mesh(new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(r, y)), seg), mat);
  // legs below the cloth
  const legs = [-1, 1].map((sx) => { const l = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.04, 0.5, 10), skin); l.position.set(sx * 0.08, 0.27, 0); return l; });
  // the shuka: from the chest to below the knee, a little fuller at the hem, and a second cloth over the shoulders
  const cloth = smooth([[0.0, 0.42], [0.2, 0.42], [0.21, 0.5], [0.19, 0.8], [0.17, 1.1], [0.16, 1.3], [0.12, 1.36], [0.0, 1.37]], shuka);
  cloth.scale.set(1, 1, 0.78);
  const drape = smooth([[0.0, 1.0], [0.17, 1.02], [0.19, 1.25], [0.15, 1.44], [0.07, 1.49], [0.0, 1.5]], shuka2);
  drape.scale.set(1.05, 1, 0.8);
  drape.rotation.z = 0.12; // tied over one shoulder
  // the bare right shoulder and arm, holding the staff
  const shoulder = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 8), skin);
  shoulder.position.set(0.17, 1.43, 0.0);
  const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.045, 0.5, 8), skin);
  arm.position.set(0.31, 1.3, 0.08);
  arm.rotation.z = -1.0;
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.14, 10), skin);
  neck.position.y = 1.55;
  const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.17, 0.025, 24), beads); // the beaded collar, as a shape
  collar.position.y = 1.5;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 12).scale(0.92, 1.12, 1.0), skin);
  head.position.y = 1.7;
  const cloak = new THREE.Group();
  cloak.add(cloth, drape);
  const hood = new THREE.Group();
  // the staff: a straight pole with a hook at the top
  const staff = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.03, 2.35, 8), new THREE.MeshStandardMaterial({ color: 0x1b140e, roughness: 0.9 }));
  staff.position.set(0.45, 1.175, 0.12);
  const hook = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.022, 8, 20, Math.PI * 0.95), staff.material);
  hook.position.set(0.65, 2.35, 0.12);
  hook.rotation.z = Math.PI * 0.55;
  // the lantern hangs from the end of the hook
  const lx = 0.85, ly = 2.12, lz = 0.12;
  const chain = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.2, 4), metal);
  chain.position.set(lx, ly + 0.2, lz);
  const frame = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.24, 0.16), metal);
  frame.position.set(lx, ly, lz);
  const capTop = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.09, 4).rotateY(Math.PI / 4), metal);
  capTop.position.set(lx, ly + 0.16, lz);
  const flameMat = new THREE.MeshStandardMaterial({ color: 0x5a3a14, emissive: 0xffb866, emissiveIntensity: 9, roughness: 0.5 });
  const flame = new THREE.Mesh(new THREE.SphereGeometry(0.075, 14, 10), flameMat);
  flame.position.set(lx, ly, lz);
  const light = new THREE.PointLight(0xffb066, 95, 46, 2);
  light.position.set(lx, ly, lz);
  const halo = makeHalo();
  halo.position.set(lx, ly, lz);
  g.add(...legs, cloak, shoulder, arm, neck, collar, head, hood, staff, hook, chain, frame, capTop, flame, light, halo);
  const dog = makeDog(0.95);
  dog.position.set(-0.85, 0, 0.5);
  dog.rotation.y = 0.9;
  g.add(dog);
  for (const o of [...legs, cloak, shoulder, neck, collar, head, arm, staff, hook, dog]) o.traverse?.((c) => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
  return { group: g, light, flameMat, halo, baseLight: 95, baseEmissive: 9, position: new THREE.Vector3(lx, g.position.y + ly, lz) };
}

// A soft round glow, drawn on a small canvas in code.
function makeHalo() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const x = c.getContext('2d');
  const grad = x.createRadialGradient(64, 64, 2, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,205,140,0.95)');
  grad.addColorStop(0.2, 'rgba(255,175,95,0.32)');
  grad.addColorStop(1, 'rgba(255,150,70,0)');
  x.fillStyle = grad;
  x.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.5, fog: false }));
  s.scale.setScalar(3.6);
  return s;
}
