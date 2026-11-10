import * as THREE from 'three';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { heightAt } from './height.js';
import { mulberry32 } from './random.js';

function blob(seed) {
  const g = new THREE.IcosahedronGeometry(1, 3);
  g.deleteAttribute('uv');
  g.deleteAttribute('normal');
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const k = 1 + 0.12 * Math.sin(x * 3.1 + seed) * Math.sin(y * 2.7 + 1) + 0.08 * Math.cos(z * 3.7 + seed * 2);
    p.setXYZ(i, x * k, y * k, z * k);
  }
  const m = mergeVertices(g, 1e-4);
  m.computeVertexNormals();
  return m;
}

// About thirty trees with round, smooth crowns, standing well outside the ring. Plain dark shapes, no lights on them.
export function buildTrees(count = 18) {
  const g = new THREE.Group();
  const rnd = mulberry32(11);
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.1, 0.2, 1.7, 8).translate(0, 0.85, 0), new THREE.MeshStandardMaterial({ color: 0x2c231d, roughness: 1 }), count);
  const crown = new THREE.InstancedMesh(blob(1.3), new THREE.MeshStandardMaterial({ roughness: 1 }), count * 2);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
  for (let i = 0; i < count; i++) {
    const a = rnd() * Math.PI * 2, r = 32 + rnd() * 18;
    const x = Math.cos(a) * r, z = -Math.abs(Math.sin(a) * r) - 2, y = heightAt(x, z) - 0.1; // behind and beside the ring, none in front of the camera
    const k = 0.8 + rnd() * 0.55;
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), rnd() * 6);
    m.compose(p.set(x, y, z), q, s.set(k, k, k));
    trunk.setMatrixAt(i, m);
    for (let j = 0; j < 2; j++) {
      const big = j === 0;
      m.compose(p.set(x + (big ? 0 : 0.25 * k), y + (big ? 2.5 : 3.7) * k, z), q, s.set((big ? 1.45 : 1.0) * k, (big ? 1.3 : 1.05) * k, (big ? 1.45 : 1.0) * k));
      crown.setMatrixAt(i * 2 + j, m);
      c.setHSL(0.37 + rnd() * 0.04, 0.3, 0.1 + rnd() * 0.04 + (big ? 0 : 0.02));
      crown.setColorAt(i * 2 + j, c);
    }
  }
  for (const o of [trunk, crown]) {
    o.castShadow = true;
    o.receiveShadow = true;
    g.add(o);
  }
  return g;
}
