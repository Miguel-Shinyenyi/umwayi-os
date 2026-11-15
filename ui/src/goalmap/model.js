// W38: the goal map, read from the W37 contract (docs/goal-map.md, written by the W23 session). Pure: text or an object in, a
// model out. It reads only the fields of the contract below and nothing else; a field of the wrong type is shown as unknown,
// never guessed, and nothing here is ever turned into markup (draw.js puts every word in with textContent).
//
//   {version:1, now, kill_switch, goal:{id,title,state,budget:{used_uu,reserved_uu,cap_uu}|null,needs_owner}|null,
//    supervisor:{alive,pid_known,last_event_age_s,state}, tasks:[{id,title,state,role_now,worktree:{branch,clean}|null,age_s,
//    needs_owner_reason|null,pr|null}], events:[{t,kind,task|null,text}], notes:[]}

export const VERSION = 1;
export const MAX_BYTES = 1_000_000; // a goal map file larger than this is not read
export const MAX_TASKS = 50; // more are counted and not drawn
export const MAX_EVENTS = 8; // the feed shows the newest few
export const STALE_S = 300; // a supervisor whose last event is older than this is drawn grey (QUIET after 5 minutes, goal status)

// every state of a task, its word and its colour; the colours differ from each other and are readable on the dark page
export const STATES = Object.freeze({
  queued: { word: 'queued', colour: '#a8b3bd' },
  running: { word: 'running', colour: '#9cc39a' },
  'in review': { word: 'in review', colour: '#8fb7e8' },
  'needs owner': { word: 'needs owner', colour: '#e0a965' }, // the amber of the scene: the warm colour
  merged: { word: 'merged', colour: '#c3a6e8' },
  stopped: { word: 'stopped', colour: '#d8cfc0' },
  failed: { word: 'failed', colour: '#e07a6f' },
});
export const UNKNOWN = Object.freeze({ word: 'unknown', colour: '#7f796e' });
export const ROLES = Object.freeze(['builder', 'tester', 'guide']);

export const MESSAGES = Object.freeze({
  notJson: 'This file is not a goal map (it is not JSON). Nothing was drawn.',
  version: 'This is not a goal map of version 1. Nothing was drawn.',
  shape: 'This file does not have the shape of a goal map. Nothing was drawn.',
  tooBig: 'This file is too large to be a goal map, or it could not be read. Nothing was drawn.',
  noGoal: 'No goal yet. To start one, run: umwayi goal start "your goal in plain words" --guide NAME --plan-budget-uu N',
});

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isCount = (v) => isNum(v) && v >= 0;
// a word of the contract as plain text: strings only, control characters made into spaces, cut to a length
export function text(v, max = 200) {
  if (typeof v !== 'string') return null;
  // eslint-disable-next-line no-control-regex
  const t = v.replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/g, ' ').trim();
  return t.length > max ? `${t.slice(0, max - 3)}...` : t;
}
// a line that must fit a box of n characters
export const fit = (s, n) => (s.length > n ? `${s.slice(0, n - 3)}...` : s);

export const stateOf = (s) => (typeof s === 'string' && Object.hasOwn(STATES, s) ? { key: s, ...STATES[s] } : { key: null, ...UNKNOWN });

export function killOf(v) {
  if (v === 'off') return { key: 'off', word: 'off', note: 'helpers may run', lit: true };
  if (v === 'on') return { key: 'on', word: 'on', note: 'everything is stopped', lit: false };
  return { key: 'unknown', word: 'unknown', note: 'drawn as on', lit: false }; // what cannot be read is the safe side
}

export function supervisorOf(v) {
  const s = isObj(v) ? v : {};
  const age = isCount(s.last_event_age_s) ? s.last_event_age_s : null;
  const alive = s.alive === true;
  const stale = !alive || age === null || age >= STALE_S;
  let word;
  if (!isObj(v)) word = 'unknown';
  else if (!alive) word = 'not running';
  else if (age === null) word = 'age unknown';
  else if (stale) word = `quiet for ${Math.floor(age / 60)} min`;
  else word = 'alive';
  return { alive, stale, age, word, state: text(s.state, 40), pidKnown: s.pid_known === true };
}

