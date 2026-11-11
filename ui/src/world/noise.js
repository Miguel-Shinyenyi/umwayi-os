// Smooth value noise, in JavaScript, for the ground, the plants and the layout. Deterministic and pure.
const fract = (x) => x - Math.floor(x);
const hash2 = (x, y) => fract(Math.sin(x * 127.1 + y * 311.7) * 43758.5453123);
const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);

export function vnoise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = fade(xf), v = fade(yf);
  const a = hash2(xi, yi), b = hash2(xi + 1, yi), c = hash2(xi, yi + 1), d = hash2(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v; // 0..1
}
export function fbm(x, y, octaves = 4) {
  let s = 0, amp = 0.5, f = 1, norm = 0;
  for (let i = 0; i < octaves; i++) {
    s += amp * vnoise(x * f + i * 17.3, y * f - i * 9.1);
    norm += amp;
    amp *= 0.5;
    f *= 2.03;
  }
  return s / norm; // 0..1
}
// ridges: sharp crests where the noise crosses its middle
export function ridged(x, y, octaves = 3) {
  let s = 0, amp = 0.5, f = 1, norm = 0;
  for (let i = 0; i < octaves; i++) {
    const n = 1 - Math.abs(2 * vnoise(x * f + i * 5.7, y * f + i * 3.3) - 1);
    s += amp * n * n;
    norm += amp;
    amp *= 0.5;
    f *= 2.1;
  }
  return s / norm;
}
