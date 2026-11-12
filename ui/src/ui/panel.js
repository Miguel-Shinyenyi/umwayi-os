// The panel of the selected station. Text is always set as text, never as markup.
import { describe, NO_COUNT } from '../data/counts.js';

export function createPanel(doc, handlers) {
  const $ = (id) => doc.getElementById(id);
  const root = $('panel');
  const el = {
    state: $('panel-state'), title: $('panel-title'), l1: $('panel-line1'), l2: $('panel-line2'), cmd: $('panel-cmd'),
    note: $('panel-note'), counts: $('panel-counts'), caption: $('pose-caption'),
    replay: $('replay'), prev: $('pose-prev'), next: $('pose-next'),
  };
  $('replay').addEventListener('click', handlers.replay);
  $('pose-prev').addEventListener('click', handlers.posePrev);
  $('pose-next').addEventListener('click', handlers.poseNext);
  $('station-prev').addEventListener('click', handlers.stationPrev);
  $('station-next').addEventListener('click', handlers.stationNext);
  $('back').addEventListener('click', handlers.back);
  return {
    root,
    // counts: the snapshot or the sample; sample is true while it is the sample
    show(def, counts, sample) {
      el.state.textContent = def.state === 'built' ? 'Built' : 'Planned';
      el.title.textContent = def.name;
      el.l1.textContent = def.lines[0];
      el.l2.textContent = def.lines[1];
      el.cmd.textContent = def.command;
      el.note.textContent = def.note || '';
      el.note.hidden = !def.note;
      const text = describe(def.id, counts);
      el.counts.textContent = text === null ? NO_COUNT : `${sample ? 'Sample: ' : ''}${text}`;
      root.setAttribute('data-open', '');
    },
    hide() {
      root.removeAttribute('data-open');
    },
    isOpen: () => root.hasAttribute('data-open'),
    setCaption(text, index, total) {
      el.caption.textContent = text ? `${index + 1} of ${total}: ${text}` : '';
    },
    // With reduced motion there is no replay; the poses are stepped by hand.
    setMode(reduced) {
      el.replay.hidden = reduced;
      el.prev.hidden = !reduced;
      el.next.hidden = !reduced;
    },
    focus() {
      root.focus({ preventScroll: true });
    },
  };
}
