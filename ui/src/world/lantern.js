import * as THREE from 'three';
import { MOUND } from './height.js';

// The lantern on the central hill is umwayi. A warm light, a small halo (drawn in code), nothing else.
export function buildLantern() {
  const g = new THREE.Group();
  g.position.y = MOUND - 0.05;
  const metal = new THREE.MeshStandardMaterial({ color: 0x2d322f, roughness: 0.55, metalness: 0.4 });
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.95, 0.3, 28), new THREE.MeshStandardMaterial({ color: 0x3b443f, roughness: 1 }));
  base.position.y = 0.15;
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 3.4, 12), metal);
  pole.position.y = 1.9;
  const lampMat = new THREE.MeshStandardMaterial({ color: 0x4a3216, emissive: 0xe0a965, emissiveIntensity: 3.2, roughness: 0.6 });
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.2, 18, 14), lampMat);
  lamp.position.set(0, 3.75, 0);
  const cap = new THREE.Mesh(new THREE.ConeGeometry(0.3, 0.22, 12), metal);
  cap.position.set(0, 4.05, 0);
  const light = new THREE.PointLight(0xffb066, 60, 30, 2);
  light.position.set(0, 3.75, 0);
  g.add(base, pole, lamp, cap, light);
  for (const o of [base, pole, cap]) o.castShadow = true;
  const halo = makeHalo();
  halo.position.set(0, 3.75, 0);
  g.add(halo);
  return { group: g, lampMat, light, halo, baseIntensity: 60, baseEmissive: 3.2 };
}

// A soft round glow, drawn on a small canvas in code.
function makeHalo() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const x = c.getContext('2d');
  const grad = x.createRadialGradient(64, 64, 2, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,196,120,0.9)');
  grad.addColorStop(0.25, 'rgba(255,170,90,0.28)');
  grad.addColorStop(1, 'rgba(255,150,70,0)');
  x.fillStyle = grad;
  x.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.4 }));
  s.scale.setScalar(3.6);
  return s;
}
