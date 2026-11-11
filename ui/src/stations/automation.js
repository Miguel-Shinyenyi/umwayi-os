// Automation: a timber water wheel on the river. The river runs along x; the wheel turns on an axis across it.
// Small lamps on the wheel count the schedules: one for each entry, brighter for installed, brightest for enabled.
// The group stands at the water level (the river bed is 1.2 m below it).
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';
import { sceneNumbers } from '../data/snapshot.js';

export const poses = [{ t: 0 }, { t: 0.5 }, { t: 1 }];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const wheel = new THREE.Group();
  wheel.position.y = 1.55;
  g.add(wheel);
  const rim = (z) => {
    const r = new THREE.Mesh(new THREE.TorusGeometry(1.75, 0.07, 8, 40), M.wood);
    r.position.z = z; r.castShadow = true;
    return r;
  };
  wheel.add(rim(0.42), rim(-0.42));
  const hub = kit.cyl(0.16, 0.16, 1.5, M.woodDark, 0, 0, 0, 12);
  hub.rotation.x = Math.PI / 2;
  wheel.add(hub);
  const lamps = [];
  const unknownMark = kit.unknownMark(0.4, 3.0);
  g.add(unknownMark);
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2, c = Math.cos(a), s = Math.sin(a);
    for (const z of [-0.42, 0.42]) {
      const spoke = kit.box(1.7, 0.07, 0.06, M.wood, c * 0.88, s * 0.88, z);
      spoke.rotation.z = a;
      wheel.add(spoke);
    }
    const paddle = kit.box(0.34, 0.07, 0.95, M.wood, c * 1.75, s * 1.75, 0);
    paddle.rotation.z = a + Math.PI / 2 - 0.35;
    wheel.add(paddle);
    const m = kit.glow(TOKENS.amber, 1.7, 0);
    const bead = kit.ball(0.06, m, c * 1.45, s * 1.45, 0.5, 10, 8);
    bead.userData.noShadow = true;
    bead.userData.part = 'lamp';
    bead.userData.mat = m;
    bead.visible = false;
    wheel.add(bead);
    lamps.push({ bead, m });
  }
  // supports on both sides, standing in the river bed
  for (const z of [-0.85, 0.85]) {
    g.add(kit.beam(new THREE.Vector3(-1.1, -1.2, z), new THREE.Vector3(0, 1.55, z * 0.6), 0.14, M.woodDark));
    g.add(kit.beam(new THREE.Vector3(1.1, -1.2, z), new THREE.Vector3(0, 1.55, z * 0.6), 0.14, M.woodDark));
  }
  // a few stones where the water meets the wheel
  [[-2.4, -0.2, 0.2, 0.5], [2.5, -0.2, -0.4, 0.55], [0.2, -0.3, 1.9, 0.45], [-0.9, -0.3, -2.0, 0.5]].forEach(([x, y, z, r], i) => g.add(kit.rock(r, M.stoneDark, x, y, z, i + 30, 1.2, 0.6, 1)));
  return {
    group: g,
    apply(p) {
      wheel.rotation.z = -p.t * (Math.PI / 6);
    },
    // the mapping table (data/snapshot.js): a lamp for each schedule, brighter if installed, brightest if enabled (12 at most);
    // a schedule that cannot be read is the mark and no lamp
    setCounts(c) {
      const n = sceneNumbers(c).automation;
      lamps.forEach((l, i) => {
        const v = n.lamps[i];
        l.bead.visible = v > 0;
        kit.level(l.m, v === 3 ? 1.9 : v === 2 ? 1.0 : 0.4);
      });
      unknownMark.visible = n.unknown;
    },
  };
}
