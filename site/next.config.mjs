// The site's settings: the security headers (12.R17.5), the repo root as the build root so the site can import the shared scene from
// ../ui/src, and one copy of three.js (the site's own) for both the site and the shared scene.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const site = dirname(fileURLToPath(import.meta.url));
const repo = join(site, '..');

// The policy allows the site's own origin only: no remote script, style, font, image or connection.
// Scripts: 'self' alone was tried in the browser pass and it blocks the three small inline scripts that Next.js writes into every
// page (its page data and start-up), so the page never starts. 'unsafe-inline' for scripts is the smallest change that works with a
// static page; a script from another host is still refused. A nonce would be stricter but makes every page render per visit
// (open question in the pull request and in docs/interface.md). Styles stay at 'self': the page needs no inline style.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self'",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

const permissions = [
  'accelerometer=()', 'autoplay=()', 'camera=()', 'display-capture=()', 'geolocation=()', 'gyroscope=()',
  'interest-cohort=()', 'magnetometer=()', 'microphone=()', 'midi=()', 'payment=()', 'usb=()', 'clipboard-write=(self)',
].join(', ');

export default {
  reactStrictMode: true,
  poweredByHeader: false,
  turbopack: {
    root: repo,
    // the shared scene lives in ../ui/src and imports 'three'; both resolve to the site's own copy
    resolveAlias: { three: './node_modules/three/build/three.module.js', 'three/addons/*': './node_modules/three/examples/jsm/*' },
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Permissions-Policy', value: permissions },
        ],
      },
    ];
  },
};
