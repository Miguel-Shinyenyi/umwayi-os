import * as THREE from 'three';
// Memory: a fenced pasture, and a walled plot with a lid. The pebbles inside stand for private paths.
import { TOKENS } from '../world/palette.js';

export const poses = [
  { graze: 0, lid: 0, glow: 0 },
  { graze: 1, lid: 0, glow: 1 },
  { graze: 1, lid: 1, glow: 0.35 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.add(kit.fenceArc(-0.85, 0.1, 1.55, Math.PI * 0.36, Math.PI * 1.72, 14, 0.5, M.wood));
  const sheep = [[-1.25, 0.15, 0.6], [-0.45, 0.62, 3.6], [-0.95, -0.55, 2.2]].map(([x, z, yaw]) => {
    const s = kit.sheep(0.9);
    s.group.position.set(x, 0, z);
    s.group.rotation.y = yaw;
    g.add(s.group);
    return s;
  });
  // the walled plot
  const plot = new THREE.Group();
  plot.position.set(1.35, 0, -0.1);
  g.add(plot);
  for (let i = 0; i < 11; i++) {
    const a = (i / 11) * Math.PI * 2;
    plot.add(kit.rock(0.2, M.stone, Math.cos(a) * 0.62, 0.15, Math.sin(a) * 0.62, i + 1));
  }
  plot.add(kit.cyl(0.58, 0.58, 0.03, M.woodDark, 0, 0.03, 0));
  const pebbleMat = kit.glow(TOKENS.amber, 1.5, 0);
  for (let i = 0; i < 5; i++) {
    const a = i * 2.4;
    plot.add(kit.ball(0.07, pebbleMat, Math.cos(a) * 0.25, 0.1, Math.sin(a) * 0.25, 12, 8));
  }
  const lid = kit.cyl(0.74, 0.74, 0.07, M.woodDark, 0, 0.4, 0, 28);
  plot.add(lid);

  return {
    group: g,
    apply(p) {
      for (const s of sheep) s.head.rotation.x = p.graze * 0.85;
      lid.position.set(p.lid < 1 ? (1 - p.lid) * 0.7 : 0, 0.42 + (1 - p.lid) * 0.55, 0);
      lid.rotation.z = (1 - p.lid) * 0.55;
      kit.level(pebbleMat, p.glow);
    },
    setCounts() {},
  };
}
