// Gives a standard material fine grain made from noise: a colour variation and a bump. No texture file.
import * as THREE from 'three';
import { NOISE, BUMP } from './glsl.js';

// opts: freq (grain size in 1/m), bump (strength), vary (colour variation 0..1), stripe (wood grain along y, 0..1), strata (rock layers, 0..1)
export function grain(material, { freq = 6, bump = 0.5, vary = 0.25, stripe = 0, strata = 0, seed = 0 } = {}) {
  material.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWp;\nvarying vec3 vLp;\nvarying vec3 vUp;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvLp = position;\nvUp = mat3(modelMatrix) * vec3(0.0, 1.0, 0.0);\nvWp = (modelMatrix * vec4(position, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying vec3 vWp;\nvarying vec3 vLp;\nvarying vec3 vUp;\n${NOISE}\n${BUMP}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec3 gp = vWp * ${freq.toFixed(2)} + ${seed.toFixed(1)};
        float gn = fbm3(gp);
        float gf = fbm3(gp * 2.0);
        diffuseColor.rgb *= 1.0 - ${vary.toFixed(2)} + ${(vary * 2).toFixed(2)} * (gn * 0.8 + gf * 0.2);
        ${stripe > 0 ? `diffuseColor.rgb *= 1.0 - ${stripe.toFixed(2)} * 0.5 * (0.5 + 0.5 * sin(vLp.y * 38.0 + fbm(vLp.xz * 6.0) * 7.0));` : ''}
        ${strata > 0 ? `diffuseColor.rgb *= 1.0 - ${strata.toFixed(2)} * smoothstep(0.35, 0.65, fbm(vec2(vWp.y * 5.0, gn * 2.0)));` : ''}`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        const float ge = 0.06;
        vec3 gradW = vec3(fbm3(gp + vec3(ge, 0.0, 0.0)) - gn, fbm3(gp + vec3(0.0, ge, 0.0)) - gn, fbm3(gp + vec3(0.0, 0.0, ge)) - gn) * (${freq.toFixed(2)} / ge);
        ${stripe > 0 ? 'float sph = vLp.y * 38.0 + fbm(vLp.xz * 6.0) * 7.0; gradW += vUp * (0.4 * 38.0 * cos(sph));' : ''}
        normal = bumpWorld(normal, gradW, ${bump.toFixed(3)});`);
  };
  material.customProgramCacheKey = () => `grain${freq}${bump}${vary}${stripe}${strata}${seed}`;
  return material;
}
