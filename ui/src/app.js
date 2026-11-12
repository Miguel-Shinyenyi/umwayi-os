// The page. It joins the shared scene (scene.js), the buttons over the features, the panel and the keyboard.
// The picture itself is built by createScene, the same module the public site uses (12.R18.3); this file only owns the page's
// own elements. Nothing moves on its own: every move starts from a click, a key or the cursor, takes a finite time and ends at rest.
import { createScene } from './scene.js';
import { createLabels } from './ui/labels.js';
import { createPanel } from './ui/panel.js';
import { feedScene, viewOf } from './data/snapshot.js';

// view: what the page shows (data/snapshot.js, viewOf): the sample world, or the snapshot the owner loaded before the picture started
export function createApp(win, view = viewOf(null)) {
  const doc = win.document;
  const $ = (id) => doc.getElementById(id);
  const canvas = $('scene'), hero = $('hero');

  let scene = null;
  let kbd = null; // the feature whose button has keyboard focus
  const labels = createLabels($('labels'), (id) => scene.select(id), (id) => { kbd = id; scene.setFocus(id); });
  const panel = createPanel(doc, {
    replay: () => scene.replay(),
    posePrev: () => scene.posePrev(),
    poseNext: () => scene.poseNext(),
    stationPrev: () => scene.step(-1),
    stationNext: () => scene.step(1),
    back: () => scene.deselect(),
  });

  // a name never covers the title or the promise: it goes just below them
  let introBox = null;
  function measureIntro() {
    const el = doc.querySelector('#hero .intro');
    if (!el || !el.getBoundingClientRect) return;
    const a = el.getBoundingClientRect(), b = hero.getBoundingClientRect();
    introBox = { x0: a.left - b.left - 6, y0: a.top - b.top - 6, x1: a.right - b.left + 6, y1: a.bottom - b.top + 6 };
  }

  // the same for the open station panel (a bottom sheet upright, a card at the side on its side): the name of the selected feature
  // moves out from under it instead of over its text. Read only while the panel is open, once for each frame.
  function panelBox() {
    const el = $('panel');
    if (!el || !el.hasAttribute('data-open') || !el.getBoundingClientRect) return null;
    const a = el.getBoundingClientRect(), b = hero.getBoundingClientRect();
    return { x0: a.left - b.left - 6, y0: a.top - b.top - 6, x1: a.right - b.left + 6, y1: a.bottom - b.top + 6 };
  }

  scene = createScene(canvas, {
    win, host: hero, counts: view.counts, sample: view.sample,
    onSelect(id, info) {
      if (id) {
        labels.setSelected(id);
        $('hint').setAttribute('data-away', '');
        panel.show(info.def, info.counts, info.sample);
        panel.setMode(scene.settings.reduced);
      } else {
        labels.setSelected(null);
        panel.hide();
      }
    },
    onSettled(id, info) {
      if (id) panel.focus();
      else if (info.focusLabel) labels.focus(info.prev);
    },
    onHover: (id) => labels.setHover(id),
    onPose: ({ index, total, caption }) => panel.setCaption(caption, index, total),
    onFrame({ w, anchors }) {
      const pb = panelBox();
      for (const a of anchors) {
        const sz = labels.size(a.id);
        let x = a.x - sz.w / 2;
        let y = a.y - sz.h - 6;
        if (introBox && x < introBox.x1 && x + sz.w > introBox.x0 && y < introBox.y1 && y + sz.h > introBox.y0) y = introBox.y1 + 4;
        if (pb && x < pb.x1 && x + sz.w > pb.x0 && y < pb.y1 && y + sz.h > pb.y0) {
          if (pb.x1 - pb.x0 < w * 0.9) x = Math.max(0, pb.x0 - sz.w); // a card at the side: the name goes to its left
          else y = Math.max(0, pb.y0 - sz.h - 4); // a sheet at the bottom: the name goes above it
        }
        labels.place(a.id, x, y);
      }
      labels.placed();
    },
    onCalm(on) {
      doc.documentElement.setAttribute('data-calm', on ? '1' : '0');
      $('calm-toggle').setAttribute('aria-pressed', String(on));
    },
    onResize() {
      measureIntro();
      labels.measure();
    },
    onLost: () => app.onLost && app.onLost(),
  });
  if (!view.sample) scene.world.placement.place(view.needs); // a snapshot loaded before the picture started: the stations start in their places
  const { settings } = scene;
  settings.onChange((key, value) => { if (key === 'reduced') panel.setMode(value); });
  $('calm-toggle').addEventListener('click', () => settings.setCalm(!settings.calm));

  // ---- The keyboard: arrows between stations, Escape back to the overview
  doc.addEventListener('keydown', (ev) => {
    if (ev.defaultPrevented || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    const tag = ev.target && ev.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (doc.documentElement.getAttribute('data-tier') === 'list') return;
    const selected = scene.selected();
    if (ev.key === 'Escape' && selected) { ev.preventDefault(); scene.deselect(); }
    else if (selected && (ev.key === 'ArrowRight' || ev.key === 'ArrowDown')) { ev.preventDefault(); scene.step(1); }
    else if (selected && (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp')) { ev.preventDefault(); scene.step(-1); }
    else if (!selected && kbd && (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft')) { ev.preventDefault(); scene.step(ev.key === 'ArrowRight' ? 1 : -1); }
  });

  const app = {
    settings, stage: scene.stage, world: scene.world, loop: scene.loop, select: scene.select, deselect: scene.deselect, detail: scene.detail,
    // UI.3 feeds numbers here and nothing else: { id: 0..1 }
    setNeeds: scene.setNeeds,
    // a snapshot was loaded after the picture started: the counts, then the needs; an open panel shows the new counts
    setData(next) {
      feedScene(scene, next);
      const open = scene.selected();
      if (open) panel.show(scene.world.byId[open].def, next.counts, next.sample);
    },
    isSample: scene.isSample,
    flow: scene.flow,
    setFlat: scene.setFlat,
    start() {
      panel.setMode(settings.reduced);
      scene.start();
    },
  };
  return app;
}
