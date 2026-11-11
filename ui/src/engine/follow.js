// A value that follows a target with an exponential ease and comes to rest.
// Used for the pointer parallax and for the drag. It snaps to the target once it is closer than eps,
// so the page stops asking for frames. With reduced motion it jumps.
export class Follow {
  constructor({ tau = 140, eps = 0.0005, value = 0, reduced = false } = {}) {
    this.tau = tau;
    this.eps = eps;
    this.value = value;
    this._target = value;
    this.reduced = reduced;
  }
  get target() {
    return this._target;
  }
  set target(v) {
    this._target = v;
    if (this.reduced) this.value = v;
  }
  get active() {
    return Math.abs(this._target - this.value) > this.eps;
  }
  step(dtMs) {
    if (!this.active) return false;
    const k = 1 - Math.exp(-dtMs / this.tau);
    this.value += (this._target - this.value) * k;
    if (Math.abs(this._target - this.value) <= this.eps) this.value = this._target;
    return true;
  }
  setReduced(on) {
    this.reduced = on;
    if (on) this.value = this._target;
  }
}
