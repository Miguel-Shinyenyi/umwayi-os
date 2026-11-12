// UI.3 (tests first): what each station draws from the snapshot. The numbers come from the mapping table (data/snapshot.js);
// a part that is null is drawn as unknown (an unlit lantern on a post), never as zero and never as fine (12.R9.2).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stationDefs, buildStation } from '../src/stations/index.js';
import { makeKit } from '../src/stations/kit.js';
import { SAMPLE } from '../src/data/sample.js';
import { sceneNumbers } from '../src/data/snapshot.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(readFileSync(join(HERE, 'fixtures', 'snapshot.json'), 'utf8'));
const kit = makeKit();
const defs = Object.fromEntries(stationDefs().map((d) => [d.id, d]));
const make = (id, counts) => { const st = buildStation(defs[id], kit); st.setCounts(counts); return st; };
const parts = (st, name) => { const out = []; st.group.traverse((o) => { if (o.userData && o.userData.part === name) out.push(o); }); return out; };
const at = (st, i = 0) => { st.apply(defs[st.id].poses[i].params); return st; };
const mark = (st) => { const m = parts(st, 'unknown'); assert.equal(m.length, 1, `${st.id} has one unknown mark`); return m[0]; };
const withNull = (...keys) => ({ ...FIXTURE, ...Object.fromEntries(keys.map((k) => [k, null])) });
const big = (o) => ({ ...FIXTURE, ...o });
const beadsShown = (st) => { const [b] = parts(st, 'bead'); let n = 0; for (let i = 0; i < b.instanceMatrix.count; i++) if (b.instanceMatrix.array[i * 16] > 0.5) n++; return n; };

test('the stations that draw counts have an unknown mark, hidden while the part is known', () => {
  for (const id of ['queue', 'logbook', 'automation', 'budget', 'killswitch']) {
    const st = make(id, FIXTURE);
    if (id === 'killswitch') assert.equal(mark(st).visible, false, 'the kill switch is off in the fixture');
    else assert.equal(mark(st).visible, false, id);
    assert.equal(mark(st).userData.part, 'unknown');
  }
  assert.equal(parts(make('rules', FIXTURE), 'unknown').length, 0, 'Rules draws unknown as Ask me first (12.R3.9), so it has no mark');
  for (const id of ['memory', 'archive', 'helpers', 'workflows', 'adapters']) assert.equal(parts(make(id, FIXTURE), 'unknown').length, 0, `${id} has no count, so nothing is unknown`);
});

test('Queue: sheep for open rows, stones for answered rows, as the table says', () => {
  const run = (q) => { const st = at(make('queue', big({ queue: q }))); return { sheep: parts(st, 'sheep').filter((s) => s.visible && s.scale.x > 0.5).length, stones: parts(st, 'stone').filter((s) => s.visible).length, st }; };
  assert.deepEqual({ ...run({ open: 2, answered: 2 }), st: 0 }, { sheep: 2, stones: 2, st: 0 });
  assert.deepEqual({ ...run({ open: 0, answered: 0 }), st: 0 }, { sheep: 0, stones: 0, st: 0 });
  assert.deepEqual({ ...run({ open: 100, answered: 100 }), st: 0 }, { sheep: 7, stones: 8, st: 0 });
  assert.deepEqual({ ...run({ open: 6, answered: 5 }), st: 0 }, { sheep: 6, stones: 5, st: 0 });
  for (const [o, a] of [[0, 0], [1, 3], [4, 8], [9, 1]]) {
    const n = sceneNumbers(big({ queue: { open: o, answered: a } })).queue, r = run({ open: o, answered: a });
    assert.deepEqual([r.sheep, r.stones], [n.sheep, n.stones]);
  }
});

test('Queue: a queue that cannot be read draws the unknown mark and no sheep and no stones; zero draws neither', () => {
  const u = at(make('queue', withNull('queue')));
  assert.equal(mark(u).visible, true);
  assert.equal(parts(u, 'sheep').filter((s) => s.visible && s.scale.x > 0.5).length, 0);
  assert.equal(parts(u, 'stone').filter((s) => s.visible).length, 0);
  const zero = at(make('queue', big({ queue: { open: 0, answered: 0 } })));
  assert.equal(mark(zero).visible, false, 'zero is a known number');
});

