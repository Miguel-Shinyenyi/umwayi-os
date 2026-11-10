// UI-Q9: Calm mode lowers contrast, but text keeps at least 4.5 to 1 (WCAG 1.4.3, level AA) in both modes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'style.css'), 'utf8');
const block = (start) => {
  const i = css.indexOf(start);
  return css.slice(css.indexOf('{', i) + 1, css.indexOf('}', i));
};
const vars = (text) => Object.fromEntries([...text.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})\s*;/gi)].map((m) => [m[1], m[2]]));
const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

const normal = vars(block(':root'));
const calm = { ...normal, ...vars(block('html[data-calm="1"]')) };

test('text keeps 4.5 to 1 against the page and against the solid panel colour, in normal and in Calm mode', () => {
  for (const [mode, v] of [['normal', normal], ['calm', calm]]) {
    for (const text of ['ink', 'muted']) {
      for (const ground of ['base', 'glass-solid']) {
        assert.ok(ratio(v[text], v[ground]) >= 4.5, `${mode}: ${text} on ${ground} is ${ratio(v[text], v[ground]).toFixed(2)}`);
      }
    }
  }
});

test('Calm mode really is lower contrast than normal', () => {
  assert.ok(ratio(calm.ink, calm.base) < ratio(normal.ink, normal.base));
  assert.ok(ratio(calm.muted, calm.base) < ratio(normal.muted, normal.base));
});

test('there is no large pure white in the palette: the brightest colour is the ink', () => {
  for (const hex of Object.values(normal)) assert.ok(lum(hex) < 0.9, hex);
});
