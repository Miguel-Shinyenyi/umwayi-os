// W38: where everything of the goal map stands. Pure: a model in, boxes out, so the tests can prove that nothing overlaps (the
// cards, the words, the decoration and the lines) without a browser. All numbers are in the units of the drawing's viewBox.
//
// The goal is in the middle, the supervisor under it. The tasks hang in two columns, one each side, like the branches of a mind
// map. Every place a task can take is ranked by its distance from the goal; a task that needs the owner takes the nearest places
// first and is then pulled in further, so it is always drawn closest.
import { fit, taskLines } from './model.js';

export const W = 1200; // the width of the drawing
export const CARD = { w: 250, h: 92 }; // one task
export const HALO = 22; // the ring round a card: the pulse and the bat live here and nowhere else
export const PITCH = CARD.h + 2 * HALO + 14; // one row of cards
export const IND = 56; // how far a task that needs the owner is pulled towards the goal
export const GOAL = { w: 320, h: 100 };
export const SUP = { w: 260, h: 60, gap: 28 };
export const MIN_H = 560;
export const TRUNK = 30; // the trunk of the branches of one side stands this far from the goal
export const MARGIN = 40;
const PAD = 10; // inside a card, round its words
export const SLOT = { size: 28, left: 8 }; // the small picture of a card (a marker, or a candle or a ghost with the theme)
const TEXT_LEFT = SLOT.left + SLOT.size + 8; // the words start after the picture
export const LINE_H = 18;
export const CHAR_W = 7.4; // a generous width of one character of the drawing's font, for cutting a line to fit
export const BAT = 16; // the bat's size; it flies on the middle line of the halo

export const charsFor = (width) => Math.floor(width / CHAR_W);

