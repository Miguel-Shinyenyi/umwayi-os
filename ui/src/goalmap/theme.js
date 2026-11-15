// W38: the Kiroween theme of the goal map, and nothing else. It is decoration only: every state keeps its word and its colour
// with the theme on or off, and every shape here stays inside the box layout.js keeps for it, away from every word.
// The shapes are drawn here as SVG path data (no picture file, no font, nothing from outside, no known character or brand).
//
// The theme is on unless the visitor turned it off (the T key, the button, or #theme=off in the address fragment), and it is
// always off when the system asks for reduced motion: the plain look is the one used then.

// a small jack-o-lantern on a 32 by 32 grid: the body, the stem, two eyes and a mouth (the face is cut out of the body)
export const PUMPKIN = {
  body: 'M16 7c-3 0-5 1-6 2-2-1-5 0-6 3-2 4-1 11 3 14 2 1 4 2 9 2s7-1 9-2c4-3 5-10 3-14-1-3-4-4-6-3-1-1-3-2-6-2z',
  stem: 'M15 3h3l-1 5h-2z',
  face: 'M9 14l4 0-2 4zM19 14l4 0-2 4zM9 21c2 3 4 4 7 4s5-1 7-4l-3 1-1-1-3 2-3-2-1 1z',
};
// a candle and its flame on a 28 by 28 grid (the flame is the part that flickers)
export const CANDLE = {
  wax: 'M10 13h8v13h-8z',
  flame: 'M14 2c3 4 4 6 4 8a4 4 0 0 1-8 0c0-2 1-4 4-8z',
};
// a small ghost on a 28 by 28 grid: a round head, a wavy hem, two eyes
export const GHOST = {
  body: 'M4 26V13a10 10 0 0 1 20 0v13l-3-3-3 3-4-3-4 3-3-3z',
  eyes: 'M10 11h2v3h-2zM16 11h2v3h-2z',
};
// a tiny bat on a 12 by 12 grid, centred on 0,0
export const BAT = 'M0 -1c1 0 1 1 1 1l2-2c0 2 1 3 3 3-2 0-3 1-3 3-1-1-2-1-3-1s-2 0-3 1c0-2-1-3-3-3 2 0 3-1 3-3l2 2s0-1 1-1z';

export const TITLE_WORD = 'Kiroween';

const params = (hash) => String(hash || '').replace(/^#/, '').split('&').filter(Boolean);
export function themeFromHash(hash) {
  for (const p of params(hash)) {
    const [k, v] = p.split('=');
    if (k === 'theme' && (v === 'off' || v === 'on')) return v === 'on';
  }
  return null;
}
export function themeHash(hash, on) {
  const rest = params(hash).filter((p) => p.split('=')[0] !== 'theme');
  return '#' + [...rest, `theme=${on ? 'on' : 'off'}`].join('&');
}

// the theme switch: what the visitor chose, and what is drawn (never the theme under reduced motion)
export function createTheme({ chosen = null, reduced = false } = {}) {
  const t = {
    chosen: chosen === null ? true : !!chosen,
    reduced: !!reduced,
    get on() { return t.chosen && !t.reduced; },
    toggle() { t.chosen = !t.chosen; return t.on; },
    setReduced(v) { t.reduced = !!v; return t.on; },
  };
  return t;
}

// The T key turns the theme on and off: only the plain key, never with a modifier, and never while the visitor types in a field.
export function isThemeKey(e) {
  if (!e || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return false;
  if (e.key !== 't' && e.key !== 'T') return false;
  const tag = e.target && e.target.tagName ? String(e.target.tagName).toLowerCase() : '';
  return !(tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable));
}

// what the small picture of a card is: the plain look has a marker in the state colour (a calm pulse on a running task); the
// theme has a candle that flickers on a running task, a ghost on a stopped or failed one, and the marker for the rest.
export function slotPicture(stateKey, themeOn) {
  if (themeOn && stateKey === 'running') return 'candle';
  if (themeOn && (stateKey === 'stopped' || stateKey === 'failed')) return 'ghost';
  return 'marker';
}
// a bat circles a task that needs the owner, with the theme on and nothing moving under reduced motion
export const hasBat = (stateKey, themeOn) => themeOn && stateKey === 'needs owner';
