// The scene, once (12.R18.3). The owner's live view (app.js, bundled into its one file) and the public site (site/) both build
// the picture with createScene; there is no second copy. It builds the world on a canvas for a tier and returns the controls.
// It knows the canvas and one host element (to size itself and to say in the DOM whether the picture moves); it looks up
// nothing else in the page, makes no request and keeps nothing. The page's own buttons, panel and names reach it through hooks.
// Nothing moves on its own: every move starts from a click, a key or the cursor, takes a finite time and ends at rest.
import * as THREE from 'three';
import { buildWorld } from './world/index.js';
import { overviewShot, stationShot } from './world/shots.js';
import { createStage, GL_ATTRIBUTES } from './engine/stage.js';
import { createSettings } from './engine/settings.js';
import { Motion } from './engine/motion.js';
import { createLoop } from './engine/loop.js';
import { createPlayer } from './engine/poses.js';
import { Rig } from './engine/rig.js';
import { chooseDetail, isPinned } from './engine/detail.js';
import { lerp } from './engine/ease.js';
import { trailOpacity, restTrailOpacity, liftIntensity } from './world/trails.js';
import { createFlow } from './engine/flow.js';
import { WATER_LEVEL } from './world/height.js';
import { waterShared } from './world/water.js';
import { SAMPLE } from './data/sample.js';

const FLY_MS = 1400;
export const STANDARD = 2; // the tier this module draws; High (3) is UI.7, List (1) draws no scene

// The controls the design names (design.md, "The shared scene module"). The returned object holds more: what the page needs to
// join its buttons, its panel and its names to the picture (see below).
export const CONTROLS = ['select', 'overview', 'setNeeds', 'setCounts', 'setCalm', 'setReducedMotion', 'dispose'];

