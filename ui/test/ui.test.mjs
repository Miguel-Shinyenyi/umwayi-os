// UI.1.4: the list view and the fallback, with a stub document (no browser).
import test from 'node:test';
import assert from 'node:assert/strict';
import { showList, toggleList } from '../src/ui/fallback.js';
import { createLabels } from '../src/ui/labels.js';
import { describe, NO_COUNT } from '../src/data/counts.js';

function stubDoc() {
  const els = {};
  for (const id of ['list-view', 'list-toggle', 'calm-toggle', 'labels', 'hint', 'panel', 'sample-tag', 'scene', 'notice', 'hero']) {
    els[id] = { hidden: id === 'list-view' || id === 'notice', attrs: {}, textContent: '', setAttribute(k, v) { this.attrs[k] = v; } };
  }
  return { els, getElementById: (id) => els[id] };
}

test('when the 3D view cannot start the list view is shown by itself, with a notice, and the 3D controls are hidden', () => {
  const doc = stubDoc();
  showList(doc, 'The 3D view could not start in this browser.');
  assert.equal(doc.els['list-view'].hidden, false);
  assert.equal(doc.els.notice.hidden, false);
  assert.match(doc.els.notice.textContent, /could not start/);
  for (const id of ['list-toggle', 'calm-toggle', 'labels', 'hint', 'panel', 'sample-tag']) assert.equal(doc.els[id].hidden, true, id);
  assert.equal(doc.els.scene.attrs['aria-hidden'], 'true');
  assert.equal(doc.els.scene.hidden, true, 'the empty picture goes');
  assert.ok('data-flat' in doc.els.hero.attrs, 'the title and promise stay');
});

test('the list view toggles, keeps aria-pressed true to its state, and hides the picture from screen readers while open', () => {
  const doc = stubDoc();
  toggleList(doc, true);
  assert.equal(doc.els['list-view'].hidden, false);
  assert.equal(doc.els['list-toggle'].attrs['aria-pressed'], 'true');
  assert.equal(doc.els.scene.attrs['aria-hidden'], 'true');
  toggleList(doc, false);
  assert.equal(doc.els['list-view'].hidden, true);
  assert.equal(doc.els['list-toggle'].textContent, 'List view');
  assert.equal(doc.els.scene.attrs['aria-hidden'], 'false');
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
