// One set of sky colours, shared by the sky dome and by the water that reflects it, so calm mode changes both.
import { skyUniforms } from './glsl.js';
import { SKY, SUN_DIR } from './palette.js';

export const SKY_UNIFORMS = skyUniforms(SKY, 1);
SKY_UNIFORMS.sunDir.value.set(...SUN_DIR);