// createScene(canvas, { tier, detail, settings, onSelect, ... }) -> controls. Throws when the canvas cannot draw (no WebGL2).
//   win       the window (matchMedia, requestAnimationFrame, location, navigator)
//   host      the element whose size the picture takes and that carries data-flow and data-motion (default: the canvas parent)
//   tier      2 (Standard). 1 and 3 are refused: List draws nothing, High is not built yet.
//   detail    the detail step (0 high, 2 low); chosen from the device when not given
//   settings  reduced motion and Calm mode; made from win.matchMedia when not given
//   counts    the counts the features show (the sample until a snapshot is loaded, UI.3); sample says which they are
// Hooks, all optional, called in the order the page used to do the same work:
//   onSelect(id|null, { prev, def, counts, sample, focusLabel })  a feature was opened (id) or the overview came back (null)
//   onSettled(id|null, { prev, focusLabel })                      after the move and the pose have been started
//   onHover(id|null)         the feature whose name is shown by hover or focus
//   onPose({ id, index, total, caption })
//   onFrame({ w, h, anchors: [{ id, x, y }] })   after each draw: where each feature's anchor is on screen, in CSS pixels
//   onCalm(on), onResize(), onLost()
export function createScene(canvas, opts = {}) {
  const { tier = STANDARD, win = globalThis.window } = opts;
  let counts = opts.counts || SAMPLE, sample = opts.sample !== false; // the counts the features show; setCounts changes them (UI.3)
  if (tier !== STANDARD) throw new RangeError(tier === 1 ? 'List draws no scene' : 'only Standard (tier 2) is built; High is UI.7');
  // fail first, before the world is built: a canvas that cannot draw is for the caller to answer with List
  if (!canvas.getContext('webgl2', GL_ATTRIBUTES)) throw new Error('no webgl2');
  const hooks = {
    onSelect() {}, onSettled() {}, onHover() {}, onPose() {}, onFrame() {}, onCalm() {}, onResize() {}, onLost() {}, ...opts,
  };
  const host = opts.host || canvas.parentElement || canvas;
  const settings = opts.settings || createSettings({ matchMedia: win.matchMedia ? win.matchMedia.bind(win) : undefined });
  const owned = []; // [target, type, handler] to take off again in dispose()
  const on = (target, type, handler) => { target.addEventListener(type, handler); owned.push([target, type, handler]); };
  let disposed = false;

  const motion = new Motion({ reduced: settings.reduced, slow: settings.calm ? 1.6 : 1, wake: () => loop.invalidate() });
  const world = buildWorld(motion);
  const stage = createStage(canvas, world.scene);
  stage.world = world;
  const { camera } = stage;
  const rig = new Rig(overviewShot(1.7));
  // the water flows by itself (the owner, Nov 11 round 2), but not with reduced motion, in Calm mode, hidden, off screen or in List
  // the host says in the DOM whether the picture is moving and whether the water flows (for the browser pass and for CSS)
  const flow = createFlow({ wake: () => loop.wake(), onChange: (flowing) => host.setAttribute('data-flow', flowing ? 'on' : 'off') });
  host.setAttribute('data-flow', 'on');
  host.setAttribute('data-motion', 'still');
  const loop = createLoop({
    render, motion, follows: rig.follows, flow, raf: (cb) => (disposed ? 0 : win.requestAnimationFrame(cb)), onFrameTime: (dt) => stage.noteFrame(dt),
    onBusy: (b) => host.setAttribute('data-motion', b ? 'moving' : 'still'),
  });
  const pageDoc = host.ownerDocument;
  flow.set({ reduced: settings.reduced, calm: settings.calm, hidden: !!pageDoc && pageDoc.visibilityState === 'hidden', flat: true });
  if (pageDoc) on(pageDoc, 'visibilitychange', () => flow.set({ hidden: pageDoc.visibilityState === 'hidden' }));
  let observer = null;
  if (win.IntersectionObserver) {
    observer = new win.IntersectionObserver((es) => flow.set({ offscreen: !es[es.length - 1].isIntersecting }));
    observer.observe(host);
  }
  const n = world.stations.length;

  let selected = null, hovered = null, kbd = null, shown = null;
  let calm = 0, trailLevel = 0, liftLevel = 0;
  let overview = null;

  const players = new Map();
  const poseInfo = (id, i) => {
    const st = world.byId[id];
    return { id, index: i, total: st.poses.length, caption: st.poses[i].caption };
  };
  world.stations.forEach((st) => {
    st.setCounts(counts);
    players.set(st.id, createPlayer({
      station: st, motion,
      onPose: (i) => { if (selected === st.id) hooks.onPose(poseInfo(st.id, i)); },
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
  // every pair of stations that work together, once: drawn faintly at rest so the links show from the default view
  const allPairs = () => {
    const seen = new Set(), out = [];
    for (const st of world.stations) for (const d of st.def.deps) {
      const k = [st.id, d].sort().join('|');
      if (world.byId[d] && d !== st.id && !seen.has(k)) { seen.add(k); out.push([st, world.byId[d]]); }
    }
    return out;
  };
  world.restTrails.set(allPairs());
  const applyTrails = () => { world.trails.setOpacity(trailOpacity(trailLevel, calm)); world.restTrails.setOpacity(restTrailOpacity(calm)); };
  const applyLift = () => { world.lift.intensity = liftIntensity(liftLevel, calm); };
  function refreshFocus() {
    const id = selected || hovered || kbd;
    hooks.onHover(id && !selected ? id : null);
    if (id !== shown) {
      if (id) {
        const st = world.byId[id];
        world.trails.set(trailsFor(id));
        world.lift.position.set(st.pos.x, (st.river ? WATER_LEVEL : st.pos.y) + 3.2, st.pos.z);
      }
      shown = id;
    }
    ease(() => trailLevel, (v) => { trailLevel = v; applyTrails(); }, id ? 1 : 0, 600, 'trails');
    ease(() => liftLevel, (v) => { liftLevel = v; applyLift(); }, id ? 1 : 0, 500, 'lift');
    loop.invalidate();
  }
  // the placement is created by the world; its onMove keeps the trails and the camera on the stations
  function onMove() {
    world.restTrails.refresh();
    if (shown) {
      const st = world.byId[shown];
      world.trails.refresh();
      world.lift.position.set(st.pos.x, (st.river ? WATER_LEVEL : st.pos.y) + 3.2, st.pos.z);
    }
    if (selected && !motion.tweens.some((t) => t.tag === 'camera')) rig.set(shotFor(selected));
  }
  world.placement.onMove = onMove;

  // UI.3: a snapshot was loaded. Every feature draws from the new counts and goes to its resting pose (the open one keeps its pose).
  function setCounts(next, isSample = false) {
    counts = next;
    sample = !!isSample;
    for (const st of world.stations) {
      st.setCounts(counts);
      const player = players.get(st.id);
      if (st.id === selected) player.goto(player.index); else player.showRest();
    }
    loop.invalidate();
  }

  function select(id) {
    if (!world.byId[id] || id === selected) return;
    const prev = selected;
    selected = id;
    const st = world.byId[id];
    if (prev) players.get(prev).settleToRest();
    rig.resetOrbit();
    fly(shotFor(id));
    hooks.onSelect(id, { prev, def: st.def, counts, sample });
    refreshFocus();
    const player = players.get(id);
    if (settings.reduced) player.showRest(); else player.play();
    hooks.onPose(poseInfo(id, player.index));
    hooks.onSettled(id, { prev });
    loop.invalidate();
  }
  function deselect(focusLabel = true) {
    if (!selected) return;
    const prev = selected;
    selected = null;
    players.get(prev).settleToRest();
    rig.resetOrbit();
    fly(shotFor(null));
    hooks.onSelect(null, { prev, focusLabel });
    refreshFocus();
    hooks.onSettled(null, { prev, focusLabel });
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
  function setCalm(value, animate = true) {
    hooks.onCalm(value);
    motion.setSlow(value ? 1.6 : 1);
    flow.set({ calm: value });
    rig.setTau(value ? 224 : 140);
    const to = value ? 1 : 0;
    if (!animate) setLook(to);
    else ease(() => calm, setLook, to, 600, 'look');
    loop.invalidate();
  }
  settings.onChange((key, value) => {
    if (disposed) return;
    if (key === 'calm') setCalm(value);
    if (key === 'reduced') {
      motion.setReduced(value);
      flow.set({ reduced: value });
      rig.setReduced(value);
      loop.invalidate();
    }
  });

  // ---- Drawing
  const v = new THREE.Vector3();
  const frame = { w: 0, h: 0, anchors: world.stations.map((st) => ({ id: st.id, x: 0, y: 0 })) };
  function render() {
    const { w, h } = stage.size;
    rig.apply(camera, w, h);
    waterShared.flowTime.value = flow.time;
    stage.render();
    frame.w = w; frame.h = h;
    world.stations.forEach((st, i) => {
      v.copy(st.anchor).project(camera);
      frame.anchors[i].x = ((v.x + 1) / 2) * w;
      frame.anchors[i].y = ((1 - v.y) / 2) * h;
    });
    hooks.onFrame(frame);
  }
  function resize() {
    stage.resize(host.clientWidth || win.innerWidth, host.clientHeight || win.innerHeight);
    overview = null;
    if (!motion.active) rig.set(shotFor(selected));
    hooks.onResize();
    loop.invalidate();
  }
  stage.onStep = () => loop.invalidate();
  if (win.ResizeObserver) {
    const ro = new win.ResizeObserver(() => resize());
    ro.observe(host);
    owned.push([ro, 'disconnect', null]);
  } else on(win, 'resize', resize);

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
  on(canvas, 'pointerdown', (ev) => {
    down = { lx: ev.clientX, ly: ev.clientY, moved: 0 };
    canvas.setPointerCapture(ev.pointerId);
  });
  on(canvas, 'pointercancel', () => { down = null; });
  on(canvas, 'pointermove', (ev) => {
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
  on(canvas, 'pointerup', (ev) => {
    const wasClick = down && down.moved < 6;
    down = null;
    if (wasClick) {
      const id = pick(ev);
      if (id) select(id);
      else if (selected) deselect(false);
    }
  });
  on(canvas, 'pointerleave', () => {
    if (!down) {
      rig.pointer(0, 0);
      if (hovered) { hovered = null; refreshFocus(); }
      loop.invalidate();
    }
  });
  on(canvas, 'webglcontextlost', (ev) => { ev.preventDefault(); hooks.onLost(); });

  // ---- Start: choose the detail, draw one frame, then rest
  const gl = canvas.getContext('webgl2');
  const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
  const nav = win.navigator || {};
  const hash = win.location ? win.location.hash : '';
  const detail = Number.isInteger(opts.detail) ? opts.detail : chooseDetail({
    hash, renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : '', cores: nav.hardwareConcurrency, memory: nav.deviceMemory,
  });
  stage.pinned = isPinned(hash);

  return {
    // the controls of the design
    select,
    overview: () => deselect(false),
    setNeeds: (needs) => world.placement.setNeeds(needs), // UI.3 feeds numbers here and nothing else: { id: 0..1 }
    setCounts, // UI.3: the counts the features draw, and whether they are the sample
    setCalm: (value) => settings.setCalm(value),
    setReducedMotion: (value) => settings.setReduced(value),
    dispose() {
      if (disposed) return;
      disposed = true;
      motion.cancel('camera');
      for (const [target, type, handler] of owned) {
        if (handler) target.removeEventListener(type, handler);
        else target[type]();
      }
      if (observer) observer.disconnect();
      stage.renderer.dispose();
    },
    // what the page needs to join its own buttons, panel and names to the picture
    deselect, step, settings, stage, world, loop, flow, detail,
    // UI.8: the page arms this while High is drawn; onSlow runs once when a short window of frames is slow (null disarms)
    watchHigh: (onSlow) => stage.watchHigh(onSlow),
    isSample: () => sample,
    selected: () => selected,
    setFocus(id) { kbd = id; refreshFocus(); }, // the feature whose button has keyboard focus, or null
    replay() { if (selected) { players.get(selected).play(); loop.invalidate(); } },
    posePrev() { if (selected) { players.get(selected).prev(); loop.invalidate(); } },
    poseNext() { if (selected) { players.get(selected).next(); loop.invalidate(); } },
    // List (true) or the picture (false): in List nothing is drawn and the water is still
    setFlat(flat) {
      flow.set({ flat });
      if (!flat) resize();
    },
    start() {
      rig.setReduced(settings.reduced);
      stage.setStep(detail, world);
      stage.resize(host.clientWidth || win.innerWidth, host.clientHeight || win.innerHeight);
      rig.set(shotFor(null));
      setCalm(settings.calm, false);
      hooks.onResize();
      loop.invalidate();
    },
  };
}
