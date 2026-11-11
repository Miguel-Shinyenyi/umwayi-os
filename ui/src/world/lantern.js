import * as THREE from 'three';
import { heightAt } from './height.js';

// The centre: a plain silhouette shepherd on the knoll, a staff with a hook, a lantern hanging from it, and a dog.
// The lantern is the brightest point of the picture and the only strong light. makeDog gives the dog the sheepdog shape.
export function buildShepherd(makeDog) {
  const g = new THREE.Group();
  g.position.y = heightAt(0, 0);
  const dark = new THREE.MeshStandardMaterial({ color: 0x07080b, roughness: 1 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x1d2024, roughness: 0.5, metalness: 0.6 });
  // a plain silhouette: a cloak, a head, a hood
  const cloak = new THREE.Mesh(new THREE.LatheGeometry([[0.0, 0], [0.38, 0], [0.33, 0.45], [0.25, 1.05], [0.2, 1.36], [0.13, 1.5], [0.0, 1.52]].map(([r, y]) => new THREE.Vector2(r, y)), 20), dark);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 14, 10), dark);
  head.position.y = 1.65;
  const hood = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.2, 12), dark);
  hood.position.set(0, 1.74, -0.02);
  const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.62, 8), dark);
  arm.position.set(0.28, 1.28, 0.08);
  arm.rotation.z = -0.9;
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
  g.add(cloak, head, hood, arm, staff, hook, chain, frame, capTop, flame, light, halo);
  const dog = makeDog(0.95);
  dog.position.set(-0.85, 0, 0.5);
  dog.rotation.y = 0.9;
  g.add(dog);
  for (const o of [cloak, head, hood, arm, staff, hook, dog]) o.traverse?.((c) => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
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
