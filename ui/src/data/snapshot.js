// The snapshot, read as untrusted input (12.R9.1), and what the page makes of it. Pure, except readSnapshotFile, which uses the
// browser's FileReader on a file the owner picked or dropped: the page reads the file in the browser and makes no request.
//
//   parseSnapshot(text)       the strict reader. { ok: true, snapshot } or { ok: false }; nothing of the file comes back on a refusal.
//   readSnapshotFile(file)    the size check, FileReader.readAsText, then parseSnapshot. Never rejects.
//   needsFrom(counts)         the numbers that feed the position function (12.R3.6): { id: 0..1 } for the eleven stations.
//   sceneNumbers(counts)      the mapping table (12.R3.9): counts to sheep, stones, lanterns, beads, lamps, marks and the water level.
//   viewOf(snapshot | null)   what the page shows: the counts, the label, the footer and the needs. Sample if and only if no snapshot.
import { SAMPLE } from './sample.js';
import { DEFAULT_NEED } from '../world/layout.js';
import { IDS } from '../stations/meta.js';

export const NOT_A_SNAPSHOT = 'This file is not a snapshot of this version';
export const MAX_BYTES = 4096; // 12.R9.1
export const MAX_COUNT = 1000000000; // 12.R4.3
export const SCHEMA = 1;
export const QUEUE_FULL = 6; // a queue of this many open rows or more is the full need
export const BUDGET_FULL = 0.5; // today this far above the average of the other six days is the full need (1.5 times)

const WORDS = ['on', 'off', 'unknown'];
const KEYS = ['schema', 'date', 'queue', 'rules', 'logbook', 'budget', 'kill_switch', 'schedule'];
const PARTS = {
  queue: ['open', 'answered'],
  rules: ['yes', 'no', 'ask'],
  logbook: ['entries', 'chain_length'],
  schedule: ['entries', 'installed', 'enabled'],
};
const DAYS = 7;

// ------------------------------------------------------------------------------------------------ the strict reader
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const plain = (v) => v !== null && typeof v === 'object' && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
const exact = (o, keys) => plain(o) && Object.keys(o).length === keys.length && keys.every((k) => own(o, k));
const whole = (v) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= MAX_COUNT;
const isDate = (v) => {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const t = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(t.getTime()) && t.toISOString().slice(0, 10) === v;
};
const numbers = (o, keys) => exact(o, keys) && keys.every((k) => whole(o[k]));
const freeze = (o) => { Object.values(o).forEach((v) => { if (v && typeof v === 'object') freeze(v); }); return Object.freeze(o); };

// The same rules as `valid` in umwayi/view.py, so a file the command wrote is accepted and nothing else is.
function shapeOk(o) {
  if (!exact(o, KEYS) || o.schema !== SCHEMA || !isDate(o.date) || !WORDS.includes(o.kill_switch)) return false;
  for (const [name, keys] of Object.entries(PARTS)) if (o[name] !== null && !numbers(o[name], keys)) return false;
  const b = o.budget;
  if (b === null) return true;
  return exact(b, ['days']) && Array.isArray(b.days) && b.days.length === DAYS
    && b.days.every((d) => exact(d, ['date', 'used_uu']) && isDate(d.date) && whole(d.used_uu));
}

// A fresh object built from the checked leaves only, so nothing of the parsed file is kept.
function copyOf(o) {
  const out = { schema: o.schema, date: o.date };
  for (const name of ['queue', 'rules', 'logbook']) out[name] = o[name] === null ? null : Object.fromEntries(PARTS[name].map((k) => [k, o[name][k]]));
  out.budget = o.budget === null ? null : { days: o.budget.days.map((d) => ({ date: d.date, used_uu: d.used_uu })) };
  out.kill_switch = o.kill_switch;
  out.schedule = o.schedule === null ? null : Object.fromEntries(PARTS.schedule.map((k) => [k, o.schedule[k]]));
  return freeze(out);
}

export function parseSnapshot(text) {
  try {
    if (typeof text !== 'string' || new TextEncoder().encode(text).length > MAX_BYTES) return { ok: false };
    const parsed = JSON.parse(text);
    if (!shapeOk(parsed)) return { ok: false };
    // The file must be the command's own text: a key given twice, an escaped key, 2.0 or 1e0 for a whole number, -0.
    // JSON.parse would accept all of them. No string of a snapshot holds white space, so removing it gives one form.
    if (text.replace(/[ \t\r\n]+/g, '') !== JSON.stringify(parsed)) return { ok: false };
    return { ok: true, snapshot: copyOf(parsed) };
  } catch {
    return { ok: false };
  }
}

export function readSnapshotFile(file, Reader = globalThis.FileReader) {
  return new Promise((resolve) => {
    const refuse = () => resolve({ ok: false });
    try {
      if (!Reader || !file || typeof file.size !== 'number' || !(file.size >= 0) || file.size > MAX_BYTES) { refuse(); return; }
      const reader = new Reader();
      reader.onload = () => resolve(typeof reader.result === 'string' ? parseSnapshot(reader.result) : { ok: false });
      reader.onerror = refuse;
      reader.onabort = refuse;
      reader.readAsText(file, 'utf-8');
    } catch {
      refuse();
    }
  });
}

// ------------------------------------------------------------------------------------------------ the needs (12.R3.6)
// A need runs from DEFAULT_NEED (quiet: the station stands where it stands by default) to 1 (it needs the owner now, so it comes
// nearer). A part that cannot be read, and a bad number, are DEFAULT_NEED. Only the kill switch stops on what it cannot tell.
const QUIET = DEFAULT_NEED;
const rise = (share) => QUIET + (1 - QUIET) * Math.min(1, Math.max(0, share));
const good = (v) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;

