// UI.4 (tests first): the logic of the owner checks panel (12.R7). Pure: the state kept in memory, the status of a check, the
// warning on a result that looks like a value, and the text of the export. No DOM here (checksview.test.mjs has the panel).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CHECKS, CHECK_IDS } from '../src/data/checks.js';
import {
  createNotes, valueWarnings, warningText, STATUS_NOT_DONE, STATUS_TICKED, END_LINE, MEMORY_NOTICE, RECORD_RULE, EXPORT_FILE, downloadHref, MAX_RESULT,
} from '../src/data/notes.js';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

// a small fixed set of checks, so the export text can be written out in full
const FIXED = [
  { id: 'X.1', name: 'First check', steps: [{ id: '1', text: 'Run `one`.' }, { id: '2', text: 'Look at it:\n- the line', exit: true }] },
  { id: 'X.2', name: 'Second check', steps: [{ id: 'a', text: 'Only step.' }] },
];

test('the six checks are there in the order of 12.R7.1', () => {
  assert.deepEqual(CHECK_IDS, ['10.21', '10.31', '11.6', 'B.10', '10.37', 'UI.5']);
  assert.equal(CHECKS.length, 6);
  for (const c of CHECKS) assert.ok(c.name && c.reason && c.notes && c.steps.length > 0, c.id);
});

test('nothing is done by default: every check is "not done" and nothing is ticked or typed', () => {
  const n = createNotes(CHECKS);
  for (const c of CHECKS) {
    assert.equal(n.status(c.id), 'not done', c.id);
    for (const s of c.steps) { assert.equal(n.isTicked(c.id, s.id), false); assert.equal(n.result(c.id, s.id), ''); }
  }
  assert.deepEqual(n.counts('10.21'), { ticked: 0, total: 4 });
});

test('a check is "not done" until every step is ticked, then "ticked by you", never "passed" or "verified"', () => {
  assert.equal(STATUS_NOT_DONE, 'not done');
  assert.equal(STATUS_TICKED, 'ticked by you');
  for (const c of CHECKS) {
    const n = createNotes(CHECKS);
    c.steps.forEach((s, i) => {
      n.tick(c.id, s.id, true);
      const want = i === c.steps.length - 1 ? STATUS_TICKED : STATUS_NOT_DONE;
      assert.equal(n.status(c.id), want, `${c.id} after ${i + 1} of ${c.steps.length}`);
      assert.doesNotMatch(n.status(c.id), /passed|verified|\bok\b|success/i);
    });
    n.tick(c.id, c.steps[0].id, false);
    assert.equal(n.status(c.id), STATUS_NOT_DONE, `${c.id} unticked again`);
  }
});

test('the statuses are the only two words the panel ever gives a check', () => {
  const n = createNotes(CHECKS);
  const seen = new Set();
  for (const c of CHECKS) { seen.add(n.status(c.id)); c.steps.forEach((s) => n.tick(c.id, s.id, true)); seen.add(n.status(c.id)); }
  assert.deepEqual([...seen].sort(), ['not done', 'ticked by you']);
});

test('ticking a step of one check changes no other check, and a typed result does not tick', () => {
  const n = createNotes(CHECKS);
  n.tick('10.21', 'A3', true);
  assert.equal(n.isTicked('10.31', 'A3'), false, 'the same step id in another check is another step');
  assert.deepEqual(n.counts('10.21'), { ticked: 1, total: 4 });
  assert.deepEqual(n.counts('10.31'), { ticked: 0, total: 16 });
  n.setResult('10.21', 'A4', 'exit 0');
  assert.equal(n.isTicked('10.21', 'A4'), false);
  for (const s of CHECKS[0].steps) n.setResult('10.21', s.id, 'x');
  assert.equal(n.status('10.21'), STATUS_NOT_DONE, 'results alone never finish a check');
});

