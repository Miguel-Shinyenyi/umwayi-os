// The phone layout audit (W1): what is measured on a rendered page, and the runner that renders it at the four phone sizes.
// `audit` runs inside the page. It finds, from real layout boxes and not from the CSS text:
//   - text or controls that overlap: every line box of text, and the border box of every button, field and text area, are
//     compared two by two; a box that holds another (a button and its label) does not count; a box clipped by a scrolling or
//     hidden parent is cut to what shows; a box that is not visible (hidden, opacity 0) is left out;
//   - a sideways overflow: the page is wider than the screen, or something that shows is cut by the right or left edge;
//   - a control that is too small to touch: a button, a field or a tick box under the sizes asked for.
// The same module is used by ui/test/phone.test.mjs (the page of ui/dist) and site/test/phone.test.mjs (the site's HTML).

export const PHONES = [
  { name: '375x667', width: 375, height: 667 },
  { name: '390x844', width: 390, height: 844 },
  { name: '412x915', width: 412, height: 915 },
  { name: '360x640', width: 360, height: 640 },
];
// the same phones turned on their side
export const PHONES_LANDSCAPE = PHONES.map((p) => ({ name: `${p.height}x${p.width}`, width: p.height, height: p.width }));

// runs in the page; the argument is { minTouch, minTick }
export function audit(opts) {
  const problems = [];
  const vw = window.innerWidth;
  const label = (e) => {
    if (!e || !e.tagName) return '?';
    const id = e.id ? `#${e.id}` : '';
    const cls = typeof e.className === 'string' && e.className ? `.${e.className.trim().split(/\s+/).join('.')}` : '';
    return `${e.tagName.toLowerCase()}${id}${cls}`;
  };
  const shown = (e) => {
    if (!e || !e.checkVisibility) return true;
    return e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true, opacityProperty: true, visibilityProperty: true });
  };
  // the part of a rectangle that is not cut off by an ancestor that scrolls or hides its overflow (the page itself is not one:
  // the page's own edge is tested on its own below)
  const clip = (el, r) => {
    let box = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.overflowX === 'visible' && s.overflowY === 'visible') continue;
      const b = p.getBoundingClientRect();
      if (s.overflowX !== 'visible') { box.left = Math.max(box.left, b.left); box.right = Math.min(box.right, b.right); }
      if (s.overflowY !== 'visible') { box.top = Math.max(box.top, b.top); box.bottom = Math.min(box.bottom, b.bottom); }
    }
    return box.right - box.left > 0.5 && box.bottom - box.top > 0.5 ? box : null;
  };

  const boxes = [];
  // line boxes of text
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || /^(script|style|noscript|title)$/i.test(el.tagName) || !n.nodeValue.trim() || !shown(el)) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      if (r.width < 1 || r.height < 1) continue;
      const c = clip(el, r);
      if (c) boxes.push({ el, node: n, ...c, kind: 'text', text: n.nodeValue.trim().slice(0, 40) });
    }
  }
  // controls
  for (const el of document.querySelectorAll('button, input, textarea, select, summary, a[href]')) {
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const c = clip(el, r);
    if (c) boxes.push({ el, node: null, ...c, kind: 'control', text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40) });
  }
  const holds = (a, b) => (a.kind === 'control' && a.el.contains(b.el)) || (b.kind === 'control' && b.el.contains(a.el));
  let overlaps = 0;
  const seen = new Set();
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.node && a.node === b.node) continue;
      if (holds(a, b)) continue;
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 2 && h > 3) {
        // a link or a button whose box holds a line of text further up is the same thing seen twice; anything else is a real overlap
        const line = `overlap: "${a.text}" (${label(a.el)}) and "${b.text}" (${label(b.el)})`;
        if (!seen.has(line)) { seen.add(line); if (seen.size <= 12) problems.push(`${line} by ${Math.round(w)} x ${Math.round(h)} px`); }
        overlaps++;
      }
    }
  }
  if (seen.size > 12) problems.push(`overlap: ${seen.size - 12} more pairs`);

  // sideways
  const de = document.documentElement;
  if (de.scrollWidth > vw) problems.push(`sideways: the page is ${de.scrollWidth} px wide on a ${vw} px screen`);
  if (document.body.scrollWidth > vw) problems.push(`sideways: the body is ${document.body.scrollWidth} px wide on a ${vw} px screen`);
  let cut = 0;
  for (const b of boxes) {
    if (b.right > vw + 0.5 || b.left < -0.5) {
      if (cut++ < 8) problems.push(`sideways: ${label(b.el)} "${b.text}" reaches ${Math.round(b.left)} to ${Math.round(b.right)} on a ${vw} px screen`);
    }
  }
  if (cut > 8) problems.push(`sideways: ${cut - 8} more`);

  // touch targets
  const small = [];
  for (const el of document.querySelectorAll('button, input[type="text"], textarea, summary')) {
    // the name tag of a feature is a button for the keyboard and a screen reader; a finger never lands on it (pointer-events: none)
    if (!shown(el) || getComputedStyle(el).pointerEvents === 'none') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1) continue;
    if (r.height < opts.minTouch - 0.5 || r.width < opts.minTouch - 0.5) small.push(`${label(el)} "${(el.textContent || '').trim().slice(0, 20)}" is ${Math.round(r.width)} x ${Math.round(r.height)}`);
  }
  for (const el of document.querySelectorAll('input[type="checkbox"]')) {
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.height < opts.minTick - 0.5 || r.width < opts.minTick - 0.5) small.push(`${label(el)} is ${Math.round(r.width)} x ${Math.round(r.height)}`);
  }
  for (const s of small.slice(0, 8)) problems.push(`small: ${s}`);
  if (small.length > 8) problems.push(`small: ${small.length - 8} more`);

  return { problems, boxes: boxes.length, width: vw, scrollWidth: de.scrollWidth, scrollY: Math.round(window.scrollY), tier: de.dataset.tier || null };
}