export function ageWords(s) {
  if (!isCount(s)) return 'age unknown';
  if (s < 60) return `${Math.floor(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 172800) return `${Math.floor(s / 3600)} h`;
  return `${Math.floor(s / 86400)} days`;
}

function taskOf(t, i) {
  const o = isObj(t) ? t : {};
  const st = stateOf(o.state);
  const wt = isObj(o.worktree) ? { branch: text(o.worktree.branch, 80), clean: typeof o.worktree.clean === 'boolean' ? o.worktree.clean : null } : null;
  const role = typeof o.role_now === 'string' && ROLES.includes(o.role_now) ? o.role_now : null;
  const reason = text(o.needs_owner_reason, 120);
  return {
    id: text(o.id, 12) || `#${i + 1}`,
    title: text(o.title, 200) || '(no title)',
    state: st,
    role,
    worktree: wt,
    age: isCount(o.age_s) ? o.age_s : null,
    reason,
    needsOwner: st.key === 'needs owner',
    pr: Number.isInteger(o.pr) && o.pr > 0 ? o.pr : null,
  };
}

function eventOf(e) {
  const o = isObj(e) ? e : {};
  const t = typeof o.t === 'string' ? text(o.t, 25) : isNum(o.t) ? String(o.t) : null;
  return { t: t || '', kind: text(o.kind, 24) || 'event', task: text(o.task, 12), text: text(o.text, 160) || '' };
}

// raw: the text of a file or a response. Returns { ok: true, model } or { ok: false, message }.
export function readGoalMap(raw) {
  let data = raw;
  if (typeof raw === 'string') {
    if (raw.length > MAX_BYTES) return { ok: false, message: MESSAGES.tooBig };
    try {
      data = JSON.parse(raw);
    } catch {
      return { ok: false, message: MESSAGES.notJson };
    }
  }
  if (!isObj(data)) return { ok: false, message: MESSAGES.shape };
  if (data.version !== VERSION) return { ok: false, message: MESSAGES.version };
  if (!Array.isArray(data.tasks) || !Array.isArray(data.events) || !(data.goal === null || isObj(data.goal))) return { ok: false, message: MESSAGES.shape };
  const g = data.goal;
  const goal = g ? {
    id: text(g.id, 16) || 'goal',
    title: text(g.title, 200) || '(no title)',
    state: text(g.state, 30) || 'unknown',
    needsOwner: g.needs_owner === true,
    budget: isObj(g.budget) ? { used: isCount(g.budget.used_uu) ? g.budget.used_uu : null, reserved: isCount(g.budget.reserved_uu) ? g.budget.reserved_uu : null, cap: isCount(g.budget.cap_uu) ? g.budget.cap_uu : null } : null,
  } : null;
  const all = data.tasks.map(taskOf);
  return {
    ok: true,
    model: {
      now: text(data.now, 40),
      kill: killOf(data.kill_switch),
      goal,
      supervisor: supervisorOf(data.supervisor),
      tasks: all.slice(0, MAX_TASKS),
      hidden: Math.max(0, all.length - MAX_TASKS),
      events: data.events.slice(-MAX_EVENTS).reverse().map(eventOf), // newest first
      notes: Array.isArray(data.notes) ? data.notes.map((n) => text(n, 160)).filter(Boolean).slice(0, 5) : [],
    },
  };
}

export function budgetWords(b) {
  if (!b) return 'no budget set';
  const n = (v) => (v === null ? 'unknown' : `${v} UU`);
  return `used ${n(b.used)} of ${n(b.cap)}, reserved ${n(b.reserved)}`;
}

// the words of one task, the same in the map and the list
export function taskLines(t) {
  const role = t.role ? `${t.role} working` : 'no role now';
  const where = t.worktree ? `${t.worktree.branch || 'branch unknown'}${t.worktree.clean === false ? ' (changes)' : t.worktree.clean === true ? ' (clean)' : ''}` : 'no worktree';
  return {
    head: `${t.id} ${t.title}`,
    state: t.needsOwner && t.reason ? `${t.state.word}: ${t.reason}` : t.state.word,
    role,
    where,
    age: ageWords(t.age),
    pr: t.pr ? `PR ${t.pr}` : null,
  };
}
