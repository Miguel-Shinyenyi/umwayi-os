import * as THREE from 'three';

// Where the stations stand and where their labels go. Pure maths, tested in Node with a real three.js camera.
export const PLATFORM_R = 2.66;
const GAP = 1.1;

export function ringRadius(n) {
  return Math.max(10.5, (n * (2 * PLATFORM_R + GAP)) / (2 * Math.PI));
}

// n stations on a ring around the lantern. angle is measured from the front (towards the viewer) and
// grows to the right; outward is the unit direction away from the lantern.
export function ringPositions(n, start = Math.PI * 0.9) {
  const R = ringRadius(n);
  return Array.from({ length: n }, (_, i) => {
    const angle = start + (i * 2 * Math.PI) / n;
    const outward = { x: Math.sin(angle), z: Math.cos(angle) };
    return { angle, x: R * outward.x, z: R * outward.z, outward };
  });
}

// The overview shot. It is wider and higher on a narrow screen. The distance is the smallest that puts the whole ring
// inside the picture, with room for the top bar above and the hint below.
export function overviewShot(aspect, n = 11) {
  const R = ringRadius(n);
  const narrow = aspect < 0.85;
  const shot = {
    fov: narrow ? 52 : 38, pitch: narrow ? 0.66 : 0.2, dist: 24, yaw: 0, tx: 0, ty: narrow ? 0.3 : 4.2, tz: 0, shiftX: 0, shiftY: 0,
  };
  const top = narrow ? 0.82 : 0.42; // on a wide screen the upper part of the picture is left for the sky
  const cam = new THREE.PerspectiveCamera(shot.fov, aspect, 0.1, 400);
  const v = new THREE.Vector3();
  const ok = () => {
    cam.position.set(0, shot.ty + shot.dist * Math.sin(shot.pitch), shot.dist * Math.cos(shot.pitch));
    cam.lookAt(0, shot.ty, 0);
    cam.updateMatrixWorld();
    cam.updateProjectionMatrix();
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * Math.PI * 2;
      for (const [r, y] of [[R + PLATFORM_R, 0], [R, 2.6]]) {
        v.set(Math.sin(a) * r, y, Math.cos(a) * r).project(cam);
        if (Math.abs(v.x) > 0.94 || v.y < -0.82 || v.y > top) return false;
      }
    }
    return true;
  };
  while (!ok() && shot.dist < 140) shot.dist += 0.5;
  return shot;
}

// The shot of one station: in front of it, looking in, with the station in the left third (or the top third on a phone).
export function stationShot(pos, aspect) {
  const narrow = aspect < 0.85;
  return {
    fov: narrow ? 52 : 38, pitch: narrow ? 0.34 : 0.22, dist: narrow ? 8.2 : 7.4,
    yaw: Math.atan2(pos.outward.x, pos.outward.z),
    tx: pos.x, ty: 1.15, tz: pos.z,
    shiftX: narrow ? 0 : 0.17, shiftY: narrow ? 0.2 : 0,
  };
}

// A label is a rectangle centred over its station. Move rectangles up until none overlaps another,
// then keep them inside the bounds. Front stations (larger y) keep their place first.
export function declutter(rects, bounds, gap = 6) {
  const out = rects.map((r) => ({ ...r }));
  const order = out.map((_, i) => i).sort((a, b) => out[b].y - out[a].y);
  const overlaps = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 + gap && Math.abs(a.y - b.y) < (a.h + b.h) / 2 + gap;
  for (let pass = 0; pass < 4; pass++) {
    const placed = [];
    for (const i of order) {
      const r = out[i];
      r.x = Math.min(bounds.right - r.w / 2, Math.max(bounds.left + r.w / 2, r.x));
      r.y = Math.min(bounds.bottom - r.h / 2, Math.max(bounds.top + r.h / 2, r.y));
      let guard = 0;
      while (placed.some((p) => overlaps(r, p)) && guard++ < 200) {
        const hit = placed.find((p) => overlaps(r, p));
        const up = hit.y - (hit.h + r.h) / 2 - gap;
        if (up - r.h / 2 >= bounds.top) r.y = Math.min(r.y, up);
        else r.y = Math.min(bounds.bottom - r.h / 2, hit.y + (hit.h + r.h) / 2 + gap); // no room above: go below
      }
      placed.push(r);
    }
  }
  return out;
}
