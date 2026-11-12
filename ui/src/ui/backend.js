// The panel of the local backend (W6.9, live view only). It shows what `umwayi serve` says (the status, the queue) and has the
// few buttons the design allows: add, answer and close an item of the queue, and Stop everything (the kill switch). There is no
// button for anything on the never list: no approval, no start of an AI helper, no install, no publish, no payment.
//
// Every request goes through the one client (../api/client.js); this file sends nothing itself. The token is typed into a
// password field, handed to the client, and the field is emptied at once: it is never put in an attribute or in the text of any
// element. Everything that came from a response is put in the page with textContent, never as markup. Nothing asks by itself:
// no timer, no polling (W6.R14.6); the owner presses Refresh. When the client stops (a wrong answer), every control is disabled and
// the data is removed from the page.
import { createClient, SENTENCES, NO_TOKEN_MESSAGE, UNAVAILABLE_MESSAGE } from '../api/client.js';

const HELP = 'This page is served by umwayi serve. Paste the token that umwayi serve token create showed once. The page keeps it in memory until you close or reload it, and sends nothing without it.';
const NO_TITLE = 'Type a title first. Nothing was sent';
const NO_ANSWER = 'Type an answer first. Nothing was sent';

const daysText = (d) => {
  if (d > 1) return `${d} days left`;
  if (d === 1) return '1 day left';
  if (d === 0) return 'expires today';
  return 'has run out';
};

