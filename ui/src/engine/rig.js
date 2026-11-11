// The camera rig. One state (where it looks from and at), blended between shots with the ease out tween,
// plus two small things that follow the pointer: a parallax and a drag. Both come to rest.
import * as THREE from 'three';
import { clamp, lerp, turnTo } from './ease.js';
import { Follow } from './follow.js';

const KEYS = ['fov', 'pitch', 'dist', 'tx', 'ty', 'tz', 'shiftX', 'shiftY'];

export class Rig {
  constructor(shot) {
    this.s = { ...shot };
    this.px = new Follow({ tau: 140 });
    this.py = new Follow({ tau: 140 });
    this.ox = new Follow({ tau: 140 });
    this.oy = new Follow({ tau: 140 });
    this.parallax = 1; // 0 when reduced motion is on
    this.limit = { yaw: 0.6, pitch: 0.28 };
    this.pos = new THREE.Vector3();
  }
  get follows() {
    return [this.px, this.py, this.ox, this.oy];
  }
  setTau(tau) {
    this.follows.forEach((f) => (f.tau = tau));
  }
  setReduced(on) {
    this.follows.forEach((f) => f.setReduced(on));
    this.parallax = on ? 0 : 1;
    if (on) {
      this.px.target = this.py.target = 0;
      this.px.value = this.py.value = 0;
    }
  }
  // blend from shot a to shot b; t goes 0 to 1
  blend(a, b, t) {
    for (const k of KEYS) this.s[k] = lerp(a[k], b[k], t);
    // the yaw takes the shorter way round
    this.s.yaw = a.yaw + (turnTo(a.yaw, b.yaw) - a.yaw) * t;
  }
  set(shot) {
    this.s = { ...shot };
  }
  // pointer position in -1..1 over the viewport
  pointer(nx, ny) {
    this.px.target = nx * this.parallax;
    this.py.target = ny * this.parallax;
  }
  drag(dx, dy) {
    this.ox.target = clamp(this.ox.target - dx * 0.005, -this.limit.yaw, this.limit.yaw);
    this.oy.target = clamp(this.oy.target + dy * 0.004, -this.limit.pitch, this.limit.pitch);
  }
  resetOrbit() {
    this.ox.target = 0;
    this.oy.target = 0;
  }
  apply(camera, w, h) {
    const s = this.s;
    const yaw = s.yaw + this.ox.value + this.px.value * 0.045;
    const pitch = clamp(s.pitch + this.oy.value - this.py.value * 0.02, 0.08, 1.2);
    this.pos.set(s.tx + s.dist * Math.sin(yaw) * Math.cos(pitch), s.ty + s.dist * Math.sin(pitch), s.tz + s.dist * Math.cos(yaw) * Math.cos(pitch));
    camera.position.copy(this.pos);
    camera.lookAt(s.tx, s.ty, s.tz);
    camera.fov = s.fov;
    camera.aspect = w / h;
    if (Math.abs(s.shiftX) + Math.abs(s.shiftY) > 1e-4) camera.setViewOffset(w, h, s.shiftX * w, s.shiftY * h, w, h);
    else camera.clearViewOffset();
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  }
}
