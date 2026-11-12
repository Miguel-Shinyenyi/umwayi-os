// UI.3 (tests first): the strict reader of the snapshot (12.R9.1), the needs that feed the position function (12.R3.6),
// the mapping from counts to scene numbers (12.R3.9) and the rule that "sample" shows if and only if no snapshot is loaded.
// Pure data: no browser, no DOM. The real file made by `umwayi view snapshot` is ui/test/fixtures/snapshot.json.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  NOT_A_SNAPSHOT, MAX_BYTES, MAX_COUNT, parseSnapshot, readSnapshotFile, needsFrom, sceneNumbers, viewOf, QUEUE_FULL,
} from '../src/data/snapshot.js';
import { statusStrip } from '../src/data/home.js';
import { SAMPLE } from '../src/data/sample.js';
import { IDS } from '../src/stations/meta.js';
import { stationPositions, DEFAULT_NEED, TABLE } from '../src/world/layout.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = readFileSync(join(HERE, 'fixtures', 'snapshot.json'), 'utf8');
const good = () => JSON.parse(FIXTURE);
const text = (o) => JSON.stringify(o, null, 2) + '\n';
const refused = (t, why = '') => assert.deepEqual(parseSnapshot(t), { ok: false }, why || String(t).slice(0, 80));
const accepted = (t) => { const r = parseSnapshot(t); assert.equal(r.ok, true, JSON.stringify(r)); return r.snapshot; };
const dist = (p) => Math.hypot(p.x, p.z);
const sortedKeys = (o) => Object.keys(o).sort();

// ------------------------------------------------------------------------------------------------ the one message
test('the one message is the words of 12.R9.1, and the limits are those of 12.R4', () => {
  assert.equal(NOT_A_SNAPSHOT, 'This file is not a snapshot of this version');
  assert.equal(MAX_BYTES, 4096);
  assert.equal(MAX_COUNT, 1000000000);
  assert.ok(!/[\u2014\u2013]/.test(NOT_A_SNAPSHOT));
});

// ------------------------------------------------------------------------------------------------ the fixture is accepted
test('the fixture of UI.2 is accepted, and what comes back holds the file\'s numbers and nothing else', () => {
  const s = accepted(FIXTURE);
  assert.deepEqual(s, good());
  assert.deepEqual(sortedKeys(s), ['budget', 'date', 'kill_switch', 'logbook', 'queue', 'rules', 'schedule', 'schema']);
  assert.equal(s.date, '2026-11-11');
  assert.deepEqual(s.queue, { open: 2, answered: 2 });
  assert.deepEqual(s.budget.days.map((d) => d.used_uu), [0, 0, 0, 0, 13, 0, 105]);
});

test('what comes back is a copy: the parsed object of the file is not the object the page keeps', () => {
  const a = accepted(FIXTURE), b = accepted(FIXTURE);
  assert.notEqual(a, b);
  assert.notEqual(a.queue, b.queue);
  assert.ok(Object.isFrozen(a) && Object.isFrozen(a.queue) && Object.isFrozen(a.budget.days[0]), 'the page cannot change it by mistake');
});

test('the shapes the command can write are accepted: null parts, the other kill switch words, the limits of the ranges', () => {
  for (const part of ['queue', 'rules', 'logbook', 'budget', 'schedule']) {
    const o = good(); o[part] = null;
    assert.equal(accepted(text(o))[part], null, part);
  }
  for (const w of ['on', 'off', 'unknown']) assert.equal(accepted(text({ ...good(), kill_switch: w })).kill_switch, w);
  const o = good();
  o.queue = { open: 0, answered: MAX_COUNT };
  o.logbook = { entries: MAX_COUNT, chain_length: 0 };
  assert.deepEqual(accepted(text(o)).queue, { open: 0, answered: 1000000000 });
  const all = good(); for (const k of ['queue', 'rules', 'logbook', 'budget', 'schedule']) all[k] = null;
  accepted(text(all));
});

test('the command\'s own bytes are accepted whatever the whitespace: compact, tabs, windows line ends', () => {
  accepted(JSON.stringify(good()));
  accepted(JSON.stringify(good(), null, '\t'));
  accepted(FIXTURE.replace(/\n/g, '\r\n'));
});

// ------------------------------------------------------------------------------------------------ each bad shape
test('an extra key, at the top and in every part, is refused', () => {
  refused(text({ ...good(), extra: 1 }), 'top');
  for (const part of ['queue', 'rules', 'logbook', 'schedule']) {
    const o = good(); o[part] = { ...o[part], extra: 1 };
    refused(text(o), part);
  }
  const b = good(); b.budget.extra = 1; refused(text(b), 'budget');
  const d = good(); d.budget.days[3].extra = 1; refused(text(d), 'a day');
});

