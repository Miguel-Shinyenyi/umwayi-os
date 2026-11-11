// Moves the stations to the places the position function gives. One ease out move, at most 2.4 s (3.84 s in Calm mode),
// from where the stations are now; with reduced motion they jump. UI.3 only calls setNeeds with numbers.
import { stationPositions, nearestOnRiver, riverPoint } from '../world/layout.js';
import { heightAt, WATER_LEVEL } from '../world/height.js';
import { lerp } from './ease.js';

export const PLACEMENT_MS = 2400;

// A free station faces the lantern. A river station lies along the river with its bank side towards the lantern.
export function facingAt(st, x, z) {
  if (st.river) {
    const u = nearestOnRiver({ x, z }).u;
    const a = riverPoint(u - 0.03), b = riverPoint(u + 0.03);
    let tx = b.x - a.x, tz = b.z - a.z;
    const l = Math.hypot(tx, tz) || 1;
    tx /= l; tz /= l;
    let nx = -tz, nz = tx;
    if (nx * -x + nz * -z < 0) { nx = -nx; nz = -nz; }
    return { x: nx, z: nz };
  }
  const l = Math.hypot(x, z) || 1;
  return { x: -x / l, z: -z / l };
}

export function createPlacement({ stations, motion, onMove = () => {} }) {
  let needs = {};
  let placement = null;
  const put = (st, x, z) => {
    st.pos.x = x;
    st.pos.z = z;
    st.pos.y = heightAt(x, z);
    st.facing = facingAt(st, x, z);
    st.group.position.set(x, st.river ? WATER_LEVEL : st.pos.y, z);
    if (st.group.rotation) st.group.rotation.y = Math.atan2(st.facing.x, st.facing.z);
    if (st.anchor && st.anchor.set) st.anchor.set(x, (st.river ? WATER_LEVEL : st.pos.y) + 2.8, z);
  };
  placement = {
    onMove,
    get needs() {
      return needs;
    },
    // at once, for the start of the page
    place(n = {}) {
      needs = n;
      const target = stationPositions(n);
      for (const st of stations) put(st, target[st.id].x, target[st.id].z);
      placement.onMove();
    },
    setNeeds(n) {
      needs = n;
      const target = stationPositions(n);
      const from = Object.fromEntries(stations.map((st) => [st.id, { x: st.pos.x, z: st.pos.z }]));
      motion.cancel('placement');
      motion.add({
        ms: PLACEMENT_MS, tag: 'placement',
        update: (t) => {
          for (const st of stations) put(st, lerp(from[st.id].x, target[st.id].x, t), lerp(from[st.id].z, target[st.id].z, t));
          placement.onMove();
        },
      });
    },
  };
  return placement;
}
