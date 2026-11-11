// UI.6 (tests first): the security headers (12.R17.5) and the settings that keep the site to its own origin.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import config from '../next.config.mjs';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const rules = await config.headers();
const all = rules.find((r) => r.source === '/(.*)');
const header = (name) => all?.headers.find((x) => x.key === name)?.value;
const directives = (csp) => Object.fromEntries(csp.split(';').map((d) => d.trim()).filter(Boolean).map((d) => { const [k, ...v] = d.split(/\s+/); return [k, v]; }));

test('every path gets the headers', () => {
  assert.ok(all, 'no rule for /(.*)');
  assert.equal(rules.length, 1);
});

test('the Content-Security-Policy allows the site\'s own origin only: no remote script, style, font, image or connection', () => {
  const csp = header('Content-Security-Policy');
  assert.ok(csp, 'no Content-Security-Policy');
  const d = directives(csp);
  assert.deepEqual(d['default-src'], ["'self'"]);
  assert.ok(!/https?:|\/\/|\*|\bdata:(?!.*img)/.test(csp.replace(/img-src[^;]*/, '')), `an address or a wildcard in ${csp}`);
  for (const k of Object.keys(d)) for (const v of d[k]) assert.ok(/^'(self|none|unsafe-inline|sha256-[A-Za-z0-9+/=]+)'$|^(data:|blob:)$/.test(v), `${k} allows ${v}`);
  assert.deepEqual(d['script-src'].filter((v) => v !== "'self'" && !v.startsWith("'sha256-")), d['script-src'].includes("'unsafe-inline'") ? ["'unsafe-inline'"] : []);
  assert.ok(!d['default-src'].includes("'unsafe-inline'") && !(d['style-src'] || []).includes("'unsafe-inline'"), 'unsafe-inline is allowed for scripts only');
  assert.ok(!csp.includes('unsafe-eval'), 'unsafe-eval is for development only and is never in the headers');
  assert.deepEqual(d['object-src'], ["'none'"]);
  assert.deepEqual(d['base-uri'], ["'self'"]);
  assert.deepEqual(d['form-action'], ["'self'"]);
  assert.deepEqual(d['frame-ancestors'], ["'none'"]);
  for (const k of ['connect-src', 'font-src', 'img-src', 'media-src', 'worker-src', 'frame-src']) {
    if (d[k]) assert.ok(d[k].every((v) => ["'self'", "'none'", 'data:', 'blob:'].includes(v)), `${k}: ${d[k]}`);
  }
  assert.ok(!d['font-src'] || d['font-src'].every((v) => v === "'self'" || v === "'none'"), 'a font may come from the site only');
  assert.ok(!d['img-src'] || !d['img-src'].some((v) => /^https?:/.test(v)), 'no remote image');
});

test('no referrer is sent', () => {
  assert.equal(header('Referrer-Policy'), 'no-referrer');
});

test('no sniffing and no framing', () => {
  assert.equal(header('X-Content-Type-Options'), 'nosniff');
  assert.equal(header('X-Frame-Options'), 'DENY');
});

test('the Permissions-Policy switches everything off but writing to the clipboard (the Copy buttons)', () => {
  const pp = header('Permissions-Policy');
  assert.ok(pp, 'no Permissions-Policy');
  for (const f of ['camera', 'microphone', 'geolocation', 'payment', 'usb', 'interest-cohort']) assert.match(pp, new RegExp(`${f}=\\(\\)`), f);
  assert.match(pp, /clipboard-write=\(self\)/);
});

test('the site is built from the repo root so it can import the shared scene, and three resolves to one copy', () => {
  const text = readFileSync(join(site, 'next.config.mjs'), 'utf8');
  assert.ok(/turbopack/.test(text) && /root/.test(text), 'turbopack.root is not set');
  assert.ok(/resolveAlias/.test(text) && /three/.test(text), 'three is not aliased to the site copy');
  assert.ok(!/images\s*:\s*\{[^}]*remotePatterns/.test(text), 'a remote image pattern');
  assert.ok(!/rewrites|redirects|assetPrefix|basePath/.test(text), 'nothing may send a visitor or a fetch to another host');
});

test('telemetry is switched off for every npm script (NEXT_TELEMETRY_DISABLED=1)', () => {
  const pkg = JSON.parse(readFileSync(join(site, 'package.json'), 'utf8'));
  const run = readFileSync(join(site, 'scripts', 'next.mjs'), 'utf8');
  assert.match(run, /NEXT_TELEMETRY_DISABLED\s*[:=]\s*['"]1['"]/);
  for (const name of ['dev', 'build', 'start']) assert.match(pkg.scripts[name], /scripts\/next\.mjs/, name);
  assert.equal(pkg.scripts.test, 'node --test');
});
