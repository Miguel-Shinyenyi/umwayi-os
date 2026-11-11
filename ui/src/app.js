// The page. It joins the world, the camera, the buttons and the panel, and decides when to draw.
// Nothing moves on its own: every move starts from a click, a key or the cursor, takes a finite time and ends at rest.
import * as THREE from 'three';
import { buildWorld } from './world/index.js';
import { overviewShot, stationShot } from './world/shots.js';
import { createStage } from './engine/stage.js';
import { createSettings } from './engine/settings.js';
import { Motion } from './engine/motion.js';
import { createLoop } from './engine/loop.js';
import { createPlayer } from './engine/poses.js';
import { Rig } from './engine/rig.js';
import { chooseDetail, isPinned } from './engine/detail.js';
import { lerp } from './engine/ease.js';
import { createLabels } from './ui/labels.js';
import { createPanel } from './ui/panel.js';
import { trailOpacity, liftIntensity } from './world/trails.js';
import { SAMPLE } from './data/sample.js';

const FLY_MS = 1400;

export function createApp(win) {
  const doc = win.document;
  const $ = (id) => doc.getElementById(id);
  const canvas = $('scene'), hero = $('hero');
  const settings = createSettings({ matchMedia: win.matchMedia ? win.matchMedia.bind(win) : undefined });

  const motion = new Motion({ reduced: settings.reduced, slow: settings.calm ? 1.6 : 1, wake: () => loop.invalidate() });
  const world = buildWorld(motion);
  const stage = createStage(canvas, world.scene);
  stage.world = world;
  const { camera } = stage;
  const rig = new Rig(overviewShot(1.7));
  const loop = createLoop({ render, motion, follows: rig.follows, raf: win.requestAnimationFrame.bind(win), onFrameTime: (dt) => stage.noteFrame(dt) });
  const n = world.stations.length;

  let counts = SAMPLE;
  let sample = true;
  let selected = null, hovered = null, kbd = null, shown = null;
  let calm = 0, trailLevel = 0, liftLevel = 0;
  let overview = null;

  const labels = createLabels($('labels'), (id) => select(id), (id) => { kbd = id; refreshFocus(); });
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
  const shotFor = (id) => (id ? stationShot(world.byId[id], aspect(), world.stations) : (overview ||= overviewShot(aspect())));

  function fly(to) {
    motion.cancel('camera');
    const from = { ...rig.s };
    motion.add({ ms: FLY_MS, tag: 'camera', update: (t) => rig.blend(from, to, t) });
    loop.invalidate();
  }
  function ease(get, set, target, ms, tag, delay = 0) {
    motion.cancel(tag);
    const from = get();
    motion.add({ ms, delay, tag, update: (t) => set(lerp(from, target, t)) });
  }

  // ---- what is in focus: the selected feature, else the hovered one, else the one with keyboard focus
  const trailsFor = (id) => {
    const me = world.byId[id], seen = new Set();
    const ids = [...me.def.deps, ...world.stations.filter((s) => s.def.deps.includes(id)).map((s) => s.id)].filter((x) => x !== id && !seen.has(x) && seen.add(x));
    ids.sort((a, b) => Math.hypot(world.byId[a].pos.x - me.pos.x, world.byId[a].pos.z - me.pos.z) - Math.hypot(world.byId[b].pos.x - me.pos.x, world.byId[b].pos.z - me.pos.z));
    return ids.slice(0, 6).map((o) => [me, world.byId[o]]);
  };
  const applyTrails = () => world.trails.setOpacity(trailOpacity(trailLevel, calm));
  const applyLift = () => { world.lift.intensity = liftIntensity(liftLevel, calm); };
  function refreshFocus() {
    const id = selected || hovered || kbd;
    labels.setHover(id && !selected ? id : null);
    if (id !== shown) {
      if (id) {
        const st = world.byId[id];
        world.trails.set(trailsFor(id));
        world.lift.position.set(st.pos.x, (st.river ? -0.4 : st.pos.y) + 3.2, st.pos.z);
      }
      shown = id;
    }
    ease(() => trailLevel, (v) => { trailLevel = v; applyTrails(); }, id ? 1 : 0, 600, 'trails');
    ease(() => liftLevel, (v) => { liftLevel = v; applyLift(); }, id ? 1 : 0, 500, 'lift');
    loop.invalidate();
  }
  world.placement; // the placement is created by the world; its onMove keeps the trails and the camera on the stations
  function onMove() {
    if (shown) {
      const st = world.byId[shown];
      world.trails.refresh();
      world.lift.position.set(st.pos.x, (st.river ? -0.4 : st.pos.y) + 3.2, st.pos.z);
    }
    if (selected && !motion.tweens.some((t) => t.tag === 'camera')) rig.set(shotFor(selected));
  }
  world.placement.onMove = onMove;

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
    refreshFocus();
    const player = players.get(id);
    if (settings.reduced) player.showRest(); else player.play();
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
    refreshFocus();
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
    applyTrails();
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
    for (const st of world.stations) {
      v.copy(st.anchor).project(camera);
      const sz = labels.size(st.id);
      labels.place(st.id, ((v.x + 1) / 2) * w - sz.w / 2, ((1 - v.y) / 2) * h - sz.h - 6);
    }
  }
  function resize() {
    const w = hero.clientWidth || win.innerWidth, h = hero.clientHeight || win.innerHeight;
    stage.resize(w, h);
    overview = null;
    if (!motion.active) rig.set(shotFor(selected));
    labels.measure();
    loop.invalidate();
  }
  stage.onStep = () => loop.invalidate();
  if (win.ResizeObserver) new win.ResizeObserver(() => resize()).observe(hero);
  else win.addEventListener('resize', resize);

  // ---- The pointer: a small parallax while it moves, a drag to look around, a click to select, a hover to show the name
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
    down = { lx: ev.clientX, ly: ev.clientY, moved: 0 };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointercancel', () => { down = null; });
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
      if (id !== hovered) { hovered = id; refreshFocus(); }
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
      if (hovered) { hovered = null; refreshFocus(); }
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
    else if (selected && (ev.key === 'ArrowRight' || ev.key === 'ArrowDown')) { ev.preventDefault(); step(1); }
    else if (selected && (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp')) { ev.preventDefault(); step(-1); }
    else if (!selected && kbd && (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft')) { ev.preventDefault(); step(ev.key === 'ArrowRight' ? 1 : -1); }
  });
  canvas.addEventListener('webglcontextlost', (ev) => { ev.preventDefault(); app.onLost && app.onLost(); });

  // ---- Start: choose the detail, draw one frame, then rest
  const gl = canvas.getContext('webgl2');
  const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
  const nav = win.navigator || {};
  const detail = chooseDetail({
    hash: win.location ? win.location.hash : '', renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : '',
    cores: nav.hardwareConcurrency, memory: nav.deviceMemory,
  });
  stage.pinned = isPinned(win.location ? win.location.hash : '');
  const app = {
    settings, stage, world, loop, select, deselect, detail,
    // UI.3 feeds numbers here and nothing else: { id: 0..1 }
    setNeeds: (needs) => world.placement.setNeeds(needs),
    isSample: () => sample,
    start() {
      panel.setMode(settings.reduced);
      rig.setReduced(settings.reduced);
      stage.setStep(detail, world);
      stage.resize(hero.clientWidth || win.innerWidth, hero.clientHeight || win.innerHeight);
      rig.set(shotFor(null));
      setCalm(settings.calm, false);
      labels.measure();
      loop.invalidate();
    },
  };
  return app;
}
