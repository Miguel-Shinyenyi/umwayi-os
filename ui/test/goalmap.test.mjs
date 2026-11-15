// W38 (tests first for the pure parts, then the page): the goal map page. The fixtures in fixtures/goal-map follow the W37
// contract as the owner gave it in the W38 task; W37 itself is not merged. A small fake document stands in for the browser, so
// what is drawn is read back exactly, and a planted script in a title is shown as words and never becomes an element.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readGoalMap, STATES, UNKNOWN, MESSAGES, STALE_S, supervisorOf, killOf, taskLines } from '../src/goalmap/model.js';
import { layout, textBoxes, overlap, inside, grow, segmentHits, HALO, BAT, CARD, W } from '../src/goalmap/layout.js';
import { drawMap, drawList, drawFeed, drawLamp } from '../src/goalmap/draw.js';
import { createTheme, themeFromHash, themeHash, isThemeKey, slotPicture, hasBat, TITLE_WORD } from '../src/goalmap/theme.js';
import { createFeed, liveLoad, LINES, RETRY_MS, OK_MS } from '../src/goalmap/feed.js';
import { readTextFile } from '../src/data/snapshot.js';
import { startGoalMap } from '../src/goalmap/page.js';

const here = dirname(fileURLToPath(import.meta.url));
const FIX = join(here, 'fixtures', 'goal-map');
const SRC = join(here, '..', 'src');
const raw = (name) => readFileSync(join(FIX, name), 'utf8');
const model = (name) => { const r = readGoalMap(raw(name)); assert.ok(r.ok, name); return r.model; };
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r)); };

// ---------------------------------------------------------------- a fake document

class Node {
  constructor(tag, ns) { this.tagName = tag; this.ns = ns; this.attrs = {}; this.children = []; this.parentNode = null; this._text = ''; this.listeners = {}; this.hidden = false; this.disabled = false; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return Object.hasOwn(this.attrs, k) ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return Object.hasOwn(this.attrs, k); }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; return c; }
  get firstChild() { return this.children[0] || null; }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); }
  fire(t, e = {}) { for (const f of this.listeners[t] || []) f({ preventDefault() {}, target: this, ...e }); }
  all() { return [this, ...this.children.flatMap((c) => c.all())]; }
}
// innerHTML and friends do not exist on this fake on purpose: code that reached for them would throw here
function fakeDoc() {
  const ids = {};
  const doc = new Node('#document');
  doc.documentElement = new Node('html');
  doc.createElement = (t) => new Node(t, 'html');
  doc.createElementNS = (ns, t) => new Node(t, ns);
  doc.getElementById = (id) => (ids[id] ||= Object.assign(new Node(id === 'drawing' || id === 'lamp' ? 'svg' : 'div', id === 'drawing' || id === 'lamp' ? 'svg-ns' : 'html'), { id, namespaceURI: id === 'drawing' || id === 'lamp' ? 'svg-ns' : 'html' }));
  const buttons = ['list', 'standard'].map((t) => { const b = new Node('button'); b.setAttribute('data-tier', t); return b; });
  doc.querySelectorAll = (q) => (q === 'button[data-tier]' ? buttons : []);
  doc.buttons = buttons;
  doc.ids = ids;
  return doc;
}
function fakeWin({ hash = '', reduced = false } = {}) {
  const timers = [];
  const listeners = [];
  const media = { matches: reduced, addEventListener(_t, f) { listeners.push(f); }, removeEventListener() {} };
  const win = {
    document: fakeDoc(),
    location: { hash },
    history: { replaceState(_s, _t, h) { win.location.hash = h; } },
    matchMedia: () => media,
    setTimeout(f, ms) { timers.push({ f, ms }); return timers.length; },
    clearTimeout(i) { if (timers[i - 1]) timers[i - 1].f = null; },
    timers,
    setReduced(v) { media.matches = v; listeners.forEach((f) => f({ matches: v })); },
  };
  return win;
}

// ---------------------------------------------------------------- the contract

