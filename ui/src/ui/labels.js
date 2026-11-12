// A real button sits over each feature, so the keyboard and a screen reader reach all eleven. Its name is not drawn in the
// picture: it shows on hover and on focus (CSS), and while the feature is selected.
export function createLabels(nav, onSelect, onFocus) {
  const buttons = new Map();
  nav.querySelectorAll('button[data-station]').forEach((b) => {
    buttons.set(b.dataset.station, b);
    b.addEventListener('click', () => onSelect(b.dataset.station));
    b.addEventListener('focus', () => onFocus(b.dataset.station));
    b.addEventListener('blur', () => onFocus(null));
  });
  const sizes = new Map();
  return {
    buttons,
    measure() {
      buttons.forEach((b, id) => sizes.set(id, { w: b.offsetWidth || 90, h: b.offsetHeight || 28 }));
    },
    size: (id) => sizes.get(id) || { w: 90, h: 28 },
    // x, y is the top left corner; whole pixels keep the text sharp
    place(id, x, y) {
      buttons.get(id).style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    },
    // While a station is selected only its own button is shown; the others wait for the overview.
    // The selected name waits (data-pending, drawn clear) until the next frame has put it at the feature's new place, so it is never
    // seen for a moment at the place the picture had before the move, where the station panel or the title may now be.
    setSelected(id) {
      buttons.forEach((b, key) => {
        b.classList.toggle('is-selected', key === id);
        if (key === id) b.setAttribute('data-pending', ''); else b.removeAttribute('data-pending');
        if (id && key !== id) b.setAttribute('data-away', '');
        else b.removeAttribute('data-away');
      });
    },
    placed() {
      buttons.forEach((b) => b.removeAttribute('data-pending'));
    },
    setHover(id) {
      buttons.forEach((b, key) => b.classList.toggle('is-hover', key === id));
    },
    focus(id) {
      const b = buttons.get(id);
      if (b) b.focus({ preventScroll: true });
    },
  };
}
