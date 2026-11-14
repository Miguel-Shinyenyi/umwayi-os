// W38: the goal map drawn into the page. Every word goes in with textContent and every attribute is a number or a word made
// here, so nothing that comes from a goal map file or from the backend can become markup or a script. The document is passed in,
// so the tests draw into a small fake document and read back exactly what was made.
import { STATES, UNKNOWN, budgetWords, taskLines, ageWords } from './model.js';
import { layout, BAT as BAT_SIZE } from './layout.js';
import { PUMPKIN, CANDLE, GHOST, BAT, slotPicture, hasBat } from './theme.js';

const r1 = (v) => String(Math.round(v * 10) / 10);

// d is { doc, ns }: ns is the SVG namespace of the drawing the page has, so no address is written here
function el(d, tag, attrs = {}, text = null) {
  const e = d.doc.createElementNS(d.ns, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== null) e.textContent = text;
  return e;
}
function html(doc, tag, attrs = {}, text = null) {
  const e = doc.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== null) e.textContent = text;
  return e;
}
const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };

function picture(d, kind, box, colour, running) {
  const g = el(d, 'g', { class: `slot ${kind}`, transform: `translate(${r1(box.x)} ${r1(box.y)})`, 'aria-hidden': 'true' });
  if (kind === 'candle') {
    g.appendChild(el(d, 'path', { d: CANDLE.wax, fill: '#eee8db' }));
    g.appendChild(el(d, 'path', { d: CANDLE.flame, fill: colour, class: 'flicker' }));
  } else if (kind === 'ghost') {
    g.appendChild(el(d, 'path', { d: GHOST.body, fill: '#eee8db', 'fill-opacity': '0.85' }));
    g.appendChild(el(d, 'path', { d: GHOST.eyes, fill: '#0e1310' }));
  } else {
    if (running) g.appendChild(el(d, 'circle', { cx: 14, cy: 14, r: 12, fill: 'none', stroke: colour, 'stroke-width': 2, class: 'pulse' }));
    g.appendChild(el(d, 'circle', { cx: 14, cy: 14, r: 7, fill: colour }));
  }
  return g;
}

function bat(d, orbit, reduced) {
  // the bat flies once round the middle line of the halo of its card, slowly; under reduced motion there is no theme at all
  const o = orbit;
  const path = `M${r1(o.x)} ${r1(o.y)}h${r1(o.w)}v${r1(o.h)}h${r1(-o.w)}z`;
  const g = el(d, 'g', { class: 'bat', 'aria-hidden': 'true' });
  const b = el(d, 'path', { d: BAT, fill: '#2a2620', stroke: '#e0a965', 'stroke-width': '0.6', transform: `scale(${BAT_SIZE / 12})` });
  const wrap = el(d, 'g');
  wrap.appendChild(b);
  if (!reduced) wrap.appendChild(el(d, 'animateMotion', { path, dur: '16s', repeatCount: 'indefinite', rotate: '0' }));
  else wrap.setAttribute('transform', `translate(${r1(o.x)} ${r1(o.y)})`);
  g.appendChild(wrap);
  return g;
}

function words(d, lines, colour) {
  const g = el(d, 'g', { class: 'words' });
  for (const l of lines) {
    const t = el(d, 'text', { x: r1(l.x), y: r1(l.y + 14), class: l.cls }, l.text);
    if (l.cls === 'state') t.setAttribute('fill', colour);
    g.appendChild(t);
  }
  return g;
}

