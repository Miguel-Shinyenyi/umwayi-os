// The renderer: WebGL2, multisampled, soft shadows (PCF), filmic tone mapping, a capped bloom. It draws only when asked.
import * as THREE from 'three';
import { STEPS, shouldStepDown, stepDown } from './detail.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

// the context attributes, once: a second getContext with the same attributes returns the same context
export const GL_ATTRIBUTES = { antialias: false, powerPreference: 'default', alpha: false };

export function createStage(canvas, scene) {
  const gl = canvas.getContext('webgl2', GL_ATTRIBUTES);
  if (!gl) throw new Error('no webgl2');
  const renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: false });
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 700);
  const target = new THREE.WebGLRenderTarget(4, 4, { type: THREE.HalfFloatType, samples: 4 });
  const composer = new EffectComposer(renderer, target);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.42, 0.6, 0.86);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  let pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  let w = 1, h = 1, step = 0, cap = 2;
  const stage = {
    renderer, camera, composer, bloom,
    get pixelRatio() {
      return pixelRatio;
    },
    get step() {
      return step;
    },
    resize(width, height) {
      w = Math.max(1, Math.floor(width));
      h = Math.max(1, Math.floor(height));
      pixelRatio = Math.min(window.devicePixelRatio || 1, cap);
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(w, h, false);
      composer.setPixelRatio(pixelRatio);
      composer.setSize(w, h);
    },
    get size() {
      return { w, h };
    },
    setLook({ bloom: b, exposure }) {
      bloom.strength = b;
      renderer.toneMappingExposure = exposure;
    },
    // apply one step of the detail ladder
    setStep(i, world) {
      step = i;
      const s = STEPS[i];
      cap = s.pixelRatio;
      bloom.enabled = s.bloom;
      for (const rt of [composer.renderTarget1, composer.renderTarget2]) {
        if (rt.samples !== s.msaa) { rt.samples = s.msaa; rt.dispose(); }
      }
      const was = renderer.shadowMap.enabled;
      renderer.shadowMap.enabled = s.shadows;
      if (world) {
        world.glow.castShadow = s.shadows;
        if (world.glow.shadow.map && world.glow.shadow.mapSize.x !== s.shadowMap) {
          world.glow.shadow.mapSize.set(s.shadowMap, s.shadowMap);
          world.glow.shadow.map.dispose();
          world.glow.shadow.map = null;
        }
        world.setPlants(s.plants);
      }
      if (was !== s.shadows) camera.parent?.traverse?.((o) => { if (o.material) o.material.needsUpdate = true; });
      stage.resize(w, h);
    },
    render() {
      composer.render();
    },
  };
  // After about two dozen slow frames while moving, step down the ladder.
  const times = [];
  stage.noteFrame = (dt) => {
    times.push(dt);
    if (times.length < 24) return;
    const slow = shouldStepDown(times);
    times.length = 0;
    if (slow && !stage.pinned && step < STEPS.length - 1) {
      stage.setStep(stepDown(step), stage.world);
      stage.onStep?.(step);
    }
  };
  return stage;
}
