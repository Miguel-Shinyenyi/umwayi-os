// The High asset files (12.R16.4): five CC0 photographs from Poly Haven, served by the public site from its own host under
// /high/ (site/public/high/). Every file, its source, its licence and its checksum is listed in site/high-assets.json and in
// adapters/NOTES-layer12.md; tests/test_site_assets.py checks the three agree. This is the only module of ui/src that loads a
// file, and the owner's live view never imports it (ui/test/high.test.mjs).
import * as THREE from 'three';

export const ASSETS = [
  { key: 'grass', file: 'grass_ground_diff_1k.jpg', colour: true },
  { key: 'grassNormal', file: 'grass_ground_nor_gl_1k.jpg', colour: false },
  { key: 'soil', file: 'red_laterite_soil_stones_diff_1k.jpg', colour: true },
  { key: 'rock', file: 'dark_rock_02_diff_1k.jpg', colour: true },
  { key: 'rockNormal', file: 'dark_rock_02_nor_gl_1k.jpg', colour: false },
];

// The browser's image element loads each file; three.js's texture loader is not used, because a three.js class that only High
// uses would be kept in the one copy of three.js that Standard visitors download too (ui/test/high.test.mjs).
const imageLoader = {
  load(url, onLoad, _onProgress, onError) {
    const img = new globalThis.Image();
    img.onload = () => {
      const tex = new THREE.Texture(img);
      tex.needsUpdate = true;
      onLoad(tex);
    };
    img.onerror = onError;
    img.src = url;
  },
};

// base must be a path on the site's own host ("/high/"): no scheme, no host, no "//". One file that fails fails the whole load,
// so High never draws with a part missing; the caller then keeps Standard.
export function loadTextures(base = '/high/', loader = null) {
  if (!/^\/[a-z0-9_/-]*\/$/.test(base) || base.includes('//')) return Promise.reject(new Error('High assets come from the site\'s own host only'));
  const l = loader || imageLoader;
  return Promise.all(ASSETS.map((a) => new Promise((resolve, reject) => {
    l.load(base + a.file, (tex) => {
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.colorSpace = a.colour ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      tex.anisotropy = 8;
      tex.generateMipmaps = true;
      tex.minFilter = THREE.LinearMipmapLinearFilter;
      resolve([a.key, tex]);
    }, undefined, () => reject(new Error(`a High asset did not load: ${a.file}`)));
  }))).then(Object.fromEntries);
}
