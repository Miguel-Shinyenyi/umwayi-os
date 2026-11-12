'use client';
// The only code of the site that runs in the browser. After the server HTML is there, it starts the shared page script
// (ui/src/boot.js): the device query, the List, Standard and High switch and the picture, built by ui/src/scene.js. It renders nothing.
// The hints the query reads stay in the browser and are never sent anywhere. The site offers High (UI.7) and counts the
// network because the site is served over one. The scene code is fetched from the site's own host only when the device query
// chooses a scene tier, and the High code and its photographs only when it chooses High: a visitor on List downloads neither,
// a visitor on Standard never downloads High.
import { useEffect } from 'react';
import { boot } from '../../ui/src/boot.js';

export function Scene() {
  useEffect(() => {
    const page = boot(
      window,
      { maxTier: 3, local: false, loadHigh: () => import('../../ui/src/high/index.js') },
      () => import('../../ui/src/app.js').then((m) => m.createApp),
    );
    return () => page.stop();
  }, []);
  return null;
}
