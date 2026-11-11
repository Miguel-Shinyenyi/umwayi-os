// The camera shots: the overview, which fits every place a station can stand, and the view of one station.
import * as THREE from 'three';
import { TABLE, stationPositions } from './layout.js';
import { WATER_LEVEL } from './height.js';

export const FAR = 30; // metres: a station this far from the lantern is a far one
const STATION_SHOT_DIST = (st) => 6.2 + st.footprint * 1.15;

// The overview: it fits the default place of every station, with the sky and the mountain above.
export function overviewShot(aspect) {
  const narrow = aspect < 0.85;
  const shot = {
    fov: narrow ? 62 : 42, pitch: narrow ? 0.3 : 0.21, dist: 40, yaw: 0, tx: 0, ty: narrow ? 2.5 : 2.0, tz: narrow ? -3 : -11, shiftX: 0, shiftY: 0, // pitched high enough to see the river in its channel
  };
  // Since Nov 11 (round 2) some stations are really far, so the overview fits the default places on every screen; a station
  // that has drifted further out than that is still reached with Next station and by dragging.
  const defaults = stationPositions({});
  // On a phone the far stations (30 m or more) would make the rest too small to read, so there it fits the near ones; the far
  // ones are at the edges or just beyond, and Next station or a drag reaches them.
  const spots = TABLE.filter((r) => !narrow || Math.hypot(defaults[r.id].x, defaults[r.id].z) < FAR)
    .map((r) => ({ x: defaults[r.id].x, z: defaults[r.id].z, r: r.footprint + 0.4 }));
  const cam = new THREE.PerspectiveCamera(shot.fov, aspect, 0.1, 900);
  const v = new THREE.Vector3();
  const top = narrow ? 0.5 : 0.5; // the sky and the mountain keep the upper part of the picture
  const ok = () => {
    cam.position.set(0, shot.ty + shot.dist * Math.sin(shot.pitch), shot.tz + shot.dist * Math.cos(shot.pitch));
    cam.lookAt(0, shot.ty, shot.tz);
    cam.updateMatrixWorld(); cam.updateProjectionMatrix();
    for (const s of spots) {
      for (const [dx, dz, y] of [[s.r, 0, 0], [-s.r, 0, 0], [0, s.r, 0], [0, -s.r, 0], [0, 0, 3.2]]) {
        v.set(s.x + dx, y, s.z + dz).project(cam);
        if (Math.abs(v.x) > 0.96 || v.y < -0.88 || v.y > top) return false;
      }
    }
    return true;
  };
  while (!ok() && shot.dist < 260) shot.dist += 0.5;
  return shot;
}

// In front of a station (on the lantern side), looking in, the station in the left third (the top third on a phone).
// The camera stands off to one side of the line to the lantern, so it never ends up in the shepherd or in another feature:
// it tries a few angles and takes the first where it is clear of the shepherd and of every other station (others: [{ pos, footprint }]).
export const KEEP_FROM_SHEPHERD = 4.5;
const ANGLES = [0.55, -0.55, 0.9, -0.9, 1.25, -1.25, 0.2, -0.2];
export function cameraPosition(st, aspect, others = []) {
  const narrow = aspect < 0.85;
  const dist = STATION_SHOT_DIST(st) * (narrow ? 1.25 : 1);
  const base = Math.atan2(st.facing.x, st.facing.z);
  const pitch = narrow ? 0.36 : 0.2;
  let best = null;
  for (const phi of ANGLES) {
    const yaw = base + phi;
    const x = st.pos.x + Math.sin(yaw) * dist * Math.cos(pitch), z = st.pos.z + Math.cos(yaw) * dist * Math.cos(pitch);
    const clear = Math.hypot(x, z) >= KEEP_FROM_SHEPHERD && others.every((o) => o.id === st.id || Math.hypot(x - o.pos.x, z - o.pos.z) >= o.footprint + 1.2);
    if (clear) return { yaw, x, z, dist, pitch };
    const room = Math.min(Math.hypot(x, z) - KEEP_FROM_SHEPHERD, ...others.filter((o) => o.id !== st.id).map((o) => Math.hypot(x - o.pos.x, z - o.pos.z) - o.footprint - 1.2));
    if (!best || room > best.room) best = { yaw, x, z, dist, pitch, room };
  }
  return best;
}
export function stationShot(st, aspect, others = []) {
  const narrow = aspect < 0.85;
  const c = cameraPosition(st, aspect, others);
  return {
    fov: narrow ? 56 : 42, pitch: c.pitch, dist: c.dist, yaw: c.yaw,
    tx: st.pos.x, ty: (st.river ? WATER_LEVEL : st.pos.y) + 1.2, tz: st.pos.z,
    shiftX: narrow ? 0 : 0.17, shiftY: narrow ? 0.12 : 0, // on a phone the station sits below the title and above the panel
  };
}
