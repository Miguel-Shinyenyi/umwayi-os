// UI.1.4: the list view and the fallback, with a stub document (no browser).
import test from 'node:test';
import assert from 'node:assert/strict';
import { setTier } from '../src/ui/fallback.js';
import { createLabels } from '../src/ui/labels.js';
import { describe, NO_COUNT } from '../src/data/counts.js';

function stubDoc() {
  const els = {};
  const attrs = (o) => ({ ...o, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } });
  for (const id of ['scene', 'notice']) els[id] = attrs({ hidden: id === 'notice', textContent: '' });
  const buttons = ['list', 'standard'].map((t) => attrs({ dataset: { tier: t } }));
  const root = attrs({});
  return { els, buttons, documentElement: root, getElementById: (id) => els[id], querySelectorAll: () => buttons };
}

test('List is tier 1: the page says which tier it shows, presses its switch button and hides the picture from screen readers', () => {
  const doc = stubDoc();
  setTier(doc, 'list', 'This browser cannot draw the picture (no WebGL). The List view shows the same stations.');
  assert.equal(doc.documentElement.attrs['data-tier'], 'list');
  assert.deepEqual(doc.buttons.map((b) => b.attrs['aria-pressed']), ['true', 'false']);
  assert.equal(doc.els.scene.attrs['aria-hidden'], 'true');
  assert.equal(doc.els.notice.hidden, false);
  assert.match(doc.els.notice.textContent, /no WebGL/);
  setTier(doc, 'standard');
  assert.equal(doc.documentElement.attrs['data-tier'], 'standard');
  assert.deepEqual(doc.buttons.map((b) => b.attrs['aria-pressed']), ['false', 'true']);
  assert.equal(doc.els.scene.attrs['aria-hidden'], 'false');
  assert.equal(doc.els.notice.hidden, true, 'no message, no notice');
});

test('a label click selects its station, and only the selected label is shown while one is selected', () => {
  const mk = (id) => {
    const cls = new Set();
    return { dataset: { station: id }, attrs: {}, style: {}, handlers: {},
      addEventListener(e, fn) { this.handlers[e] = fn; }, classList: { toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)) },
      setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; }, focus() { this.focused = true; } };
  };
  const buttons = ['memory', 'rules', 'queue'].map(mk);
  const nav = { querySelectorAll: () => buttons };
  const picked = [];
  const labels = createLabels(nav, (id) => picked.push(id));
  buttons[1].handlers.click();
  assert.deepEqual(picked, ['rules']);
  labels.setSelected('rules');
  assert.ok('data-away' in buttons[0].attrs && !('data-away' in buttons[1].attrs) && 'data-away' in buttons[2].attrs);
  labels.setSelected(null);
  assert.ok(buttons.every((b) => !('data-away' in b.attrs)));
  labels.focus('queue');
  assert.equal(buttons[2].focused, true);
});

test('stations the snapshot has no count for say so in words', () => {
  assert.equal(NO_COUNT, 'No count is shown for this station.');
  assert.equal(describe('memory', {}), null);
});
