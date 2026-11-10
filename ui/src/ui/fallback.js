// The list view: a plain list of the same stations, as text. It is shown on request, and by itself when the 3D view
// cannot start. Functions take the document so they can be tested without a browser.
export function showList(doc, message) {
  const $ = (id) => doc.getElementById(id);
  $('list-view').hidden = false;
  for (const id of ['list-toggle', 'calm-toggle', 'labels', 'hint', 'panel', 'sample-tag']) $(id).hidden = true;
  $('scene').setAttribute('aria-hidden', 'true');
  if (message) {
    $('notice').textContent = message;
    $('notice').hidden = false;
  }
}

export function toggleList(doc, on) {
  const $ = (id) => doc.getElementById(id);
  $('list-view').hidden = !on;
  $('list-toggle').setAttribute('aria-pressed', String(on));
  $('list-toggle').textContent = on ? 'Back to the picture' : 'List view';
  $('scene').setAttribute('aria-hidden', String(on));
}
