import { Color, Vector3 } from 'three';

// Shader pieces shared by the ground, the rock, the wood, the water and the sky. Nothing is loaded: noise is made here.
export const NOISE = /* glsl */ `
float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
float vn(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), u.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbmN(vec2 p, int n){ float s = 0.0, a = 0.5, w = 0.0; for (int i = 0; i < 5; i++) { if (i >= n) break; s += a * vn(p); w += a; p = p * 2.03 + 11.7; a *= 0.5; } return s / w; }
float fbm(vec2 p){ return fbmN(p, 5); }
// three octaves for surfaces seen close up: the finest octaves of fbm are smaller than a pixel and alias into blocks
float fbm3(vec3 p){ return fbmN(p.xz + p.y * 1.7, 3) * 0.6 + fbmN(p.xy * 1.3 + p.z, 3) * 0.4; }
`;

// A bump with no texture. The caller gives the world space gradient of a noise height (by finite differences of the noise
// itself, not by dFdx/dFdy, which are computed per 2x2 pixel block and show up as blocks on close surfaces).
export const BUMP = /* glsl */ `
vec3 bumpWorld(vec3 n, vec3 gradWorld, float scale){
  vec3 g = mat3(viewMatrix) * gradWorld;
  g -= n * dot(g, n);
  return normalize(n - scale * g);
}
`;

// The sky colour in a direction. Used by the sky itself and by the water that reflects it.
export const SKY_FN = /* glsl */ `
uniform vec3 skyTop; uniform vec3 skyMid; uniform vec3 skyHorizon; uniform vec3 skyGlow; uniform vec3 skyLow; uniform vec3 sunDir; uniform float glowAmount;
vec3 skyColor(vec3 d){
  float h = d.y;
  vec3 c = mix(skyHorizon, skyMid, smoothstep(0.0, 0.22, h));
  c = mix(c, skyTop, smoothstep(0.18, 0.8, h));
  float g = pow(max(dot(normalize(d), normalize(sunDir)), 0.0), 3.5);
  float g2 = pow(max(dot(normalize(d), normalize(sunDir)), 0.0), 14.0);
  c += skyGlow * (g * 0.38 + g2 * 0.55) * glowAmount * (1.0 - smoothstep(0.0, 0.6, h));
  c = mix(c, skyLow, smoothstep(0.0, -0.18, h));
  return c;
}
`;

export function skyUniforms(P, glowAmount = 1) {
  const c = (h) => new Color(h);
  return {
    skyTop: { value: c(P.top) }, skyMid: { value: c(P.mid) }, skyHorizon: { value: c(P.horizon) }, skyGlow: { value: c(P.glow) },
    skyLow: { value: c(P.low) }, sunDir: { value: new Vector3() }, glowAmount: { value: glowAmount },
  };
}
