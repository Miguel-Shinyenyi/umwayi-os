// W8 slice: the progress page. Pure functions, no file or network access: build.mjs reads three files of the repo and hands
// their text in; the tests hand in text of their own. Nothing here reads the logbook or any .umwayi data.

const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => entities[c]);

// "### 265. Title" lines of docs/KNOWN-LIMITS.md: the highest number
export function highestLimit(text) {
  let top = 0;
  for (const m of text.matchAll(/^### (\d+)\./gm)) top = Math.max(top, Number(m[1]));
  return top;
}

// the table under "### Pull requests" in docs/status-log.md: date, PR, what. File order is newest first, so the first rows are
// the latest. A row whose date is not YYYY-MM-DD is not a row.
export function statusRows(text) {
  const rows = [];
  for (const line of text.split('\n')) {
    if (!line.startsWith('| ')) continue;
    const cells = line.replace(/^\|\s*/, '').replace(/\s*\|\s*$/, '').split(/\s\|\s/);
    if (cells.length < 3 || !/^\d{4}-\d{2}-\d{2}$/.test(cells[0].trim())) continue;
    rows.push({ date: cells[0].trim(), pr: cells[1].trim(), what: cells[2].trim() });
  }
  return rows;
}

// the first sentence of a row, without backticks, cut at 240 characters
export function firstSentence(what) {
  const plain = what.replace(/`/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
  const m = plain.match(/^(.*?[.])(\s|$)/);
  let s = m ? m[1] : plain;
  if (s.length > 240) s = s.slice(0, 237).replace(/\s+\S*$/, '') + '...';
  return s;
}

// tasks.md: every "## " heading opens a group, and "### " headings stay inside it. A task is a "- [ ]" or "- [x]" line.
export function taskGroups(text) {
  const groups = [];
  let cur = null;
  for (const line of text.split('\n')) {
    const h = line.match(/^## (.+?)\s*$/);
    if (h) { cur = { name: h[1].replace(/\s+\(.*$/, '').replace(/:$/, ''), done: 0, open: 0 }; groups.push(cur); continue; }
    const t = line.match(/^\s*- \[([ xX])\]/);
    if (t && cur) { if (t[1] === ' ') cur.open += 1; else cur.done += 1; }
  }
  return groups.filter((g) => g.done + g.open > 0);
}

export function model({ statusLog, tasks, limits }) {
  return { groups: taskGroups(tasks), rows: statusRows(statusLog).slice(0, 10), limit: highestLimit(limits) };
}

// the pieces the template takes. date is YYYY-MM-DD.
export function render(m, date) {
  const done = m.groups.reduce((a, g) => a + g.done, 0);
  const open = m.groups.reduce((a, g) => a + g.open, 0);
  const groups = m.groups.map((g) => {
    return `    <li data-group="${esc(g.name)}"><span class="name">${esc(g.name)}</span><span class="nums"><span class="done">${g.done} done</span><span class="open">${g.open} open</span></span><progress value="${g.done}" max="${g.done + g.open}" aria-label="${esc(g.name)}: ${g.done} of ${g.done + g.open} done"></progress></li>`;
  }).join('\n');
  const rows = m.rows.map((r) => `    <li><span class="when">${esc(r.date)}</span><span class="pr">PR ${esc(r.pr)}</span><span class="what">${esc(firstSentence(r.what))}</span></li>`).join('\n');
  return {
    groups, rows, date,
    totals: `${done} tasks done and ${open} open, in ${m.groups.length} groups.`,
    limit: String(m.limit),
  };
}