test('an unknown check or step is ignored: no throw, nothing added to the state', () => {
  const n = createNotes(CHECKS);
  const before = JSON.stringify(n.state());
  n.tick('99', 'x', true); n.tick('10.21', 'nope', true); n.setResult('99', 'x', 'a'); n.setResult('10.21', 'nope', 'a');
  assert.equal(n.isTicked('99', 'x'), false);
  assert.equal(n.result('10.21', 'nope'), '');
  assert.equal(n.status('99'), STATUS_NOT_DONE);
  assert.deepEqual(n.counts('99'), { ticked: 0, total: 0 });
  assert.equal(JSON.stringify(n.state()), before);
  n.tick('10.21', 'A3', 'yes'); // only a real true ticks
  assert.equal(n.isTicked('10.21', 'A3'), false);
  n.tick('__proto__', 'A3', true); n.tick('constructor', 'x', true);
  assert.equal(({}).A3, undefined);
});

test('a result is text of at most 500 characters on one line: control characters and line ends become spaces', () => {
  assert.equal(MAX_RESULT, 500);
  const n = createNotes(CHECKS);
  n.setResult('10.21', 'A3', 'a\nb\r\nc\td\u0000e\u001b[31m');
  assert.equal(n.result('10.21', 'A3'), 'a b c d e [31m');
  n.setResult('10.21', 'A3', 'x'.repeat(900));
  assert.equal(n.result('10.21', 'A3').length, 500);
  n.setResult('10.21', 'A3', 42);
  assert.equal(n.result('10.21', 'A3'), '');
  n.setResult('10.21', 'A3', null); n.setResult('10.21', 'A4', undefined); n.setResult('10.21', 'A5', { toString() { return 'x'; } });
  assert.equal(n.result('10.21', 'A4'), '');
  assert.equal(n.result('10.21', 'A5'), '');
});

test('the state is in memory only and per notes object: two notes share nothing, and the module touches no storage', () => {
  const a = createNotes(CHECKS), b = createNotes(CHECKS);
  a.tick('10.21', 'A3', true); a.setResult('10.21', 'A3', 'hi');
  assert.equal(b.isTicked('10.21', 'A3'), false);
  assert.equal(b.result('10.21', 'A3'), '');
  const copy = a.state();
  copy['10.21'].A3.ticked = false; // the copy is a copy
  assert.equal(a.isTicked('10.21', 'A3'), true);
  assert.deepEqual(a.state(), { '10.21': { A3: { ticked: true, result: 'hi' } } });
  const text = readFileSync(join(SRC, 'data', 'notes.js'), 'utf8');
  for (const bad of ['localStorage', 'sessionStorage', 'indexedDB', 'cookie', 'fetch(', 'XMLHttpRequest', 'sendBeacon', 'navigator', 'window', 'document', 'Date', 'Math.random']) {
    assert.ok(!text.includes(bad), `notes.js contains ${bad}`);
  }
});

// ---------------------------------------------------------------------------------------------------- the warnings
const fires = (t, code, opts) => assert.ok(valueWarnings(t, opts).includes(code), `${JSON.stringify(t)} should give ${code}`);
const quiet = (t, opts) => assert.deepEqual(valueWarnings(t, opts), [], `${JSON.stringify(t)} should give no warning`);

