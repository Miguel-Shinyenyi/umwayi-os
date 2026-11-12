// UI.6 (tests first): what the server sends. The home text and the list of the eleven stations are rendered on the server, so they
// are in the HTML before any script runs and with JavaScript off the page is List (12.R17.3, 12.R16.1). These tests render the same
// components the server renders (react-dom/server) and need no build, no browser and no network.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { Home } from '../app/home.js';
import { Document } from '../app/document.js';
import { STATIONS } from '../../ui/src/stations/meta.js';
import { TITLE, PROMISE, INSTALL, FIRST, LINKS, REPO, DOCS } from '../../ui/src/data/home.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const html = renderToStaticMarkup(h(Home));
const strip = (s) => s.replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
const section = (id) => new RegExp(`<(?:section|ul|ol|nav|div|header)[^>]*\\bid="${id}"[^>]*>([\\s\\S]*?)</(?:section|ul|ol|nav|div|header)>`).exec(html)?.[1] ?? '';

test('the home text is in the HTML the server renders: title, promise, status strip, install and first commands, links', () => {
  assert.match(html, new RegExp(`<h1>${TITLE}</h1>`));
  assert.ok(html.includes(strip(PROMISE).replace(/'/g, '&#x27;')) || strip(html).includes(PROMISE), 'the promise is missing');
  for (const c of [...INSTALL, ...FIRST]) assert.ok(strip(html).includes(c.text), `missing command: ${c.text}`);
  for (const l of LINKS) assert.ok(strip(html).includes(l.name), `missing link: ${l.name}`);
  assert.deepEqual([...html.matchAll(/<li[^>]*data-strip="([a-z]+)"/g)].map((m) => m[1]), ['killswitch', 'budget', 'queue', 'logbook']);
});

test('the list of the eleven stations is in the server HTML, in the order of the keyboard, with the same words as the stations', () => {
  const ul = /<ul[^>]*id="station-list"[^>]*>([\s\S]*?)<\/ul>/.exec(html)?.[1] ?? '';
  const items = [...ul.matchAll(/<li[^>]*data-station="([a-z]+)"[^>]*>([\s\S]*?)<\/li>/g)];
  assert.deepEqual(items.map((m) => m[1]), STATIONS.map((s) => s.id));
  assert.equal(items.length, 11);
  items.forEach((m, i) => {
    const text = strip(m[2]);
    assert.ok(text.includes(STATIONS[i].name), STATIONS[i].id);
    assert.ok(text.includes(STATIONS[i].lines[0]) && text.includes(STATIONS[i].lines[1]), `${STATIONS[i].id} lines`);
    assert.ok(text.includes(STATIONS[i].command), `${STATIONS[i].id} command`);
  });
});

test('the list is not hidden and the page is List in its HTML, so with JavaScript off the site shows List', () => {
  assert.ok(!/<section[^>]*id="list-view"[^>]*\bhidden\b/.test(html), 'the list is hidden in the HTML');
  const doc = renderToStaticMarkup(h(Document, null, h('main')));
  assert.match(doc, /<html[^>]*\blang="en"/);
  assert.match(doc, /<html[^>]*\bdata-tier="list"/);
  assert.ok(!/data-js/.test(doc), 'data-js is set by the script, never by the server');
});

test('every sample value says so: the server sends the status strip with sample, and the sample label and footer', () => {
  for (const m of html.matchAll(/<li[^>]*data-strip="[a-z]+"[^>]*>([\s\S]*?)<\/li>/g)) assert.match(m[1], /<span class="t">sample<\/span>/);
  assert.match(html, /<p id="sample-tag">sample<\/p>/);
  assert.match(html, /<p id="foot-note">A sample world\./);
});

test('a visitor can open a snapshot file of their own, read in the browser: one file input for json, no form, no upload (12.R17.6, changed in UI.3)', () => {
  const inputs = [...html.matchAll(/<input\b([^>]*)>/g)].map((m) => m[1]);
  assert.equal(inputs.length, 1, 'one input, the file picker');
  assert.match(inputs[0], /type="file"/);
  assert.match(inputs[0], /id="snapshot-file"/);
  assert.match(inputs[0], /accept="\.json,application\/json"/);
  assert.match(inputs[0], /\bhidden\b/);
  assert.ok(!/multiple|capture|webkitdirectory|name=/.test(inputs[0]), inputs[0]);
  assert.ok(!/<form\b|action=|method=|formaction/i.test(html), 'nothing is submitted');
  assert.match(html, /id="snapshot-open"/);
  assert.match(html, /id="snapshot-msg"[^>]*role="status"/);
  assert.match(html, /It is not uploaded, sent or kept\./);
});

test('Devpost and the demo video are text marked link to come, and the only anchors are Repo and Docs with noopener and noreferrer', () => {
  const anchors = [...html.matchAll(/<a\b([^>]*)>([^<]*)<\/a>/g)];
  assert.deepEqual(anchors.map((m) => m[2]), ['Repo', 'Docs']);
  for (const m of anchors) {
    assert.match(m[1], /rel="noopener noreferrer"/);
    assert.ok([REPO, DOCS].some((u) => m[1].includes(`href="${u}"`)), m[1]);
  }
  assert.equal([...html.matchAll(/data-placeholder/g)].length, 2);
  assert.ok(/Devpost[\s\S]*?link to come/.test(html) && /Demo video[\s\S]*?link to come/.test(html));
});

test('seven Copy buttons, each for the text of its command, and no clipboard call in the markup', () => {
  const copies = [...html.matchAll(/data-copy="(cmd-[a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(copies, [...INSTALL, ...FIRST].map((c) => `cmd-${c.id}`));
  for (const id of copies) assert.ok(html.includes(`id="${id}"`), id);
  assert.ok(!/clipboard|onclick|onClick/i.test(html));
});

test('the switch is List and Standard, with no High on this site yet (UI.7), and the page has the scene elements the shared script joins to', () => {
  const sw = /<div[^>]*id="tiers"[^>]*>([\s\S]*?)<\/div>/.exec(html)?.[1] ?? '';
  assert.deepEqual([...sw.matchAll(/data-tier="([a-z]+)"/g)].map((m) => m[1]), ['list', 'standard']);
  assert.ok(!/id="list-toggle"/.test(html));
  const labels = /<nav[^>]*id="labels"[^>]*>([\s\S]*?)<\/nav>/.exec(html)?.[1] ?? '';
  assert.deepEqual([...labels.matchAll(/data-station="([a-z]+)"/g)].map((m) => m[1]), STATIONS.map((s) => s.id));
  assert.deepEqual([...labels.matchAll(/data-station="[a-z]+"[^>]*>([^<]*)</g)].map((m) => m[1]), STATIONS.map((s) => s.name));
});

test('every id of the live view page template is in the site page, so the one script that joins the buttons to the picture finds them', () => {
  const template = readFileSync(join(root, 'ui', 'src', 'index.html'), 'utf8');
  const ids = [...new Set([...template.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]))];
  assert.ok(ids.length > 30);
  const mine = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
  for (const id of ids) assert.ok(mine.has(id), `the site page has no #${id}`);
});

test('the site list says the same as the live view page: the same words for all eleven stations', () => {
  const built = readFileSync(join(root, 'ui', 'dist', 'index.html'), 'utf8');
  const words = (s) => strip(s.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();
  const items = (text) => [...(/<ul[^>]*id="station-list"[^>]*>([\s\S]*?)<\/ul>/.exec(text)?.[1] ?? '').matchAll(/<li[^>]*>([\s\S]*?)<\/li>/g)].map((m) => words(m[1]));
  assert.deepEqual(items(html), items(built));
  const stripWords = (text) => [...text.matchAll(/<li[^>]*data-strip="[a-z]+"[^>]*>([\s\S]*?)<\/li>/g)].map((m) => words(m[1]));
  assert.deepEqual(stripWords(html), stripWords(built));
});

test('the server HTML loads nothing: no script, link, image, frame, form or style attribute, and no address but the repo and its docs', () => {
  assert.ok(!/<(script|link|img|iframe|object|embed|form|audio|video|source|base)\b/i.test(html));
  assert.ok(!/\sstyle=/.test(html), 'an inline style attribute would need unsafe-inline in the policy');
  const urls = [...html.matchAll(/https?:\/\/[^\s"'<>)]*/g)].map((m) => m[0]);
  for (const u of urls) assert.ok([REPO, `${REPO}.git`, DOCS].includes(u), `an address: ${u}`);
});

test('no em dash in the rendered page', () => {
  assert.ok(!html.includes('\u2014'));
});

import { SCENE_LABEL } from '../app/home.js';
test('the label on the canvas is the live view page label, word for word', () => {
  const template = readFileSync(join(root, 'ui', 'src', 'index.html'), 'utf8');
  const label = /<canvas[^>]*aria-label="([^"]*)"/.exec(template)?.[1];
  assert.equal(SCENE_LABEL, label);
});

test('the owner checks panel is in the server HTML, hidden, with the notice and the rule; its steps are built in the browser, so the server sends no input of it (UI.4)', () => {
  assert.match(html, /<section class="home" id="checks"[^>]*\bhidden(="")?/);
  assert.ok(html.includes('These notes are lost when you close this page. Export them first.'));
  assert.ok(html.includes('Record field names, exit codes and version strings, never a value.'));
  for (const id of ['checks-open', 'checks-open-list', 'checks-list', 'checks-export-btn', 'checks-copy', 'checks-download', 'checks-close', 'checks-export', 'checks-status', 'checks-copy-only']) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.match(html, /<textarea[^>]*id="checks-export"[^>]*readOnly=""|<textarea[^>]*readonly/i);
  assert.equal([...html.matchAll(/<input\b/g)].length, 1, 'the snapshot file picker is the only input the server sends');
  assert.ok(!/localStorage|sessionStorage|indexedDB|cookie/i.test(html.replace(/cookie-free/g, '')), 'no storage in the server HTML');
});