test('every fixture is a goal map of the contract, and nothing else is read', () => {
  const files = readdirSync(FIX).filter((f) => f.endsWith('.json'));
  assert.ok(files.length >= 7);
  for (const f of files) {
    const d = JSON.parse(raw(f));
    assert.deepEqual(Object.keys(d).sort(), ['events', 'goal', 'kill_switch', 'notes', 'now', 'supervisor', 'tasks', 'version'], f);
    if (d.goal) assert.deepEqual(Object.keys(d.goal).sort(), ['budget', 'id', 'needs_owner', 'state', 'title'], f);
    assert.deepEqual(Object.keys(d.supervisor).sort(), ['alive', 'last_event_age_s', 'pid_known', 'state'], f);
    for (const t of d.tasks) assert.deepEqual(Object.keys(t).sort(), ['age_s', 'id', 'needs_owner_reason', 'pr', 'role_now', 'state', 'title', 'worktree'], f);
    for (const e of d.events) assert.deepEqual(Object.keys(e).sort(), ['kind', 't', 'task', 'text'], f);
    assert.ok(readGoalMap(raw(f)).ok, f);
  }
});

test('a file that is not a goal map is refused with one plain line, and nothing is drawn', () => {
  assert.equal(readGoalMap('not json').message, MESSAGES.notJson);
  assert.equal(readGoalMap('[]').message, MESSAGES.shape);
  assert.equal(readGoalMap('{"version":2,"tasks":[],"events":[],"goal":null}').message, MESSAGES.version);
  assert.equal(readGoalMap('{"version":1,"tasks":{},"events":[],"goal":null}').message, MESSAGES.shape);
  assert.equal(readGoalMap('{"version":1,"tasks":[],"events":[],"goal":"x"}').message, MESSAGES.shape);
  assert.equal(readGoalMap('x'.repeat(1_000_001)).message, MESSAGES.tooBig);
});

test('a field of the wrong type is unknown, never guessed and never fine', () => {
  const d = JSON.parse(raw('tasks-1.json'));
  d.tasks[0].state = 'done'; d.tasks[0].role_now = 'admin'; d.tasks[0].age_s = -3; d.tasks[0].worktree = 'x'; d.tasks[0].pr = '12';
  d.kill_switch = 'maybe'; d.supervisor.last_event_age_s = 'soon';
  const m = readGoalMap(d).model;
  assert.equal(m.tasks[0].state.word, 'unknown');
  assert.equal(m.tasks[0].role, null);
  assert.equal(m.tasks[0].age, null);
  assert.equal(m.tasks[0].worktree, null);
  assert.equal(m.tasks[0].pr, null);
  assert.deepEqual(killOf('maybe'), { key: 'unknown', word: 'unknown', note: 'drawn as on', lit: false });
  assert.equal(m.supervisor.stale, true, 'an age that cannot be read is drawn as stale');
});

// ---------------------------------------------------------------- the states

