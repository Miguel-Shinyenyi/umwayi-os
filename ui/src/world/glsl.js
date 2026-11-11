import { Color, Vector3 } from 'three';

// Shader pieces shared by the ground, the rock, the wood, the water and the sky. Nothing is loaded: noise is made here.
export const NOISE = /* glsl */ `
float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
float vn(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), u.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * vn(p); p = p * 2.03 + 11.7; a *= 0.5; } return s; }
float fbm3(vec3 p){ return fbm(p.xz + p.y * 1.7) * 0.6 + fbm(p.xy * 1.3 + p.z) * 0.4; }
`;

// A bump with no texture: perturb the normal by the screen space change of a noise value (as three.js does for bump maps).
export const BUMP = /* glsl */ `
vec3 bumpNormal(vec3 n, vec3 viewPos, float h, float scale){
  vec3 sx = dFdx(viewPos), sy = dFdy(viewPos);
  vec3 r1 = cross(sy, n), r2 = cross(n, sx);
  float det = dot(sx, r1);
  vec2 d = vec2(dFdx(h), dFdy(h));
  vec3 grad = sign(det) * (d.x * r1 + d.y * r2);
  return normalize(abs(det) * n - scale * grad);
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
