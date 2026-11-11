'use client';
// The only code of the site that runs in the browser. After the server HTML is there, it starts the shared page script
// (ui/src/boot.js): the device query, the List and Standard switch and the picture, built by ui/src/scene.js. It renders nothing.
// The hints the query reads stay in the browser and are never sent anywhere. The site draws Standard at most for now
// (High is UI.7), and counts the network because the site is served over one. The scene code is fetched from the site's own
// host only when the device query chooses a scene tier: a visitor on List never downloads it.
import { useEffect } from 'react';
import { boot } from '../../ui/src/boot.js';

export function Scene() {
  useEffect(() => {
    const page = boot(window, { maxTier: 2, local: false }, () => import('../../ui/src/app.js').then((m) => m.createApp));
    return () => page.stop();
  }, []);
  return null;
}
