// The page. It joins the world, the camera, the labels and the panel, and decides when to draw.
// Nothing moves on its own: every move starts from a click, a key or the cursor, takes a finite time and ends at rest.
import * as THREE from 'three';
import { buildWorld } from './world/index.js';
import { createStage } from './engine/stage.js';
import { createSettings } from './engine/settings.js';
import { Motion } from './engine/motion.js';
import { createLoop } from './engine/loop.js';
import { createPlayer } from './engine/poses.js';
import { Rig } from './engine/rig.js';
import { overviewShot, stationShot, declutter } from './engine/layout.js';
import { lerp } from './engine/ease.js';
import { createLabels } from './ui/labels.js';
import { createPanel } from './ui/panel.js';
import { SAMPLE } from './data/sample.js';

const FLY_MS = 1400;

export function createApp(win) {
  const doc = win.document;
  const $ = (id) => doc.getElementById(id);
  const canvas = $('scene');
  const settings = createSettings({ matchMedia: win.matchMedia ? win.matchMedia.bind(win) : undefined });

  const world = buildWorld();
  const stage = createStage(canvas, world.scene);
  const { camera } = stage;
  const motion = new Motion({ reduced: settings.reduced, slow: settings.calm ? 1.6 : 1, wake: () => loop.invalidate() });
  const rig = new Rig(overviewShot(1.7, world.stations.length));
  const loop = createLoop({ render, motion, follows: rig.follows, raf: win.requestAnimationFrame.bind(win), onFrameTime: (dt) => stage.noteFrame(dt) });
  const n = world.stations.length;

  let counts = SAMPLE;
  let sample = true;
  let selected = null;
  let calm = 0;
  let arcLevel = 0;
  let liftLevel = 0;

  const labels = createLabels($('labels'), (id) => select(id));
  const panel = createPanel(doc, {
    replay: () => { if (selected) { players.get(selected).play(); loop.invalidate(); } },
    posePrev: () => { if (selected) { players.get(selected).prev(); loop.invalidate(); } },
    poseNext: () => { if (selected) { players.get(selected).next(); loop.invalidate(); } },
    stationPrev: () => step(-1),
    stationNext: () => step(1),
    back: () => deselect(),
  });

  const players = new Map();
  world.stations.forEach((st) => {
    st.setCounts(counts);
    players.set(st.id, createPlayer({
      station: st, motion,
      onPose: (i) => { if (selected === st.id) panel.setCaption(st.poses[i].caption, i, st.poses.length); },
    }));
    players.get(st.id).showRest();
  });

  const aspect = () => stage.size.w / stage.size.h;
  const shotFor = (id) => (id ? stationShot(world.byId[id].pos, aspect()) : overviewShot(aspect(), n));

  function fly(to) {
    motion.cancel('camera');
    const from = { ...rig.s };
    motion.add({ ms: FLY_MS, tag: 'camera', update: (t) => rig.blend(from, to, t) });
    loop.invalidate();
  }
  // a level (arcs, the lift light) eased to a target
  function ease(get, set, target, ms, tag, delay = 0) {
    motion.cancel(tag);
    const from = get();
    motion.add({ ms, delay, tag, update: (t) => set(lerp(from, target, t)) });
  }
  const applyArcs = () => world.arcs.setOpacity(arcLevel * (1 - calm));
  const applyLift = () => { world.lift.intensity = liftLevel * 22 * (1 - 0.4 * calm); };

  function select(id) {
    if (!world.byId[id] || id === selected) return;
    const prev = selected;
    selected = id;
    const st = world.byId[id];
    if (prev) players.get(prev).settleToRest();
    rig.resetOrbit();
    fly(shotFor(id));
    labels.setSelected(id);
    $('hint').setAttribute('data-away', '');
    panel.show(st.def, counts, sample);
    panel.setMode(settings.reduced);
    world.arcs.set(st.anchor, st.def.deps.map((d) => world.byId[d].anchor));
    world.lift.position.set(st.pos.x, 4.2, st.pos.z);
    ease(() => arcLevel, (v) => { arcLevel = v; applyArcs(); }, 0.3, 800, 'arcs', 500);
    ease(() => liftLevel, (v) => { liftLevel = v; applyLift(); }, 1, 1000, 'lift');
    const player = players.get(id);
    if (settings.reduced) player.showRest();
    else player.play();
    panel.setCaption(st.poses[player.index].caption, player.index, st.poses.length);
    panel.focus();
    loop.invalidate();
  }
  function deselect(focusLabel = true) {
    if (!selected) return;
    const prev = selected;
    selected = null;
    players.get(prev).settleToRest();
    rig.resetOrbit();
    fly(shotFor(null));
    labels.setSelected(null);
    panel.hide();
    ease(() => arcLevel, (v) => { arcLevel = v; applyArcs(); }, 0, 600, 'arcs');
    ease(() => liftLevel, (v) => { liftLevel = v; applyLift(); }, 0, 800, 'lift');
    if (focusLabel) labels.focus(prev);
    loop.invalidate();
  }
  function step(dir) {
    const i = selected ? world.stations.findIndex((s) => s.id === selected) : dir > 0 ? -1 : 0;
    select(world.stations[(i + dir + n) % n].id);
  }

  // ---- Calm mode and reduced motion
  function setLook(c) {
    calm = c;
    stage.setLook(world.look(c));
    applyArcs();
    applyLift();
  }
  function setCalm(on, animate = true) {
    doc.documentElement.setAttribute('data-calm', on ? '1' : '0');
    $('calm-toggle').setAttribute('aria-pressed', String(on));
    motion.setSlow(on ? 1.6 : 1);
    rig.setTau(on ? 224 : 140);
    const to = on ? 1 : 0;
    if (!animate) setLook(to);
    else ease(() => calm, setLook, to, 600, 'look');
    win.requestAnimationFrame(() => { labels.measure(); loop.invalidate(); });
    loop.invalidate();
  }
  settings.onChange((key, value) => {
    if (key === 'calm') setCalm(value);
    if (key === 'reduced') {
      motion.setReduced(value);
      rig.setReduced(value);
      panel.setMode(value);
      loop.invalidate();
    }
  });
  $('calm-toggle').addEventListener('click', () => settings.setCalm(!settings.calm));

  // ---- Drawing
  const v = new THREE.Vector3();
  function render() {
    const { w, h } = stage.size;
    rig.apply(camera, w, h);
    stage.render();
    const rects = world.stations.map((st) => {
      v.copy(st.anchor).project(camera);
      const sz = labels.size(st.id);
      return { id: st.id, x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h - sz.h / 2 - 6, w: sz.w, h: sz.h };
    });
    const bounds = { left: 8, right: w - 8, top: w < 700 ? 56 : 64, bottom: h - 54 };
    declutter(rects, bounds).forEach((r, i) => labels.place(world.stations[i].id, r.x - r.w / 2, r.y - r.h / 2));
  }
  function resize() {
    const w = win.innerWidth, h = win.innerHeight;
    stage.resize(w, h);
    if (!motion.active) rig.set(shotFor(selected));
    labels.measure();
    loop.invalidate();
  }
  stage.onPixelRatio = () => loop.invalidate();
  win.addEventListener('resize', resize);

  // ---- The pointer: a small parallax while it moves, a drag to look around, a click to select
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const hits = world.stations.map((s) => s.hit);
  const pick = (ev) => {
    const r = canvas.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    camera.updateMatrixWorld();
    raycaster.setFromCamera(ndc, camera);
    const hit = raycaster.intersectObjects(hits, false)[0];
    return hit ? hit.object.userData.station : null;
  };
  let down = null;
  canvas.addEventListener('pointerdown', (ev) => {
    down = { x: ev.clientX, y: ev.clientY, lx: ev.clientX, ly: ev.clientY, moved: 0 };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointermove', (ev) => {
    const r = canvas.getBoundingClientRect();
    if (down) {
      const dx = ev.clientX - down.lx, dy = ev.clientY - down.ly;
      down.lx = ev.clientX; down.ly = ev.clientY;
      down.moved += Math.abs(dx) + Math.abs(dy);
      if (!settings.reduced) rig.drag(dx, dy);
    } else {
      rig.pointer(((ev.clientX - r.left) / r.width) * 2 - 1, ((ev.clientY - r.top) / r.height) * 2 - 1);
      const id = pick(ev);
      canvas.classList.toggle('is-over', !!id);
      labels.setHover(id);
    }
    loop.invalidate();
  });
  canvas.addEventListener('pointerup', (ev) => {
    const wasClick = down && down.moved < 6;
    down = null;
    if (wasClick) {
      const id = pick(ev);
      if (id) select(id);
      else if (selected) deselect(false);
    }
  });
  canvas.addEventListener('pointerleave', () => {
    if (!down) {
      rig.pointer(0, 0);
      labels.setHover(null);
      loop.invalidate();
    }
  });

  // ---- The keyboard: arrows between stations, Escape back to the overview
  doc.addEventListener('keydown', (ev) => {
    if (ev.defaultPrevented || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    const tag = ev.target && ev.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (!$('list-view').hidden) return;
    if (ev.key === 'Escape' && selected) { ev.preventDefault(); deselect(); }
    else if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown') { ev.preventDefault(); step(1); }
    else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp') { ev.preventDefault(); step(-1); }
  });

  canvas.addEventListener('webglcontextlost', (ev) => { ev.preventDefault(); app.onLost && app.onLost(); });

  // ---- Start: one frame, then rest
  const app = {
    settings, stage, world, loop, select, deselect,
    isSample: () => sample,
    start() {
      panel.setMode(settings.reduced);
      rig.setReduced(settings.reduced);
      stage.resize(win.innerWidth, win.innerHeight);
      rig.set(shotFor(null));
      setCalm(settings.calm, false);
      labels.measure();
      loop.invalidate();
    },
  };
  return app;
}