test('every state has its own word and its own colour, and the needs owner colour is the warm amber of the scene', () => {
  const keys = ['queued', 'running', 'in review', 'needs owner', 'merged', 'stopped', 'failed'];
  assert.deepEqual(Object.keys(STATES), keys);
  for (const k of keys) assert.equal(STATES[k].word, k);
  const colours = [...Object.values(STATES).map((s) => s.colour), UNKNOWN.colour];
  assert.equal(new Set(colours).size, colours.length, 'no two states share a colour');
  assert.equal(STATES['needs owner'].colour, '#e0a965');
  const css = readFileSync(join(SRC, 'style.css'), 'utf8');
  assert.match(css, /--amber:\s*#e0a965/, 'the same amber as the live view');
});

test('every card of the drawing has its state word in its state colour, with the theme on and off', () => {
  const m = model('tasks-12.json');
  for (const theme of [false, true]) {
    const doc = fakeDoc();
    const svg = doc.getElementById('drawing');
    drawMap(doc, svg, m, { theme });
    const cards = svg.all().filter((n) => n.tagName === 'g' && /\btask\b/.test(n.getAttribute('class') || ''));
    assert.equal(cards.length, 12);
    for (const c of cards) {
      const word = c.getAttribute('data-state');
      const st = STATES[word];
      const stateText = c.all().find((n) => n.tagName === 'text' && n.getAttribute('class') === 'state');
      assert.ok(stateText.textContent.startsWith(word), `${word} is written`);
      assert.equal(stateText.getAttribute('fill'), st.colour, `${word} is in its colour`);
      assert.equal(c.all().find((n) => n.tagName === 'rect').getAttribute('stroke'), st.colour);
    }
  }
});

// ---------------------------------------------------------------- the layout

const LONG = 'x'.repeat(300);
function randomModel(n, seed) {
  let s = seed;
  const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const keys = Object.keys(STATES);
  const d = JSON.parse(raw('tasks-1.json'));
  d.goal.title = rnd() < 0.5 ? LONG : 'A goal';
  d.tasks = Array.from({ length: n }, (_v, i) => ({ id: `T-${String(i + 1).padStart(2, '0')}`, title: rnd() < 0.3 ? LONG : `task ${i}`, state: keys[Math.floor(rnd() * keys.length)], role_now: ['builder', 'tester', 'guide', null][Math.floor(rnd() * 4)], worktree: rnd() < 0.2 ? null : { branch: rnd() < 0.3 ? LONG : `work-branch-${i}`, clean: rnd() < 0.5 }, age_s: Math.floor(rnd() * 200000), needs_owner_reason: rnd() < 0.5 ? LONG : 'ask', pr: rnd() < 0.3 ? 120 + i : null }));
  return readGoalMap(d).model;
}

function assertNoOverlap(m, label) {
  const L = layout(m);
  const fixed = [grow(L.goal.box, 2), grow(L.supervisor.box, 2)];
  const area = { x: 0, y: 0, w: L.width, h: L.height };
  for (const [i, c] of L.cards.entries()) {
    assert.ok(inside(c.halo, area), `${label}: card ${i} is inside the drawing`);
    for (const f of fixed) assert.ok(!overlap(c.halo, f), `${label}: card ${i} and the centre column`);
    for (const d of L.cards.slice(i + 1)) assert.ok(!overlap(c.halo, d.halo), `${label}: two cards overlap`);
    for (const l of c.lines) {
      assert.ok(inside(l, c.textBox), `${label}: a word of card ${i} leaves its box`);
      assert.ok(!overlap(l, c.slot), `${label}: the picture of card ${i} covers a word`);
    }
    assert.ok(inside(c.slot, c.box), `${label}: the picture leaves its card`);
    // the bat flies on the middle line of the halo: its whole path, with its size, stays in the halo and out of the card
    assert.ok(inside(grow(c.orbit, BAT / 2), c.halo), `${label}: the bat leaves the halo of card ${i}`);
    assert.ok(inside(c.box, grow(c.orbit, -BAT / 2)), `${label}: the bat enters card ${i}`);
    // a branch crosses no word and no other card on its way
    const others = [...textBoxes(L).filter((b) => !c.lines.includes(b)), ...L.cards.filter((d) => d !== c).map((d) => d.box), L.supervisor.box];
    for (let k = 0; k + 1 < c.line.length; k++) for (const b of others) assert.ok(!segmentHits(c.line[k], c.line[k + 1], b), `${label}: the branch of card ${i} crosses a box`);
  }
  for (const l of L.goal.lines) assert.ok(inside(l, L.goal.box), `${label}: a word leaves the goal`);
  assert.ok(inside(L.supervisor.textBox, L.supervisor.box) && !overlap(L.supervisor.beat, L.supervisor.textBox), `${label}: the supervisor`);
  return L;
}

test('nothing overlaps at 0, 1, 4 and 12 tasks: cards, words, pictures, the bat and the branches', () => {
  for (const f of ['tasks-0.json', 'tasks-1.json', 'tasks-4.json', 'tasks-12.json', 'no-goal.json', 'planted-script.json']) assertNoOverlap(model(f), f);
});

test('nothing overlaps for every number of tasks from 0 to 12, with long words and every mix of states', () => {
  for (let n = 0; n <= 12; n++) for (let seed = 1; seed <= 25; seed++) assertNoOverlap(randomModel(n, seed * 97 + n), `n=${n} seed=${seed}`);
});

test('a task that needs the owner is always drawn closest to the goal', () => {
  for (let n = 1; n <= 12; n++) for (let seed = 1; seed <= 25; seed++) {
    const L = layout(randomModel(n, seed * 31 + n));
    const gc = { x: L.goal.box.x + L.goal.box.w / 2, y: L.goal.box.y + L.goal.box.h / 2 };
    const d = (c) => Math.hypot(c.box.x + CARD.w / 2 - gc.x, c.box.y + CARD.h / 2 - gc.y);
    const owner = L.cards.filter((c) => c.task.needsOwner).map(d);
    const rest = L.cards.filter((c) => !c.task.needsOwner).map(d);
    if (owner.length && rest.length) assert.ok(Math.max(...owner) < Math.min(...rest), `n=${n} seed=${seed}`);
  }
});

test('the map stays readable at 1 and at 12 tasks: the same card size, the words cut to fit and never smaller', () => {
  const one = layout(model('tasks-1.json'));
  const twelve = layout(model('tasks-12.json'));
  assert.equal(one.width, W);
  assert.equal(one.cards[0].box.w, twelve.cards[0].box.w);
  assert.ok(twelve.height > one.height, 'twelve tasks make the drawing taller, not the cards smaller');
  for (const c of layout(randomModel(12, 5)).cards) for (const l of c.lines) assert.ok(l.text.length * 7.4 <= c.textBox.w, 'a line is cut to its card');
});

// ---------------------------------------------------------------- empty, stale, the lamp

test('with no goal the map is quiet: no card, one line saying how to start one, no feed', async () => {
  const m = model('no-goal.json');
  assert.equal(m.goal, null);
  assert.equal(layout(m).cards.length, 0);
  const win = fakeWin();
  const page = startGoalMap(win, { load: async () => raw('no-goal.json') });
  await flush();
  const $ = (id) => win.document.getElementById(id);
  assert.equal($('line').textContent, MESSAGES.noGoal);
  assert.match(MESSAGES.noGoal, /umwayi goal start/);
  assert.equal($('task-list').children.length, 0);
  assert.equal($('feed').children.length, 0);
  assert.equal($('drawing').all().filter((n) => n.tagName === 'g' && /\btask\b/.test(n.getAttribute('class') || '')).length, 0);
  assert.ok($('drawing').textContent.includes('No goal yet'));
  page.stop();
});

test('the supervisor goes grey when its last event is old, or when it is not running', () => {
  assert.equal(supervisorOf({ alive: true, last_event_age_s: 12 }).stale, false);
  assert.equal(supervisorOf({ alive: true, last_event_age_s: STALE_S - 1 }).stale, false);
  assert.equal(supervisorOf({ alive: true, last_event_age_s: STALE_S }).stale, true);
  assert.equal(supervisorOf({ alive: true, last_event_age_s: 900 }).word, 'quiet for 15 min');
  assert.equal(supervisorOf({ alive: false, last_event_age_s: 1 }).word, 'not running');
  assert.equal(supervisorOf(null).stale, true);
  for (const [f, stale] of [['tasks-4.json', false], ['stale.json', true]]) {
    const doc = fakeDoc();
    drawMap(doc, doc.getElementById('drawing'), model(f), { theme: true });
    const sup = doc.getElementById('drawing').all().find((n) => /\bsupervisor\b/.test(n.getAttribute('class') || ''));
    assert.equal(sup.getAttribute('data-stale'), String(stale), f);
    const heart = sup.all().find((n) => n.tagName === 'circle');
    assert.equal(/\bbeat\b/.test(heart.getAttribute('class')), !stale, `${f}: a stale heart does not beat`);
    assert.equal(heart.getAttribute('fill'), stale ? '#7f796e' : '#9cc39a');
  }
});

test('the kill switch lamp: lit when the switch is off, dark when it is on or unknown, with its word always', () => {
  for (const theme of [true, false]) {
    for (const [v, lit] of [['off', true], ['on', false], ['x', false]]) {
      const doc = fakeDoc();
      const svg = doc.getElementById('lamp');
      drawLamp(doc, svg, killOf(v), theme);
      assert.equal(svg.getAttribute('data-lit'), String(lit), `${v} theme=${theme}`);
      if (theme) assert.equal(!!svg.all().find((n) => n.getAttribute('class') === 'glow'), lit, 'the jack-o-lantern glows only when lit');
    }
  }
  const win = fakeWin();
  const page = startGoalMap(win, { load: async () => raw('stale.json') });
  return flush().then(() => {
    assert.equal(win.document.getElementById('lamp-words').textContent, 'Kill switch: on, everything is stopped');
    page.stop();
  });
});

// ---------------------------------------------------------------- the theme

test('the theme pictures: a candle on a running task, a ghost on a stopped or failed one, a bat on one that needs the owner', () => {
  assert.equal(slotPicture('running', true), 'candle');
  assert.equal(slotPicture('stopped', true), 'ghost');
  assert.equal(slotPicture('failed', true), 'ghost');
  for (const k of ['queued', 'in review', 'needs owner', 'merged', null]) assert.equal(slotPicture(k, true), 'marker');
  for (const k of Object.keys(STATES)) assert.equal(slotPicture(k, false), 'marker', 'the plain look has only the marker');
  assert.equal(hasBat('needs owner', true), true);
  assert.equal(hasBat('needs owner', false), false);
  const doc = fakeDoc();
  drawMap(doc, doc.getElementById('drawing'), model('tasks-12.json'), { theme: true });
  const all = doc.getElementById('drawing').all();
  assert.equal(all.filter((n) => /\bbat\b/.test(n.getAttribute('class') || '')).length, 2, 'one bat for each task that needs the owner');
  assert.equal(all.filter((n) => /\bslot candle\b/.test(n.getAttribute('class') || '')).length, 2);
  assert.equal(all.filter((n) => /\bslot ghost\b/.test(n.getAttribute('class') || '')).length, 2);
  assert.ok(all.some((n) => n.tagName === 'animateMotion'), 'the bat circles');
  const plain = fakeDoc();
  drawMap(plain, plain.getElementById('drawing'), model('tasks-12.json'), { theme: false });
  const p = plain.getElementById('drawing').all();
  assert.equal(p.filter((n) => /\bbat\b|candle|ghost/.test(n.getAttribute('class') || '')).length, 0, 'no decoration in the plain look');
  assert.equal(p.filter((n) => /\bpulse\b/.test(n.getAttribute('class') || '')).length, 2, 'a calm pulse on each running task');
});

test('the T key and the button turn the theme off and on, the header says Kiroween only with the theme, and the choice is in the fragment', async () => {
  const win = fakeWin();
  const page = startGoalMap(win, { load: async () => raw('tasks-4.json') });
  await flush();
  const $ = (id) => win.document.getElementById(id);
  const root = win.document.documentElement;
  assert.equal(root.getAttribute('data-theme'), 'kiroween');
  assert.equal($('kiro').hidden, false);
  assert.equal($('kiro').textContent, TITLE_WORD);
  win.document.fire('keydown', { key: 't' });
  assert.equal(root.getAttribute('data-theme'), 'plain');
  assert.equal($('kiro').hidden, true);
  assert.match(win.location.hash, /theme=off/);
  win.document.fire('keydown', { key: 'T', ctrlKey: true });
  assert.equal(root.getAttribute('data-theme'), 'plain', 'not with a modifier');
  win.document.fire('keydown', { key: 't', target: { tagName: 'INPUT' } });
  assert.equal(root.getAttribute('data-theme'), 'plain', 'not while typing in a field');
  $('theme-toggle').fire('click');
  assert.equal(root.getAttribute('data-theme'), 'kiroween');
  assert.equal($('theme-toggle').getAttribute('aria-pressed'), 'true');
  // the words of the states do not change with the theme
  const words = (svg) => svg.all().filter((n) => n.getAttribute('class') === 'state').map((n) => n.textContent);
  const on = words($('drawing'));
  win.document.fire('keydown', { key: 't' });
  assert.deepEqual(words($('drawing')), on);
  page.stop();
  assert.equal(themeFromHash('#tier=list&theme=off'), false);
  assert.equal(themeFromHash('#theme=on'), true);
  assert.equal(themeFromHash('#theme=maybe'), null);
  assert.equal(themeHash('#tier=list&theme=on', false), '#tier=list&theme=off');
  assert.equal(isThemeKey({ key: 't', target: { isContentEditable: true } }), false);
});

test('with reduced motion the look is the plain one, the theme cannot be turned on, and nothing animates', async () => {
  const win = fakeWin({ reduced: true });
  const page = startGoalMap(win, { load: async () => raw('tasks-12.json') });
  await flush();
  const $ = (id) => win.document.getElementById(id);
  const root = win.document.documentElement;
  assert.equal(root.getAttribute('data-theme'), 'plain');
  assert.equal(root.hasAttribute('data-reduced'), true);
  assert.equal($('theme-toggle').disabled, true);
  win.document.fire('keydown', { key: 't' });
  assert.equal(root.getAttribute('data-theme'), 'plain');
  const all = $('drawing').all();
  assert.equal(all.filter((n) => n.tagName === 'animateMotion').length, 0);
  assert.equal(all.filter((n) => /\b(pulse|beat|flicker)\b/.test(n.getAttribute('class') || '')).length, 0, 'no moving part is drawn');
  win.setReduced(false);
  assert.equal(root.getAttribute('data-theme'), 'kiroween', 'the theme comes back when the system allows motion');
  page.stop();
  const t = createTheme({ chosen: true, reduced: true });
  assert.equal(t.on, false);
  t.toggle();
  assert.equal(t.on, false);
});

test('the CSS stops every animation under prefers-reduced-motion', () => {
  const css = readFileSync(join(SRC, 'goal-map.css'), 'utf8');
  const block = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{([^}]*)\}/);
  assert.ok(block);
  for (const c of ['.pulse', '.heart.beat', '.flicker', '.lamp-pic .glow']) assert.ok(block[1].includes(c), c);
  assert.match(block[1], /animation:\s*none/);
});

