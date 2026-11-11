// UI.1.11 (tests first): the home content, and the detail mode. Pure data and text, no browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { REPO, DOCS, INSTALL, FIRST, LINKS, TITLE, PROMISE, statusStrip, isAllowedAddress } from '../src/data/home.js';
import { SAMPLE } from '../src/data/sample.js';
import { chooseDetail, stepDown, shouldStepDown, isPinned, STEPS, LOW_START, SLOW_FRAMES } from '../src/engine/detail.js';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const files = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : [join(dir, n)]));

test('the title and the promise are in the product words, short, with no em dash', () => {
  assert.equal(TITLE, 'umwayi-os');
  assert.ok(PROMISE.length < 160 && /rules/.test(PROMISE) && /AI helper/.test(PROMISE) && /logbook|written down/.test(PROMISE));
  assert.ok(!/[\u2014\u2013]/.test(PROMISE));
});

test('the install and the first commands are the real ones', () => {
  assert.deepEqual(INSTALL.map((c) => c.text), [`git clone ${REPO}.git`, 'cd umwayi-os', 'pip install -e .']);
  assert.deepEqual(FIRST.map((c) => c.text), ['umwayi memory bundle', 'umwayi queue add --kind task "Write the spec"', `umwayi check '{"type": "payment", "amount": 5}'`, 'umwayi logbook verify']);
  for (const c of [...INSTALL, ...FIRST]) assert.ok(c.id && c.text && !/[\u2014\u2013]/.test(c.text));
});

test('the links: the repo and the docs are addresses; Devpost and the demo video are placeholders until the owner supplies them', () => {
  const by = Object.fromEntries(LINKS.map((l) => [l.id, l]));
  assert.equal(by.repo.href, REPO);
  assert.equal(by.docs.href, DOCS);
  for (const id of ['devpost', 'demo']) {
    assert.equal(by[id].href, null, `${id} must stay a placeholder`);
    assert.equal(by[id].note, 'link to come');
  }
  assert.deepEqual(LINKS.map((l) => l.name), ['Repo', 'Docs', 'Devpost', 'Demo video']);
});

test('only the listed addresses are allowed', () => {
  assert.ok(isAllowedAddress(REPO) && isAllowedAddress(`${REPO}.git`) && isAllowedAddress(DOCS) && isAllowedAddress('http://www.w3.org/1999/xhtml'));
  for (const bad of ['https://example.com', 'http://github.com/Miguel-Shinyenyi/umwayi-os', `${REPO}/evil`, 'javascript:alert(1)']) assert.equal(isAllowedAddress(bad), false, bad);
});

test('the status strip shows a sample value with the word sample, and a snapshot value with its date', () => {
  const sample = statusStrip(SAMPLE, { sample: true, date: SAMPLE.date });
  assert.deepEqual(sample.map((s) => s.id), ['killswitch', 'budget', 'queue', 'logbook']);
  assert.deepEqual(sample.map((s) => s.name), ['Kill switch', 'Budget used today', 'Queue open', 'Logbook chain']);
  for (const s of sample) assert.equal(s.tag, 'sample', s.id);
  assert.deepEqual(sample.map((s) => s.value), ['off', '18 UU', '6', '20 linked entries']);
  const real = statusStrip({ ...SAMPLE, kill_switch: 'on', queue: { open: 2, answered: 9 } }, { sample: false, date: '2026-11-12' });
  for (const s of real) assert.equal(s.tag, 'as of 2026-11-12', s.id);
  assert.equal(real[0].value, 'on');
  assert.equal(real[2].value, '2');
});

test('a part that cannot be read is unknown in the strip, never zero or fine', () => {
  const s = statusStrip({ ...SAMPLE, kill_switch: 'unknown', queue: null, logbook: null, budget: null }, { sample: false, date: '2026-11-12' });
  assert.deepEqual(s.map((x) => x.value), ['unknown, drawn as on', 'unknown', 'unknown', 'unknown']);
  assert.deepEqual(statusStrip(null, { sample: true, date: '' }).map((x) => x.value), ['unknown', 'unknown', 'unknown', 'unknown']);
});

