// The renderer: WebGL2, multisampled, soft shadows (PCF), filmic tone mapping, a capped bloom. It draws only when asked.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

export function createStage(canvas, scene) {
  const gl = canvas.getContext('webgl2', { antialias: false, powerPreference: 'default', alpha: false });
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
  let w = 1, h = 1;
  const stage = {
    renderer, camera, composer, bloom,
    get pixelRatio() {
      return pixelRatio;
    },
    resize(width, height) {
      w = Math.max(1, Math.floor(width));
      h = Math.max(1, Math.floor(height));
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
    render() {
      composer.render();
    },
  };
  // After about two dozen slow frames while moving, draw at a lower pixel ratio.
  const times = [];
  stage.noteFrame = (dt) => {
    times.push(dt);
    if (times.length < 24) return;
    const avg = times.reduce((a, b) => a + b, 0) / times.length;
    times.length = 0;
    if (avg > 34 && pixelRatio > 1) {
      pixelRatio = Math.max(1, pixelRatio - 0.5);
      stage.resize(w, h);
      stage.onPixelRatio?.(pixelRatio);
    }
  };
  return stage;
}
