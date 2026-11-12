// The home text and the list of the eleven stations, rendered by the server (12.R17.3). The words are the live view's own: they
// come from ui/src/data/home.js and ui/src/stations/meta.js, which the page of ui/ is built from, so there is one set of words.
// The markup has the same ids as ui/src/index.html because the shared script (ui/src/boot.js) joins the buttons to the picture
// by them; site/test/home.test.mjs compares both. Nothing here runs in the browser: the script is app/scene.js.
import { createElement as h } from 'react';
import { STATIONS } from '../../ui/src/stations/meta.js';
import { TITLE, PROMISE, INSTALL, FIRST, LINKS, statusStrip } from '../../ui/src/data/home.js';
import { SAMPLE } from '../../ui/src/data/sample.js';

// the same text as the label on the canvas of ui/src/index.html (the test compares them)
export const SCENE_LABEL = 'The Kenyan highlands at dusk. A shepherd with a lantern stands at the centre of a river valley, with Mount Kenya on the horizon. Eleven features of the land stand round him: a spring pool, a drystone wall with gates, a sheepfold, a cave in a rock face, a standing stone, a river with a water wheel, a sheepdog and herd, a stream through pools, a ford and bridge, a lone gate with a red lamp and a rain water tank. The List view has the same stations as text.';

const tiers = [['list', 'List', true], ['standard', 'Standard', false]];

function Command({ c }) {
  return h('li', { key: c.id },
    h('code', { id: `cmd-${c.id}` }, c.text),
    h('button', { type: 'button', className: 'btn small', 'data-copy': `cmd-${c.id}`, 'aria-label': `Copy: ${c.text}` }, 'Copy'),
    c.what ? h('p', { className: 'what' }, c.what) : null);
}

function Station({ s }) {
  return h('li', { key: s.id, 'data-station': s.id },
    h('p', { className: 'state' }, s.state === 'built' ? 'Built' : 'Planned'),
    h('h3', null, s.name),
    h('p', null, s.lines[0]),
    h('p', null, s.lines[1]),
    s.note ? h('p', { className: 'note' }, s.note) : null,
    h('p', null, h('code', null, s.command)));
}