// client: for a test. The page passes nothing, and the client is made from the page's own address.
export function initBackend(doc, win, { client } = {}) {
  // The section is made here, not written in the page: the public site shows the same template and must not hold a place for it.
  const anchor = doc.getElementById('start');
  const parent = anchor && anchor.parentNode;
  if (!parent || typeof parent.insertBefore !== 'function') return { stop() {} };
  const make = (tag, props, ...kids) => {
    const e = doc.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) e.setAttribute(k, v);
    e.append(...kids);
    return e;
  };
  const note = make('p', { id: 'backend-note' }), body = make('div', { id: 'backend-body' });
  const msg = make('p', { id: 'backend-msg', class: 'backend-msg', role: 'status', 'aria-live': 'polite' });
  const section = make('section', { id: 'backend', class: 'home', 'aria-labelledby': 'backend-title' }, make('h2', { id: 'backend-title' }, 'Local backend'), note, body, msg);
  const api = client || createClient({ location: win.location });
  parent.insertBefore(section, anchor);
  if (!api.available) {
    note.textContent = UNAVAILABLE_MESSAGE;
    return { stop() {} };
  }
  note.textContent = HELP;

  const owned = [];
  const controls = [];
  const on = (target, type, fn) => { target.addEventListener(type, fn); owned.push([target, type, fn]); };
  const el = (tag, props, ...kids) => {
    const e = doc.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) e.setAttribute(k, v);
    e.append(...kids);
    if (props && props.id && ['input', 'button', 'select'].includes(tag)) controls.push(e); // the controls of a row go away with the data
    return e;
  };
  const say = (text) => { msg.textContent = text; };

  // ---- the token
  const tokenField = el('input', { id: 'backend-token', type: 'password', autocomplete: 'off', spellcheck: 'false', maxlength: '64', 'aria-label': 'Token of umwayi serve' });
  const connectBtn = el('button', { id: 'backend-connect', type: 'button', class: 'btn small' }, 'Use token');

  // ---- what is shown once connected
  const area = el('div', { id: 'backend-area' });
  area.hidden = true;
  const statusEl = el('p', { id: 'backend-status' });
  const refreshBtn = el('button', { id: 'backend-refresh', type: 'button', class: 'btn small' }, 'Refresh');
  const killBtn = el('button', { id: 'backend-kill', type: 'button', class: 'btn small' }, 'Stop everything');
  const kindSel = el('select', { id: 'backend-add-kind', 'aria-label': 'Kind of the new item' }, el('option', { value: 'task' }, 'task'), el('option', { value: 'decision' }, 'decision'));
  const titleField = el('input', { id: 'backend-add-title', type: 'text', maxlength: '200', autocomplete: 'off', 'aria-label': 'Title of the new item' });
  const recField = el('input', { id: 'backend-add-rec', type: 'text', maxlength: '500', autocomplete: 'off', 'aria-label': 'Recommendation for the new item' });
  const addBtn = el('button', { id: 'backend-add', type: 'button', class: 'btn small' }, 'Add');
  const queueEl = el('ul', { id: 'backend-queue' });
  area.append(
    statusEl,
    el('div', { class: 'backend-row' }, refreshBtn, killBtn),
    el('h3', {}, 'Add to the queue'),
    el('div', { class: 'backend-row' }, kindSel, titleField, recField, addBtn),
    el('h3', {}, 'The queue'),
    queueEl,
  );
  body.append(el('div', { class: 'backend-row' }, tokenField, connectBtn), area);

  function showStatus(s) {
    const t = s.token === null ? 'no token on record' : daysText(s.token.days_left);
    statusEl.textContent = `Kill switch: ${s.kill_switch}. Token: ${t}.${s.degraded ? ' umwayi serve cannot write the logbook, so it answers nothing but the status.' : ''}`;
  }

  function showRows(rows, more) {
    queueEl.replaceChildren();
    for (const r of rows) {
      const li = el('li', { 'data-id': r.id });
      li.append(el('p', { class: 'backend-title' }, `${r.id}: ${r.title}`), el('p', { class: 'note' }, `${r.kind}, ${r.status}${r.answered ? ` on ${r.answered}` : ''}`));
      if (r.recommendation) li.append(el('p', { class: 'note' }, `Recommendation: ${r.recommendation}`));
      if (r.answer) li.append(el('p', { class: 'note' }, `Answer: ${r.answer}`));
      if (r.status === 'open') {
        const answer = el('input', { type: 'text', maxlength: '500', autocomplete: 'off', 'aria-label': `Answer for ${r.id}` });
        const answerBtn = el('button', { type: 'button', class: 'btn small', 'aria-label': `Answer ${r.id}` }, 'Answer');
        on(answerBtn, 'click', () => answerOnce(r.id, answer));
        li.append(el('div', { class: 'backend-row' }, answer, answerBtn));
      }
      if (r.status !== 'closed') {
        const closeBtn = el('button', { type: 'button', class: 'btn small', 'aria-label': `Close ${r.id}` }, 'Close');
        on(closeBtn, 'click', () => closeOnce(r.id));
        li.append(closeBtn);
      }
      queueEl.append(li);
    }
    if (more) queueEl.append(el('li', {}, 'There are more rows than this shows. Use umwayi queue list in a terminal.'));
  }

  function clearData() {
    statusEl.textContent = '';
    queueEl.replaceChildren();
    area.hidden = true;
  }

  // one failure: the message, and either everything locked (the client stopped) or the data removed (no token or a wrong one)
  function fail(r) {
    say(r.message);
    if (api.stopped()) {
      clearData();
      for (const c of controls) c.disabled = true;
    } else if (r.kind === 'token' || r.kind === 'notoken') {
      clearData();
    }
    return false;
  }

  async function load() {
    const s = await api.call('status');
    if (!s.ok) return fail(s);
    const q = await api.call('queue.list');
    if (!q.ok) return fail(q);
    showStatus(s.data);
    showRows(q.data.rows, q.data.more);
    area.hidden = false;
    return true;
  }

  // one action at a time: a second click while a request is on its way does nothing (Stop everything is never held back)
  let busy = false;
  const once = (fn) => async (...args) => {
    if (busy || api.stopped()) return;
    busy = true;
    try { await fn(...args); } finally { busy = false; }
  };

  async function connect() {
    if (api.stopped()) return;
    const value = tokenField.value;
    tokenField.value = ''; // the field is emptied before anything else happens
    if (value === '' && api.hasToken()) { say(''); await load(); return; }
    if (!api.setToken(value)) { say(NO_TOKEN_MESSAGE); return; }
    say('');
    await load();
  }

  async function addItem() {
    if (api.stopped()) return;
    const title = titleField.value.trim();
    if (!title) { say(NO_TITLE); return; }
    const fields = { kind: kindSel.value === 'decision' ? 'decision' : 'task', title };
    const rec = recField.value.trim();
    if (rec) fields.recommendation = rec;
    const r = await api.call('queue.add', { body: fields });
    if (!r.ok) { fail(r); return; }
    titleField.value = '';
    recField.value = '';
    say(SENTENCES.done);
    await load();
  }

  async function answerRow(id, field) {
    if (api.stopped()) return;
    const text = field.value.trim();
    if (!text) { say(NO_ANSWER); return; }
    const r = await api.call('queue.answer', { id, body: { answer: text } });
    if (!r.ok) { fail(r); return; }
    say(SENTENCES.done);
    await load();
  }

  async function closeRow(id) {
    if (api.stopped()) return;
    const r = await api.call('queue.close', { id });
    if (!r.ok) { fail(r); return; }
    say(SENTENCES.done);
    await load();
  }

  async function stopEverything() {
    if (api.stopped()) return;
    const r = await api.call('kill.on', { body: {} });
    if (!r.ok) { fail(r); return; }
    say(SENTENCES.done);
    await load();
  }

  async function refresh() {
    if (api.stopped()) return;
    say('');
    await load();
  }

  const connectOnce = once(connect), refreshOnce = once(refresh), addOnce = once(addItem), answerOnce = once(answerRow), closeOnce = once(closeRow);
  on(connectBtn, 'click', connectOnce);
  on(tokenField, 'keydown', (ev) => { if (ev && ev.key === 'Enter') connectOnce(); });
  on(refreshBtn, 'click', refreshOnce);
  on(killBtn, 'click', stopEverything);
  on(addBtn, 'click', addOnce);
  return { stop() { for (const [t, type, fn] of owned) t.removeEventListener(type, fn); owned.length = 0; } };
}
