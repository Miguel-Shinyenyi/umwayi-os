import * as THREE from 'three';
import { heightAt, WATER_LEVEL } from './height.js';

// Trails of light: a row of small soft lights that follows the ground between two stations that work together.
// Not a path: nothing is drawn on the ground. Since Nov 11 (round 2) every trail is drawn faintly at rest, so the links
// show from the default view; the trails of the station in focus are drawn again, brighter. They never move.
// spacing: metres between two lights; a long trail gets more lights, up to perTrail.
export function buildTrails(maxTrails = 6, perTrail = 90, { size = 0.36, spacing = 0.75 } = {}) {
  const group = new THREE.Group();
  group.visible = false;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const x = c.getContext('2d');
  const grad = x.createRadialGradient(32, 32, 1, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,214,160,1)');
  grad.addColorStop(0.35, 'rgba(255,190,120,0.5)');
  grad.addColorStop(1, 'rgba(255,170,90,0)');
  x.fillStyle = grad;
  x.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.PointsMaterial({ map: tex, size, sizeAttenuation: true, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, fog: false, color: 0xffc58a });
  const lines = [];
  for (let i = 0; i < maxTrails; i++) {
    const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(perTrail * 3), 3));
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    pts.visible = false;
    group.add(pts);
    lines.push(pts);
  }
  const lift = (x, z) => Math.max(heightAt(x, z), WATER_LEVEL) + 0.55;
  const trails = {
    group, mat,
    // pairs: [[stationA, stationB], ...], each station has .pos {x, z}; called again when stations move
    set(pairs) {
      trails.pairs = pairs;
      lines.forEach((ln, i) => {
        const pair = pairs[i];
        ln.visible = !!pair;
        if (!pair) return;
        const [a, b] = pair, arr = ln.geometry.attributes.position.array;
        const n = Math.max(8, Math.min(perTrail, Math.round(Math.hypot(b.pos.x - a.pos.x, b.pos.z - a.pos.z) / spacing)));
        ln.geometry.setDrawRange(0, n);
        for (let k = 0; k < n; k++) {
          const t = k / (n - 1);
          const px = a.pos.x + (b.pos.x - a.pos.x) * t, pz = a.pos.z + (b.pos.z - a.pos.z) * t;
          arr[k * 3] = px; arr[k * 3 + 1] = lift(px, pz) + Math.sin(t * Math.PI) * 0.35; arr[k * 3 + 2] = pz;
        }
        ln.geometry.attributes.position.needsUpdate = true;
      });
    },
    refresh() {
      if (trails.pairs) trails.set(trails.pairs);
    },
    setOpacity(o) {
      mat.opacity = o;
      group.visible = o > 0.004;
    },
    pairs: null,
  };
  return trails;
}

// How bright the trails and the lift light are for a focus level (0 to 1) and a Calm amount (0 to 1). Calm mode makes them
// fainter; it no longer hides them (round 2).
export const trailOpacity = (level, calm) => level * 0.7 * (1 - 0.45 * calm);
export const restTrailOpacity = (calm) => 0.4 * (1 - 0.45 * calm);
export const liftIntensity = (level, calm) => level * 26 * (1 - 0.4 * calm);