// ---------------------------------------------------------------- the tiers

test('the tiers: List shows the list, Map draws the drawing, and the choice is in the fragment', async () => {
  const win = fakeWin({ hash: '#tier=list' });
  const page = startGoalMap(win, { load: async () => raw('tasks-4.json') });
  await flush();
  const $ = (id) => win.document.getElementById(id);
  assert.equal(win.document.documentElement.getAttribute('data-tier'), 'list');
  assert.equal($('map').hidden, true);
  assert.equal($('task-list').children.length, 4);
  win.document.buttons[1].fire('click');
  assert.equal(win.document.documentElement.getAttribute('data-tier'), 'standard');
  assert.equal($('map').hidden, false);
  assert.match(win.location.hash, /tier=standard/);
  page.stop();
  const high = fakeWin({ hash: '#tier=high' });
  const p2 = startGoalMap(high, { load: async () => raw('tasks-4.json') });
  await flush();
  assert.equal(high.document.documentElement.getAttribute('data-tier'), 'standard', 'High draws the map as Standard does');
  p2.stop();
});

test('the list has the same words as the drawing, for every task', () => {
  const m = model('tasks-12.json');
  const doc = fakeDoc();
  const ul = doc.getElementById('task-list');
  drawList(doc, ul, m);
  assert.equal(ul.children.length, 12);
  for (const [i, li] of ul.children.entries()) {
    const l = taskLines(m.tasks[i]);
    assert.equal(li.children[0].textContent, l.head);
    assert.equal(li.children[1].textContent, l.state);
  }
});

