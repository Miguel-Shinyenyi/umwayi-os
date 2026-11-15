// W38, W38b: the source of the goal map. Two sources, chosen with a switch on the page:
//   file  a goal map file the visitor opens (the fixtures in ui/test/fixtures are such files); read in this browser only
//   live  GET /v1/goal-map of `umwayi serve` (W37), through the page client (src/api/client.js), the one module allowed to send
//         a request. The page is served by `umwayi serve --page ui/dist/goal-map.html` (W38b). It reads once when the page opens
//         and again only when the owner presses Refresh. There is no timer and no retry: W6.R14.6, the page does not poll.
//
// A reader never runs two reads at once: a press while a read is running is ignored.

import { createClient } from '../api/client.js';

export const LINES = Object.freeze({
  reading: 'Reading the goal map from umwayi...',
  read: (now) => `Read from umwayi${now ? ` at ${now}` : ''}. Press Refresh to read again.`,
});

// The live load of the page: one call of the route goal.map. Returns { ok: true, data } or { ok: false, message }.
export function liveLoad(client) {
  return async () => {
    const r = await client.call('goal.map');
    return r.ok ? { ok: true, data: r.data } : { ok: false, message: r.message };
  };
}

// load(): a promise of { ok: true, data } or { ok: false, message } (or, from a test, the text or object of a goal map). onData(data) and onDown(message) are told what happened.
export function createReader({ load, onData, onDown }) {
  let busy = false;
  let reads = 0;
  async function read() {
    if (busy) return false;
    busy = true;
    reads += 1;
    try {
      const r = await load();
      // a load gives { ok, data } or { ok: false, message }; a test may give the text or the object of a goal map itself
      const wrapped = r !== null && typeof r === 'object' && typeof r.ok === 'boolean';
      if (!wrapped) onData(r);
      else if (r.ok) onData(r.data);
      else onDown(typeof r.message === 'string' ? r.message : 'umwayi did not answer');
    } catch (e) {
      onDown('umwayi did not answer');
    } finally {
      busy = false;
    }
    return true;
  }
  return { read, get busy() { return busy; }, get reads() { return reads; } };
}

export { createClient };