// svg: the drawing. opts: { theme (on or off), reduced }
export function drawMap(doc, svg, model, { theme = false, reduced = false } = {}) {
  const d = { doc, ns: svg.namespaceURI };
  const L = layout(model);
  clear(svg);
  svg.setAttribute('viewBox', `0 0 ${L.width} ${r1(L.height)}`);
  svg.setAttribute('data-tasks', String(L.cards.length));
  // the branches first, so every card and word is drawn over them
  const lines = el(d, 'g', { class: 'branches', 'aria-hidden': 'true' });
  for (const c of L.cards) {
    const st = c.task.state.key ? STATES[c.task.state.key] : UNKNOWN;
    lines.appendChild(el(d, 'polyline', { points: c.line.map((p) => `${r1(p.x)},${r1(p.y)}`).join(' '), stroke: st.colour, 'stroke-opacity': c.task.needsOwner ? '0.9' : '0.45', fill: 'none', 'stroke-width': c.task.needsOwner ? 3 : 1.5 }));
  }
  svg.appendChild(lines);

  // the goal
  const g = el(d, 'g', { class: 'goal' });
  g.appendChild(el(d, 'rect', { x: r1(L.goal.box.x), y: r1(L.goal.box.y), width: L.goal.box.w, height: L.goal.box.h, rx: 14, class: 'goal-box' }));
  g.appendChild(words(d, L.goal.lines, '#eee8db'));
  svg.appendChild(g);

  // the supervisor, with its heartbeat: grey and still when its last event is old or it is not running
  const s = model.supervisor;
  const sg = el(d, 'g', { class: `supervisor ${s.stale ? 'stale' : 'fresh'}`, 'data-stale': String(s.stale) });
  const sb = L.supervisor.box;
  sg.appendChild(el(d, 'rect', { x: r1(sb.x), y: r1(sb.y), width: sb.w, height: sb.h, rx: 10, class: 'sup-box' }));
  const beat = L.supervisor.beat;
  sg.appendChild(el(d, 'circle', { cx: r1(beat.x + beat.w / 2), cy: r1(beat.y + beat.h / 2), r: 7, class: s.stale || reduced ? 'heart' : 'heart beat', fill: s.stale ? '#7f796e' : '#9cc39a' }));
  const st = L.supervisor.textBox;
  sg.appendChild(el(d, 'text', { x: r1(st.x), y: r1(st.y + 14), class: 'title' }, 'Supervisor'));
  sg.appendChild(el(d, 'text', { x: r1(st.x), y: r1(st.y + 32), class: 'state', fill: s.stale ? '#b3ada0' : '#9cc39a' }, s.word));
  svg.appendChild(sg);

  // the tasks
  for (const c of L.cards) {
    const t = c.task;
    const st2 = t.state.key ? STATES[t.state.key] : UNKNOWN;
    const kind = slotPicture(t.state.key, theme);
    const cg = el(d, 'g', { class: `task${t.needsOwner ? ' owner' : ''}`, 'data-state': t.state.word, 'data-picture': kind });
    cg.appendChild(el(d, 'rect', { x: r1(c.box.x), y: r1(c.box.y), width: c.box.w, height: c.box.h, rx: 10, class: 'card', stroke: st2.colour, 'stroke-width': t.needsOwner ? 3 : 1.5 }));
    cg.appendChild(picture(d, kind, c.slot, st2.colour, t.state.key === 'running' && !reduced));
    cg.appendChild(words(d, c.lines, st2.colour));
    if (hasBat(t.state.key, theme)) cg.appendChild(bat(d, c.orbit, reduced));
    svg.appendChild(cg);
  }
  return L;
}

// the List tier, and the words for a screen reader: the same facts as the drawing, as text
export function drawList(doc, ul, model) {
  clear(ul);
  for (const t of model.goal ? model.tasks : []) {
    const l = taskLines(t);
    const li = html(doc, 'li', { 'data-state': t.state.word });
    li.appendChild(html(doc, 'strong', {}, l.head));
    li.appendChild(html(doc, 'span', { class: 'state' }, l.state));
    li.appendChild(html(doc, 'span', {}, `${l.role}; ${l.where}; ${l.age}${l.pr ? `; ${l.pr}` : ''}`));
    ul.appendChild(li);
  }
}

export function drawFeed(doc, ol, model) {
  clear(ol);
  for (const e of model.events) {
    const li = html(doc, 'li');
    li.appendChild(html(doc, 'span', { class: 'when' }, e.t));
    li.appendChild(html(doc, 'span', { class: 'kind' }, e.task ? `${e.kind} ${e.task}` : e.kind));
    li.appendChild(html(doc, 'span', { class: 'what' }, e.text));
    ol.appendChild(li);
  }
}

// the kill switch lamp: a small jack-o-lantern with the theme, a plain round lamp without. Lit when the switch is off (helpers
// may run), dark when it is on or cannot be read. The word is always beside it.
export function drawLamp(doc, svg, kill, theme) {
  const d = { doc, ns: svg.namespaceURI };
  clear(svg);
  svg.setAttribute('viewBox', '0 0 32 32');
  svg.setAttribute('data-lit', String(kill.lit));
  if (theme) {
    if (kill.lit) svg.appendChild(el(d, 'circle', { cx: 16, cy: 17, r: 15, fill: '#e0a965', 'fill-opacity': '0.25', class: 'glow' }));
    svg.appendChild(el(d, 'path', { d: PUMPKIN.stem, fill: kill.lit ? '#9cc39a' : '#4a4a40' }));
    svg.appendChild(el(d, 'path', { d: PUMPKIN.body, fill: kill.lit ? '#d9822b' : '#3a3530' }));
    svg.appendChild(el(d, 'path', { d: PUMPKIN.face, fill: kill.lit ? '#ffd27a' : '#1a1814' }));
  } else {
    svg.appendChild(el(d, 'circle', { cx: 16, cy: 16, r: 12, fill: kill.lit ? '#9cc39a' : '#e07a6f' }));
  }
}

export function goalWords(model) {
  if (!model.goal) return '';
  return `${model.goal.id}: ${model.goal.state}. Budget ${budgetWords(model.goal.budget)}.`;
}

export const supervisorWords = (s) => `Supervisor: ${s.word}${s.state ? ` (${s.state})` : ''}${s.age !== null ? `, last event ${ageWords(s.age)} ago` : ''}.`;
