// The High tier (12.R16.3, 12.R16.4), for the public site only. boot.js calls upgrade() after the Standard scene has drawn its
// first frame: the asset files load from the site's own host, then applyHigh adds the High scene on top of Standard and the
// picture is drawn again. Any failure rejects with nothing left in the scene, and the page stays Standard.
import { loadTextures } from './assets.js';
import { applyHigh } from './build.js';

// app: what createApp returns (world, loop). options: base (the path of the files), loader (a texture loader, for the tests)
export async function upgrade(app, { base = '/high/', loader } = {}) {
  const textures = await loadTextures(base, loader);
  let high;
  try {
    high = applyHigh(app.world, textures);
  } catch (e) {
    for (const t of Object.values(textures)) t.dispose?.();
    throw e;
  }
  app.loop.invalidate();
  return {
    remove() {
      high.remove();
      for (const t of Object.values(textures)) t.dispose?.();
      app.loop.invalidate();
    },
  };
}
