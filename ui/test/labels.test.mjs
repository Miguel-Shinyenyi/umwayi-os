// W1: the name of the selected feature waits for the frame that places it. Until then it is drawn clear (data-pending), so it is
// never seen at the place the picture had before the move, where the station panel or the title may now be.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createLabels } from '../src/ui/labels.js';

function fakeNav(ids) {
  const buttons = ids.map((id) => {
    const attrs = new Map(), classes = new Set();
    return {
      dataset: { station: id }, style: {}, offsetWidth: 60, offsetHeight: 25,
      addEventListener() {},
      setAttribute: (k, v) => attrs.set(k, v), removeAttribute: (k) => attrs.delete(k), hasAttribute: (k) => attrs.has(k),
      classList: { toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)), has: (c) => classes.has(c) },
    };
  });
  return { buttons, nav: { querySelectorAll: () => buttons } };
}

test('a selected name is pending until a frame has placed it, and only that name', () => {
  const { buttons, nav } = fakeNav(['a', 'b', 'c']);
  const labels = createLabels(nav, () => {}, () => {});
  labels.setSelected('b');
  assert.deepEqual(buttons.map((b) => b.hasAttribute('data-pending')), [false, true, false]);
  assert.ok(buttons[1].classList.has('is-selected'));
  labels.placed();
  assert.deepEqual(buttons.map((b) => b.hasAttribute('data-pending')), [false, false, false]);
  assert.ok(buttons[1].classList.has('is-selected'), 'placing does not unselect');
});

test('selecting another name moves the wait to it, and the overview has none', () => {
  const { buttons, nav } = fakeNav(['a', 'b']);
  const labels = createLabels(nav, () => {}, () => {});
  labels.setSelected('a');
  labels.setSelected('b');
  assert.deepEqual(buttons.map((b) => b.hasAttribute('data-pending')), [false, true]);
  labels.setSelected(null);
  assert.deepEqual(buttons.map((b) => b.hasAttribute('data-pending')), [false, false]);
});

test('the style keeps a pending name clear, after the rule that shows a selected name, and the app places names on each frame', async () => {
  const { readFileSync } = await import('node:fs');
  const { join, dirname } = await import('node:path');
  const { fileURLToPath } = await import('node:url');
  const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
  const css = readFileSync(join(root, 'style.css'), 'utf8');
  assert.ok(css.indexOf('.label[data-pending] { opacity: 0; }') > css.indexOf('.label:focus-visible, .label.is-hover, .label.is-selected { opacity: 1; }'), 'pending wins over selected');
  assert.match(readFileSync(join(root, 'app.js'), 'utf8'), /labels\.placed\(\);/);
});
