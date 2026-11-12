// Starts a page: the device query, the tier switch and the picture (12.R16). The owner's live view (main.js) and the public site
// (site/app/scene.js) both call boot, so the device query is one function and not two. The page is List (tier 1) in its HTML; this
// picks the tier from the device and starts the picture for Standard. The hints the query reads (env.js) stay in the page: nothing
// here sends, stores or writes them to the address. The only thing written to the address is the tier name, in the fragment.
import { setTier } from './ui/fallback.js';
import { initHome } from './ui/home.js';
import { initSnapshot } from './ui/snapshot.js';
import { viewOf } from './data/snapshot.js';
import { chooseTier, parseTier, tierHash, TIERS } from './engine/tier.js';
import { readEnv } from './engine/env.js';

const NO_WEBGL = 'This browser cannot draw the picture (no WebGL). The List view shows the same stations.';
const FAILED = 'The picture could not start in this browser. The List view shows the same stations.';

// options: { maxTier, local }. The live view passes a highest tier of Standard and ignores the network (it is a file on disk).
// loadApp() gives a promise of createApp: the live view has the code in its one file already, the site fetches it from its own host
// only when a scene tier is chosen, so a visitor on List (a slow network, Save-Data, no WebGL) never downloads the 3D code.
// Returns { stop } so a page that is torn down (the site, when its component unmounts) can take the listeners off again.
export function boot(win, options, loadApp) {
  const doc = win.document;
  doc.documentElement.setAttribute('data-js', '');
  const stopHome = initHome(doc, win);
  const env = readEnv(win);
  let app = null, loading = null, turn = 0;
  // What the page shows: the sample world, until the owner (or a visitor) opens a snapshot file. The file is read in this browser
  // and nowhere else (ui/snapshot.js). A scene that starts later starts with it; one that is running is told with setData.
  let view = viewOf(null);
  const snapshot = initSnapshot(doc, win, { onView(next) { view = next; if (app) app.setData(next); } });

  function startScene() {
    if (app) return Promise.resolve(true);
    loading ||= loadApp().then((createApp) => {
      app = createApp(win, view);
      app.onLost = () => { env.webgl = false; use(chooseTier(env, options), 'The picture stopped. The List view shows the same stations.'); };
      app.start();
      return true;
    }).catch(() => {
      app = null;
      return false;
    }).finally(() => { loading = null; });
    return loading;
  }

  // The newest choice wins: a scene that finishes loading after the visitor chose List is built but not shown.
  function use(choice, message = '') {
    const mine = ++turn;
    if (choice.tier >= 2) {
      setTier(doc, 'standard', choice.warn ? 'You chose Standard. The picture may be slow on this device.' : '');
      startScene().then((ok) => {
        if (mine !== turn) return;
        if (ok) { app.setFlat(false); return; }
        env.webgl = false;
        setTier(doc, 'list', FAILED);
        if (app) app.setFlat(true);
      });
      return;
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
  return { stop() { clicks.forEach(([b, f]) => b.removeEventListener('click', f)); snapshot.stop(); if (stopHome) stopHome(); } };
}
