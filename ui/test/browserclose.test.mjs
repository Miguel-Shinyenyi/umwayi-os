// Closing the test browser removes its profile folder. Chrome can still be writing there for a moment, so a delete that fails with
// ENOTEMPTY is tried again; anything else, and a delete that never works, still throws.
import test from 'node:test';
import assert from 'node:assert/strict';
import { removeProfile } from '../tools/browser.mjs';

const err = (code) => Object.assign(new Error(code), { code });

test('a delete that fails with ENOTEMPTY twice and then works does not throw', () => {
  let calls = 0;
  const slept = [];
  removeProfile('/x', (dir, opts) => {
    calls += 1;
    assert.equal(dir, '/x');
    assert.deepEqual(opts, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    if (calls <= 2) throw err('ENOTEMPTY');
  }, (ms) => slept.push(ms));
  assert.equal(calls, 3);
  assert.deepEqual(slept, [200, 200]);
});

test('a delete that keeps failing with ENOTEMPTY throws', () => {
  let calls = 0;
  assert.throws(() => removeProfile('/x', () => { calls += 1; throw err('ENOTEMPTY'); }, () => {}), { code: 'ENOTEMPTY' });
  assert.ok(calls > 1 && calls <= 7);
});

test('any other error is thrown at once', () => {
  let calls = 0;
  assert.throws(() => removeProfile('/x', () => { calls += 1; throw err('EACCES'); }, () => {}), { code: 'EACCES' });
  assert.equal(calls, 1);
});
