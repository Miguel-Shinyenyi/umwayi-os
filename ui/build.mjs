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
  write: false, legalComments: 'inline', logLevel: 'warning',
});
// nothing inside the script may end the script element early
const script = bundle.outputFiles[0].text.replace(/<\/script/gi, '<\\/script').replace(/<!--/g, '<\\!--');
const css = (await transform(readFileSync(join(root, 'src/style.css'), 'utf8'), { loader: 'css', minify: true })).code;

// W6.9: the old policy plus connect-src 'self' (requests to the origin the page came from, which is `umwayi serve`), and nothing else
const csp = [
  "default-src 'none'", `script-src '${cspHash(script)}'`, `style-src '${cspHash(css)}'`, 'img-src data:', "base-uri 'none'", "form-action 'none'", "connect-src 'self'",
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

// W2: the command map, a second page. It has no script at all (the groups open and close with the browser's own details element),
// so its policy has no script-src, no connect-src and no img-src: default-src 'none' covers them. Its words come from
// src/data/cli-map.json, which ui/tools/cli_map.py writes from the real argparse tree.
const cliMap = JSON.parse(readFileSync(join(root, 'src/data/cli-map.json'), 'utf8'));
const NONE = 'no help line yet';
const countNodes = (nodes) => nodes.reduce((a, n) => { const c = countNodes(n.children); return { groups: a.groups + c.groups + (n.children.length ? 1 : 0), commands: a.commands + c.commands + (n.children.length ? 0 : 1) }; }, { groups: 0, commands: 0 });
const what = (n) => (n.line ? `<span class="what">${escapeHtml(n.line)}</span>` : `<span class="what none">${NONE}</span>`);
const branch = (nodes, pad) => `${pad}<ul>\n${nodes.map((n) => {
  const head = `<span class="name">${escapeHtml(n.name)}</span>${what(n)}`;
  if (!n.children.length) return `${pad}  <li data-path="${escapeHtml(n.path.join(' '))}"><span class="row">${head}</span></li>`;
  return `${pad}  <li data-path="${escapeHtml(n.path.join(' '))}"><details><summary class="row">${head}</summary>\n${branch(n.children, pad + '    ')}\n${pad}  </details></li>`;
}).join('\n')}\n${pad}</ul>`;
const mapCss = (await transform(readFileSync(join(root, 'src/cli-map.css'), 'utf8'), { loader: 'css', minify: true })).code;
const mapCsp = ["default-src 'none'", `style-src '${cspHash(mapCss)}'`, "base-uri 'none'", "form-action 'none'"].join('; ');
const total = countNodes(cliMap.children);
let mapHtml = readFileSync(join(root, 'src/cli-map.html'), 'utf8')
  .replace('<!--@csp-->', `<meta http-equiv="Content-Security-Policy" content="${mapCsp}">`)
  .replace('<!--@style-->', () => mapCss)
  .replace('<!--@program-->', () => escapeHtml(cliMap.program))
  .replace('<!--@tree-->', () => branch(cliMap.children, '    '))
  .replace('<!--@counts-->', () => `${total.groups} groups and ${total.commands} commands.`);
if (/<!--@/.test(mapHtml)) throw new Error('a placeholder was not replaced in the command map');
writeFileSync(join(dist, 'cli-map.html'), mapHtml);

// W8 slice: the progress page, a third page. No script, so the policy is the map's: default-src 'none' plus the style hash.
// W22: it is written to ui/dist/progress.html on every build and is not committed. Its words come from three files of the repo, read here and nowhere else: docs/status-log.md, docs/KNOWN-LIMITS.md and
// .kiro/specs/umwayi-os/tasks.md. The date is the day of the build (UMWAYI_BUILD_DATE sets it for a repeatable build).
const progress = await import(pathToFileURL(join(root, 'src/data/progress.js')).href);
const repo = join(root, '..');
const progressSources = { 'docs/status-log.md': null, 'docs/KNOWN-LIMITS.md': null, '.kiro/specs/umwayi-os/tasks.md': null };
for (const name of Object.keys(progressSources)) progressSources[name] = readFileSync(join(repo, name));
const progressModel = progress.model({
  statusLog: progressSources['docs/status-log.md'].toString('utf8'),
  limits: progressSources['docs/KNOWN-LIMITS.md'].toString('utf8'),
  tasks: progressSources['.kiro/specs/umwayi-os/tasks.md'].toString('utf8'),
});
const parts = progress.render(progressModel, process.env.UMWAYI_BUILD_DATE || new Date().toISOString().slice(0, 10));
const progressCss = (await transform(readFileSync(join(root, 'src/progress.css'), 'utf8'), { loader: 'css', minify: true })).code;
const progressCsp = ["default-src 'none'", `style-src '${cspHash(progressCss)}'`, "base-uri 'none'", "form-action 'none'"].join('; ');
const progressHtml = readFileSync(join(root, 'src/progress.html'), 'utf8')
  .replace('<!--@csp-->', `<meta http-equiv="Content-Security-Policy" content="${progressCsp}">`)
  .replace('<!--@style-->', () => progressCss)
  .replace('<!--@totals-->', () => escapeHtml(parts.totals))
  .replace('<!--@groups-->', () => parts.groups)
  .replace('<!--@rows-->', () => parts.rows)
  .replace('<!--@limit-->', () => parts.limit)
  .replace('<!--@date-->', () => parts.date);
if (/<!--@/.test(progressHtml)) throw new Error('a placeholder was not replaced in the progress page');
writeFileSync(join(dist, 'progress.html'), progressHtml);

// what the pages were built from: tests recompute these without npm. The progress page is not in it: it is built here from the
// docs and is not committed (ui/dist/progress.html is in .gitignore), so a pull request that adds a status row changes no committed file
const inputs = ['build.mjs', 'package.json', 'package-lock.json', ...walk(join(root, 'src')).map((f) => relative(root, f).split('\\').join('/'))];
const files = {};
for (const name of [...new Set(inputs)].sort()) files[name] = sha256(readFileSync(join(root, name)));
writeFileSync(join(dist, 'build.json'), JSON.stringify({ files, page: sha256(readFileSync(join(dist, 'index.html'))), cliMapPage: sha256(readFileSync(join(dist, 'cli-map.html'))) }, null, 2) + '\n');
console.log(`built ui/dist/index.html (${Math.round(html.length / 1024)} KB)`);
