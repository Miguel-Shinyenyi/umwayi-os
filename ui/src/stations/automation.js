import * as THREE from 'three';
// Automation: a sundial under an arc. The sun crosses and the shadow turns. Studs on the rim count the schedules:
// a tall stud for each entry, a lit one for each that is installed, a bright one for each that is enabled.
import { TOKENS } from '../world/palette.js';
import { lerp } from '../engine/ease.js';

export const poses = [{ t: 0.12 }, { t: 0.5 }, { t: 0.88 }];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.add(kit.cyl(0.98, 1.05, 0.16, M.stone, 0, 0.08, 0, 40));
  g.add(kit.cyl(0.88, 0.88, 0.03, M.stoneDark, 0, 0.17, 0, 40));
  const studs = [];
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    const x = Math.sin(a) * 0.76, z = -Math.cos(a) * 0.76;
    const stud = kit.box(0.06, 0.1, 0.06, M.stone, x, 0.24, z);
    stud.rotation.y = -a;
    g.add(stud);
    const lamp = kit.glow(TOKENS.amber, 1.7, 1);
    const cap = kit.ball(0.04, lamp, x, 0.31, z, 10, 8);
    cap.visible = false;
    g.add(cap);
    studs.push({ stud, cap, lamp });
  }
  const shape = new THREE.Shape();
  shape.moveTo(0, 0); shape.lineTo(0.5, 0); shape.lineTo(0, 0.5); shape.lineTo(0, 0);
  const gnomon = kit.mesh(new THREE.ExtrudeGeometry(shape, { depth: 0.05, bevelEnabled: false }), M.metal, 0, 0.18, 0);
  gnomon.rotation.y = -Math.PI / 2;
  gnomon.position.z = 0.025;
  g.add(gnomon);
  const shadowMat = new THREE.MeshBasicMaterial({ color: 0x090c0b, transparent: true, opacity: 0.55, depthWrite: false });
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 0.07).rotateX(-Math.PI / 2), shadowMat);
  shadow.position.y = 0.19;
  g.add(shadow);
  const R = 1.75, cy = 0.35;
  const arc = new THREE.Mesh(new THREE.TorusGeometry(R, 0.018, 6, 72, Math.PI), M.metal);
  arc.position.set(0, cy, -0.4);
  g.add(arc);
  const sun = kit.ball(0.14, kit.glow(TOKENS.amber, 2.6), 0, 0, -0.4, 16, 12);
  g.add(sun);
  return {
    group: g,
    apply(p) {
      const th = Math.PI * (1 - p.t);
      sun.position.set(Math.cos(th) * R, cy + Math.sin(th) * R, -0.4);
      const high = Math.sin(Math.PI * p.t);
      const sx = -Math.cos(Math.PI * p.t), sz = -0.15 - 0.85 * high; // the sun's direction on the ground
      const len = Math.min(0.8, lerp(1.0, 0.3, high));
      const d = new THREE.Vector2(-sx, -sz).normalize();
      shadow.scale.x = len;
      shadow.rotation.y = Math.atan2(-d.y, d.x);
      shadow.position.x = d.x * len * 0.5;
      shadow.position.z = d.y * len * 0.5;
    },
    // counts: { schedule: { entries, installed, enabled } }
    setCounts(c) {
      const s = c && c.schedule ? c.schedule : { entries: 0, installed: 0, enabled: 0 };
      studs.forEach((u, i) => {
        u.stud.scale.y = i < s.entries ? 2.2 : 1;
        u.stud.position.y = i < s.entries ? 0.29 : 0.24;
        u.cap.position.y = i < s.entries ? 0.42 : 0.31;
        u.cap.visible = i < s.installed;
        kit.level(u.lamp, i < s.enabled ? 1.8 : 0.7);
      });
    },
  };
}
