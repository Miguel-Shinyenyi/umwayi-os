import * as THREE from 'three';
// Budget: a trough inside a scaffold. The water is today's use against the day's limit. Seven bars beside it are the
// last seven days. A run that would pass the limit line does not start.
import { TOKENS, SCENE } from '../world/palette.js';
import { lerp } from '../engine/ease.js';

export const poses = [{ level: 0.22 }, { level: 0.62 }, { level: 1 }];

const LIMIT = 0.86;

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.rotation.y = 0.25;
  // trough
  const W = 1.7, D = 0.7, H = 0.62;
  g.add(kit.box(W, 0.06, D, M.woodDark, 0, 0.03, 0));
  for (const s of [-1, 1]) {
    g.add(kit.box(W, H, 0.06, M.wood, 0, H / 2, s * (D / 2 - 0.03)));
    g.add(kit.box(0.06, H, D, M.wood, s * (W / 2 - 0.03), H / 2, 0));
  }
  const waterMat = new THREE.MeshStandardMaterial({ color: SCENE.water, roughness: 0.25, metalness: 0.1, transparent: true, opacity: 0.85 });
  const water = new THREE.Mesh(new THREE.BoxGeometry(W - 0.14, 1, D - 0.14), waterMat);
  water.position.set(0, 0.06, 0);
  g.add(water);
  const lineMat = kit.glow(TOKENS.amber, 1.8);
  g.add(kit.mesh(new THREE.BoxGeometry(W - 0.1, 0.014, 0.012), lineMat, 0, 0.06 + H * LIMIT * 0.9, D / 2 - 0.058));
  // scaffold (thin, open)
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(kit.post(1.55, 0.03, M.metal, sx * (W / 2 + 0.14), sz * (D / 2 + 0.14)));
  for (const y of [0.9, 1.55]) {
    for (const sz of [-1, 1]) g.add(kit.box(W + 0.4, 0.03, 0.03, M.metal, 0, y, sz * (D / 2 + 0.14)));
    for (const sx of [-1, 1]) g.add(kit.box(0.03, 0.03, D + 0.4, M.metal, sx * (W / 2 + 0.14), y, 0));
  }
  // the last seven days
  const bars = [];
  for (let i = 0; i < 7; i++) {
    const m = kit.glow(TOKENS.amber, 1.1, i === 6 ? 1 : 0.55);
    const bar = kit.mesh(new THREE.BoxGeometry(0.1, 1, 0.1), m, -0.66 + i * 0.22, 0, D / 2 + 0.55);
    g.add(bar);
    bars.push(bar);
  }
  let restLevel = 0.22;
  const top = H * 0.9;
  return {
    group: g,
    apply(p) {
      const h = Math.max(0.001, p.level * top * 0.98);
      water.scale.y = h;
      water.position.y = 0.06 + h / 2;
    },
    // counts: { budget: { days: [{ date, used_uu } x 7] } }
    setCounts(c) {
      const days = c && c.budget ? c.budget.days.map((d) => d.used_uu) : new Array(7).fill(0);
      const max = Math.max(1, ...days);
      bars.forEach((bar, i) => {
        const h = Math.max(0.03, (days[i] / max) * 0.5);
        bar.scale.y = h;
        bar.position.y = h / 2;
      });
      restLevel = lerp(0.12, LIMIT * 0.8, days[6] / max);
    },
    rest: () => ({ level: restLevel }),
  };
}
