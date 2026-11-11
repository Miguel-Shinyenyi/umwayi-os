// Every move in the page is a tween here: one ease out curve, a finite time, then it is gone.
// There is no repeating timer. When no tween is active the page asks for no frame.
import { clamp, easeOut } from './ease.js';

export class Motion {
  constructor({ reduced = false, slow = 1, wake = () => {} } = {}) {
    this.reduced = reduced;
    this.slow = slow; // 1 normally, 1.6 in calm mode: every time (and delay) is multiplied by it
    this.wake = wake; // called when the first tween starts after the page was at rest
    this.tweens = [];
  }
  get active() {
    return this.tweens.length > 0;
  }
  // ms: how long; delay: wait before it starts; update(t): t goes 0 to 1 along the ease out curve.
  add({ ms, delay = 0, update, done, tag = '' }) {
    if (this.reduced) {
      update(1);
      if (done) done();
      return;
    }
    const wasIdle = this.tweens.length === 0;
    this.tweens.push({ ms: ms * this.slow, elapsed: -delay * this.slow, update, done, tag });
    if (wasIdle) this.wake();
  }
  step(dtMs) {
    if (this.tweens.length === 0) return;
    const finished = [];
    const live = [];
    for (const tw of this.tweens) {
      tw.elapsed += dtMs;
      if (tw.elapsed < 0) {
        live.push(tw);
        continue;
      }
      const t = clamp(tw.elapsed / tw.ms);
      tw.update(easeOut(t));
      if (t >= 1) finished.push(tw);
      else live.push(tw);
    }
    this.tweens = live;
    for (const tw of finished) if (tw.done) tw.done();
  }
  cancel(tag) {
    this.tweens = this.tweens.filter((tw) => tw.tag !== tag);
  }
  // End every tween now, on its last value.
  finish() {
    const all = this.tweens;
    this.tweens = [];
    for (const tw of all) {
      tw.update(1);
      if (tw.done) tw.done();
    }
  }
  setReduced(on) {
    this.reduced = on;
    if (on) this.finish();
  }
  setSlow(k) {
    this.slow = k;
  }
}
