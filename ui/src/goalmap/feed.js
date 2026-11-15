// W38: the source of the goal map. Two sources, chosen with a switch on the page:
//   file  a goal map file the visitor opens (the fixtures in ui/test/fixtures are such files); read in this browser only
//   live  the backend of W37 (GET /api/goal-map). It is not merged yet, so the page sends nothing: liveLoad() always says "not
//         connected", the page shows one plain line and tries again slowly. When W37 lands, liveLoad becomes one route of the
//         page client (src/api/client.js), the one module allowed to send a request, and nothing else here changes.
//
// The loop never runs two loads at once, waits OK_MS between good reads and longer and longer (RETRY_MS) after a failure.

export const OK_MS = 5000;
export const RETRY_MS = Object.freeze([15000, 30000, 60000]);

export class NotConnected extends Error {
  constructor() { super('not connected'); this.name = 'NotConnected'; }
}
export const liveLoad = () => Promise.reject(new NotConnected());

export const LINES = Object.freeze({
  notConnected: (s) => `No live goal map: this page is not connected to umwayi yet. Open a goal map file instead. Trying again in ${s} s.`,
  unreachable: (s) => `umwayi did not answer. Trying again in ${s} s.`,
});

// load(): a promise of the text (or object) of a goal map. onData(raw), onDown(line) are told what happened.
export function createFeed({ load, onData, onDown, setTimer, clearTimer }) {
  let timer = null, failures = 0, stopped = false, busy = false;
  const next = (ms) => { if (!stopped) timer = setTimer(tick, ms); };
  async function tick() {
    timer = null;
    if (stopped || busy) return;
    busy = true;
    try {
      const raw = await load();
      if (stopped) return;
      failures = 0;
      onData(raw);
      next(OK_MS);
    } catch (e) {
      if (stopped) return;
      const ms = RETRY_MS[Math.min(failures, RETRY_MS.length - 1)];
      failures += 1;
      onDown((e instanceof NotConnected ? LINES.notConnected : LINES.unreachable)(Math.round(ms / 1000)));
      next(ms);
    } finally {
      busy = false;
    }
  }
  return {
    start() { stopped = false; if (!timer) tick(); },
    stop() { stopped = true; if (timer) clearTimer(timer); timer = null; },
    get failures() { return failures; },
  };
}
