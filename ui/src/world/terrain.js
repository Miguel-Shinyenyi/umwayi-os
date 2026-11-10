import * as THREE from 'three';
import { heightAt } from './height.js';

export function buildTerrain() {
  const size = 190, seg = 190;
  const geo = new THREE.PlaneGeometry(size, size, seg, seg).rotateX(-Math.PI / 2);
  const p = geo.attributes.position;
  const col = new Float32Array(p.count * 3);
  const lawn = new THREE.Color(0x27402f), moss = new THREE.Color(0x2f4a37), far = new THREE.Color(0x1a2b22), c = new THREE.Color();
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i);
    const h = heightAt(x, z);
    p.setY(i, h);
    const r = Math.hypot(x, z);
    const n = 0.5 + 0.5 * Math.sin(x * 0.7) * Math.sin(z * 0.63 + 1.1);
    c.copy(moss).lerp(lawn, Math.min(1, (r - 8) / 24)).lerp(far, Math.min(1, Math.max(0, (h - 1) / 7)));
    c.multiplyScalar(0.9 + 0.2 * n);
    col.set([c.r, c.g, c.b], i * 3);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0 });
  const uniforms = { uContour: { value: 1 } };
  // Soft contour lines on the hills, as in the reference. None on the flat ring.
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uContour = uniforms.uContour;
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying float vH;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvH = position.y;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vH;\nuniform float uContour;')
      .replace('#include <color_fragment>', `#include <color_fragment>
      float lv = vH * 0.7;
      float dl = min(fract(lv), 1.0 - fract(lv));
      float wl = fwidth(lv) * 1.2 + 0.004;
      float line = 1.0 - smoothstep(wl, wl * 2.0, dl);
      diffuseColor.rgb += vec3(0.02, 0.04, 0.03) * line * uContour * smoothstep(0.7, 3.0, vH);`);
  };
  const mesh = new THREE.Mesh(geo, mat);
  mesh.receiveShadow = true;
  return { mesh, uniforms };
}
