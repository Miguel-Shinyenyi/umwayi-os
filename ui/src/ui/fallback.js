// The tier on the page (12.R16): List is tier 1, the plain list of the eleven stations with the home content, and the
// picture is tier 2. The page starts as List in the HTML itself, so with no script, no WebGL or a failed start it stays List.
// Functions take the document so they can be tested without a browser.
export function setTier(doc, name, message = '') {
  const $ = (id) => doc.getElementById(id);
  const list = name === 'list';
  doc.documentElement.setAttribute('data-tier', name);
  doc.querySelectorAll('#tiers button[data-tier]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tier === name)));
  $('scene').setAttribute('aria-hidden', String(list));
  $('notice').textContent = message;
  $('notice').hidden = !message;
}
