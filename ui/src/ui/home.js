// The home content's few behaviours: Copy buttons (the clipboard is written only in the click handler) and the status strip.
export function initHome(doc, win) {
  const status = doc.getElementById('copy-status');
  const say = (text) => { if (status) status.textContent = text; };
  doc.querySelectorAll('button[data-copy]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const code = doc.getElementById(btn.dataset.copy);
      const text = code.textContent;
      const done = () => {
        btn.textContent = 'Copied';
        say(`Copied: ${text}`);
        win.setTimeout(() => { btn.textContent = 'Copy'; }, 1800);
      };
      // where the browser does not allow it, select the text so the owner can press Ctrl+C
      const fallback = () => {
        const r = doc.createRange();
        r.selectNodeContents(code);
        const s = win.getSelection();
        s.removeAllRanges();
        s.addRange(r);
        say('The browser did not allow a copy here. The command is selected: press Ctrl+C.');
      };
      const nav = win.navigator;
      if (nav && nav.clipboard && nav.clipboard.writeText) nav.clipboard.writeText(text).then(done, fallback);
      else fallback();
    });
  });
}

// Writes the values of statusStrip() into the strip that the build already put in the page.
export function renderStrip(doc, items) {
  for (const it of items) {
    const li = doc.querySelector(`#status li[data-strip="${it.id}"]`);
    if (!li) continue;
    li.querySelector('.v').textContent = it.value;
    li.querySelector('.t').textContent = it.tag;
  }
}
