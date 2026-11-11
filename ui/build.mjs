// Builds the one self contained page: ui/dist/index.html, and ui/dist/build.json (what it was built from).
// Run by the owner: npm ci --ignore-scripts, then node build.mjs. umwayi never runs this.
import { build, transform } from 'esbuild';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const sha256 = (data) => createHash('sha256').update(data).digest('hex');
const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const cspHash = (text) => `sha256-${createHash('sha256').update(text, 'utf8').digest('base64')}`;

const walk = (dir) => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));

// the words of the stations make the label buttons and the list view, and the home content makes its sections, so all of it is in
// the page before any script runs
const { STATIONS } = await import(pathToFileURL(join(root, 'src/stations/meta.js')).href);
const home = await import(pathToFileURL(join(root, 'src/data/home.js')).href);
const sample = (await import(pathToFileURL(join(root, 'src/data/sample.js')).href)).SAMPLE;
const labels = STATIONS.map((s) => `    <button type="button" class="label" data-station="${s.id}">${escapeHtml(s.name)}</button>`).join('\n');
const list = STATIONS.map((s) => {
  const note = s.note ? `\n      <p class="note">${escapeHtml(s.note)}</p>` : '';
  return `    <li data-station="${s.id}">
      <p class="state">${s.state === 'built' ? 'Built' : 'Planned'}</p>
      <h3>${escapeHtml(s.name)}</h3>
      <p>${escapeHtml(s.lines[0])}</p>
      <p>${escapeHtml(s.lines[1])}</p>${note}
      <p><code>${escapeHtml(s.command)}</code></p>
    </li>`;
}).join('\n');
const strip = home.statusStrip(sample, { sample: true, date: sample.date }).map((s) => `    <li data-strip="${s.id}"><span class="k">${escapeHtml(s.name)}</span><span class="v">${escapeHtml(s.value)}</span><span class="t">${escapeHtml(s.tag)}</span></li>`).join('\n');
const cmd = (c) => `    <li><code id="cmd-${c.id}">${escapeHtml(c.text)}</code><button type="button" class="btn small" data-copy="cmd-${c.id}" aria-label="Copy: ${escapeHtml(c.text)}">Copy</button>${c.what ? `<p class="what">${escapeHtml(c.what)}</p>` : ''}</li>`;
const install = home.INSTALL.map(cmd).join('\n');
const first = home.FIRST.map(cmd).join('\n');
const links = home.LINKS.map((l) => (l.href
  ? `    <li><a href="${l.href}" rel="noopener noreferrer">${escapeHtml(l.name)}</a><span class="note">${escapeHtml(l.note)}</span></li>`
  : `    <li data-placeholder><span class="name">${escapeHtml(l.name)}</span><span class="note">${escapeHtml(l.note)}</span></li>`)).join('\n');

const bundle = await build({
  entryPoints: [join(root, 'src/main.js')], bundle: true, minify: true, format: 'iife', target: 'es2020',
  write: false, legalComments: 'none', logLevel: 'warning',
});
// nothing inside the script may end the script element early
const script = bundle.outputFiles[0].text.replace(/<\/script/gi, '<\\/script').replace(/<!--/g, '<\\!--');
const css = (await transform(readFileSync(join(root, 'src/style.css'), 'utf8'), { loader: 'css', minify: true })).code;

const csp = [
  "default-src 'none'", `script-src '${cspHash(script)}'`, `style-src '${cspHash(css)}'`, 'img-src data:', "base-uri 'none'", "form-action 'none'",
].join('; ');

let html = readFileSync(join(root, 'src/index.html'), 'utf8');
html = html
  .replace('<!--@csp-->', `<meta http-equiv="Content-Security-Policy" content="${csp}">`)
  .replace('<!--@style-->', () => css)
  .replace('<!--@labels-->', () => labels)
  .replace('<!--@list-->', () => list)
  .replace('<!--@title-->', () => home.TITLE)
  .replace('<!--@promise-->', () => escapeHtml(home.PROMISE))
  .replace('<!--@strip-->', () => strip)
  .replace('<!--@install-->', () => install)
  .replace('<!--@first-->', () => first)
  .replace('<!--@links-->', () => links)
  .replace('<!--@script-->', () => script);
if (/<!--@/.test(html)) throw new Error('a placeholder was not replaced');

const dist = join(root, 'dist');
mkdirSync(dist, { recursive: true });
writeFileSync(join(dist, 'index.html'), html);

// what the page was built from: tests recompute these without npm
const inputs = ['build.mjs', 'package.json', 'package-lock.json', ...walk(join(root, 'src')).map((f) => relative(root, f).split('\\').join('/'))];
const files = {};
for (const name of [...new Set(inputs)].sort()) files[name] = sha256(readFileSync(join(root, name)));
writeFileSync(join(dist, 'build.json'), JSON.stringify({ files, page: sha256(readFileSync(join(dist, 'index.html'))) }, null, 2) + '\n');
console.log(`built ui/dist/index.html (${Math.round(html.length / 1024)} KB)`);
