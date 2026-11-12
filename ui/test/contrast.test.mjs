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

test('no name is written in the picture at rest: the buttons over the features are invisible until hover, focus or selection', () => {
  const rule = (sel) => { const i = css.indexOf(sel); return css.slice(css.indexOf('{', i) + 1, css.indexOf('}', i)); };
  const base = rule('.label {');
  assert.match(base, /opacity:\s*0\s*;/, 'a button over a feature starts invisible');
  assert.match(base, /pointer-events:\s*none/, 'and does not catch the pointer: the picture does');
  const shown = rule('.label:focus-visible, .label.is-hover, .label.is-selected');
  assert.match(shown, /opacity:\s*1\s*;/, 'hover, focus and selection show the name');
  assert.ok(!/opacity:\s*1/.test(base));
});

// ---- UI.5: every text colour against every ground it sits on, worked out from the CSS (12.R6.3, UI-Q9). The glass panel over
// the sky is not checked (the owner cut that on Nov 11): the grounds below are the page base, the solid panel colour, the glass
// over the page base, and the dark wells (code blocks, fields) over each of them.
const rgba = (s) => {
  const m = /rgba\(\s*(\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\s*\)/.exec(s);
  return m ? { c: [Number(m[1]), Number(m[2]), Number(m[3])], a: Number(m[4]) } : null;
};
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const over = (top, under) => '#' + under.map((u, i) => Math.round(top.c[i] * top.a + u * (1 - top.a)).toString(16).padStart(2, '0')).join('');
const varsRaw = (text) => Object.fromEntries([...text.matchAll(/--([a-z-]+):\s*([^;]+);/gi)].map((m) => [m[1], m[2].trim()]));
const rawNormal = varsRaw(block(':root'));
const rawCalm = { ...rawNormal, ...varsRaw(block('html[data-calm="1"]')) };
const wells = [...css.matchAll(/background:\s*(rgba\(0, 0, 0, [\d.]+\))/g)].map((m) => rgba(m[1]));

function grounds(raw) {
  const base = raw.base, solid = raw['glass-solid'], glass = over(rgba(raw.glass), hexRgb(base));
  const g = { base, 'glass-solid': solid, 'glass over base': glass };
  for (const w of wells) for (const [name, hex] of Object.entries({ base, 'glass-solid': solid, 'glass over base': glass })) g[`well ${w.a} over ${name}`] = over(w, hexRgb(hex));
  return g;
}

test('UI.5: ink and muted text keep 4.5 to 1 on every ground the CSS puts them on, in normal and in Calm mode', () => {
  assert.ok(wells.length >= 4, 'the dark wells of the code blocks, fields and notes box are found in the CSS');
  for (const [mode, raw] of [['normal', rawNormal], ['calm', rawCalm]]) {
    for (const [gname, ground] of Object.entries(grounds(raw))) {
      for (const t of ['ink', 'muted']) assert.ok(ratio(raw[t], ground) >= 4.5, `${mode}: ${t} on ${gname} is ${ratio(raw[t], ground).toFixed(2)}`);
    }
  }
});

test('UI.5: no text colour in the CSS is a literal: every colour property is the ink, the muted colour, the amber, or inherited', () => {
  const used = [...css.matchAll(/(?<![-\w])color:\s*([^;}]+)[;}]/g)].map((m) => m[1].trim());
  assert.ok(used.length > 15);
  for (const u of used) assert.match(u, /^(var\(--(ink|muted|amber)\)|inherit|currentColor)$/, u);
});

test('UI.5: the placeholder of a result field is coloured on purpose (the browser default is too faint) and keeps 4.5 to 1', () => {
  const ph = css.match(/::placeholder\s*\{([^}]*)\}/);
  assert.ok(ph, 'a ::placeholder rule');
  assert.match(ph[1], /color:\s*var\(--muted\)/);
  assert.match(ph[1], /opacity:\s*1/, 'Firefox dims a placeholder unless told not to');
});

test('UI.5: the border of a result field and of the notes box keeps 3 to 1 against what is inside and what is around it (WCAG 1.4.11)', () => {
  const rules = [css.match(/\.steps input\[type="text"\]\s*\{([^}]*)\}/)[1], css.match(/#checks-export\s*\{([^}]*)\}/)[1]];
  for (const r of rules) assert.match(r, /border:\s*1px solid var\(--field-line\)/);
  for (const [mode, raw] of [['normal', rawNormal], ['calm', rawCalm]]) {
    assert.ok(raw['field-line'], `${mode} has --field-line`);
    const g = grounds(raw);
    for (const [gname, ground] of Object.entries(g)) {
      if (gname.startsWith('well')) continue;
      assert.ok(ratio(raw['field-line'], ground) >= 3, `${mode}: the field border on ${gname} is ${ratio(raw['field-line'], ground).toFixed(2)}`);
    }
    for (const gname of Object.keys(g).filter((k) => k.startsWith('well'))) assert.ok(ratio(raw['field-line'], g[gname]) >= 3, `${mode}: the field border against ${gname}`);
  }
});

test('UI.5: the focus ring keeps 3 to 1 on the page, on the solid panel and on the glass, in both modes', () => {
  const ring = { normal: rawNormal.amber, calm: /html\[data-calm="1"\] :focus-visible\s*\{\s*outline-color:\s*(#[0-9a-f]{6})/i.exec(css)[1] };
  for (const [mode, raw] of [['normal', rawNormal], ['calm', rawCalm]]) {
    for (const gname of ['base', 'glass-solid', 'glass over base']) assert.ok(ratio(ring[mode], grounds(raw)[gname]) >= 3, `${mode} ${gname}`);
  }
});

test('UI.5: Calm mode keeps its text above the floor and below the normal contrast, for the dark wells too', () => {
  const n = grounds(rawNormal), c = grounds(rawCalm);
  for (const g of Object.keys(n)) assert.ok(ratio(rawCalm.ink, c[g]) < ratio(rawNormal.ink, n[g]) + 1e-9, g);
  const floor = Math.min(...Object.keys(c).flatMap((g) => ['ink', 'muted'].map((t) => ratio(rawCalm[t], c[g]))));
  assert.ok(floor >= 4.5 && floor < 12, floor.toFixed(2));
});