test('the clipboard is written only from the Copy click handler, in one file', () => {
  const users = files(SRC).filter((f) => f.endsWith('.js') && /clipboard/i.test(readFileSync(f, 'utf8')));
  assert.deepEqual(users.map((f) => f.slice(SRC.length + 1)), ['ui/home.js']);
  const text = readFileSync(join(SRC, 'ui', 'home.js'), 'utf8');
  assert.equal((text.match(/writeText\(/g) || []).length, 1);
  assert.ok(/addEventListener\('click'/.test(text));
});

// ---- the detail mode
test('detail: a strong machine starts high; software rendering, few cores or little memory start low; the address forces a mode', () => {
  assert.equal(chooseDetail({ renderer: 'ANGLE (NVIDIA, GeForce RTX 4060)', cores: 12, memory: 16, hash: '' }), 0);
  assert.equal(chooseDetail({ renderer: 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 620)', cores: 8, memory: 8, hash: '' }), 0);
  assert.equal(chooseDetail({ renderer: 'Google SwiftShader', cores: 16, memory: 16, hash: '' }), LOW_START);
  assert.equal(chooseDetail({ renderer: 'llvmpipe (LLVM 15)', cores: 16, hash: '' }), LOW_START);
  assert.equal(chooseDetail({ renderer: 'Microsoft Basic Render Driver' }), LOW_START);
  assert.equal(chooseDetail({ cores: 4 }), LOW_START);
  assert.equal(chooseDetail({ memory: 2 }), LOW_START);
  assert.equal(chooseDetail({ cores: 12, memory: 16, hash: '#detail=low' }), LOW_START);
  assert.equal(chooseDetail({ renderer: 'SwiftShader', cores: 2, hash: '#detail=high' }), 0);
  assert.equal(chooseDetail({}), 0, 'what is not known is not held against the machine');
  assert.equal(chooseDetail({ cores: NaN, memory: undefined, renderer: null, hash: '#x' }), 0);
});

test('detail: two steps down, one at a time, in order, and the last is the second (the owner cut the third)', () => {
  assert.deepEqual(STEPS.map((s) => s.name), ['high', 'high, pixel ratio 1', 'low']);
  assert.equal(STEPS.length, 3, 'the start and two steps');
  assert.equal(STEPS[1].pixelRatio, 1);
  assert.ok(STEPS[0].bloom && STEPS[1].bloom && !STEPS[2].bloom, 'the second step drops the bloom');
  assert.ok(STEPS[0].msaa > 0 && STEPS[1].msaa > 0 && STEPS[2].msaa === 0, 'and the multisampling');
  assert.ok(STEPS.every((s) => s.shadows), 'shadows stay: the step that removed them is cut');
  assert.ok(STEPS.every((s) => s.plants === 1), 'plants stay: the step that thinned them is cut');
  assert.equal(LOW_START, 2);
  let i = 0; const seen = [i];
  for (let k = 0; k < 5; k++) { i = stepDown(i); seen.push(i); }
  assert.deepEqual(seen, [0, 1, 2, 2, 2, 2]);
});

test('detail: a step down needs a full window of slow frames', () => {
  assert.equal(shouldStepDown(Array(SLOW_FRAMES - 1).fill(80)), false);
  assert.equal(shouldStepDown(Array(SLOW_FRAMES).fill(80)), true);
  assert.equal(shouldStepDown(Array(SLOW_FRAMES).fill(16)), false);
  assert.equal(shouldStepDown([]), false);
});

test('detail: a mode forced in the address stays; only the automatic choice steps down', () => {
  assert.equal(isPinned('#detail=high'), true);
  assert.equal(isPinned('#detail=low'), true);
  assert.equal(isPinned(''), false);
  assert.equal(isPinned('#something'), false);
  assert.equal(isPinned(undefined), false);
});