// ---------------------------------------------------------------- the feed and the source

test('the feed shows the newest events first, at most eight', () => {
  const d = JSON.parse(raw('tasks-4.json'));
  d.events = Array.from({ length: 12 }, (_v, i) => ({ t: `0${i}`, kind: 'output', task: 'T-01', text: `line ${i}` }));
  const m = readGoalMap(d).model;
  const doc = fakeDoc();
  const ol = doc.getElementById('feed');
  drawFeed(doc, ol, m);
  assert.equal(ol.children.length, 8);
  assert.equal(ol.children[0].children[2].textContent, 'line 11');
  assert.equal(ol.children[7].children[2].textContent, 'line 4');
});

test('an unreachable backend is one plain line and the page tries again slowly, never faster than 15 s', async () => {
  const lines = [];
  const timers = [];
  let calls = 0;
  const feed = createFeed({
    load: () => { calls++; return Promise.reject(new Error('down')); },
    onData: () => assert.fail('no data'),
    onDown: (l) => lines.push(l),
    setTimer: (f, ms) => { timers.push({ f, ms }); return timers.length; },
    clearTimer: () => {},
  });
  feed.start();
  for (let i = 0; i < 4; i++) { await flush(); timers[timers.length - 1].f(); }
  await flush();
  assert.equal(calls, 5);
  assert.deepEqual(timers.map((t) => t.ms), [...RETRY_MS, 60000, 60000]);
  assert.ok(timers.every((t) => t.ms >= 15000));
  assert.equal(lines[0], LINES.unreachable(15));
  feed.stop();
  assert.ok(OK_MS >= 5000);
});

