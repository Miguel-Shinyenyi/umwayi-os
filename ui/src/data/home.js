// The words and values of the home content: the title, the promise, the status strip, the install and first commands, the links.
// Pure data and text. The build makes the page from this, so it reads without any script.
import { describe } from './counts.js';

export const TITLE = 'umwayi-os';
export const PROMISE = 'An AI operating system for one person. Your rules come before every AI helper acts, and every change is written down.';
export const REPO = 'https://github.com/Miguel-Shinyenyi/umwayi-os';
export const DOCS = `${REPO}/tree/main/docs`;
const XML_NAMESPACE = 'http://www.w3.org/1999/xhtml'; // a name three.js carries, never fetched
const ALLOWED = new Set([REPO, `${REPO}.git`, DOCS, XML_NAMESPACE]);
export const isAllowedAddress = (a) => ALLOWED.has(a);

export const INSTALL = [
  { id: 'clone', text: `git clone ${REPO}.git` },
  { id: 'cd', text: 'cd umwayi-os' },
  { id: 'pip', text: 'pip install -e .' },
];
export const FIRST = [
  { id: 'bundle', text: 'umwayi memory bundle', what: 'Build the context bundle for an AI helper. Private paths are left out.' },
  { id: 'queue', text: 'umwayi queue add --kind task "Write the spec"', what: 'Put a task in the queue.' },
  { id: 'check', text: `umwayi check '{"type": "payment", "amount": 5}'`, what: 'Ask the rules. A payment gets the answer No.' },
  { id: 'verify', text: 'umwayi logbook verify', what: 'Check that nobody edited the logbook.' },
];
// Devpost and the demo video have no address yet. They stay text, marked "link to come", until the owner supplies them.
export const LINKS = [
  { id: 'repo', name: 'Repo', href: REPO, note: 'The code, the specs and the tests.' },
  { id: 'docs', name: 'Docs', href: DOCS, note: 'One page for each part.' },
  { id: 'devpost', name: 'Devpost', href: null, note: 'link to come' },
  { id: 'demo', name: 'Demo video', href: null, note: 'link to come' },
];

const num = (v) => (Number.isFinite(v) ? String(v) : 'unknown');
// The four values of the strip. counts is a snapshot (or the sample); sample says which. A part that cannot be read is unknown.
export function statusStrip(counts, { sample, date }) {
  const c = counts || {};
  const tag = sample ? 'sample' : `as of ${date}`;
  const days = c.budget && Array.isArray(c.budget.days) ? c.budget.days : null;
  const last = days && days.length ? days[days.length - 1].used_uu : null;
  return [
    { id: 'killswitch', name: 'Kill switch', value: c.kill_switch === undefined ? 'unknown' : describe('killswitch', { kill_switch: c.kill_switch }), tag },
    { id: 'budget', name: 'Budget used today', value: Number.isFinite(last) ? `${last} UU` : 'unknown', tag },
    { id: 'queue', name: 'Queue open', value: c.queue ? num(c.queue.open) : 'unknown', tag },
    { id: 'logbook', name: 'Logbook chain', value: c.logbook && Number.isFinite(c.logbook.chain_length) ? `${c.logbook.chain_length} linked entries` : 'unknown', tag },
  ];
}
