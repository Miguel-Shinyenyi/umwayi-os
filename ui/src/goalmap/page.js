// W38: the goal map page. It joins the model, the layout, the drawing, the theme and the source. win is the window (a fake one
// in the tests). The page is List in its HTML; it shows the map when the tier allows (List, Standard and High as in the live
// view: #tier=list keeps the list, Standard and High draw the map; High adds nothing here). It never reads the query of its
// address and keeps its two choices (the tier and the theme) in the fragment only.
import { readGoalMap, MESSAGES, MAX_BYTES } from './model.js';
import { drawMap, drawList, drawFeed, drawLamp, goalWords, supervisorWords } from './draw.js';
import { createTheme, themeFromHash, themeHash, isThemeKey, TITLE_WORD } from './theme.js';
import { createReader, createClient, liveLoad, LINES } from './feed.js';
import { readTextFile } from '../data/snapshot.js';
import { parseTier, tierHash } from '../engine/tier.js';

export function startGoalMap(win, { load, client } = {}) {
  const doc = win.document;
  const $ = (id) => doc.getElementById(id);
  const root = doc.documentElement;
  root.setAttribute('data-js', '');
  const media = win.matchMedia ? win.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const theme = createTheme({ chosen: themeFromHash(win.location.hash), reduced: !!(media && media.matches) });
  let tier = parseTier(win.location.hash) === 1 ? 'list' : 'standard';
  let model = null, source = 'live';
  const api = client || createClient({ location: win.location });
  const loadLive = load || liveLoad(api);

  const line = (text) => { $('line').textContent = text; };
  function render() {
    root.setAttribute('data-tier', tier);
    root.setAttribute('data-theme', theme.on ? 'kiroween' : 'plain');
    if (theme.reduced) root.setAttribute('data-reduced', ''); else root.removeAttribute('data-reduced');
    doc.querySelectorAll('button[data-tier]').forEach((b) => b.setAttribute('aria-pressed', String(b.getAttribute('data-tier') === tier)));
    $('map').hidden = tier === 'list';
    $('kiro').hidden = !theme.on;
    $('kiro').textContent = TITLE_WORD;
    const tb = $('theme-toggle');
    tb.setAttribute('aria-pressed', String(theme.on));
    tb.textContent = theme.reduced ? 'Theme: off (reduced motion)' : `Theme: ${theme.on ? TITLE_WORD : 'off'}`;
    tb.disabled = theme.reduced;
    $('src-live').setAttribute('aria-pressed', String(source === 'live'));
    $('src-file').setAttribute('aria-pressed', String(source === 'file'));
    $('file').hidden = source !== 'file';
    $('live').hidden = source !== 'live';
    const kill = model ? model.kill : { lit: false, word: 'unknown', note: 'drawn as on' };
    drawLamp(doc, $('lamp'), kill, theme.on);
    $('lamp-words').textContent = `Kill switch: ${kill.word}, ${kill.note}`;
    if (!model) return;
    drawMap(doc, $('drawing'), model, { theme: theme.on, reduced: theme.reduced });
    drawList(doc, $('task-list'), model);
    drawFeed(doc, $('feed'), model);
    $('sup-words').textContent = supervisorWords(model.supervisor);
    $('summary').textContent = model.goal ? goalWords(model) : MESSAGES.noGoal;
  }

  function take(raw) {
    const r = readGoalMap(raw);
    if (!r.ok) { line(r.message); return false; }
    model = r.model;
    line(model.goal ? '' : MESSAGES.noGoal);
    render();
    return true;
  }

  const reader = createReader({
    load: loadLive,
    onData: (data) => { if (source === 'live' && take(data) && model.goal) line(LINES.read(model.now)); },
    onDown: (text) => { if (source === 'live') line(text); },
  });

  // the one way a live read starts: on open, and on a press of Refresh (or Enter in the token field)
  function refresh() {
    const field = $('token');
    const value = field.value;
    field.value = ''; // emptied before anything else happens
    if (value) api.setToken(value.trim());
    if (source !== 'live' || reader.busy) return;
    $('refresh').disabled = true;
    line(LINES.reading);
    reader.read().finally(() => { $('refresh').disabled = false; });
  }

  function useSource(next) {
    source = next;
    render();
    if (next === 'live') refresh(); else line('Open a goal map file to draw it.');
  }

  const handlers = [];
  const on = (target, type, f) => { target.addEventListener(type, f); handlers.push([target, type, f]); };
  doc.querySelectorAll('button[data-tier]').forEach((b) => on(b, 'click', () => {
    tier = b.getAttribute('data-tier') === 'list' ? 'list' : 'standard';
    win.history.replaceState(null, '', tierHash(win.location.hash, tier === 'list' ? 1 : 2));
    render();
  }));
  const toggle = () => {
    if (theme.reduced) return;
    theme.toggle();
    win.history.replaceState(null, '', themeHash(win.location.hash, theme.chosen));
    render();
  };
  on($('theme-toggle'), 'click', toggle);
  on(doc, 'keydown', (e) => { if (isThemeKey(e)) { e.preventDefault(); toggle(); } });
  on($('src-live'), 'click', () => useSource('live'));
  on($('src-file'), 'click', () => useSource('file'));
  on($('refresh'), 'click', refresh);
  on($('token'), 'keydown', (e) => { if (e && e.key === 'Enter') { e.preventDefault(); refresh(); } });
  on($('file-input'), 'change', () => {
    const f = $('file-input').files && $('file-input').files[0];
    readTextFile(f, win.FileReader, MAX_BYTES).then((text) => (text === null ? line(MESSAGES.tooBig) : take(text)));
  });
  if (media && media.addEventListener) on(media, 'change', (e) => { theme.setReduced(e.matches); render(); });

  line('');
  render();
  refresh(); // the one read on open
  return {
    stop() { for (const [t, ty, f] of handlers) t.removeEventListener(ty, f); },
    refresh,
    get reads() { return reader.reads; },
    get model() { return model; },
    get theme() { return theme; },
    take,
  };
}
