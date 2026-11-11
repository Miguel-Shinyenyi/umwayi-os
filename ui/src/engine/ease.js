// Small helpers shared by the engine. Everything here is pure.
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, t) => a + (b - a) * t;
// Ease out (cubic): fast at the start, slows down, ends at rest.
export const easeOut = (t) => {
  const u = 1 - clamp(t);
  return 1 - u * u * u;
};
export const smoothstep = (a, b, x) => {
  const t = clamp((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
// The shortest turn from angle a to angle b, in radians.
export const turnTo = (a, b) => a + Math.atan2(Math.sin(b - a), Math.cos(b - a));
