// The two settings that change how the page moves and looks: reduced motion (from the system) and Calm mode (a button).
// Calm mode starts on when the system asks for less contrast (UI-Q9).
const REDUCED = '(prefers-reduced-motion: reduce)';
const LESS = '(prefers-contrast: less)';

export function createSettings({ matchMedia } = {}) {
  const listeners = [];
  const ask = (q) => {
    try {
      return matchMedia ? matchMedia(q) : null;
    } catch {
      return null;
    }
  };
  const mReduced = ask(REDUCED);
  const mLess = ask(LESS);
  const s = {
    reduced: !!(mReduced && mReduced.matches),
    calm: !!(mLess && mLess.matches),
    onChange(fn) {
      listeners.push(fn);
    },
    setCalm(on) {
      if (s.calm === !!on) return;
      s.calm = !!on;
      listeners.forEach((fn) => fn('calm', s.calm));
    },
    setReduced(on) {
      if (s.reduced === !!on) return;
      s.reduced = !!on;
      listeners.forEach((fn) => fn('reduced', s.reduced));
    },
  };
  if (mReduced && mReduced.addEventListener) mReduced.addEventListener('change', (e) => s.setReduced(e.matches));
  return s;
}