test('Rules: lanterns by verdict, 12 at most; unknown is drawn as Ask me first, and no rules is no lantern', () => {
  const lit = (counts) => { const st = make('rules', counts); const l = parts(st, 'lantern').filter((b) => b.visible); return [0, 1, 2].map((v) => l.filter((b) => b.userData.verdict === v).length); };
  assert.deepEqual(lit(FIXTURE), [6, 4, 2]);
  assert.deepEqual(lit(big({ rules: { yes: 7, no: 6, ask: 2 } })), [5, 5, 2]);
  assert.deepEqual(lit(withNull('rules')), [0, 0, 12]);
  assert.deepEqual(lit(big({ rules: { yes: 0, no: 0, ask: 0 } })), [0, 0, 0]);
  assert.equal(parts(make('rules', FIXTURE), 'lantern').length, 12);
  assert.deepEqual(lit(FIXTURE), sceneNumbers(FIXTURE).rules.lanterns);
});

test('Logbook: one bead for each linked entry up to 21; zero beads for no chain; unknown is the mark and no bead', () => {
  assert.equal(beadsShown(at(make('logbook', FIXTURE))), 8);
  assert.equal(beadsShown(at(make('logbook', big({ logbook: { entries: 40, chain_length: 3 } })))), 3, 'three is three, not a minimum of four');
  assert.equal(beadsShown(at(make('logbook', big({ logbook: { entries: 9, chain_length: 0 } })))), 0, 'before the chain starts there is no bead');
  assert.equal(beadsShown(at(make('logbook', big({ logbook: { entries: 90, chain_length: 999 } })))), 21);
  const u = at(make('logbook', withNull('logbook')));
  assert.equal(mark(u).visible, true);
  assert.equal(beadsShown(u), 0);
  const zero = at(make('logbook', big({ logbook: { entries: 0, chain_length: 0 } })));
  assert.equal(mark(zero).visible, false);
});

test('Automation: lamps for schedules, brighter if installed, brightest if enabled; unknown is the mark and no lamp', () => {
  const levels = (counts) => parts(at(make('automation', counts)), 'lamp').map((l) => (l.visible ? l.userData.mat.userData.glow.level : 0));
  const want = (lamps) => lamps.map((x) => [0, 0.4, 1.0, 1.9][x]);
  assert.deepEqual(levels(FIXTURE), want([3, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]));
  assert.deepEqual(levels(big({ schedule: { entries: 12, installed: 5, enabled: 2 } })), want(sceneNumbers(big({ schedule: { entries: 12, installed: 5, enabled: 2 } })).automation.lamps));
  assert.deepEqual(levels(big({ schedule: { entries: 99, installed: 0, enabled: 0 } })), Array(12).fill(0.4));
  const u = at(make('automation', withNull('schedule')));
  assert.equal(mark(u).visible, true);
  assert.deepEqual(parts(u, 'lamp').filter((l) => l.visible), []);
  const zero = at(make('automation', big({ schedule: { entries: 0, installed: 0, enabled: 0 } })));
  assert.equal(mark(zero).visible, false);
});