test('a missing key, at the top and in every part, is refused', () => {
  for (const k of Object.keys(good())) { const o = good(); delete o[k]; refused(text(o), k); }
  for (const part of ['queue', 'rules', 'logbook', 'schedule']) {
    for (const k of Object.keys(good()[part])) { const o = good(); delete o[part][k]; refused(text(o), `${part}.${k}`); }
  }
  const b = good(); delete b.budget.days; refused(text(b), 'days');
  const d = good(); delete d.budget.days[0].used_uu; refused(text(d), 'used_uu');
  const e = good(); delete e.budget.days[0].date; refused(text(e), 'day date');
});

test('a string where a number belongs is refused, in every number', () => {
  const places = [['queue', 'open'], ['queue', 'answered'], ['rules', 'yes'], ['rules', 'no'], ['rules', 'ask'], ['logbook', 'entries'],
    ['logbook', 'chain_length'], ['schedule', 'entries'], ['schedule', 'installed'], ['schedule', 'enabled']];
  for (const [part, k] of places) {
    for (const bad of ['3', '', 'three', '0x10', null, true, [3], { n: 3 }]) {
      const o = good(); o[part][k] = bad; refused(text(o), `${part}.${k}=${JSON.stringify(bad)}`);
    }
  }
  const d = good(); d.budget.days[6].used_uu = '105'; refused(text(d), 'used_uu');
  const s = good(); s.schema = '1'; refused(text(s), 'schema as a string');
});

test('a float, a negative and a number over a billion are refused, and the edges of the range are not', () => {
  const places = [['queue', 'open'], ['rules', 'ask'], ['logbook', 'chain_length'], ['schedule', 'enabled']];
  for (const [part, k] of places) {
    for (const bad of [1.5, 0.1, -1, 1000000001, 2 ** 53, -0.5, 1e21]) {
      const o = good(); o[part][k] = bad; refused(text(o), `${part}.${k}=${bad}`);
    }
    const lo = good(); lo[part][k] = 0; accepted(text(lo));
    const hi = good(); hi[part][k] = 1000000000; accepted(text(hi));
  }
  const d = good(); d.budget.days[2].used_uu = -3; refused(text(d), 'negative used_uu');
  const e = good(); e.budget.days[2].used_uu = 1000000001; refused(text(e), 'big used_uu');
  const f = good(); f.budget.days[2].used_uu = 2.25; refused(text(f), 'float used_uu');
});

test('a number written as a float or with an exponent is refused even when its value is whole (the file is the command\'s text)', () => {
  refused(FIXTURE.replace('"open": 2', '"open": 2.0'), '2.0');
  refused(FIXTURE.replace('"open": 2', '"open": 2e0'), '2e0');
  refused(FIXTURE.replace('"open": 2', '"open": 0.2e1'), '0.2e1');
  refused(FIXTURE.replace('"answered": 2', '"answered": -0'), '-0');
  refused(FIXTURE.replace('"schema": 1', '"schema": 1.0'), 'schema 1.0');
});

test('a file of 4096 bytes is read and a file of 4097 bytes is refused, by bytes and not by characters', () => {
  const pad = (n) => {
    const o = good();
    const base = Buffer.byteLength(text(o));
    return text(o) + ' '.repeat(n - base); // trailing white space is not data
  };
  assert.equal(Buffer.byteLength(pad(4096)), 4096);
  accepted(pad(4096));
  refused(pad(4097), '4097 bytes');
  refused(pad(5000), '5000 bytes');
  // two bytes a character: 2049 characters is 4098 bytes, which is over
  const wide = text(good()) + '\u00e9'.repeat(2049);
  assert.ok(wide.length <= 4096 && Buffer.byteLength(wide) > 4096);
  refused(wide, 'by bytes');
  refused('x'.repeat(4097));
});

