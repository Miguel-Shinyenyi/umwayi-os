import * as THREE from 'three';

// Thin arcs from the selected station to the stations it leans on. Drawn only while a station is selected.
export function buildArcs() {
  const group = new THREE.Group();
  const mat = new THREE.MeshBasicMaterial({ color: 0xe0a965, transparent: true, opacity: 0, depthWrite: false, fog: false });
  const meshes = [];
  group.visible = false;
  return {
    group,
    mat,
    // from and to are world positions of the anchors
    set(from, tos) {
      meshes.forEach((m) => {
        group.remove(m);
        m.geometry.dispose();
      });
      meshes.length = 0;
      for (const to of tos) {
        const mid = new THREE.Vector3().addVectors(from, to).multiplyScalar(0.5);
        mid.y += 3.2 + from.distanceTo(to) * 0.18;
        const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
        const m = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.011, 4, false), mat);
        m.renderOrder = 5;
        group.add(m);
        meshes.push(m);
      }
    },
    clear() {
      this.set(new THREE.Vector3(), []);
    },
    setOpacity(o) {
      mat.opacity = o;
      group.visible = o > 0.003;
    },
  };
}