test('the live source is not connected until W37 is merged: the page says so in one line and sends nothing', async () => {
  await assert.rejects(liveLoad(), { name: 'NotConnected' });
  const win = fakeWin();
  const page = startGoalMap(win);
  await flush();
  assert.equal(win.document.getElementById('line').textContent, LINES.notConnected(15));
  assert.equal(win.timers.at(-1).ms, 15000);
  page.stop();
});

test('a new reading replaces the drawing (a live map), and a bad one keeps the last drawing and says why', async () => {
  const win = fakeWin();
  const texts = [raw('tasks-1.json'), raw('tasks-4.json'), '{bad'];
  const page = startGoalMap(win, { load: async () => texts.shift() });
  await flush();
  const count = () => win.document.getElementById('task-list').children.length;
  assert.equal(count(), 1);
  win.timers.at(-1).f(); await flush();
  assert.equal(count(), 4);
  win.timers.at(-1).f(); await flush();
  assert.equal(count(), 4, 'the last good drawing stays');
  assert.equal(win.document.getElementById('line').textContent, MESSAGES.notJson);
  page.stop();
});

// ---------------------------------------------------------------- nothing becomes markup

test('a planted script tag in a title, a task and an event is drawn as words and never becomes an element', async () => {
  const win = fakeWin();
  const page = startGoalMap(win, { load: async () => raw('planted-script.json') });
  await flush();
  const nodes = Object.values(win.document.ids).flatMap((n) => n.all());
  const tags = new Set(nodes.map((n) => String(n.tagName).toLowerCase()));
  for (const bad of ['script', 'img', 'iframe', 'object', 'foreignobject', 'a', 'use']) assert.ok(!tags.has(bad), `no <${bad}> was made`);
  const all = nodes.map((n) => n._text).join('\n');
  assert.ok(all.includes('<script>window.__planted'), 'the planted words are shown as words');
  for (const n of nodes) for (const [k, v] of Object.entries(n.attrs)) {
    assert.ok(!/^on/i.test(k), `no event attribute ${k}`);
    assert.ok(!/<|javascript:/i.test(v), `no markup in the attribute ${k}`);
  }
  assert.equal(globalThis.__planted, undefined);
  page.stop();
});