// the visible reading order of the controls of the header, left to right and top to bottom, and the order Tab takes: they must be the same
export function headerOrder() {
  const names = (list) => list.map((e) => e.dataset.tier || e.id || e.tagName.toLowerCase());
  const controls = [...document.querySelectorAll('.bar button')].filter((e) => e.checkVisibility());
  const visual = controls.map((e) => ({ e, r: e.getBoundingClientRect() }))
    .sort((a, b) => (Math.abs(a.r.top - b.r.top) > 4 ? a.r.top - b.r.top : a.r.left - b.r.left)).map((x) => x.e);
  return { dom: names(controls), visual: names(visual) };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Render the page at each size. `scenario(page, check)` drives one page; `check(name, prepare)` runs `prepare(page)` (a click, a key)
// and then the audit, and records the result under the phone and the name of the state.
export async function runPhones(browser, url, scenario, { phones = PHONES, minTouch = 44, minTick = 44, settleMs = 700 } = {}) {
  const out = [], extras = [];
  for (const phone of phones) {
    const page = await browser.newPage();
    try {
      await page.emulate({ width: phone.width, height: phone.height });
      await page.goto(url);
      await sleep(settleMs);
      const check = async (name, prepare) => {
        const note = prepare ? await prepare(page) : null;
        await sleep(120);
        out.push({ phone: phone.name, state: name, note, order: await page.evaluate(headerOrder), ...(await page.evaluate(audit, { minTouch, minTick })) });
      };
      extras.push({ phone: phone.name, ...(await scenario(page, check, phone)) });
    } finally {
      await page.close();
    }
  }
  return { results: out, extras };
}

export const problemsOf = (results) => results.flatMap((r) => r.problems.map((p) => `${r.phone} ${r.state}${r.scrollY ? ` (scrolled ${r.scrollY} px)` : ''}: ${p}`));