function queueNeed(q) {
  if (!plain(q) || !good(q.open)) return DEFAULT_NEED;
  return rise(q.open / QUEUE_FULL);
}
function killNeed(word) {
  return word === 'off' ? QUIET : 1; // on, unknown and anything else stop
}
function budgetNeed(b) {
  const days = budgetDays(b);
  if (!days) return DEFAULT_NEED;
  const today = days[DAYS - 1];
  const average = days.slice(0, DAYS - 1).reduce((s, v) => s + v, 0) / (DAYS - 1);
  if (average === 0) return today > 0 ? 1 : QUIET;
  return rise((today - average) / average / BUDGET_FULL);
}
function budgetDays(b) {
  if (!plain(b) || !Array.isArray(b.days) || b.days.length !== DAYS) return null;
  const used = b.days.map((d) => (plain(d) ? d.used_uu : NaN));
  return used.every(good) ? used : null;
}

export function needsFrom(counts) {
  const c = plain(counts) ? counts : {};
  const needs = Object.fromEntries(IDS.map((id) => [id, DEFAULT_NEED]));
  needs.queue = queueNeed(c.queue);
  needs.killswitch = killNeed(c.kill_switch);
  needs.budget = budgetNeed(c.budget);
  return needs;
}

// ------------------------------------------------------------------------------------------------ the mapping table (12.R3.9)
export const LIMITS = { sheep: 7, stones: 8, lanterns: 12, beads: 21, lamps: 12 };

const unknown = (rest) => ({ unknown: true, ...rest });

function queueNumbers(q) {
  if (!plain(q) || !good(q.open) || !good(q.answered)) return unknown({ sheep: 0, stones: 0 });
  return { unknown: false, sheep: Math.min(q.open, LIMITS.sheep), stones: Math.min(q.answered, LIMITS.stones) };
}
// Lamps on the wall, shares of 12: a verdict that has rules shows at least one; the largest gives one up while the total is over 12.
function rulesNumbers(r) {
  if (!plain(r) || !good(r.yes) || !good(r.no) || !good(r.ask)) return unknown({ lanterns: [0, 0, LIMITS.lanterns] }); // unknown is Ask me first
  const n = [r.yes, r.no, r.ask];
  const total = Math.max(1, n[0] + n[1] + n[2]);
  const shown = n.map((v) => (v > 0 ? Math.max(1, Math.round((v / total) * LIMITS.lanterns)) : 0));
  while (shown[0] + shown[1] + shown[2] > LIMITS.lanterns) shown[shown.indexOf(Math.max(...shown))]--;
  return { unknown: false, lanterns: shown };
}
function logbookNumbers(l) {
  if (!plain(l) || !good(l.chain_length)) return unknown({ beads: 0 });
  return { unknown: false, beads: Math.min(l.chain_length, LIMITS.beads) };
}
function killNumbers(word) {
  return { unknown: !(word === 'on' || word === 'off'), shut: word !== 'off' }; // unknown is drawn as on
}
// One value for each of the 12 lamps: 0 dark, 1 a schedule, 2 installed, 3 enabled.
function automationNumbers(s) {
  if (!plain(s) || !good(s.entries) || !good(s.installed) || !good(s.enabled)) return unknown({ lamps: Array(LIMITS.lamps).fill(0) });
  const lamps = Array.from({ length: LIMITS.lamps }, (_, i) => (i >= s.entries ? 0 : i < s.enabled ? 3 : i < s.installed ? 2 : 1));
  return { unknown: false, lamps };
}
// marks: the seven days against the busiest, 0 to 1. level: today against the busiest day, 0 to 1.
function budgetNumbers(b) {
  const days = budgetDays(b);
  if (!days) return unknown({ marks: Array(DAYS).fill(0), level: 0 });
  const max = Math.max(...days);
  if (max === 0) return { unknown: false, marks: Array(DAYS).fill(0), level: 0 };
  return { unknown: false, marks: days.map((v) => v / max), level: days[DAYS - 1] / max };
}

export function sceneNumbers(counts) {
  const c = plain(counts) ? counts : {};
  return {
    queue: queueNumbers(c.queue),
    rules: rulesNumbers(c.rules),
    logbook: logbookNumbers(c.logbook),
    killswitch: killNumbers(c.kill_switch),
    automation: automationNumbers(c.schedule),
    budget: budgetNumbers(c.budget),
  };
}

// ------------------------------------------------------------------------------------------------ what the page shows
export const SAMPLE_LABEL = 'sample';
export const SAMPLE_FOOTER = 'A sample world. The picture shows made up counts until you load your own.';

// "sample" is shown if and only if no snapshot is loaded (12.R3.8, 12.R4.10). Sample and real counts are never mixed.
export function viewOf(snapshot) {
  if (!snapshot) return { sample: true, counts: SAMPLE, date: SAMPLE.date, label: SAMPLE_LABEL, footer: SAMPLE_FOOTER, needs: {} };
  return {
    sample: false,
    counts: snapshot,
    date: snapshot.date,
    label: `snapshot ${snapshot.date}`,
    footer: `Your snapshot of ${snapshot.date}. The picture and the numbers are from that file. Run umwayi view snapshot again to refresh it.`,
    needs: needsFrom(snapshot),
  };
}

// A loaded view goes to the scene in the one way the scene has: the counts the features draw, then the needs for setNeeds, the
// position function's only input (12.R3.6). Nothing else of the scene is touched.
export function feedScene(scene, view) {
  scene.setCounts(view.counts, view.sample);
  scene.setNeeds(view.needs);
}