test('a goal map file is read with the one file reader of the page, and a file that is too large is refused before it is read', async () => {
  class R { readAsText() { this.result = '{"version":1}'; this.onload(); } }
  assert.equal(await readTextFile({ size: 10 }, R, 1000), '{"version":1}');
  assert.equal(await readTextFile({ size: 2000 }, R, 1000), null);
  class Bad { readAsText() { this.onerror(); } }
  assert.equal(await readTextFile({ size: 10 }, Bad), null);
});

test('no module of the goal map writes markup, reads the query, stores anything or sends a request', () => {
  const files = readdirSync(join(SRC, 'goalmap')).map((f) => join(SRC, 'goalmap', f)).concat([join(SRC, 'goal-map.js')]);
  for (const f of files) {
    const text = readFileSync(f, 'utf8');
    for (const bad of [/\.innerHTML/, /outerHTML/, /insertAdjacent/, /document\.write/, /DOMParser/, /\beval\s*\(/, /new Function/, /location\.search/, /URLSearchParams/, /localStorage/, /sessionStorage/, /document\.cookie/, /\bfetch\s*\(/, /XMLHttpRequest/, /EventSource/, /WebSocket/, /sendBeacon/, /setInterval/, /requestAnimationFrame/]) {
      assert.ok(!bad.test(text), `${f}: ${bad}`);
    }
  }
});

test('the built page: one inline script and style by hash, no request allowed, no outside file, and the header has its title', () => {
  const html = readFileSync(join(here, '..', 'dist', 'goal-map.html'), 'utf8');
  const csp = html.match(/<meta http-equiv="Content-Security-Policy" content="([^"]*)">/)[1];
  assert.match(csp, /^default-src 'none'; script-src 'sha256-[^']+'; style-src 'sha256-[^']+'; base-uri 'none'; form-action 'none'$/);
  assert.ok(!/connect-src|unsafe-inline|unsafe-eval|\*/.test(csp));
  assert.equal((html.match(/<script\b/g) || []).length, 1);
  assert.ok(!/<script[^>]*\bsrc=|<link\b|<img\b|<iframe\b|@import|url\(/i.test(html));
  assert.match(html, /<h1>umwayi goal map <span class="kiro" id="kiro" hidden>Kiroween<\/span><\/h1>/);
  const addresses = [...html.matchAll(/https?:\/\/[^\s"'<>)]+/g)].map((m) => m[0]);
  assert.deepEqual(addresses, [], 'no address at all, not even a namespace: the drawing takes it from the page');
  assert.match(html, /data-tier="list"/, 'List in its HTML, before any script');
});