export function Home() {
  const strip = statusStrip(SAMPLE, { sample: true, date: SAMPLE.date });
  return h('div', null,
    h('header', { className: 'bar' },
      h('span', { className: 'mark' }, 'umwayi-os'),
      h('div', { className: 'actions' },
        h('div', { className: 'tiers', id: 'tiers', role: 'group', 'aria-label': 'View' },
          tiers.map(([name, label, on]) => h('button', { key: name, type: 'button', className: 'btn', 'data-tier': name, 'aria-pressed': on ? 'true' : 'false' }, label))),
        h('button', { type: 'button', className: 'btn', id: 'calm-toggle', 'aria-pressed': 'false' }, 'Calm mode'))),
    h('main', null,
      h('section', { id: 'hero', 'aria-label': 'The valley' },
        h('canvas', { id: 'scene', role: 'img', 'aria-label': SCENE_LABEL }),
        h('div', { className: 'intro' }, h('h1', null, TITLE), h('p', { className: 'promise' }, PROMISE)),
        h('nav', { id: 'labels', 'aria-label': 'Stations' },
          STATIONS.map((s) => h('button', { key: s.id, type: 'button', className: 'label', 'data-station': s.id }, s.name))),
        h('p', { id: 'hint' },
          h('span', { className: 'wide' }, 'Drag to look around. Move over a feature, or press Tab, to see its name.'),
          h('span', { className: 'narrow' }, 'Drag to look around. Touch a feature to open it.')),
        h('p', { id: 'sample-tag' }, 'sample'),
        h('aside', { id: 'panel', tabIndex: -1, 'aria-labelledby': 'panel-title' },
          h('p', { className: 'state', id: 'panel-state' }),
          h('h2', { id: 'panel-title' }),
          h('p', { id: 'panel-line1' }),
          h('p', { id: 'panel-line2' }),
          h('p', { className: 'cmd' }, h('code', { id: 'panel-cmd' })),
          h('p', { className: 'note', id: 'panel-note' }),
          h('p', { className: 'counts', id: 'panel-counts' }),
          h('p', { className: 'caption', id: 'pose-caption', role: 'status', 'aria-live': 'polite' }),
          h('div', { className: 'row' },
            h('button', { type: 'button', className: 'btn small', id: 'replay' }, 'Replay'),
            h('button', { type: 'button', className: 'btn small', id: 'pose-prev' }, 'Previous pose'),
            h('button', { type: 'button', className: 'btn small', id: 'pose-next' }, 'Next pose')),
          h('div', { className: 'row' },
            h('button', { type: 'button', className: 'btn small', id: 'station-prev' }, 'Previous station'),
            h('button', { type: 'button', className: 'btn small', id: 'station-next' }, 'Next station'),
            h('button', { type: 'button', className: 'btn small', id: 'back' }, 'Overview')))),
      h('section', { className: 'home', id: 'status', 'aria-labelledby': 'status-title' },
        h('div', { className: 'status-head' }, h('h2', { id: 'status-title' }, 'The state of this root'), h('p', { className: 'more' }, 'Scroll down for the install steps and the links.')),
        h('ul', { className: 'strip' },
          strip.map((s) => h('li', { key: s.id, 'data-strip': s.id },
            h('span', { className: 'k' }, s.name), h('span', { className: 'v' }, s.value), h('span', { className: 't' }, s.tag)))),
        h('div', { className: 'snapshot', id: 'snapshot' },
          h('button', { type: 'button', className: 'btn small', id: 'snapshot-open' }, 'Open a snapshot file'),
          h('input', { type: 'file', id: 'snapshot-file', accept: '.json,application/json', tabIndex: -1, hidden: true }),
          h('p', { className: 'snapshot-help' }, 'Run ', h('code', null, 'umwayi view snapshot'), ', then open the file it wrote, or drop it on this page. The file is read in this browser. It is not uploaded, sent or kept.'),
          h('p', { className: 'snapshot-msg', id: 'snapshot-msg', role: 'status', 'aria-live': 'polite' }))),
      h('section', { className: 'home', id: 'list-view', 'aria-labelledby': 'list-title' },
        h('h2', { id: 'list-title' }, 'The eleven stations'),
        h('p', { className: 'intro-text' }, 'The same stations as the picture, as text. This is the List view: it needs no WebGL and no script.'),
        h('ul', { id: 'station-list' }, STATIONS.map((s) => h(Station, { key: s.id, s })))),
      h('section', { className: 'home', id: 'start', 'aria-labelledby': 'start-title' },
        h('h2', { id: 'start-title' }, 'Start'),
        h('p', null, 'Python 3.10 or newer, no third party packages.'),
        h('ol', { className: 'cmds' }, INSTALL.map((c) => h(Command, { key: c.id, c }))),
        h('h3', null, 'First commands'),
        h('ol', { className: 'cmds' }, FIRST.map((c) => h(Command, { key: c.id, c }))),
        h('p', { className: 'copied', id: 'copy-status', role: 'status', 'aria-live': 'polite' })),
      h('section', { className: 'home', id: 'links', 'aria-labelledby': 'links-title' },
        h('h2', { id: 'links-title' }, 'Links'),
        h('ul', { className: 'links' },
          LINKS.map((l) => (l.href
            ? h('li', { key: l.id }, h('a', { href: l.href, rel: 'noopener noreferrer' }, l.name), h('span', { className: 'note' }, l.note))
            : h('li', { key: l.id, 'data-placeholder': '' }, h('span', { className: 'name' }, l.name), h('span', { className: 'note' }, l.note)))))),
      h('footer', { className: 'home foot' }, h('p', { id: 'foot-note' }, 'A sample world. The picture shows made up counts until you load your own.'))),
    h('p', { id: 'notice', role: 'status', hidden: true }));
}
