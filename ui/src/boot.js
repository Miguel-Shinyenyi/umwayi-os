// Starts a page: the device query, the tier switch and the picture (12.R16). The owner's live view (main.js) and the public site
// (site/app/scene.js) both call boot, so the device query is one function and not two. The page is List (tier 1) in its HTML; this
// picks the tier from the device and starts the picture for Standard. The hints the query reads (env.js) stay in the page: nothing
// here sends, stores or writes them to the address. The only thing written to the address is the tier name, in the fragment.
import { createApp } from './app.js';
import { setTier } from './ui/fallback.js';
import { initHome } from './ui/home.js';
import { chooseTier, parseTier, tierHash, TIERS } from './engine/tier.js';
import { readEnv } from './engine/env.js';

const NO_WEBGL = 'This browser cannot draw the picture (no WebGL). The List view shows the same stations.';
const FAILED = 'The picture could not start in this browser. The List view shows the same stations.';

// options: { maxTier, local }. The live view passes a highest tier of Standard and ignores the network (it is a file on disk).
// Returns { stop } so a page that is torn down (the site, when its component unmounts) can take the listeners off again.
export function boot(win, options) {
  const doc = win.document;
  doc.documentElement.setAttribute('data-js', '');
  const stopHome = initHome(doc, win);
  const env = readEnv(win);
  let app = null;

  function startScene() {
    if (app) return true;
    try {
      app = createApp(win);
      app.onLost = () => { env.webgl = false; use(chooseTier(env, options), 'The picture stopped. The List view shows the same stations.'); };
      app.start();
      return true;
    } catch {
      app = null;
      return false;
    }
  }

  function use(choice, message = '') {
    if (choice.tier >= 2) {
      setTier(doc, 'standard', choice.warn ? 'You chose Standard. The picture may be slow on this device.' : '');
      if (startScene()) { app.setFlat(false); return; }
      env.webgl = false;
      message = FAILED;
    }
    setTier(doc, 'list', message);
    if (app) app.setFlat(true);
  }

  const first = chooseTier(env, { ...options, requested: parseTier(win.location.hash) });
  use(first, first.reason === 'no-webgl' ? NO_WEBGL : '');

  const clicks = [];
  doc.querySelectorAll('#tiers button[data-tier]').forEach((b) => {
    const onClick = () => {
      const tier = TIERS.find((t) => t.name === b.dataset.tier).tier;
      win.history.replaceState(null, '', tierHash(win.location.hash, tier)); // the fragment only: it never leaves the browser
      const choice = chooseTier(env, { ...options, requested: tier });
      use(choice, choice.reason === 'no-webgl' ? NO_WEBGL : '');
    };
    b.addEventListener('click', onClick);
    clicks.push([b, onClick]);
  });
  return { stop() { clicks.forEach(([b, f]) => b.removeEventListener('click', f)); if (stopHome) stopHome(); } };
}