test('warning: an email address', () => {
  for (const t of ['me@example.com', 'owner: me@example.org (work)', 'a.b+c@sub.example.co.uk', 'x@y.z']) fires(t, 'email');
});
test('warning: a URL', () => {
  for (const t of ['https://example.com', 'http://localhost:3000/x', 'see ftp://host/file', 'wss://a.b', 'file:///tmp/x']) fires(t, 'url');
});
test('warning: a token of 24 letters and digits or more', () => {
  fires('abcdefghijklmnopqrstuvwx', 'token');
  fires('sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123', 'token');
  fires('A'.repeat(24), 'token');
  fires('x 0123456789abcdefghijklmnop y', 'token');
  quiet('G'.repeat(23));
});
test('warning: a long hex string, with or without dashes of a UUID', () => {
  fires('3b9f1c2d4e5a6b7c', 'hex');
  fires('3B9F1C2D4E5A6B7C8D9E0F1A2B3C4D5E6F708192A3B4C5D6E7F8091A2B3C4D5E', 'hex');
  fires('123e4567-e89b-12d3-a456-426614174000', 'hex');
  fires('sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'hex');
  quiet('3b9f1c2d4e5a6b7');
});
test('warning: a step that records an exit code gives a warning for anything but a plain number', () => {
  const o = { exit: true };
  fires('hello', 'exit', o); fires('0 and 2', 'exit', o); fires('-1', 'exit', o); fires('256', 'exit', o); fires('1.5', 'exit', o); fires('exit code is zero', 'exit', o);
  quiet('0', o); quiet('2', o); quiet('64', o); quiet('255', o); quiet(' 3 ', o); quiet('exit 3', o); quiet('', o);
  quiet('hello'); quiet('0 and 2');
});
test('no warning on a plain exit code, a name, a version string, a path or a number', () => {
  for (const t of ['0', '1', '2', '3', '64', 'exit 0', 'exit 2', '', '   ', 'v22.5.0', '2.1.318', '0.101.0', 'running', 'degraded', 'No such file or directory', 'status=3',
    '/v1/logs', '/v1/metrics', 'cache_creation_input_tokens', 'claude_code.cost.usage', "['apiKeySource', 'email', 'loggedIn']", 'authMethod, apiProvider',
    '@agentclientprotocol/claude-agent-acp 0.101.0', 'adapter package: @agentclientprotocol/claude-agent-acp 0.101.0', 'umwayi-ID-open-queue.timer', '08:00 local',
    'Connected.', 'yes', 'no', '12 lines', 'PURPLEHERON count 0', '.config/systemd/user/timers.target.wants/umwayi-x.timer']) quiet(t);
});
test('warning: several shapes in one result give several codes, in a fixed order', () => {
  assert.deepEqual(valueWarnings('me@example.com https://example.com abcdefghijklmnopqrstuvwxyz 3b9f1c2d4e5a6b7c'), ['email', 'url', 'token', 'hex']);
  assert.deepEqual(valueWarnings('0123456789abcdef0123456789abcdef'), ['token', 'hex']);
});
test('warning: any input is safe', () => {
  for (const t of [null, undefined, 5, {}, [], NaN, 'a'.repeat(100000)]) assert.ok(Array.isArray(valueWarnings(t)));
  assert.deepEqual(valueWarnings(null), []);
});
test('the warning text names the shape, repeats the rule and is a hint (it never says the value is wrong or blocks)', () => {
  assert.equal(RECORD_RULE, 'Record field names, exit codes and version strings, never a value.');
  assert.equal(warningText('email'), 'This looks like an email address. Record field names, exit codes and version strings, never a value.');
  assert.equal(warningText('url'), 'This looks like a URL. Record field names, exit codes and version strings, never a value.');
  assert.equal(warningText('token'), 'This looks like a token. Record field names, exit codes and version strings, never a value.');
  assert.equal(warningText('hex'), 'This looks like a long hex string. Record field names, exit codes and version strings, never a value.');
  assert.equal(warningText('exit'), 'This step records an exit code. Type the number only.');
  assert.equal(warningText('what'), '');
  for (const c of ['email', 'url', 'token', 'hex', 'exit']) assert.ok(!/[\u2014\u2013]/.test(warningText(c)));
});
test('notes.warnings(check, step) follows the typed result and the exit flag of the step', () => {
  const n = createNotes(FIXED);
  n.setResult('X.1', '1', 'me@example.com');
  assert.deepEqual(n.warnings('X.1', '1'), ['email']);
  n.setResult('X.1', '2', 'maybe');
  assert.deepEqual(n.warnings('X.1', '2'), ['exit'], 'step 2 records an exit code');
  n.setResult('X.1', '2', '0');
  assert.deepEqual(n.warnings('X.1', '2'), []);
  assert.deepEqual(n.warnings('nope', '1'), []);
  n.tick('X.1', '1', true);
  assert.equal(n.isTicked('X.1', '1'), true, 'a warning never blocks a tick');
});

// ---------------------------------------------------------------------------------------------------- the export
test('the export of a fixed state equals a fixed text', () => {
  const n = createNotes(FIXED);
  n.tick('X.1', '1', true);
  n.setResult('X.1', '1', 'exit 0');
  n.setResult('X.1', '2', 'me@example.com');
  n.tick('X.2', 'a', true);
  n.setResult('X.2', 'a', 'v22.5.0');
  const want = [
    'umwayi owner checks: my notes',
    'These notes were made in the page. They are lost when you close it.',
    '',
    '== X.1: First check ==',
    'Status: not done (1 of 2 steps ticked)',
    '[x] 1. Run `one`.',
    '    Result: exit 0',
    '[ ] 2. Look at it: - the line',
    '    Result: me@example.com',
    '    Check this result: it looks like an email address, and this step records an exit code.',
    '',
    '== X.2: Second check ==',
    'Status: ticked by you (1 of 1 steps ticked)',
    '[x] a. Only step.',
    '    Result: v22.5.0',
    '',
    'These are your notes. umwayi did not run or verify anything.',
    '',
  ].join('\n');
  assert.equal(n.exportText(), want);
});

test('the export ends with the line "These are your notes. umwayi did not run or verify anything." and nothing after it but a line end', () => {
  assert.equal(END_LINE, 'These are your notes. umwayi did not run or verify anything.');
  for (const notes of [createNotes(FIXED), createNotes(CHECKS)]) {
    const t = notes.exportText();
    assert.ok(t.endsWith(`\n${END_LINE}\n`), t.slice(-120));
    assert.equal(t.split('\n').filter((l) => l === END_LINE).length, 1, 'once, as a line of its own (step 3.4 of the interface check quotes it inside a longer line)');
  }
  const all = createNotes(CHECKS);
  for (const c of CHECKS) c.steps.forEach((s) => all.tick(c.id, s.id, true));
  assert.ok(all.exportText().endsWith(`\n${END_LINE}\n`));
});

test('the export lists every check and every step, in order, with [ ] or [x] and the status', () => {
  const n = createNotes(CHECKS);
  const t = n.exportText();
  let at = 0;
  for (const c of CHECKS) {
    const head = `== ${c.id}: ${c.name} ==`;
    const i = t.indexOf(head, at);
    assert.ok(i >= at, head);
    at = i;
    assert.ok(t.includes(`Status: not done (0 of ${c.steps.length} steps ticked)`), c.id);
    for (const s of c.steps) {
      const line = `[ ] ${s.id}. ${s.text.replace(/\s*\n\s*/g, ' ')}`;
      const j = t.indexOf(line, at);
      assert.ok(j >= at, `${c.id} ${s.id}`);
      at = j;
    }
  }
  assert.equal((t.match(/^\[ \] /gm) || []).length, CHECKS.reduce((s, c) => s + c.steps.length, 0));
  assert.equal((t.match(/^\[x\] /gm) || []).length, 0);
});

test('the export says "ticked by you" for a finished check and never "passed" or "verified" about one', () => {
  const n = createNotes(CHECKS);
  for (const c of CHECKS) c.steps.forEach((s) => n.tick(c.id, s.id, true));
  const t = n.exportText();
  assert.equal((t.match(/^Status: ticked by you \(/gm) || []).length, 6);
  assert.equal((t.match(/^Status: /gm) || []).length, 6);
  assert.ok(!/^Status: .*(passed|verified|ok|success)/im.test(t));
  const statusLines = t.split('\n').filter((l) => l.startsWith('Status: '));
  for (const l of statusLines) assert.match(l, /^Status: (not done|ticked by you) \(\d+ of \d+ steps ticked\)$/);
});

test('the export has no em dash and keeps a typed result on one line', () => {
  const n = createNotes(FIXED);
  n.setResult('X.1', '1', 'line one\nline two');
  const t = n.exportText();
  assert.ok(!/[\u2014\u2013]/.test(t));
  assert.ok(t.includes('    Result: line one line two\n'));
});

test('the export is made from the state at the time it is asked for', () => {
  const n = createNotes(FIXED);
  const a = n.exportText();
  n.tick('X.2', 'a', true);
  const b = n.exportText();
  assert.notEqual(a, b);
  assert.equal(n.exportText(), b);
});

test('the words of the panel: the memory notice and the file name', () => {
  assert.equal(MEMORY_NOTICE, 'These notes are lost when you close this page. Export them first.');
  assert.equal(EXPORT_FILE, 'umwayi-owner-checks.txt');
});

test('the download link holds the text in the address itself, so it makes no request and needs no Blob', () => {
  const href = downloadHref('a b\n\u00e9 100%');
  assert.ok(href.startsWith('data:text/plain;charset=utf-8,'));
  assert.equal(decodeURIComponent(href.slice('data:text/plain;charset=utf-8,'.length)), 'a b\n\u00e9 100%');
  assert.ok(!/[\s]/.test(href));
});
