// The eleven labels are real buttons that are already in the page. This only places them over their stations.
export function createLabels(nav, onSelect) {
  const buttons = new Map();
  nav.querySelectorAll('button[data-station]').forEach((b) => {
    buttons.set(b.dataset.station, b);
    b.addEventListener('click', () => onSelect(b.dataset.station));
  });
  const sizes = new Map();
  return {
    buttons,
    measure() {
      buttons.forEach((b, id) => sizes.set(id, { w: b.offsetWidth || 90, h: b.offsetHeight || 28 }));
    },
    size: (id) => sizes.get(id) || { w: 90, h: 28 },
    place(id, x, y) {
      // x, y is the top left corner; whole pixels keep the text sharp
      buttons.get(id).style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    },
    // While a station is selected only its own label is shown; the others wait for the overview.
    setSelected(id) {
      buttons.forEach((b, key) => {
        b.classList.toggle('is-selected', key === id);
        if (id && key !== id) b.setAttribute('data-away', '');
        else b.removeAttribute('data-away');
      });
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
