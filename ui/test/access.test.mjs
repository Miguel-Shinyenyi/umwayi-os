// UI.5 (tests first): keyboard and screen reader access (12.R6) on the built page, as far as the code can show it: landmarks,
// names, heading order, focus order, the text alternative, live regions, a visible focus, target sizes and the phone layout of
// the panels. Nothing here hears a screen reader; docs/interface.md says what was and was not checked by hand.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { STATIONS, IDS } from '../src/stations/meta.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const page = readFileSync(join(ROOT, 'dist', 'index.html'), 'utf8');
const css = readFileSync(join(ROOT, 'src', 'style.css'), 'utf8');
const markup = page.replace(/<script\b[\s\S]*?<\/script>/g, '').replace(/<style\b[\s\S]*?<\/style>/g, '');

// ---- a small reader of the markup: every opening tag with its attributes, in order
const tags = [];
for (const m of markup.matchAll(/<([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^\s=>/]+(?:="[^"]*")?)*)\s*\/?>/g)) {
  const attrs = {};
  for (const a of m[2].matchAll(/([^\s=>/]+)(?:="([^"]*)")?/g)) attrs[a[1]] = a[2] ?? '';
  tags.push({ tag: m[1].toLowerCase(), attrs, at: m.index });
}
const all = (tag) => tags.filter((t) => t.tag === tag);
const withId = (id) => tags.find((t) => t.attrs.id === id);
const textOf = (t) => {
  const end = markup.indexOf(`</${t.tag}>`, t.at);
  return markup.slice(markup.indexOf('>', t.at) + 1, end).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
};
const hasName = (t) => (t.attrs['aria-label'] || '').trim() !== '' || textOf(t) !== '';
const rule = (sel) => { const i = css.indexOf(sel); return i < 0 ? null : css.slice(css.indexOf('{', i) + 1, css.indexOf('}', i)); };

test('the page has a language, a title, a viewport and one main landmark, one banner and one footer', () => {
  assert.match(page, /<html[^>]*\blang="en"/);
  assert.match(page, /<title>[^<]+<\/title>/);
  assert.match(page, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.equal(all('main').length, 1);
  assert.equal(all('header').length, 1);
  assert.equal(all('footer').length, 1);
  assert.equal(all('h1').length, 1);
});

test('every section, nav and aside is a named landmark, and every name points at a heading or label that exists', () => {
  for (const t of [...all('section'), ...all('aside'), ...all('nav')]) {
    const label = t.attrs['aria-label'], by = t.attrs['aria-labelledby'];
    assert.ok(label || by, `${t.tag}#${t.attrs.id} has no name`);
    if (by) {
      const target = withId(by);
      assert.ok(target, `${t.tag}#${t.attrs.id} points at ${by}, which does not exist`);
      assert.match(target.tag, /^h[1-6]$/, `${by} is a heading`);
      // the station panel's title is filled in when it opens; while it is closed the panel is hidden from the accessibility tree
      if (by !== 'panel-title') assert.ok(textOf(target) !== '', `${by} is empty in the page, so it would have no name before the script ran`);
    }
  }
});

test('the station panel and the owner checks panel are landmarks with a heading, and take focus from code only', () => {
  const panel = withId('panel');
  assert.equal(panel.tag, 'aside');
  assert.equal(panel.attrs.tabindex, '-1');
  assert.equal(panel.attrs['aria-labelledby'], 'panel-title');
  assert.equal(withId('panel-title').tag, 'h2');
  const checks = withId('checks');
  assert.equal(checks.tag, 'section');
  assert.equal(checks.attrs['aria-labelledby'], 'checks-title');
  assert.equal(withId('checks-title').tag, 'h2');
  assert.equal(withId('checks-title').attrs.tabindex, '-1');
  assert.ok('hidden' in checks.attrs);
});

test('every id is unique, and every aria-labelledby, aria-controls and aria-describedby points at an element that exists', () => {
  const ids = tags.filter((t) => 'id' in t.attrs).map((t) => t.attrs.id);
  assert.equal(new Set(ids).size, ids.length, ids.filter((x, i) => ids.indexOf(x) !== i).join());
  for (const t of tags) {
    for (const a of ['aria-labelledby', 'aria-controls', 'aria-describedby']) {
      if (t.attrs[a]) for (const id of t.attrs[a].split(/\s+/)) assert.ok(ids.includes(id), `${t.tag}#${t.attrs.id} ${a}=${id}`);
    }
  }
});

test('every button has a name, and a button that only says Copy or Replay is told apart by its aria-label or its place', () => {
  const buttons = all('button');
  assert.ok(buttons.length > 30);
  for (const b of buttons) assert.ok(hasName(b), `a button without a name: ${JSON.stringify(b.attrs)}`);
  for (const b of buttons.filter((x) => 'data-copy' in x.attrs && x.attrs['data-copy'].startsWith('cmd-'))) {
    assert.match(b.attrs['aria-label'], /^Copy: /, 'a command Copy button says which command');
  }
  assert.equal(withId('checks-copy').attrs['data-copy'], 'checks-export');
});

test('every input and text box has a name in the page or is built with one', () => {
  for (const t of [...all('input'), ...all('textarea')]) assert.ok((t.attrs['aria-label'] || '').trim() !== '' || t.attrs.id === 'snapshot-file', JSON.stringify(t.attrs));
  const built = readFileSync(join(ROOT, 'src', 'ui', 'checks.js'), 'utf8');
  for (const m of built.matchAll(/el\('input', \{([^}]*)\}/g)) assert.match(m[1], /'aria-label'/, 'the panel builds an input with no name');
  assert.equal((built.match(/el\('input'/g) || []).length, 2, 'the panel builds a checkbox and a text field for each step, and nothing else');
  assert.ok(withId('snapshot-open'), 'the hidden file input is opened by a named button');
  assert.ok('hidden' in withId('snapshot-file').attrs && withId('snapshot-file').attrs.tabindex === '-1');
});

test('headings go down one level at a time, from the one h1', () => {
  const hs = tags.filter((t) => /^h[1-6]$/.test(t.tag)).map((t) => Number(t.tag[1]));
  assert.equal(hs[0], 1);
  for (let i = 1; i < hs.length; i++) assert.ok(hs[i] <= hs[i - 1] + 1, `h${hs[i - 1]} then h${hs[i]} (heading ${i})`);
});

test('no positive tabindex, and the only tabindex values are 0 and -1', () => {
  for (const t of tags.filter((x) => 'tabindex' in x.attrs)) assert.match(t.attrs.tabindex, /^(0|-1)$/, `${t.tag}#${t.attrs.id}`);
});

test('the focus order is the order of the markup: the top bar, then the eleven names in the order of the list view, then the panel and the rest', () => {
  const tabbable = tags.filter((t) => (t.tag === 'button' || t.tag === 'a' && 'href' in t.attrs || t.tag === 'textarea' || t.tag === 'input') && t.attrs.tabindex !== '-1' && !('hidden' in t.attrs));
  const names = tabbable.map((t) => t.attrs['data-tier'] || t.attrs['data-station'] || t.attrs.id || t.tag);
  assert.deepEqual(names.slice(0, 4), ['list', 'standard', 'checks-open', 'calm-toggle']);
  assert.deepEqual(names.slice(4, 15), IDS, 'the eleven names, in the order of the list view');
  assert.deepEqual(STATIONS.map((s) => s.id), IDS);
  const after = names.slice(15);
  assert.deepEqual(after.slice(0, 6), ['replay', 'pose-prev', 'pose-next', 'station-prev', 'station-next', 'back'], 'the station panel comes next, and is not reachable while it is closed');
  assert.ok(after.indexOf('snapshot-open') > 5 && after.indexOf('checks-open-list') > after.indexOf('snapshot-open'));
  assert.ok(!names.includes('checks-copy') && !names.includes('checks-download'), 'hidden until there is something to copy');
  const list = tags.filter((t) => t.tag === 'li' && 'data-station' in t.attrs).map((t) => t.attrs['data-station']);
  assert.deepEqual(list, IDS, 'the list view has the same order');
});

test('the closed station panel cannot be reached by Tab: it is hidden from the keyboard until it opens', () => {
  const p = rule('#panel {');
  assert.match(p, /visibility:\s*hidden/);
  assert.match(rule('#panel[data-open]'), /visibility:\s*visible/);
});

test('the picture has a text alternative that says what it shows and where the list view is', () => {
  const canvas = withId('scene');
  assert.equal(canvas.attrs.role, 'img');
  const alt = canvas.attrs['aria-label'];
  for (const word of ['Kenyan highlands', 'shepherd', 'lantern', 'Mount Kenya', 'spring pool', 'drystone wall', 'sheepfold', 'cave', 'standing stone', 'water wheel', 'sheepdog', 'stream', 'ford', 'lone gate', 'rain water tank', 'List view']) {
    assert.ok(alt.includes(word), `the text alternative lacks ${word}`);
  }
  assert.ok(!/[\u2014\u2013]/.test(alt));
  assert.equal(withId('tiers').attrs.role, 'group');
  assert.equal(withId('tiers').attrs['aria-label'], 'View');
  assert.ok(markup.indexOf('data-tier="list"') < markup.indexOf('id="hero"'), 'the List switch comes before the picture');
});

test('each message the page gives is in a live region that a screen reader announces', () => {
  for (const id of ['notice', 'pose-caption', 'copy-status', 'snapshot-msg', 'checks-status']) {
    const t = withId(id);
    assert.ok(t, id);
    assert.ok(t.attrs.role === 'status' || t.attrs['aria-live'] === 'polite', `${id} is not a live region`);
  }
  const built = readFileSync(join(ROOT, 'src', 'ui', 'checks.js'), 'utf8');
  assert.match(built, /className: 'check-warning', role: 'status'/, 'a warning on a result is announced');
});

test('a toggle says its state: the tier switch, Calm mode and the panel buttons', () => {
  for (const b of all('button').filter((x) => 'data-tier' in x.attrs)) assert.ok(b.attrs['aria-pressed'] === 'true' || b.attrs['aria-pressed'] === 'false');
  assert.equal(withId('calm-toggle').attrs['aria-pressed'], 'false');
  for (const id of ['checks-open', 'checks-open-list']) {
    assert.equal(withId(id).attrs['aria-expanded'], 'false', id);
    assert.equal(withId(id).attrs['aria-controls'], 'checks', id);
  }
});

test('a status is never carried by colour alone: the checks say their state in words, and the warning has words', () => {
  const built = readFileSync(join(ROOT, 'src', 'data', 'notes.js'), 'utf8');
  assert.match(built, /STATUS_TICKED = 'ticked by you'/);
  assert.match(built, /STATUS_NOT_DONE = 'not done'/);
  assert.match(built, /This looks like/);
});

// ---- focus, motion and size
test('a visible focus on everything: a 2px outline, and the only outline removed is the panel\'s own, which has its own focus-visible', () => {
  assert.match(rule(':focus-visible'), /outline:\s*2px solid var\(--amber\)/);
  const removed = [...css.matchAll(/([^{}]+)\{[^{}]*outline:\s*(?:none|0)[^{}]*\}/g)].map((m) => m[1].trim());
  assert.deepEqual(removed, ['#panel:focus'], 'an outline is removed only for the panel that code focuses');
  assert.match(rule('#panel:focus-visible'), /outline:\s*2px solid var\(--amber\)/);
});

test('reduced motion removes every transition and animation, and nothing in the style loops', () => {
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)\s*\{[^}]*transition:\s*none !important;[^}]*animation:\s*none !important/);
  assert.ok(!/@keyframes/.test(css));
  assert.ok(!/infinite/.test(css));
  assert.ok(!/animation(?:-name)?:\s*(?!none)/.test(css.replace(/@media \(prefers-reduced-motion[\s\S]*?\n\}/, '')), 'no animation is declared');
});

// the size of a control, from the CSS: font-size x line-height 1.5 + padding + 2 borders
const px = (s) => Number(String(s).replace('px', ''));
test('every control is at least 24 by 24 CSS pixels (WCAG 2.2, 2.5.8): buttons, the tick boxes and the text fields', () => {
  const lh = 1.5;
  const btn = rule('.btn {'); const small = rule('.btn.small');
  const fs = px(/font-size:\s*([\d.]+)px/.exec(btn)[1]), pad = px(/padding:\s*([\d.]+)px/.exec(btn)[1]);
  assert.ok(fs * lh + 2 * pad + 2 >= 24, 'a button');
  const sfs = px(/font-size:\s*([\d.]+)px/.exec(small)[1]), spad = px(/padding:\s*([\d.]+)px/.exec(small)[1]);
  assert.ok(sfs * lh + 2 * spad + 2 >= 24, 'a small button');
  const phone = css.slice(css.indexOf('@media (max-width: 700px)'));
  const pb = /\.btn \{ padding: ([\d.]+)px [\d.]+px; font-size: ([\d.]+)px/.exec(phone);
  assert.ok(px(pb[2]) * lh + 2 * px(pb[1]) + 2 >= 24, 'a button on a phone');
  const box = rule('.step-head input[type="checkbox"]');
  assert.ok(px(/width:\s*([\d.]+)px/.exec(box)[1]) >= 24 && px(/height:\s*([\d.]+)px/.exec(box)[1]) >= 24, 'a tick box is 24 by 24 or more');
  const field = rule('.steps input[type="text"]');
  const ffs = px(/font:\s*([\d.]+)px/.exec(field)[1]), fpad = px(/padding:\s*([\d.]+)px/.exec(field)[1]);
  assert.ok(ffs * 1.4 + 2 * fpad + 2 >= 24, 'a result field');
});

// ---- the phone layout of the panels (390 by 844): nothing is wider than the screen, long text wraps or scrolls inside its box
test('the owner checks panel fits a phone: its grid may shrink, long words wrap, a code block scrolls inside its own box', () => {
  assert.match(rule('.steps {'), /grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(rule('.steps li'), /min-width:\s*0/);
  assert.match(rule('.check {'), /min-width:\s*0/);
  assert.match(rule('.step-head {'), /min-width:\s*0/);
  assert.match(rule('.step-line code'), /overflow-wrap:\s*anywhere/);
  assert.match(rule('.step-line {'), /overflow-wrap:\s*anywhere/);
  const pre = rule('pre.cmd {');
  assert.match(pre, /overflow-x:\s*auto/);
  assert.match(pre, /max-width:\s*calc\(100% - 28px\)|min-width:\s*0/);
  assert.match(rule('.step-record'), /overflow-wrap:\s*anywhere/);
  assert.match(rule('.check-warning {'), /overflow-wrap:\s*anywhere/);
  assert.match(rule('.check-reason, .check-source'), /overflow-wrap:\s*anywhere/);
  assert.match(rule('#checks-export {'), /box-sizing:\s*border-box;[^}]*width:\s*100%|width:\s*100%;[^}]*box-sizing:\s*border-box/);
});

test('on a phone the checks panel gives the steps the whole width: less padding and a smaller indent', () => {
  const phone = css.slice(css.indexOf('@media (max-width: 700px)', css.indexOf('.foot {')));
  assert.match(phone, /\.check \{[^}]*padding:\s*12px/);
  assert.match(phone, /pre\.cmd[^{]*\{[^}]*margin-left:\s*0/);
  assert.match(phone, /\.steps input\[type="text"\][^{]*\{[^}]*margin-left:\s*0[^}]*width:\s*100%/);
});

test('the station panel is a bottom sheet on a phone: full width at the bottom, scrolls inside itself and leaves the picture its top half', () => {
  const phone = css.slice(css.indexOf('@media (max-width: 700px)'));
  const p = /#panel \{([^}]*)\}/.exec(phone)[1];
  assert.match(p, /left:\s*0/); assert.match(p, /right:\s*0/); assert.match(p, /bottom:\s*0/); assert.match(p, /top:\s*auto/);
  assert.ok(Number(/max-height:\s*(\d+)%/.exec(p)[1]) <= 50, 'at most half the screen');
  assert.match(rule('#panel {'), /overflow:\s*auto/);
});

test('the fixed top bar does not cover the title of the owner checks panel when it is scrolled into view', () => {
  const m = /scroll-margin-top:\s*(\d+)px/.exec(rule('#checks {'));
  assert.ok(m && Number(m[1]) >= 60, 'a scroll margin at least as tall as the top bar');
});
