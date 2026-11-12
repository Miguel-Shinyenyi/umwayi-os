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
const HIGH_LOADING = 'Loading High. This is Standard until it is ready.';
const HIGH_WARN = 'You chose High. It loads more and may be slow on this device.';
const HIGH_FAILED = 'High could not start in this browser, so this is Standard.';
const HIGH_SLOW = 'High took too long to load, so this is Standard.';
// how long High may take to load and build before the page gives up and stays Standard
export const HIGH_TIMEOUT_MS = 15000;

// options: { maxTier, local, loadHigh }. The live view passes a highest tier of Standard and ignores the network (it is a file on
// disk), and has no loadHigh. The public site passes a highest tier of High and loadHigh(), a promise of the High module
// (ui/src/high): Standard draws first, then High is built on top of it; a failed or slow High leaves Standard and says why.
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

  // High, on top of a drawn Standard scene: high is { remove } while it is on
  let high = null;
  const highState = (s) => { if (options.loadHigh) doc.documentElement.setAttribute('data-high', s); };
  function dropHigh() {
    if (high) { high.remove(); high = null; }
    if (options.loadHigh) highState('off');
  }
  function startHigh(mine, warn) {
    if (high) { setTier(doc, 'high', warn ? HIGH_WARN : ''); highState('on'); return; }
    highState('loading'); // use() has already shown High with the loading words
    let late = false;
    const timer = win.setTimeout(() => {
      late = true;
      if (mine !== turn) return;
      highState('failed');
      setTier(doc, 'standard', HIGH_SLOW);
    }, HIGH_TIMEOUT_MS);
    Promise.resolve().then(() => options.loadHigh()).then((m) => m.upgrade(app)).then((h) => {
      win.clearTimeout(timer);
      if (late || mine !== turn) { h.remove(); return; } // too late, or the visitor chose another tier meanwhile
      high = h;
      highState('on');
      setTier(doc, 'high', warn ? HIGH_WARN : '');
    }, () => {
      win.clearTimeout(timer);
      if (late || mine !== turn) return;
      highState('failed');
      setTier(doc, 'standard', HIGH_FAILED);
    });
  }

  // The newest choice wins: a scene that finishes loading after the visitor chose List is built but not shown.
  function use(choice, message = '') {
    const mine = ++turn;
    if (choice.tier >= 2) {
      const wantHigh = choice.tier >= 3 && !!options.loadHigh;
      setTier(doc, wantHigh ? 'high' : 'standard', wantHigh ? HIGH_LOADING : choice.warn ? 'You chose Standard. The picture may be slow on this device.' : '');
      startScene().then((ok) => {
        if (mine !== turn) return;
        if (ok) {
          app.setFlat(false);
          if (wantHigh) startHigh(mine, choice.warn);
          else if (high || options.loadHigh) dropHigh();
          return;
        }
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
