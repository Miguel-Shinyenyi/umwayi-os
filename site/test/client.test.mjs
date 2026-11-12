// UI.6 (tests first): the client part. The browser reads the device hints and draws the scene from the shared module; nothing
// is sent anywhere. The pages are checked in a real browser by hand (docs/interface.md); these tests read the source.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (name) => readFileSync(join(site, name), 'utf8');
const walk = (dir) => readdirSync(dir).flatMap((n) => (['node_modules', '.next'].includes(n) ? [] : statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));
const sources = walk(site).filter((f) => /\.(js|mjs|css|json)$/.test(f) && !f.endsWith('package-lock.json') && !relative(site, f).startsWith('test'));

test('app/scene.js is a client component that starts the shared page script, up to High, with the network counted', () => {
  const text = read('app/scene.js');
  assert.match(text, /^['"]use client['"]/);
  assert.match(text, /ui\/src\/boot\.js/, 'it does not use the shared boot module');
  assert.match(text, /import\(['"]\.\.\/\.\.\/ui\/src\/app\.js['"]\)/, 'the scene code is not fetched on demand, so a List visitor would download it');
  assert.ok(!/^import .*ui\/src\/app\.js/m.test(text), 'the scene code is imported at the top, so every visitor downloads it');
  assert.match(text, /maxTier:\s*3/, 'the site offers High (UI.7)');
  assert.match(text, /loadHigh:\s*\(\)\s*=>\s*import\(['"]\.\.\/\.\.\/ui\/src\/high\/index\.js['"]\)/, 'the High code is not fetched on demand, so a Standard visitor would download it');
  assert.ok(!/^import .*ui\/src\/high/m.test(text), 'the High code is imported at the top, so every visitor downloads it');
  assert.match(text, /local:\s*false/, 'the site is served over a network, so the network counts');
  assert.match(text, /useEffect/, 'the picture starts in the browser, after the server HTML');
});

test('the site draws through the shared module (ui/src/scene.js via boot.js and app.js): it has no file of its own that builds a world', () => {
  for (const f of sources) {
    const text = readFileSync(f, 'utf8');
    assert.ok(!/from ['"]three['"]/.test(text) || f.endsWith('next.config.mjs'), `${relative(site, f)} imports three itself`);
    assert.ok(!/buildWorld|createStage|createScene/.test(text) || relative(site, f).startsWith('test'), `${relative(site, f)} builds the scene itself`);
  }
});

test('the device hints go nowhere: no request, no storage, no cookie, no beacon, no analytics call in any site source', () => {
  for (const f of sources) {
    const text = readFileSync(f, 'utf8');
    for (const bad of ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'localStorage', 'sessionStorage', 'indexedDB', 'document.cookie', 'navigator.connection', 'hardwareConcurrency', 'deviceMemory', 'WEBGL_debug_renderer_info', 'gtag', 'dataLayer']) {
      assert.ok(!text.includes(bad), `${relative(site, f)} contains ${bad}`);
    }
  }
});

test('no remote font, script or image: no next/font, no next/script, no next/image, no link or script tag with an address', () => {
  for (const f of sources) {
    const text = readFileSync(f, 'utf8');
    for (const bad of ['next/font', 'next/script', 'next/image', '@vercel/', '@next/third-parties', '@import', 'url(http', "src=\"http", 'src: "http', 'href="http://', 'googleapis', 'gstatic']) {
      assert.ok(!text.includes(bad), `${relative(site, f)} contains ${bad}`);
    }
  }
});

test('the layout puts the page in List and uses the live view style file, not a copy of it', () => {
  const text = read('app/layout.js');
  assert.match(text, /ui\/src\/style\.css/);
  assert.match(text, /Document/);
  assert.ok(!sources.some((f) => f.endsWith('.css')), 'the site has a style file of its own; it must use ui/src/style.css');
});

test('no file of the site is a copy of a file of ui/src', () => {
  const ui = join(site, '..', 'ui', 'src');
  const theirs = new Map(walk(ui).map((f) => [readFileSync(f, 'utf8'), relative(ui, f)]));
  for (const f of walk(site)) {
    if (!statSync(f).isFile() || statSync(f).size < 40) continue;
    const text = readFileSync(f, 'utf8');
    assert.ok(!theirs.has(text), `${relative(site, f)} is a copy of ui/src/${theirs.get(text)}`);
  }
});
