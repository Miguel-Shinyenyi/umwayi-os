// A small driver for a Chromium that is already installed, used by the phone layout tests (W1). It speaks the Chrome DevTools
// Protocol over the WebSocket that Node 22 has built in, so it adds no package: nothing is installed, nothing is downloaded and
// umwayi never runs it. A test calls findBrowser(); with no browser it returns null and the test skips and says how to run it.
//
// Which browser: the file named by UMWAYI_BROWSER, else the first of google-chrome, chromium, chrome-headless-shell and so on
// found on PATH, else a Playwright download under ~/.cache/ms-playwright. The browser is started with a throwaway profile, with
// no extension and no sandbox flag but --no-sandbox (a container has no user namespace), and listens on 127.0.0.1 only.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';

const NAMES = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome-headless-shell'];

// Chrome may still be writing into its profile folder for a moment after it is killed, so a delete can fail with ENOTEMPTY.
// Try again (rmSync retries too, and this loop covers a delete that still reports it); any other error is thrown at once, and so
// is ENOTEMPTY when it keeps coming after the last try. `rm` and `sleep` are arguments so a test can fake them.
const sleepSync = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
export function removeProfile(dir, rm = rmSync, sleep = sleepSync) {
  const opts = { recursive: true, force: true, maxRetries: 5, retryDelay: 200 };
  for (let attempt = 0; ; attempt += 1) {
    try { rm(dir, opts); return; } catch (e) {
      if (e?.code !== 'ENOTEMPTY' || attempt >= 5) throw e;
      sleep(200);
    }
  }
}

export function findBrowser(env = process.env) {
  if (env.UMWAYI_BROWSER) return existsSync(env.UMWAYI_BROWSER) ? env.UMWAYI_BROWSER : null;
  for (const dir of (env.PATH || '').split(delimiter)) {
    for (const name of NAMES) if (dir && existsSync(join(dir, name))) return join(dir, name);
  }
  const cache = join(homedir(), '.cache', 'ms-playwright');
  if (existsSync(cache)) {
    for (const d of readdirSync(cache).sort().reverse()) {
      for (const sub of ['chrome-headless-shell-linux64/chrome-headless-shell', 'chrome-linux/chrome', 'chrome-linux64/chrome']) {
        const p = join(cache, d, sub);
        if (existsSync(p)) return p;
      }
    }
  }
  return null;
}

export const HOW_TO_RUN = 'No Chromium found. Install one (for example Google Chrome, or `npx playwright-core install chromium-headless-shell`) '
  + 'or set UMWAYI_BROWSER to its file, then run this test again. The phone layout check is by hand without it: open ui/dist/index.html '
  + 'in a browser, use the device toolbar at 375 by 667, 390 by 844, 412 by 915 and 360 by 640, in portrait and landscape.';

export async function launch(exe, { timeoutMs = 20000 } = {}) {
  const profile = mkdtempSync(join(tmpdir(), 'umwayi-browser-'));
  const args = ['--headless', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-sandbox', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-background-networking', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
    '--hide-scrollbars', 'about:blank'];
  const child = spawn(exe, args, { stdio: ['ignore', 'ignore', 'pipe'] });
  const endpoint = await new Promise((resolve, reject) => {
    let text = '';
    const timer = setTimeout(() => reject(new Error('the browser did not start in time')), timeoutMs);
    child.stderr.on('data', (d) => {
      text += d;
      const m = /DevTools listening on (ws:\/\/\S+)/.exec(text);
      if (m) { clearTimeout(timer); resolve(m[1]); }
    });
    child.on('exit', (code) => { clearTimeout(timer); reject(new Error(`the browser exited with ${code}`)); });
  });
  const ws = new WebSocket(endpoint);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = () => reject(new Error('no DevTools connection')); });
  let nextId = 1;
  const waiting = new Map(), listeners = [];
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && waiting.has(msg.id)) {
      const { resolve, reject } = waiting.get(msg.id);
      waiting.delete(msg.id);
      if (msg.error) reject(new Error(`${msg.error.message}`)); else resolve(msg.result);
    } else if (msg.method) {
      for (const l of listeners) l(msg);
    }
  };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = nextId++;
    waiting.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });

  async function newPage() {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const call = (method, params) => send(method, params, sessionId);
    await call('Page.enable');
    await call('Runtime.enable');
    const page = {
      call,
      // a phone: the size, a pixel ratio of 1 by default (layout is in CSS pixels; pass scale: 2 for screenshots), touch, the mobile viewport rules, and reduced motion so that nothing is moving
      async emulate({ width, height, mobile = true, reducedMotion = true, scale = 1 }) {
        await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile, screenWidth: width, screenHeight: height });
        await call('Emulation.setTouchEmulationEnabled', mobile ? { enabled: true, maxTouchPoints: 5 } : { enabled: false });
        await call('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: reducedMotion ? 'reduce' : 'no-preference' }] });
      },
      async goto(url) {
        const loaded = new Promise((resolve) => {
          const l = (msg) => { if (msg.method === 'Page.loadEventFired' && msg.sessionId === sessionId) { listeners.splice(listeners.indexOf(l), 1); resolve(); } };
          listeners.push(l);
        });
        await call('Page.navigate', { url });
        await loaded;
      },
      async evaluate(fn, arg) {
        const expression = `(${fn.toString()})(${JSON.stringify(arg === undefined ? null : arg)})`;
        const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
        if (r.exceptionDetails) throw new Error(`in the page: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
        return r.result.value;
      },
      async key(key, { shift = false } = {}) {
        const code = key === 'Tab' ? 9 : key === 'Escape' ? 27 : key === 'Enter' ? 13 : 0;
        const p = { key, code: key, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code, modifiers: shift ? 8 : 0 };
        await call('Input.dispatchKeyEvent', { type: 'rawKeyDown', ...p });
        await call('Input.dispatchKeyEvent', { type: 'keyUp', ...p });
      },
      async screenshot() { return Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'); },
      async close() { await send('Target.closeTarget', { targetId }); },
    };
    return page;
  }

  return {
    newPage,
    async version() { return (await send('Browser.getVersion')).product; },
    async close() {
      try { await send('Browser.close'); } catch { /* already gone */ }
      try { ws.close(); } catch { /* already closed */ }
      child.kill('SIGKILL');
      removeProfile(profile);
    },
  };
}
