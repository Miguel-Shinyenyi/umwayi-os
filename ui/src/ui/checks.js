// The owner checks panel in the page (12.R7). It lists the six physical tests only the owner can run, with their steps from the
// NOTES files, a tick and a place to type a result for each step, and an export as text. The notes live in this page's memory and
// nowhere else. Everything is built with createElement and textContent, never as markup. The page runs nothing and cannot tell
// whether a check passed: a finished check says "ticked by you". It needs no scene and no WebGL, makes no request and reads
// nothing of the page's data. The Copy button is the page's own (ui/home.js, data-copy); Download is a link made on a click.
import { CHECKS } from '../data/checks.js';
import { createNotes, warningText, downloadHref, EXPORT_FILE } from '../data/notes.js';

const COPY_ONLY = 'This browser cannot save a file from this page. Copy only.';

// "win" is not used: the panel needs the document only.
export function initChecks(doc, win, { checks = CHECKS } = {}) {
  const $ = (id) => doc.getElementById(id);
  const section = $('checks'), list = $('checks-list');
  if (!section || !list) return { notes: null, stop() {} };
  const title = $('checks-title'), box = $('checks-export'), copy = $('checks-copy'), download = $('checks-download');
  const copyOnly = $('checks-copy-only'), status = $('checks-status');
  const openers = ['checks-open', 'checks-open-list'].map($).filter(Boolean);
  const notes = createNotes(checks);
  const owned = [];
  const on = (target, type, fn) => { if (target) { target.addEventListener(type, fn); owned.push([target, type, fn]); } };
  const say = (text) => { if (status) status.textContent = text; };

  const el = (tag, props, ...kids) => {
    const e = doc.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) { if (k === 'className') e.className = v; else e.setAttribute(k, v); }
    e.append(...kids);
    return e;
  };
  // text between backticks is code; the rest is text. Nothing is parsed as markup.
  const inline = (text) => text.split('`').map((part, i) => (i % 2 ? el('code', {}, part) : doc.createTextNode(part)));
  const lines = (text) => text.split('\n').map((line) => el('p', { className: 'step-line' }, ...inline(line)));

  const badges = new Map(), previous = new Map(), warnings = new Map();
  let exported = false;

  function refreshExport() {
    if (!exported || !box) return;
    const text = notes.exportText();
    box.value = text;
    box.textContent = text;
  }
  function refreshBadge(cid, announce) {
    const now = notes.status(cid);
    badges.get(cid).textContent = now;
    if (announce && previous.get(cid) !== now) say(`Check ${cid}: ${now}.`);
    previous.set(cid, now);
  }
  function refreshWarning(cid, sid) {
    const w = warnings.get(`${cid}\u0000${sid}`);
    const codes = notes.warnings(cid, sid);
    w.textContent = codes.map(warningText).join(' ');
    w.hidden = codes.length === 0;
  }

  for (const c of checks) {
    const head = el('h3', {}, `${c.id}: ${c.name}`);
    const badge = el('span', { className: 'check-status' }, notes.status(c.id));
    badges.set(c.id, badge);
    previous.set(c.id, notes.status(c.id));
    const steps = el('ol', { className: 'steps' });
    for (const s of c.steps) {
      const li = el('li', { 'data-step': s.id });
      const tick = el('input', { type: 'checkbox', 'aria-label': `Step ${s.id} of check ${c.id}: ticked by you` });
      on(tick, 'change', (ev) => {
        notes.tick(c.id, s.id, ev.target.checked === true);
        refreshBadge(c.id, true);
        refreshExport();
      });
      li.append(el('div', { className: 'step-head' }, tick, el('span', { className: 'step-id' }, s.id), el('div', { className: 'step-text' }, ...lines(s.text))));
      for (const cmd of s.commands || []) li.append(el('pre', { className: 'cmd' }, el('code', {}, cmd)));
      if (s.block) li.append(el('pre', { className: 'cmd' }, el('code', {}, s.block)));
      if (s.record) li.append(el('p', { className: 'step-record' }, 'Record: ', ...inline(s.record)));
      const warn = el('p', { className: 'check-warning', role: 'status' });
      warn.hidden = true;
      warnings.set(`${c.id}\u0000${s.id}`, warn);
      const field = el('input', { type: 'text', maxlength: '500', autocomplete: 'off', spellcheck: 'false', 'aria-label': `Result for step ${s.id} of check ${c.id}` });
      on(field, 'input', (ev) => {
        notes.setResult(c.id, s.id, ev.target.value);
        refreshWarning(c.id, s.id);
        refreshExport();
      });
      li.append(field, warn);
      steps.append(li);
    }
    list.append(el('article', { className: 'check', 'data-check': c.id }, el('div', { className: 'check-head' }, head, badge),
      el('p', { className: 'check-reason' }, `Why it is open: ${c.reason}`), el('p', { className: 'check-source' }, `Steps from ${c.notes}.`), steps));
  }

  // ---- open and close
  let opener = null;
  const setExpanded = (v) => openers.forEach((b) => b.setAttribute('aria-expanded', v));
  function open(from) {
    opener = from || opener || openers[0] || null;
    section.hidden = false;
    setExpanded('true');
    if (section.scrollIntoView) section.scrollIntoView({ block: 'start' });
    if (title) title.focus({ preventScroll: true });
  }
  function close() {
    section.hidden = true;
    setExpanded('false');
    if (opener) opener.focus();
  }
  openers.forEach((b) => on(b, 'click', () => open(b)));
  on($('checks-close'), 'click', close);

  // ---- export, copy (the page's Copy button) and download
  on($('checks-export-btn'), 'click', () => {
    exported = true;
    refreshExport();
    if (!box) return;
    const probe = doc.createElement('a');
    const canSave = 'download' in probe;
    box.hidden = false;
    if (copy) copy.hidden = false;
    if (download) download.hidden = !canSave;
    if (copyOnly) { copyOnly.textContent = COPY_ONLY; copyOnly.hidden = canSave; }
    box.select();
    say(canSave ? 'The notes are in the box. Copy them or download them.' : 'The notes are in the box. Copy them.');
  });
  on(download, 'click', () => {
    const a = doc.createElement('a');
    a.setAttribute('href', downloadHref(notes.exportText()));
    a.download = EXPORT_FILE;
    a.hidden = true;
    if (doc.body) doc.body.appendChild(a);
    a.click();
    if (a.remove) a.remove();
    say(`Download started as ${EXPORT_FILE}. If nothing was saved, use Copy.`);
  });

  return {
    notes,
    open,
    close,
    stop() { for (const [t, type, fn] of owned) t.removeEventListener(type, fn); owned.length = 0; },
  };
}
