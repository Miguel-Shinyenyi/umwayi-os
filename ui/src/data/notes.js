// The owner checks panel's logic (12.R7): the notes kept in memory, the status of a check, the warning on a result that looks
// like a value, and the text of the export. Pure. The page cannot tell whether a check passed: a check is "not done" until
// every step is ticked, and then "ticked by you". Nothing here touches the page, a storage, a clock or the network.
import { CHECKS } from './checks.js';

export const STATUS_NOT_DONE = 'not done';
export const STATUS_TICKED = 'ticked by you';
export const END_LINE = 'These are your notes. umwayi did not run or verify anything.';
export const MEMORY_NOTICE = 'These notes are lost when you close this page. Export them first.';
export const RECORD_RULE = 'Record field names, exit codes and version strings, never a value.';
export const EXPORT_FILE = 'umwayi-owner-checks.txt';
export const MAX_RESULT = 500;

// ------------------------------------------------------------------------------------------------ the warning (12.R7.6)
// A hint, never a block. Order is fixed so the tests and the export are stable.
const EMAIL = /[^\s@]+@[^\s@]+\.[^\s@]+/;
const URL_LIKE = /:\/\//;
const TOKEN = /[A-Za-z0-9]{24,}/;
const HEX = /\b[0-9a-f]{16,}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;
const PLAIN_EXIT = /^(exit\s*)?\d{1,3}$/i;

export function valueWarnings(text, { exit = false } = {}) {
  const t = typeof text === 'string' ? text : '';
  const out = [];
  if (EMAIL.test(t)) out.push('email');
  if (URL_LIKE.test(t)) out.push('url');
  if (TOKEN.test(t)) out.push('token');
  if (HEX.test(t)) out.push('hex');
  if (exit) {
    const s = t.trim();
    if (s !== '' && !(PLAIN_EXIT.test(s) && Number(s.replace(/\D/g, '')) <= 255)) out.push('exit');
  }
  return out;
}

const LOOKS = { email: 'an email address', url: 'a URL', token: 'a token', hex: 'a long hex string' };
export function warningText(code) {
  if (code === 'exit') return 'This step records an exit code. Type the number only.';
  return LOOKS[code] ? `This looks like ${LOOKS[code]}. ${RECORD_RULE}` : '';
}
function exportWarning(codes) {
  const looks = codes.filter((c) => LOOKS[c]).map((c) => LOOKS[c]);
  const parts = [];
  if (looks.length) parts.push(`it looks like ${looks.join(' or ')}`);
  if (codes.includes('exit')) parts.push('this step records an exit code');
  return parts.length ? `Check this result: ${parts.join(', and ')}.` : '';
}

export function downloadHref(text) {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(String(text))}`;
}

// ------------------------------------------------------------------------------------------------ the notes
const clean = (v) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f\s]+/g, ' ').slice(0, MAX_RESULT) : '');

export function createNotes(checks = CHECKS) {
  const spec = new Map(checks.map((c) => [c.id, new Map(c.steps.map((s) => [s.id, s]))]));
  const state = new Map(); // checkId -> Map(stepId -> { ticked, result }); in memory only
  const slot = (cid, sid) => {
    if (!spec.has(cid) || !spec.get(cid).has(sid)) return null;
    if (!state.has(cid)) state.set(cid, new Map());
    const m = state.get(cid);
    if (!m.has(sid)) m.set(sid, { ticked: false, result: '' });
    return m.get(sid);
  };
  const peek = (cid, sid) => (state.has(cid) && state.get(cid).get(sid)) || { ticked: false, result: '' };
  const counts = (cid) => {
    const steps = spec.get(cid);
    if (!steps) return { ticked: 0, total: 0 };
    let ticked = 0;
    for (const sid of steps.keys()) if (peek(cid, sid).ticked) ticked++;
    return { ticked, total: steps.size };
  };
  const status = (cid) => {
    const { ticked, total } = counts(cid);
    return total > 0 && ticked === total ? STATUS_TICKED : STATUS_NOT_DONE;
  };
  const warnings = (cid, sid) => {
    const step = spec.has(cid) && spec.get(cid).get(sid);
    return step ? valueWarnings(peek(cid, sid).result, { exit: step.exit === true }) : [];
  };
  return {
    tick(cid, sid, on) {
      const s = slot(cid, sid);
      if (s) s.ticked = on === true;
    },
    setResult(cid, sid, text) {
      const s = slot(cid, sid);
      if (s) s.result = clean(text);
    },
    isTicked: (cid, sid) => peek(cid, sid).ticked,
    result: (cid, sid) => peek(cid, sid).result,
    counts,
    status,
    warnings,
    // a copy of what is held, for the tests
    state() {
      const out = {};
      for (const [cid, m] of state) { out[cid] = {}; for (const [sid, v] of m) out[cid][sid] = { ...v }; }
      return out;
    },
    // the text of 12.R7.5, made from the state as it is now
    exportText() {
      const lines = ['umwayi owner checks: my notes', 'These notes were made in the page. They are lost when you close it.'];
      for (const c of checks) {
        const { ticked, total } = counts(c.id);
        lines.push('', `== ${c.id}: ${c.name} ==`, `Status: ${status(c.id)} (${ticked} of ${total} steps ticked)`);
        for (const s of c.steps) {
          const v = peek(c.id, s.id);
          lines.push(`[${v.ticked ? 'x' : ' '}] ${s.id}. ${s.text.replace(/\s*\n\s*/g, ' ')}`);
          if (v.result !== '') {
            lines.push(`    Result: ${v.result}`);
            const w = exportWarning(warnings(c.id, s.id));
            if (w) lines.push(`    ${w}`);
          }
        }
      }
      lines.push('', END_LINE, '');
      return lines.join('\n');
    },
  };
}
