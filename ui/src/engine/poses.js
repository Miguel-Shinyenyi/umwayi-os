// A station is an ordered list of poses (a full arrangement of its parts, as numbers) and the short moves between them.
// A click plays the moves once. Reduced motion shows the poses one at a time instead.
import { lerp } from './ease.js';

export const ACTION_DELAY = 500; // the camera starts first
export const MOVE_MAX = 1200;
export const ACTION_BUDGET = 2400; // all moves together, before the delay
export const SETTLE_MS = 900;

export const moveMs = (nPoses) => Math.min(MOVE_MAX, ACTION_BUDGET / (nPoses - 1));
// From the click to the last pose. At most 2900 ms; times 1.6 in calm mode is at most 4640 ms.
export const actionMs = (nPoses) => ACTION_DELAY + moveMs(nPoses) * (nPoses - 1);

export function mixParams(a, b, t) {
  const out = {};
  for (const k of Object.keys(b)) out[k] = lerp(a[k] ?? b[k], b[k], t);
  return out;
}

export function createPlayer({ station, motion, onPose = () => {} }) {
  const n = station.poses.length;
  const tag = `pose:${station.id ?? ''}`; // one tag per station, so moving to another station leaves this one's move alone
  const restIndex = () => station.restIndex ?? n - 1;
  const restParams = () => (station.rest ? station.rest() : station.poses[restIndex()].params);
  const player = {
    index: restIndex(),
    params: { ...restParams() },
    _set(p, i) {
      player.params = { ...p };
      if (i !== undefined && i !== player.index) {
        player.index = i;
        onPose(i);
      }
      station.apply(player.params);
    },
    goto(i) {
      motion.cancel(tag);
      const k = Math.max(0, Math.min(n - 1, i));
      player._set(station.poses[k].params, k);
    },
    showRest() {
      motion.cancel(tag);
      player._set(restParams(), restIndex());
    },
    next() {
      player.goto(player.index + 1);
    },
    prev() {
      player.goto(player.index - 1);
    },
    // Play the action once: the first pose at once, then each move in turn, ending on the last pose.
    play() {
      player.goto(0);
      const ms = moveMs(n);
      for (let k = 1; k < n; k++) {
        const from = station.poses[k - 1].params;
        const to = station.poses[k].params;
        motion.add({
          ms,
          delay: ACTION_DELAY + (k - 1) * ms,
          tag,
          // the caption changes when a move starts, so it says what is happening
          update: (t) => player._set(mixParams(from, to, t), k),
        });
      }
    },
    // Back to the resting pose with one ease out move (or at once with reduced motion).
    settleToRest() {
      motion.cancel(tag);
      const from = { ...player.params };
      const to = restParams();
      const toIndex = restIndex();
      if (motion.reduced) return player._set(to, toIndex);
      motion.add({
        ms: SETTLE_MS,
        tag,
        update: (t) => player._set(mixParams(from, to, t), toIndex),
      });
    },
    cancel() {
      motion.cancel(tag);
    },
  };
  return player;
}
