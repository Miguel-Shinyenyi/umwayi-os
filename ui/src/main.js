// Entry point. If the 3D view cannot start, the list view takes its place and says so.
import { createApp } from './app.js';
import { showList, toggleList } from './ui/fallback.js';
import { initHome } from './ui/home.js';

const doc = document;
const $ = (id) => doc.getElementById(id);
initHome(doc, window);

$('list-toggle').addEventListener('click', () => toggleList(doc, $('list-view').hidden));
doc.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('list-view').hidden && !$('list-toggle').hidden) toggleList(doc, false);
});

try {
  const app = createApp(window);
  app.onLost = () => showList(doc, 'The 3D view stopped. The list view shows the same stations.');
  app.start();
} catch {
  showList(doc, 'The 3D view could not start in this browser. The list view shows the same stations.');
}
