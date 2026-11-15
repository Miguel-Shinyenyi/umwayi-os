// W51a: the owner's logo is the site's icon. Next.js serves site/app/icon.png and site/app/apple-icon.png by its file convention
// and writes the link tags into the head of every page. Both files are byte for byte the owner's file ui/assets/amwayi-logo-512.png
// (no resizing, no image library: the size is read from the PNG header), and the built home page names both icons.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildOnce } from '../scripts/build-once.mjs';

const SITE = join(dirname(fileURLToPath(import.meta.url)), '..');
const LOGO = readFileSync(join(SITE, '..', 'ui', 'assets', 'amwayi-logo-512.png'));
const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

// the width and height of a PNG from its first chunk, which must be IHDR (bytes 12 to 15 name it, 16 to 23 hold the size)
function pngSize(buf) {
  assert.ok(buf.subarray(0, 8).equals(SIGNATURE), 'not a PNG signature');
  assert.equal(buf.subarray(12, 16).toString('latin1'), 'IHDR', 'the first chunk is not IHDR');
  return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
}

for (const name of ['icon.png', 'apple-icon.png']) {
  test(`app/${name} is the owner's logo, byte for byte, a PNG of 512 by 512`, () => {
    const buf = readFileSync(join(SITE, 'app', name));
    assert.ok(buf.equals(LOGO), `${name} is not the same bytes as ui/assets/amwayi-logo-512.png`);
    assert.deepEqual(pngSize(buf), { w: 512, h: 512 });
  });
}

test('the reader of the PNG header refuses what is not a 512 by 512 PNG (planted faults)', () => {
  const small = Buffer.from(LOGO);
  small.writeUInt32BE(256, 16);
  assert.deepEqual(pngSize(small), { w: 256, h: 512 });
  const bad = Buffer.from(LOGO);
  bad[1] = 0;
  assert.throws(() => pngSize(bad));
  const noIhdr = Buffer.from(LOGO);
  noIhdr.write('IDAT', 12, 'latin1');
  assert.throws(() => pngSize(noIhdr));
});

test('the built home page names the icon and the apple touch icon in its head', () => {
  const built = buildOnce();
  assert.equal(built.status, 0, `next build failed: ${built.out}`);
  const html = readFileSync(join(SITE, '.next', 'server', 'app', 'index.html'), 'utf8');
  const head = html.slice(0, html.indexOf('</head>'));
  assert.match(head, /<link rel="icon" href="\/icon\.png\?[^"]*" sizes="512x512" type="image\/png"\/>/);
  assert.match(head, /<link rel="apple-touch-icon" href="\/apple-icon\.png\?[^"]*" sizes="512x512" type="image\/png"\/>/);
});