export function overlap(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
export const grow = (b, d) => ({ x: b.x - d, y: b.y - d, w: b.w + 2 * d, h: b.h + 2 * d });
export const inside = (a, b) => a.x >= b.x && a.y >= b.y && a.x + a.w <= b.x + b.w && a.y + a.h <= b.y + b.h;

// the lines of a box of words, each cut to the width it has
function words(box, lines) {
  const n = charsFor(box.w);
  return lines.map((l, i) => ({ text: fit(l.text, n), cls: l.cls, x: box.x, y: box.y + i * LINE_H, w: Math.min(box.w, fit(l.text, n).length * CHAR_W), h: LINE_H }));
}

export function layout(model) {
  const goal = model && model.goal;
  const tasks = goal ? model.tasks : [];
  const rows = Math.max(1, Math.ceil(tasks.length / 2));
  const height = Math.max(MIN_H, rows * PITCH + 2 * MARGIN);
  const mid = height / 2;
  const cx = W / 2;

  // the centre column: the goal and, under it, the supervisor; together they are centred on the middle line
  const block = GOAL.h + SUP.gap + SUP.h;
  const goalBox = { x: cx - GOAL.w / 2, y: mid - block / 2, w: GOAL.w, h: GOAL.h };
  const supBox = { x: cx - SUP.w / 2, y: goalBox.y + GOAL.h + SUP.gap, w: SUP.w, h: SUP.h };
  const gc = { x: cx, y: goalBox.y + GOAL.h / 2 };

  // every place, ranked by distance from the goal (ties: right before left, top before bottom)
  const leftX = MARGIN + HALO;
  const rightX = W - MARGIN - HALO - CARD.w;
  const slots = [];
  for (let r = 0; r < rows; r++) {
    const y = mid + (r - (rows - 1) / 2) * PITCH - CARD.h / 2;
    for (const side of ['right', 'left']) {
      const x = side === 'right' ? rightX : leftX;
      const c = { x: x + CARD.w / 2, y: y + CARD.h / 2 };
      slots.push({ side, row: r, x, y, d: Math.hypot(c.x - gc.x, c.y - gc.y) });
    }
  }
  slots.sort((a, b) => a.d - b.d || (a.side === b.side ? 0 : a.side === 'right' ? -1 : 1) || a.row - b.row);
  const order = [...tasks.filter((t) => t.needsOwner), ...tasks.filter((t) => !t.needsOwner)];

  const cards = order.map((t, i) => {
    const s = slots[i];
    const pull = t.needsOwner ? (s.side === 'right' ? -IND : IND) : 0;
    const box = { x: s.x + pull, y: s.y, w: CARD.w, h: CARD.h };
    const l = taskLines(t);
    const textBox = { x: box.x + TEXT_LEFT, y: box.y + PAD, w: CARD.w - TEXT_LEFT - PAD, h: CARD.h - 2 * PAD };
    const lines = words(textBox, [
      { text: l.head, cls: 'title' },
      { text: l.state, cls: 'state' },
      { text: `${l.role}, ${l.age}${l.pr ? `, ${l.pr}` : ''}`, cls: 'detail' },
      { text: l.where, cls: 'detail' },
    ]);
    const slot = { x: box.x + SLOT.left, y: box.y + (CARD.h - SLOT.size) / 2, w: SLOT.size, h: SLOT.size };
    // the bat's path: the middle line of the halo, a rectangle round the card
    const o = HALO / 2;
    const orbit = { x: box.x - o, y: box.y - o, w: CARD.w + 2 * o, h: CARD.h + 2 * o };
    const anchor = s.side === 'right' ? { x: box.x, y: box.y + CARD.h / 2 } : { x: box.x + CARD.w, y: box.y + CARD.h / 2 };
    const from = s.side === 'right' ? { x: goalBox.x + GOAL.w, y: gc.y } : { x: goalBox.x, y: gc.y };
    // an elbow: out of the goal to the trunk of its side, along the trunk, then straight into the card on its own row
    const trunk = s.side === 'right' ? goalBox.x + GOAL.w + TRUNK : goalBox.x - TRUNK;
    const line = [from, { x: trunk, y: from.y }, { x: trunk, y: anchor.y }, anchor];
    return { task: t, side: s.side, box, halo: grow(box, HALO), textBox, lines, slot, orbit, line };
  });

  const goalLines = goal ? words({ x: goalBox.x + PAD + 4, y: goalBox.y + PAD + 4, w: GOAL.w - 2 * PAD - 8, h: GOAL.h - 2 * PAD }, [
    { text: `${goal.id} ${goal.title}`, cls: 'title' },
    { text: `goal ${goal.state}${goal.needsOwner ? ', needs you' : ''}`, cls: 'state' },
    { text: `${tasks.length} task${tasks.length === 1 ? '' : 's'}${model.hidden ? `, ${model.hidden} more not drawn` : ''}`, cls: 'detail' },
  ]) : words({ x: goalBox.x + PAD + 4, y: goalBox.y + GOAL.h / 2 - LINE_H, w: GOAL.w - 2 * PAD - 8, h: LINE_H * 2 }, [
    { text: 'No goal yet', cls: 'title' },
    { text: 'nothing is running', cls: 'detail' },
  ]);
  const beat = { x: supBox.x + 12, y: supBox.y + SUP.h / 2 - 8, w: 16, h: 16 };
  const supText = { x: beat.x + beat.w + 10, y: supBox.y + 12, w: SUP.w - (beat.w + 10) - 24, h: SUP.h - 24 };
  return { width: W, height, goal: { box: goalBox, lines: goalLines }, supervisor: { box: supBox, beat, textBox: supText }, cards };
}

// every box of words in a layout, and every box of decoration, for the tests and for nothing else
export function textBoxes(L) {
  return [...L.goal.lines, ...L.cards.flatMap((c) => c.lines), L.supervisor.textBox];
}

// a straight line meets a box (the Liang-Barsky clip): a connector must not cross a word
export function segmentHits(p, q, b) {
  let t0 = 0, t1 = 1;
  const dx = q.x - p.x, dy = q.y - p.y;
  const edges = [[-dx, p.x - b.x], [dx, b.x + b.w - p.x], [-dy, p.y - b.y], [dy, b.y + b.h - p.y]];
  for (const [pp, qq] of edges) {
    if (pp === 0) { if (qq < 0) return false; continue; }
    const r = qq / pp;
    if (pp < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; }
  }
  return t0 < t1;
}
