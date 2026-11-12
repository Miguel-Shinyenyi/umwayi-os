// The page part of reading a snapshot (12.R4.9, 12.R9.1): the file picker and the drop, the one message, and what the page shows
// once a snapshot is loaded (the status strip, the date next to the scene, the footer). The file is read in the browser with
// FileReader (data/snapshot.js) and goes nowhere else: no request, no storage, no address. Every value is put in the page as
// text (textContent), never as markup, and only numbers, one of three words and a date can reach it, because the strict reader
// has already refused anything else.
import { NOT_A_SNAPSHOT, readSnapshotFile, viewOf } from '../data/snapshot.js';
import { statusStrip } from '../data/home.js';
import { renderStrip } from './home.js';

// options: { onView(view) } is called with the view of each snapshot that was accepted (never for a refused one).
// Returns { stop }. A page without the picker (or any of its elements) still works: the parts it lacks are skipped.
export function initSnapshot(doc, win, { onView = () => {} } = {}) {
  const $ = (id) => doc.getElementById(id);
  const input = $('snapshot-file'), open = $('snapshot-open'), msg = $('snapshot-msg'), tag = $('sample-tag'), foot = $('foot-note');
  const say = (text) => { if (msg) msg.textContent = text; };
  let turn = 0;

  function show(view) {
    renderStrip(doc, statusStrip(view.counts, { sample: view.sample, date: view.date }));
    if (tag) tag.textContent = view.label;
    if (foot) foot.textContent = view.footer;
  }

  // The newest choice wins: an older, slower file that finishes last is dropped.
  function load(file) {
    const mine = ++turn;
    return readSnapshotFile(file, win.FileReader).then((result) => {
      if (mine !== turn) return false;
      if (!result.ok) { say(NOT_A_SNAPSHOT); return false; }
      const view = viewOf(result.snapshot);
      show(view);
      say(`Loaded the snapshot of ${view.date}.`);
      onView(view);
      return true;
    });
  }

  const hasFiles = (ev) => !!(ev && ev.dataTransfer && ev.dataTransfer.types && Array.prototype.includes.call(ev.dataTransfer.types, 'Files'));
  const onChange = () => {
    const files = input.files;
    if (files && files.length === 1) load(files[0]);
    else if (files && files.length > 1) { turn++; say(NOT_A_SNAPSHOT); }
    input.value = ''; // so the same file can be picked again after the command has refreshed it
  };
  const onOpen = () => input.click();
  const onOver = (ev) => { if (hasFiles(ev)) ev.preventDefault(); };
  const onDrop = (ev) => {
    if (!hasFiles(ev)) return;
    ev.preventDefault(); // the browser would otherwise open the file in the tab
    const files = ev.dataTransfer.files;
    if (files && files.length === 1) load(files[0]);
    else { turn++; say(NOT_A_SNAPSHOT); }
  };

  if (input) input.addEventListener('change', onChange);
  if (open && input) open.addEventListener('click', onOpen);
  doc.addEventListener('dragover', onOver);
  doc.addEventListener('drop', onDrop);
  return {
    stop() {
      if (input) input.removeEventListener('change', onChange);
      if (open) open.removeEventListener('click', onOpen);
      doc.removeEventListener('dragover', onOver);
      doc.removeEventListener('drop', onDrop);
    },
  };
}