test('text that is not JSON, and JSON that is not an object, is refused', () => {
  for (const t of ['', ' ', 'not json', '{', '{"schema":1', "{'schema': 1}", '[]', '[1]', 'null', 'true', '1', '"snapshot"', '{}', FIXTURE.slice(0, 200),
    FIXTURE + 'x', FIXTURE + FIXTURE, '\ufeff' + FIXTURE, `# comment\n${FIXTURE}`, FIXTURE.replace(/"/g, "'")]) refused(t, JSON.stringify(t).slice(0, 40));
  for (const t of [undefined, null, 5, {}, [], Buffer.from(FIXTURE)]) refused(t, String(typeof t));
});

test('schema 2 and any schema but 1 are refused', () => {
  for (const v of [2, 0, -1, 1.5, '1', null, true, [1]]) refused(text({ ...good(), schema: v }), `schema ${JSON.stringify(v)}`);
  accepted(text({ ...good(), schema: 1 }));
});

test('a nested extra object is refused, wherever it hides', () => {
  const a = good(); a.queue = { open: 1, answered: { n: 1 } }; refused(text(a), 'object for a number');
  const b = good(); b.queue = { open: 1, answered: 1, deeper: { open: 1, answered: 1 } }; refused(text(b), 'nested in a part');
  const c = good(); c.budget = { days: good().budget.days, more: { days: [] } }; refused(text(c), 'nested in budget');
  const d = good(); d.budget.days[0] = { date: '2026-11-05', used_uu: { v: 0 } }; refused(text(d), 'object in a day');
  const e = good(); e.kill_switch = { v: 'on' }; refused(text(e), 'object for the word');
  const f = good(); f.extra = { schema: 1 }; refused(text(f), 'a second snapshot inside');
  const g = good(); g.budget.days[0] = [0, 0]; refused(text(g), 'an array for a day');
  refused(text(good()) + text(good()), 'two snapshots one after the other');
  const i = good(); i.queue = [2, 2]; refused(text(i), 'an array for a part');
});

test('the kill switch is on, off or unknown; any other word, case or type is refused', () => {
  for (const v of ['ON', 'Off', 'yes', 'no', '', 'unknown ', ' on', 'null', null, true, false, 0, 1, undefined]) {
    const o = good(); if (v === undefined) delete o.kill_switch; else o.kill_switch = v;
    refused(text(o), `kill_switch ${JSON.stringify(v)}`);
  }
});

test('the dates are real dates in the form YYYY-MM-DD, and anything else is refused', () => {
  const bad = ['2026-13-01', '2026-02-30', '2026-00-10', '2026-11-31', '26-11-11', '2026/11/11', '2026-1-1', '2026-11-11T00:00:00Z', ' 2026-11-11',
    '2026-11-11\n', '', 'today', null, 20261111, ['2026-11-11'], '２０２６-11-11'];
  for (const v of bad) { const o = good(); o.date = v; refused(text(o), `date ${JSON.stringify(v)}`); }
  for (const v of bad) { const o = good(); o.budget.days[3].date = v; refused(text(o), `day date ${JSON.stringify(v)}`); }
  const leap = good(); leap.date = '2028-02-29'; accepted(text(leap));
  const notLeap = good(); notLeap.date = '2027-02-29'; refused(text(notLeap));
});

test('the budget holds exactly seven days', () => {
  for (const n of [0, 1, 6, 8, 14]) {
    const o = good(); o.budget.days = Array.from({ length: n }, (_, i) => ({ date: `2026-11-0${(i % 9) + 1}`, used_uu: i }));
    refused(text(o), `${n} days`);
  }
  const o = good(); o.budget.days = 'seven'; refused(text(o));
  const p = good(); p.budget = []; refused(text(p));
});

test('a key given twice, an escaped key and a key from the prototype chain are refused', () => {
  refused(FIXTURE.replace('"schema": 1,', '"schema": 1,\n  "schema": 1,'), 'a key twice');
  refused(FIXTURE.replace('"open": 2', '"open": 9,\n    "open": 2'), 'a nested key twice');
  refused(FIXTURE.replace('"schema"', '"sch\\u0065ma"'), 'an escaped key');
  refused('{"__proto__": {"schema": 1}, ' + FIXTURE.trim().slice(1), '__proto__ as a key');
  const o = good(); o.queue = JSON.parse('{"open": 1, "answered": 1, "__proto__": {"x": 1}}'); refused(text(o), 'nested __proto__');
  refused(FIXTURE.replace('"queue"', '"constructor"'), 'constructor for queue');
});

test('the refusal gives back nothing from the file: no field of it is in the result', () => {
  for (const t of [FIXTURE.replace('"schema": 1', '"schema": 2'), text({ ...good(), extra: 'QSENTINEL' }), 'SECRETSENTINEL']) {
    const r = parseSnapshot(t);
    assert.deepEqual(r, { ok: false });
    assert.ok(!JSON.stringify(r).includes('SENTINEL'));
  }
});

// ------------------------------------------------------------------------------------------------ reading the file
function fakeReader({ result, fail = false, abort = false, seen = {} } = {}) {
  return class {
    readAsText(file, enc) {
      seen.called = (seen.called || 0) + 1; seen.file = file; seen.enc = enc;
      Promise.resolve().then(() => {
        if (fail) return this.onerror && this.onerror(new Error('boom'));
        if (abort) return this.onabort && this.onabort();
        this.result = result;
        return this.onload && this.onload();
      });
    }
    readAsDataURL() { seen.dataUrl = true; }
    readAsArrayBuffer() { seen.buffer = true; }
    readAsBinaryString() { seen.binary = true; }
  };
}

test('readSnapshotFile reads with readAsText and nothing else, and checks the result', async () => {
  const seen = {};
  const file = { size: FIXTURE.length, name: 'snapshot.json' };
  const r = await readSnapshotFile(file, fakeReader({ result: FIXTURE, seen }));
  assert.equal(r.ok, true);
  assert.deepEqual(r.snapshot, good());
  assert.equal(seen.called, 1);
  assert.equal(seen.file, file);
  assert.ok(!seen.dataUrl && !seen.buffer && !seen.binary);
  assert.match(String(seen.enc), /^utf-?8$/i);
});

test('readSnapshotFile refuses a file over 4096 bytes before it reads it', async () => {
  const seen = {};
  assert.deepEqual(await readSnapshotFile({ size: 4097 }, fakeReader({ result: FIXTURE, seen })), { ok: false });
  assert.equal(seen.called, undefined, 'a file that is too big is not read at all');
  const at = await readSnapshotFile({ size: 4096 }, fakeReader({ result: FIXTURE, seen }));
  assert.equal(at.ok, true, 'the size of 4096 is allowed');
});

test('readSnapshotFile never throws or rejects: a read error, an abort, a result that is not text and a missing reader are the one refusal', async () => {
  const file = { size: 100 };
  assert.deepEqual(await readSnapshotFile(file, fakeReader({ fail: true })), { ok: false });
  assert.deepEqual(await readSnapshotFile(file, fakeReader({ abort: true })), { ok: false });
  assert.deepEqual(await readSnapshotFile(file, fakeReader({ result: new ArrayBuffer(8) })), { ok: false });
  assert.deepEqual(await readSnapshotFile(file, fakeReader({ result: null })), { ok: false });
  assert.deepEqual(await readSnapshotFile(file, undefined), { ok: false });
  assert.deepEqual(await readSnapshotFile(null, fakeReader({ result: FIXTURE })), { ok: false });
  assert.deepEqual(await readSnapshotFile({}, fakeReader({ result: FIXTURE })), { ok: false });
  assert.deepEqual(await readSnapshotFile({ size: -1 }, fakeReader({ result: FIXTURE })), { ok: false });
  assert.deepEqual(await readSnapshotFile({ size: '100' }, fakeReader({ result: FIXTURE })), { ok: false });
  const throwing = class { readAsText() { throw new Error('no'); } };
  assert.deepEqual(await readSnapshotFile(file, throwing), { ok: false });
  const constructorThrows = class { constructor() { throw new Error('no'); } };
  assert.deepEqual(await readSnapshotFile(file, constructorThrows), { ok: false });
  assert.deepEqual(await readSnapshotFile({ size: 100 }, fakeReader({ result: 'not json' })), { ok: false });
});

// ------------------------------------------------------------------------------------------------ the needs (12.R3.6)
test('the needs: a queue of 6 or more gives need 1, and fewer give less', () => {
  const q = (open) => needsFrom({ ...good(), queue: { open, answered: 0 } }).queue;
  assert.equal(QUEUE_FULL, 6);
  assert.equal(q(6), 1);
  assert.equal(q(7), 1);
  assert.equal(q(1000000000), 1);
  assert.ok(q(5) < 1 && q(5) > q(4) && q(4) > q(3) && q(3) > q(2) && q(2) > q(1) && q(1) > q(0));
  assert.ok(Math.abs(q(3) - 0.7) < 1e-9, 'half the way from quiet to full');
  assert.equal(q(0), DEFAULT_NEED, 'a quiet queue stands where it stands by default');
});

test('the needs: the kill switch on or unknown gives 1, off gives the quiet need', () => {
  const k = (v) => needsFrom({ ...good(), kill_switch: v }).killswitch;
  assert.equal(k('on'), 1);
  assert.equal(k('unknown'), 1);
  assert.equal(k('off'), DEFAULT_NEED);
  for (const bad of [undefined, null, 'ON', 7, '', {}]) assert.equal(k(bad), 1, `${String(bad)} is not off, so it stops`);
});

test('the needs: budget is the share by which today is above the other six days, and 1 once it is 1.5 times their average', () => {
  const b = (used) => needsFrom({ ...good(), budget: { days: used.map((u, i) => ({ date: `2026-11-0${i + 1}`, used_uu: u })) } }).budget;
  assert.equal(b([10, 10, 10, 10, 10, 10, 10]), DEFAULT_NEED, 'today as usual');
  assert.equal(b([10, 10, 10, 10, 10, 10, 5]), DEFAULT_NEED, 'less than usual');
  assert.equal(b([10, 10, 10, 10, 10, 10, 15]), 1, 'exactly 1.5 times');
  assert.equal(b([10, 10, 10, 10, 10, 10, 100]), 1);
  const mid = b([10, 10, 10, 10, 10, 10, 12.5 | 0]);
  assert.ok(mid > DEFAULT_NEED && mid < 1, String(mid));
  assert.ok(b([10, 10, 10, 10, 10, 10, 13]) > b([10, 10, 10, 10, 10, 10, 12]), 'more use, more need');
  assert.equal(b([0, 0, 0, 0, 0, 0, 0]), DEFAULT_NEED, 'a week of nothing is quiet');
  assert.equal(b([0, 0, 0, 0, 0, 0, 7]), 1, 'use after a week of nothing is above 1.5 times nothing');
  assert.equal(needsFrom(good()).budget, 1, 'the fixture: 105 against an average of 2.2');
});

test('the needs: a quiet snapshot gives the defaults', () => {
  const quiet = good();
  quiet.queue = { open: 0, answered: 9 };
  quiet.kill_switch = 'off';
  quiet.budget.days.forEach((d) => { d.used_uu = 4; });
  const needs = needsFrom(quiet);
  assert.deepEqual(sortedKeys(needs), [...IDS].sort(), 'a number for each of the eleven');
  for (const id of IDS) assert.equal(needs[id], DEFAULT_NEED, id);
  assert.deepEqual(stationPositions(needs), stationPositions({}), 'and so the stations stand where they stand by default');
  assert.deepEqual(stationPositions(needs), stationPositions(Object.fromEntries(IDS.map((id) => [id, DEFAULT_NEED]))));
});

test('the needs: the stations the snapshot has no number for stay at the default, whatever the snapshot says', () => {
  const needs = needsFrom(good());
  for (const id of ['memory', 'rules', 'archive', 'logbook', 'automation', 'helpers', 'workflows', 'adapters']) assert.equal(needs[id], DEFAULT_NEED, id);
  assert.deepEqual(sortedKeys(needsFrom(null)), [...IDS].sort());
  for (const id of IDS) assert.equal(needsFrom(null)[id], id === 'killswitch' ? 1 : DEFAULT_NEED, `null counts: ${id}`);
});

test('the needs: a bad number gives 0.4', () => {
  assert.equal(DEFAULT_NEED, 0.4);
  for (const bad of [-1, 1.5, NaN, Infinity, -Infinity, '6', null, undefined, {}, [6], true]) {
    const n = needsFrom({ ...good(), queue: { open: bad, answered: 1 } });
    assert.equal(n.queue, 0.4, `open ${String(bad)}`);
  }
  for (const bad of [{ days: 'x' }, { days: [] }, { days: [{ used_uu: 'a' }] }, { days: Array.from({ length: 7 }, () => ({ used_uu: -5 })) },
    { days: Array.from({ length: 7 }, (_, i) => ({ used_uu: i === 6 ? NaN : 4 })) }, {}, [], 'budget', 7, null]) {
    assert.equal(needsFrom({ ...good(), budget: bad }).budget, 0.4, JSON.stringify(bad));
  }
  assert.equal(needsFrom({ ...good(), queue: null }).queue, 0.4, 'a part that cannot be read');
  assert.equal(needsFrom({ ...good(), queue: 'six' }).queue, 0.4);
  assert.equal(needsFrom({ ...good(), queue: [6] }).queue, 0.4);
  for (const n of Object.values(needsFrom({}))) assert.ok(n >= 0 && n <= 1);
  for (const junk of [undefined, null, 0, 'x', [], () => 1]) for (const n of Object.values(needsFrom(junk))) assert.ok(Number.isFinite(n) && n >= 0 && n <= 1);
});

test('every need is a number from 0 to 1 for every snapshot the validator accepts', () => {
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const pick = () => [0, 1, 2, 5, 6, 7, 100, MAX_COUNT][Math.floor(rnd() * 8)];
  for (let i = 0; i < 300; i++) {
    const o = good();
    o.queue = rnd() < 0.2 ? null : { open: pick(), answered: pick() };
    o.kill_switch = ['on', 'off', 'unknown'][Math.floor(rnd() * 3)];
    o.budget = rnd() < 0.2 ? null : { days: o.budget.days.map((d) => ({ ...d, used_uu: pick() })) };
    const s = accepted(text(o));
    for (const [id, n] of Object.entries(needsFrom(s))) assert.ok(Number.isFinite(n) && n >= 0 && n <= 1, `${id} ${n}`);
  }
});

// ------------------------------------------------------------------------------------------------ and the positions that follow
test('the positions that follow: a full queue and the kill switch on bring Queue and Kill switch nearer the lantern; the rest do not move', () => {
  const quiet = good();
  quiet.queue = { open: 0, answered: 0 }; quiet.kill_switch = 'off'; quiet.budget.days.forEach((d) => { d.used_uu = 3; });
  const busy = { ...quiet, queue: { open: 6, answered: 0 }, kill_switch: 'on', budget: { days: quiet.budget.days.map((d, i) => ({ ...d, used_uu: i === 6 ? 60 : 3 })) } };
  const a = stationPositions(needsFrom(quiet)), b = stationPositions(needsFrom(busy));
  for (const id of ['queue', 'killswitch', 'budget']) assert.ok(dist(b[id]) < dist(a[id]), `${id} comes nearer: ${dist(b[id]).toFixed(2)} < ${dist(a[id]).toFixed(2)}`);
  for (const id of ['memory', 'rules', 'archive', 'logbook', 'automation', 'helpers', 'workflows', 'adapters']) {
    assert.ok(dist(b[id]) <= dist(a[id]) + 1e-9, `${id} does not move away`);
  }
});

test('the positions that follow: the same snapshot gives the same positions, and no two stations overlap at any snapshot', () => {
  const s = accepted(FIXTURE);
  assert.deepEqual(stationPositions(needsFrom(s)), stationPositions(needsFrom(s)));
  const pos = stationPositions(needsFrom(s));
  const foot = Object.fromEntries(TABLE.map((r) => [r.id, r.footprint]));
  for (const i of IDS) for (const j of IDS) if (i < j) {
    assert.ok(Math.hypot(pos[i].x - pos[j].x, pos[i].z - pos[j].z) >= foot[i] + foot[j] + 0.8 - 1e-6, `${i} ${j}`);
  }
});

// ------------------------------------------------------------------------------------------------ the mapping table
test('the mapping table: counts to sheep, stones, lanterns, beads, lamps, marks and the water level (the fixture)', () => {
  const m = sceneNumbers(accepted(FIXTURE));
  assert.deepEqual(m.queue, { unknown: false, sheep: 2, stones: 2 });
  assert.deepEqual(m.rules, { unknown: false, lanterns: [6, 4, 2] });
  assert.deepEqual(m.logbook, { unknown: false, beads: 8 });
  assert.deepEqual(m.killswitch, { unknown: false, shut: false });
  assert.deepEqual(m.automation, { unknown: false, lamps: [3, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0] });
  assert.equal(m.budget.unknown, false);
  assert.deepEqual(m.budget.marks.map((x) => Math.round(x * 1000) / 1000), [0, 0, 0, 0, 0.124, 0, 1]);
  assert.equal(m.budget.level, 1);
  assert.deepEqual(sortedKeys(m), ['automation', 'budget', 'killswitch', 'logbook', 'queue', 'rules']);
});

test('the mapping table: the caps of what the features can hold', () => {
  const big = { ...good(), queue: { open: 500, answered: 500 }, logbook: { entries: MAX_COUNT, chain_length: MAX_COUNT }, schedule: { entries: 99, installed: 99, enabled: 99 } };
  const m = sceneNumbers(big);
  assert.equal(m.queue.sheep, 7, 'seven sheep in the line');
  assert.equal(m.queue.stones, 8, 'eight stones in the cairn');
  assert.equal(m.logbook.beads, 21, 'the helix holds 21 beads');
  assert.deepEqual(m.automation.lamps, Array(12).fill(3), 'twelve lamps on the wheel');
  assert.equal(sceneNumbers({ ...good(), queue: { open: 7, answered: 8 } }).queue.sheep, 7);
  assert.equal(sceneNumbers({ ...good(), queue: { open: 6, answered: 7 } }).queue.stones, 7);
  assert.equal(sceneNumbers({ ...good(), logbook: { entries: 5, chain_length: 21 } }).logbook.beads, 21);
  assert.equal(sceneNumbers({ ...good(), logbook: { entries: 5, chain_length: 22 } }).logbook.beads, 21);
});

test('the mapping table: zero is zero, drawn as nothing and not as a few', () => {
  const m = sceneNumbers({ ...good(), queue: { open: 0, answered: 0 }, logbook: { entries: 0, chain_length: 0 }, schedule: { entries: 0, installed: 0, enabled: 0 },
    rules: { yes: 0, no: 0, ask: 0 }, budget: { days: good().budget.days.map((d) => ({ ...d, used_uu: 0 })) } });
  assert.deepEqual(m.queue, { unknown: false, sheep: 0, stones: 0 });
  assert.deepEqual(m.logbook, { unknown: false, beads: 0 });
  assert.deepEqual(m.automation.lamps, Array(12).fill(0));
  assert.deepEqual(m.rules, { unknown: false, lanterns: [0, 0, 0] }, 'no rules, no lantern; this is not unknown');
  assert.deepEqual(m.budget.marks, Array(7).fill(0));
  assert.equal(m.budget.level, 0);
});

test('the mapping table: the lanterns of Rules show every verdict that has a rule, and never more than 12', () => {
  const l = (yes, no, ask) => sceneNumbers({ ...good(), rules: { yes, no, ask } }).rules.lanterns;
  assert.deepEqual(l(1, 0, 0), [12, 0, 0]);
  assert.deepEqual(l(0, 0, 5), [0, 0, 12]);
  assert.deepEqual(l(7, 6, 2), [5, 5, 2], 'shares of 12, a verdict with rules at least 1, the largest gives one up while the total is over 12');
  assert.deepEqual(l(3, 2, 1), [6, 4, 2]);
  for (const [y, n, a] of [[1, 1, 1], [1, 100, 1], [100, 1, 1], [1, 1, 100], [1000000000, 1, 1], [7, 6, 2], [3, 2, 1]]) {
    const out = l(y, n, a);
    assert.ok(out.reduce((s, v) => s + v, 0) <= 12, `${y} ${n} ${a}`);
    out.forEach((v, i) => assert.ok(([y, n, a][i] > 0) === (v > 0), `a verdict with rules shows, one without does not: ${y} ${n} ${a}`));
    assert.ok(out.every((v) => Number.isInteger(v) && v >= 0));
  }
  assert.ok(l(7, 6, 2)[0] >= l(7, 6, 2)[2], 'more rules, at least as many lanterns');
});

test('the mapping table: the kill switch is shut for on and for unknown, open for off; unknown says so', () => {
  const k = (v) => sceneNumbers({ ...good(), kill_switch: v }).killswitch;
  assert.deepEqual(k('on'), { unknown: false, shut: true });
  assert.deepEqual(k('off'), { unknown: false, shut: false });
  assert.deepEqual(k('unknown'), { unknown: true, shut: true });
  assert.deepEqual(k('maybe'), { unknown: true, shut: true });
  assert.deepEqual(k(undefined), { unknown: true, shut: true });
});

test('the mapping table: the marks are the seven days against the busiest, and the water level is today against the busiest', () => {
  const days = (u) => ({ days: u.map((x, i) => ({ date: `2026-11-0${i + 1}`, used_uu: x })) });
  const m = sceneNumbers({ ...good(), budget: days([10, 20, 40, 0, 5, 40, 20]) }).budget;
  assert.deepEqual(m.marks, [0.25, 0.5, 1, 0, 0.125, 1, 0.5]);
  assert.equal(m.level, 0.5);
  assert.equal(sceneNumbers({ ...good(), budget: days([1, 1, 1, 1, 1, 1, 100]) }).budget.level, 1);
  assert.equal(sceneNumbers({ ...good(), budget: days([100, 1, 1, 1, 1, 1, 1]) }).budget.level, 0.01);
  assert.ok(sceneNumbers({ ...good(), budget: days([9, 9, 9, 9, 9, 9, 9]) }).budget.marks.every((x) => x === 1));
});

test('the mapping table: the lamps of Automation are lit by entries, brighter if installed, brightest if enabled', () => {
  const a = (entries, installed, enabled) => sceneNumbers({ ...good(), schedule: { entries, installed, enabled } }).automation.lamps;
  assert.deepEqual(a(3, 3, 3).slice(0, 4), [3, 3, 3, 0]);
  assert.deepEqual(a(3, 2, 0).slice(0, 4), [2, 2, 1, 0]);
  assert.deepEqual(a(5, 1, 3).slice(0, 6), [3, 3, 3, 1, 1, 0]);
  assert.deepEqual(a(1, 5, 5).slice(0, 3), [3, 0, 0], 'a lamp that has no entry is dark, whatever else is said');
  assert.equal(a(12, 0, 0).filter((x) => x > 0).length, 12);
});

test('unknown parts are marked unknown in the scene numbers: never zero, never fine', () => {
  const m = sceneNumbers({ ...good(), queue: null, rules: null, logbook: null, budget: null, schedule: null, kill_switch: 'unknown' });
  for (const id of ['queue', 'rules', 'logbook', 'killswitch', 'automation', 'budget']) assert.equal(m[id].unknown, true, id);
  assert.deepEqual(m.rules.lanterns, [0, 0, 12], 'Rules draws unknown as Ask me first');
  assert.equal(m.killswitch.shut, true, 'and the kill switch as on');
  for (const none of [null, undefined, {}, [], 'x', 5]) {
    const n = sceneNumbers(none);
    for (const id of ['queue', 'rules', 'logbook', 'killswitch', 'automation', 'budget']) assert.equal(n[id].unknown, true, `${String(none)} ${id}`);
  }
  const known = sceneNumbers(good());
  for (const id of ['queue', 'rules', 'logbook', 'killswitch', 'automation', 'budget']) assert.equal(known[id].unknown, false, id);
  assert.equal(sceneNumbers({ ...good(), queue: { open: 'x', answered: 1 } }).queue.unknown, true, 'a bad number is unknown too');
  assert.equal(sceneNumbers({ ...good(), budget: { days: [1, 2] } }).budget.unknown, true);
  assert.equal(sceneNumbers({ ...good(), budget: { days: good().budget.days.slice(0, 6) } }).budget.unknown, true);
});

test('the sample counts have no unknown part: the sample world is whole', () => {
  const m = sceneNumbers(SAMPLE);
  for (const id of Object.keys(m)) assert.equal(m[id].unknown, false, id);
});

// ------------------------------------------------------------------------------------------------ sample, if and only if
const WORD = /sample/i;
const everyText = (view) => {
  const strip = statusStrip(view.counts, { sample: view.sample, date: view.date });
  return { label: view.label, footer: view.footer, tags: strip.map((s) => s.tag), values: strip.map((s) => s.value) };
};

test('"sample" is shown if and only if no snapshot is loaded: the label, the footer and every strip tag', () => {
  const none = viewOf(null);
  assert.equal(none.sample, true);
  assert.equal(none.label, 'sample');
  assert.deepEqual(none.counts, SAMPLE);
  assert.deepEqual(none.needs, {}, 'the sample world stands where the stations stand by default');
  const t = everyText(none);
  assert.match(t.footer, WORD);
  for (const tag of t.tags) assert.equal(tag, 'sample');

  const real = viewOf(accepted(FIXTURE));
  assert.equal(real.sample, false);
  assert.equal(real.date, '2026-11-11');
  const r = everyText(real);
  assert.doesNotMatch(r.label, WORD);
  assert.doesNotMatch(r.footer, WORD);
  for (const tag of r.tags) assert.equal(tag, 'as of 2026-11-11');
  for (const v of r.values) assert.doesNotMatch(v, WORD);
  assert.match(r.label, /2026-11-11/, 'the date of the snapshot is next to the scene');
  assert.ok(!/[\u2014\u2013]/.test(r.label + r.footer + none.label + none.footer));
});

test('the real view holds the snapshot\'s counts and the needs made from them, and never a mix with the sample', () => {
  const snap = accepted(FIXTURE);
  const v = viewOf(snap);
  assert.deepEqual(v.counts, snap);
  assert.deepEqual(v.needs, needsFrom(snap));
  assert.notDeepEqual(v.counts, SAMPLE);
  assert.deepEqual(viewOf(undefined), viewOf(null));
});

test('the strip of a real snapshot shows the file\'s numbers and its date', () => {
  const v = viewOf(accepted(FIXTURE));
  const s = statusStrip(v.counts, { sample: v.sample, date: v.date });
  assert.deepEqual(s.map((x) => x.value), ['off', '105 UU', '2', '8 linked entries']);
  for (const x of s) assert.equal(x.tag, 'as of 2026-11-11');
});

test('a snapshot with unknown parts shows unknown in the strip and never a zero', () => {
  const o = good(); o.kill_switch = 'unknown'; o.queue = null; o.logbook = null; o.budget = null;
  const v = viewOf(accepted(text(o)));
  assert.deepEqual(statusStrip(v.counts, { sample: false, date: v.date }).map((x) => x.value), ['unknown, drawn as on', 'unknown', 'unknown', 'unknown']);
});
