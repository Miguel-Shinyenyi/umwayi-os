// Entry point. The page is List (tier 1) in its HTML; this picks the tier from the device (12.R16) and starts the picture
// for Standard. The owner's live view has no High (12.R18.2) and ignores the network: it is a file on disk.
import { createApp } from './app.js';
import { setTier } from './ui/fallback.js';
import { initHome } from './ui/home.js';
import { chooseTier, parseTier, tierHash, TIERS } from './engine/tier.js';
import { readEnv } from './engine/env.js';

const doc = document;
doc.documentElement.setAttribute('data-js', '');
initHome(doc, window);

const OPTIONS = { maxTier: 2, local: true };
const env = readEnv(window);
const NO_WEBGL = 'This browser cannot draw the picture (no WebGL). The List view shows the same stations.';
const FAILED = 'The picture could not start in this browser. The List view shows the same stations.';
let app = null;

function startScene() {
  if (app) return true;
  try {
    app = createApp(window);
    app.onLost = () => { env.webgl = false; use(chooseTier(env, OPTIONS), 'The picture stopped. The List view shows the same stations.'); };
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

const first = chooseTier(env, { ...OPTIONS, requested: parseTier(location.hash) });
use(first, first.reason === 'no-webgl' ? NO_WEBGL : '');

doc.querySelectorAll('#tiers button[data-tier]').forEach((b) => b.addEventListener('click', () => {
  const tier = TIERS.find((t) => t.name === b.dataset.tier).tier;
  history.replaceState(null, '', tierHash(location.hash, tier)); // the fragment only: it never leaves the browser
  const choice = chooseTier(env, { ...OPTIONS, requested: tier });
  use(choice, choice.reason === 'no-webgl' ? NO_WEBGL : '');
}));