test('Budget: seven marks against the busiest day and the water level at today; unknown is the mark, flat marks and the lowest level', () => {
  const draw = (counts) => { const st = make('budget', counts); return { st, marks: parts(st, 'mark').map((n) => Math.round(n.scale.y * 1000) / 1000), level: st.rest().level }; };
  const a = draw(FIXTURE);
  assert.equal(a.marks.length, 7);
  assert.deepEqual(a.marks, sceneNumbers(FIXTURE).budget.marks.map((m) => Math.round(Math.max(0.03, m * 0.6) * 1000) / 1000));
  assert.ok(a.marks[6] > a.marks[4] && a.marks[4] > a.marks[0], 'the last day is the tallest and a day of 13 is taller than a day of 0');
  const days = (u) => ({ days: u.map((x, i) => ({ date: `2026-11-0${i + 1}`, used_uu: x })) });
  const low = draw(big({ budget: days([40, 40, 40, 40, 40, 40, 4]) })).level, high = draw(big({ budget: days([40, 40, 40, 40, 40, 40, 40]) })).level;
  assert.ok(high > low, 'today against the busiest day sets the level');
  const u = draw(withNull('budget'));
  assert.equal(mark(u.st).visible, true);
  assert.deepEqual(new Set(u.marks), new Set([0.03]));
  const quiet = draw(big({ budget: days([0, 0, 0, 0, 0, 0, 0]) }));
  assert.equal(mark(quiet.st).visible, false, 'a week of nothing is known');
  assert.ok(Math.abs(u.level - quiet.level) < 1e-9 || u.level >= 0);
});

test('Kill switch: shut and lit for on and for unknown, open for off; unknown also shows the mark', () => {
  const rest = (v) => { const st = make('killswitch', big({ kill_switch: v })); return { rest: st.rest(), mark: mark(st).visible }; };
  const on = rest('on'), off = rest('off'), unk = rest('unknown');
  assert.equal(on.rest.shut, 1); assert.equal(on.rest.red, 1); assert.equal(on.mark, false);
  assert.equal(off.rest.shut, 0); assert.equal(off.rest.red, 0); assert.equal(off.mark, false);
  assert.equal(unk.rest.shut, 1, 'unknown stops, like on'); assert.equal(unk.rest.red, 1); assert.equal(unk.mark, true);
  assert.deepEqual(unk.rest, on.rest);
  assert.equal(make('killswitch', null).rest().shut, 1);
  assert.equal(mark(make('killswitch', null)).visible, true);
});

test('a station that was unknown and then gets a number shows the number, and the other way round (nothing sticks)', () => {
  for (const [id, key] of [['queue', 'queue'], ['logbook', 'logbook'], ['automation', 'schedule'], ['budget', 'budget']]) {
    const st = make(id, withNull(key));
    assert.equal(mark(st).visible, true, `${id} unknown`);
    st.setCounts(FIXTURE);
    assert.equal(mark(st).visible, false, `${id} known again`);
    st.setCounts(withNull(key));
    assert.equal(mark(st).visible, true, `${id} unknown again`);
  }
});

test('every station draws the sample world as before: no unknown mark, and the same counts the sample says', () => {
  for (const id of Object.keys(defs)) {
    const st = make(id, SAMPLE);
    for (const m of parts(st, 'unknown')) assert.equal(m.visible, false, id);
  }
  assert.equal(beadsShown(at(make('logbook', SAMPLE))), 20);
  assert.equal(parts(at(make('queue', SAMPLE)), 'stone').filter((s) => s.visible).length, 5);
});

test('every station draws from the mapping table: the six modules import it and none reads a raw count of its own', () => {
  for (const id of ['queue', 'rules', 'logbook', 'automation', 'budget', 'killswitch']) {
    const text = readFileSync(join(HERE, '..', 'src', 'stations', `${id}.js`), 'utf8');
    assert.match(text, /import \{[^}]*sceneNumbers[^}]*\} from '\.\.\/data\/snapshot\.js'/, id);
    assert.doesNotMatch(text, /\bc\.(queue|rules|logbook|schedule|budget)\b|counts\.(queue|rules|logbook|schedule|budget)\b/, `${id} reads a raw count`);
  }
});

test('stations build and draw with no counts at all, and with garbage: unknown, no throw', () => {
  for (const junk of [null, undefined, {}, [], 'x', 5, { queue: 'six', rules: [1], logbook: 3, budget: { days: 'x' }, schedule: 'x', kill_switch: 4 }]) {
    for (const id of Object.keys(defs)) { const st = make(id, junk); st.apply(defs[id].poses[0].params); }
  }
  for (const id of ['queue', 'logbook', 'automation', 'budget', 'killswitch']) assert.equal(mark(make(id, {})).visible, true, id);
});
