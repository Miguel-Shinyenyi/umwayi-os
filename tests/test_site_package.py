"""The layer 12 public site package (tasks.md UI.6, requirements 12.R16 to 12.R18, 12.R10.2).

Checks, on the repo and on temporary copies with a planted fault each:
- site/package.json has exact versions (next, react, react-dom, three) and no range, and no install script;
- site/package-lock.json is lockfile version 3 and every package has a sha512 and comes from registry.npmjs.org;
- no analytics, tracking, speed insights, error reporting or third party script package in the package file or the lockfile;
- site/.gitignore keeps node_modules/ and .next/ out;
- the source loads nothing from outside: no next/font, next/script, next/image, no remote script, font, image or style, no
  address but the repo and its docs folder (site/high-assets.json, the High licence listing, is checked by
  tests/test_site_assets.py instead), no request call, no storage, no cookie, no API route, no server action;
- the site has no copy of ui/src: no file of it repeats a file of ui/src, and it reaches the scene only through the shared
  modules (site/app/scene.js -> ui/src/boot.js and ui/src/app.js -> ui/src/scene.js), which the live view's main.js uses too;
- next.config.mjs sends a Content-Security-Policy for the site's own origin only, no referrer, no sniffing and no framing,
  and the build runs with Next.js telemetry off;
- nothing of Vercel is in the repo (no vercel.json, no .vercel folder, no deploy script): the owner deploys;
- no em dash in anything under site/.
Standard library only; no npm, no node, no browser, no network. The repo is never changed by the planted faults.
The site has no build record like ui/dist/build.json: Next.js writes .next, which is not committed (see site/README.md).
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EM_DASH = "\u2014"
PINS = {"next": "16.4.6", "react": "19.3.1", "react-dom": "19.3.1", "three": "0.187.0"}
EXACT = re.compile(r"^\d+\.\d+\.\d+$")
REPO_URL = "https://github.com/Miguel-Shinyenyi/umwayi-os"
ALLOWED_URLS = {REPO_URL, REPO_URL + ".git", REPO_URL + "/tree/main/docs"}
SKIP_DIRS = {"node_modules", ".next"}
# the High asset listing names where each photograph came from and its licence; it is not served and loads nothing, and
# tests/test_site_assets.py allows only the Poly Haven and Creative Commons addresses in it
LISTING = "site/high-assets.json"
LIFECYCLE = ("preinstall", "install", "postinstall", "prepublish", "preprepare", "prepare", "postprepare")
# words in a package name that mean analytics, tracking, error reporting or a third party script
TRACKERS = ("analytics", "speed-insights", "@vercel/", "third-parties", "gtag", "segment", "mixpanel", "amplitude", "posthog",
            "plausible", "fathom", "hotjar", "sentry", "datadog", "logrocket", "fullstory", "heap-", "matomo", "umami",
            "clarity", "newrelic", "rollbar", "bugsnag", "tracking", "telemetry", "react-ga", "partytown")
# text that would load something from outside or keep something; none may be in the site's source
FORBIDDEN = ("next/font", "next/script", "next/image", "@vercel/", "@next/third-parties", "fetch(", "XMLHttpRequest", "sendBeacon",
             "WebSocket", "EventSource", "localStorage", "sessionStorage", "indexedDB", "document.cookie", "next/headers",
             "'use server'", '"use server"', "@import", "googleapis", "gstatic", "gtag", "dataLayer", "importScripts")
REMOTE_TAG = re.compile(r"<(?:script|link|img|iframe)\b[^>]*\b(?:src|href)\s*=\s*[\"']https?://", re.I)
REMOTE_PROP = re.compile(r"\b(?:src|href)\s*:\s*[\"']https?://", re.I)
ANY_URL = re.compile(r"https?://[^\s\"'<>)\\`]*")
SOURCE_SUFFIXES = {".js", ".mjs", ".jsx", ".css", ".json", ".md", ".ts", ".tsx", ".html"}
CHAIN = (
    ("site/app/scene.js", "ui/src/boot.js"),
    ("site/app/scene.js", "ui/src/app.js"),
    ("ui/src/app.js", "./scene.js"),
    ("ui/src/main.js", "./boot.js"),
    ("ui/src/main.js", "./app.js"),
)


def site_files(root: Path) -> list:
    """Every file under site/ except what npm and next write (node_modules, .next), as paths."""
    base = root / "site"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.relative_to(base).parts))


def source_files(root: Path) -> list:
    """The site's own source (not its tests, not the lockfile): what the rules about requests and addresses read."""
    base = root / "site"
    out = []
    for p in site_files(root):
        rel = p.relative_to(base)
        if rel.parts[0] == "test" or p.name == "package-lock.json" or p.suffix not in SOURCE_SUFFIXES:
            continue
        out.append(p)
    return out


def csp_items(config_text: str) -> list:
    m = re.search(r"const csp = \[(.*?)\]\.join\(", config_text, re.S)
    return re.findall(r'"([^"]*)"', m.group(1)) if m else []


def check_package(root: Path) -> list:
    site = root / "site"
    problems = []
    pkg_path = site / "package.json"
    if not pkg_path.is_file():
        return ["site/package.json is missing"]
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {}), **pkg.get("optionalDependencies", {})}
    if sorted(deps) != sorted(PINS):
        problems.append(f"site/package.json has the packages {sorted(deps)}, not {sorted(PINS)}")
    for name, version in deps.items():
        if not EXACT.match(version):
            problems.append(f"site/package.json: {name} is {version!r}, not an exact version")
        elif PINS.get(name) not in (None, version):
            problems.append(f"site/package.json: {name} is {version}, not the pinned {PINS[name]}")
    for name in deps:
        if any(t in name for t in TRACKERS):
            problems.append(f"site/package.json: {name} is an analytics or tracking package")
    for name in pkg.get("scripts", {}):
        if name in LIFECYCLE:
            problems.append(f"site/package.json: the script {name} would run on install")
    scripts = pkg.get("scripts", {})
    for name in ("dev", "build", "start"):
        if "scripts/next.mjs" not in scripts.get(name, ""):
            problems.append(f"site/package.json: {name} does not run through scripts/next.mjs (telemetry off)")
    lock_path = site / "package-lock.json"
    if not lock_path.is_file():
        problems.append("site/package-lock.json is missing")
    else:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if lock.get("lockfileVersion") != 3:
            problems.append("site/package-lock.json is not lockfile version 3")
        for name, entry in lock.get("packages", {}).items():
            if name == "":
                continue
            if not str(entry.get("integrity", "")).startswith("sha512-"):
                problems.append(f"site/package-lock.json: {name} has no sha512 integrity")
            if not str(entry.get("resolved", "")).startswith("https://registry.npmjs.org/"):
                problems.append(f"site/package-lock.json: {name} does not come from registry.npmjs.org")
            if any(t in name for t in TRACKERS):
                problems.append(f"site/package-lock.json: {name} is an analytics or tracking package")
        root_deps = {**lock.get("packages", {}).get("", {}).get("dependencies", {}),
                     **lock.get("packages", {}).get("", {}).get("devDependencies", {})}
        if root_deps != {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}:
            problems.append("site/package-lock.json does not list the same packages as site/package.json")
    inner = site / ".gitignore"
    words = inner.read_text(encoding="utf-8").split() if inner.is_file() else []
    for need in ("node_modules/", ".next/"):
        if need not in words:
            problems.append(f"site/.gitignore does not keep {need} out")
    for name in ("README.md", "next.config.mjs", "scripts/next.mjs", "app/layout.js", "app/page.js", "app/scene.js"):
        if not (site / name).is_file():
            problems.append(f"site/{name} is missing")
    return problems


def check_source(root: Path) -> list:
    problems = []
    for p in source_files(root):
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8")
        if p.name == "package.json":
            continue
        for token in FORBIDDEN:
            if token in text and not (p.suffix == ".md"):
                problems.append(f"{rel} contains {token!r}")
        if REMOTE_TAG.search(text) or REMOTE_PROP.search(text):
            problems.append(f"{rel} loads a script, link, image or frame from an address")
        if p.suffix != ".md" and rel != LISTING:
            for url in sorted(set(ANY_URL.findall(text))):
                if url not in ALLOWED_URLS:
                    problems.append(f"{rel} contains the address {url}, which is not listed")
        if re.search(r"(?<![\w$])url\(\s*['\"]?https?:", text, re.I):
            problems.append(f"{rel} has a url() with a remote address")
    names = {p.relative_to(root / "site").as_posix() for p in site_files(root)}
    for n in sorted(names):
        parts = n.split("/")
        if parts[0] == "app" and parts[-1] in ("route.js", "route.ts", "route.mjs"):
            problems.append(f"site/{n} is an API route; the site takes no data")
        if parts[0] in ("middleware.js", "proxy.js", "middleware.ts", "proxy.ts"):
            problems.append(f"site/{n}: nothing runs per visit (the page is static)")
    for n in ("vercel.json", ".vercel", "now.json"):
        if (root / n).exists() or (root / "site" / n).exists():
            problems.append(f"{n} is in the repo; the owner deploys, nothing here touches Vercel")
    return problems


def check_shared(root: Path) -> list:
    """The site has no copy of ui/src and reaches the scene only through the shared modules."""
    problems = []
    for src, needle in CHAIN:
        p = root / src
        if not p.is_file():
            problems.append(f"{src} is missing")
        elif needle not in p.read_text(encoding="utf-8"):
            problems.append(f"{src} does not import {needle}")
    scene = root / "ui" / "src" / "scene.js"
    if not scene.is_file() or "export function createScene" not in scene.read_text(encoding="utf-8"):
        problems.append("ui/src/scene.js does not export createScene")
    ui_src = root / "ui" / "src"
    whole = {}
    lines = set()
    if ui_src.is_dir():
        for p in ui_src.rglob("*"):
            if p.is_file():
                try:
                    text = p.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                whole[text] = p.relative_to(ui_src).as_posix()
                lines |= {ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 40}
    for p in site_files(root):
        if p.suffix not in SOURCE_SUFFIXES or p.name == "package-lock.json":
            continue
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(root).as_posix()
        if len(text) > 40 and text in whole:
            problems.append(f"{rel} is a copy of ui/src/{whole[text]}")
            continue
        shared = [ln for ln in {ln.strip() for ln in text.splitlines()} if ln in lines]
        if len(shared) >= 3:
            problems.append(f"{rel} repeats {len(shared)} lines of ui/src; use the shared module")
    return problems


def check_config(root: Path) -> list:
    cfg = root / "site" / "next.config.mjs"
    if not cfg.is_file():
        return ["site/next.config.mjs is missing"]
    text = cfg.read_text(encoding="utf-8")
    problems = []
    items = csp_items(text)
    if not items:
        return ["site/next.config.mjs has no Content-Security-Policy list"]
    directives = {i.split()[0]: i.split()[1:] for i in items}
    if directives.get("default-src") != ["'self'"]:
        problems.append("the Content-Security-Policy does not start from default-src 'self'")
    for need, want in (("object-src", ["'none'"]), ("base-uri", ["'self'"]), ("form-action", ["'self'"]), ("frame-ancestors", ["'none'"])):
        if directives.get(need) != want:
            problems.append(f"the Content-Security-Policy lacks {need} {' '.join(want)}")
    for name, values in directives.items():
        for v in values:
            if re.match(r"^(https?:|wss?:|\*|//)", v) or "." in v and not v.startswith("'"):
                problems.append(f"the Content-Security-Policy allows {v} in {name}, which is not the site's own origin")
            if v == "'unsafe-eval'":
                problems.append("the Content-Security-Policy allows unsafe-eval")
            if v == "'unsafe-inline'" and name != "script-src":
                problems.append(f"the Content-Security-Policy allows unsafe-inline in {name}; only script-src needs it")
    for key, value in (("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY")):
        if not re.search(r"key:\s*['\"]" + re.escape(key) + r"['\"],\s*value:\s*['\"]" + re.escape(value) + r"['\"]", text):
            problems.append(f"site/next.config.mjs does not send {key}: {value}")
    if not re.search(r"key:\s*['\"]Content-Security-Policy['\"],\s*value:\s*csp\b", text):
        problems.append("site/next.config.mjs does not send the Content-Security-Policy")
    if "Permissions-Policy" not in text or "clipboard-write=(self)" not in text:
        problems.append("site/next.config.mjs does not send a Permissions-Policy that allows only clipboard-write")
    if not re.search(r"turbopack\s*:\s*\{[^}]*\broot\b", text, re.S):
        problems.append("site/next.config.mjs does not set the build root to the repo, so the shared scene cannot be imported")
    if not re.search(r"\bresolveAlias\s*:\s*\{[^}]*\bthree\b", text):
        problems.append("site/next.config.mjs does not make three.js resolve to the site's own copy")
    if re.search(r"remotePatterns|assetPrefix|basePath|rewrites|redirects", text):
        problems.append("site/next.config.mjs points the site at another host")
    runner = root / "site" / "scripts" / "next.mjs"
    if not runner.is_file() or not re.search(r"NEXT_TELEMETRY_DISABLED\s*:\s*['\"]1['\"]", runner.read_text(encoding="utf-8")):
        problems.append("site/scripts/next.mjs does not set NEXT_TELEMETRY_DISABLED=1")
    return problems


def check_no_em_dash(root: Path) -> list:
    problems = []
    for p in site_files(root):
        if p.name == "package-lock.json":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if EM_DASH in text:
            problems.append(f"{p.relative_to(root).as_posix()}: an em dash")
    return problems


def check(root: Path) -> list:
    """Every problem of the site package and source under root, as text. Empty when all is well."""
    root = Path(root).resolve()
    return check_package(root) + check_source(root) + check_shared(root) + check_config(root) + check_no_em_dash(root)


class RepoTests(unittest.TestCase):
    def test_the_site_package_and_source_have_no_problem(self):
        self.assertEqual(check(REPO), [])

    def test_the_site_is_a_folder_outside_the_umwayi_package(self):
        self.assertTrue((REPO / "site" / "package.json").is_file())
        self.assertFalse((REPO / "umwayi" / "site").exists())

    def test_the_core_package_imports_nothing_from_ui_or_site(self):
        for p in sorted((REPO / "umwayi").rglob("*.py")):
            text = p.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\s*(?:from|import)\s+(?:ui|site)\b", p.name)

    def test_the_live_view_and_the_site_use_the_same_scene_module(self):
        # one entry builds the scene; both pages reach it through boot.js, and the live view bundles it into its one file
        self.assertIn("./boot.js", (REPO / "ui" / "src" / "main.js").read_text(encoding="utf-8"))
        self.assertIn("ui/src/boot.js", (REPO / "site" / "app" / "scene.js").read_text(encoding="utf-8"))
        builders = [p.relative_to(REPO).as_posix() for p in (REPO / "ui" / "src").rglob("*.js")
                    if re.search(r"=\s*buildWorld\(|=\s*createStage\(", p.read_text(encoding="utf-8"))]
        self.assertEqual(builders, ["ui/src/scene.js"])


class PlantedFaultTests(unittest.TestCase):
    """Each planted fault, in a temporary copy, is found."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-site-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        ignore = shutil.ignore_patterns("node_modules", ".next")
        shutil.copytree(REPO / "site", self.root / "site", ignore=ignore)
        (self.root / "ui").mkdir()
        shutil.copytree(REPO / "ui" / "src", self.root / "ui" / "src")

    def edit(self, rel: str, fn):
        p = self.root / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")

    def write(self, rel: str, text: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def assert_found(self, fragment: str):
        problems = check(self.root)
        self.assertTrue(any(fragment in x for x in problems), f"{fragment!r} not in {problems}")

    def test_the_copy_is_clean_before_any_plant(self):
        self.assertEqual(check(self.root), [])

    # package and lockfile
    def test_a_version_with_a_range(self):
        self.edit("site/package.json", lambda t: t.replace('"16.4.6"', '"^16.4.6"'))
        self.assert_found("not an exact version")

    def test_another_version_than_the_pinned_one(self):
        self.edit("site/package.json", lambda t: t.replace('"0.187.0"', '"0.187.1"'))
        self.assert_found("not the pinned 0.187.0")

    def test_a_package_added_that_is_not_in_the_list(self):
        self.edit("site/package.json", lambda t: t.replace('"three": "0.187.0"', '"three": "0.187.0", "left-pad": "1.3.0"'))
        self.assert_found("has the packages")

    def test_an_analytics_package(self):
        for name in ("@vercel/analytics", "@vercel/speed-insights", "@next/third-parties", "posthog-js"):
            with self.subTest(name=name):
                self.setUp()
                self.edit("site/package.json", lambda t: t.replace('"three": "0.187.0"', '"three": "0.187.0", "' + name + '": "1.0.0"'))
                self.assert_found("analytics or tracking package")

    def test_an_analytics_package_in_the_lockfile_only(self):
        def plant(t):
            lock = json.loads(t)
            lock["packages"]["node_modules/@vercel/analytics"] = {
                "version": "1.0.0", "resolved": "https://registry.npmjs.org/@vercel/analytics/-/analytics-1.0.0.tgz", "integrity": "sha512-abc"}
            return json.dumps(lock, indent=2)
        self.edit("site/package-lock.json", plant)
        self.assert_found("site/package-lock.json: node_modules/@vercel/analytics is an analytics")

    def test_a_lockfile_entry_without_sha512(self):
        def drop(t):
            lock = json.loads(t)
            name = next(k for k in lock["packages"] if k)
            lock["packages"][name]["integrity"] = "sha1-abc"
            return json.dumps(lock, indent=2)
        self.edit("site/package-lock.json", drop)
        self.assert_found("has no sha512 integrity")

    def test_a_lockfile_entry_from_another_registry(self):
        def move(t):
            lock = json.loads(t)
            name = next(k for k in lock["packages"] if k)
            lock["packages"][name]["resolved"] = "https://example.invalid/x.tgz"
            return json.dumps(lock, indent=2)
        self.edit("site/package-lock.json", move)
        self.assert_found("does not come from registry.npmjs.org")

    def test_a_lockfile_that_does_not_match_the_package_file(self):
        def skew(t):
            lock = json.loads(t)
            lock["packages"][""]["dependencies"]["next"] = "16.4.5"
            return json.dumps(lock, indent=2)
        self.edit("site/package-lock.json", skew)
        self.assert_found("does not list the same packages")

    def test_an_install_script(self):
        self.edit("site/package.json", lambda t: t.replace('"scripts": {', '"scripts": {\n    "postinstall": "node x.js",'))
        self.assert_found("would run on install")

    def test_a_build_script_that_skips_the_telemetry_wrapper(self):
        self.edit("site/package.json", lambda t: t.replace('"build": "node scripts/next.mjs build"', '"build": "next build"'))
        self.assert_found("build does not run through scripts/next.mjs")

    def test_telemetry_not_switched_off(self):
        self.edit("site/scripts/next.mjs", lambda t: t.replace("NEXT_TELEMETRY_DISABLED: '1'", "NEXT_TELEMETRY_DISABLED: '0'"))
        self.assert_found("does not set NEXT_TELEMETRY_DISABLED=1")

    def test_a_missing_gitignore_entry(self):
        self.edit("site/.gitignore", lambda t: t.replace(".next/", ""))
        self.assert_found("does not keep .next/ out")

    # nothing loaded from outside
    def test_a_google_font(self):
        self.write("site/app/font.js", "import { Inter } from 'next/font/google';\n")
        self.assert_found("contains 'next/font'")

    def test_a_script_component(self):
        self.write("site/app/ga.js", "import Script from 'next/script';\n")
        self.assert_found("contains 'next/script'")

    def test_a_remote_script_tag_and_a_remote_stylesheet(self):
        self.write("site/app/tag.js", "export const a = '<script src=\"https://cdn.example.invalid/a.js\"></script>';\n")
        self.assert_found("loads a script, link, image or frame from an address")
        self.setUp()
        self.write("site/app/tag.js", "export const a = { href: 'https://fonts.example.invalid/a.css' };\n")
        self.assert_found("loads a script, link, image or frame from an address")

    def test_an_address_that_is_not_listed(self):
        self.edit("site/app/home.js", lambda t: t + "\nexport const x = 'https://example.invalid/a';\n")
        self.assert_found("https://example.invalid/a")

    def test_an_asset_address_outside_the_listing(self):
        # the listing may name Poly Haven; the code may not
        self.edit("site/app/home.js", lambda t: t + "\nexport const x = 'https://dl.polyhaven.org/file/a.jpg';\n")
        self.assert_found("https://dl.polyhaven.org/file/a.jpg")

    def test_a_remote_url_function_and_an_import_rule(self):
        self.write("site/app/a.css", "@import 'b.css';\n")
        self.assert_found("contains '@import'")
        self.setUp()
        self.write("site/app/a.css", "a{background:url(https://example.invalid/b.png)}\n")
        self.assert_found("url() with a remote address")

    def test_requests_storage_and_cookies(self):
        for word in ("fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "sessionStorage", "indexedDB", "document.cookie", "WebSocket"):
            with self.subTest(word=word):
                self.setUp()
                self.edit("site/app/scene.js", lambda t: t + f"\nexport const x = {word!r};\n")
                self.assert_found(f"contains {word!r}")

    def test_an_api_route_and_a_server_action_and_a_middleware(self):
        self.write("site/app/api/hint/route.js", "export function POST() {}\n")
        self.assert_found("is an API route")
        self.setUp()
        self.write("site/app/act.js", "'use server';\nexport async function a() {}\n")
        self.assert_found("contains \"'use server'\"")
        self.setUp()
        self.write("site/proxy.js", "export function proxy() {}\n")
        self.assert_found("nothing runs per visit")

    def test_a_vercel_file(self):
        self.write("site/vercel.json", "{}\n")
        self.assert_found("the owner deploys")
        self.setUp()
        self.write("vercel.json", "{}\n")
        self.assert_found("the owner deploys")

    # no copy of ui/src, and the shared chain
    def test_a_file_copied_from_ui_src(self):
        shutil.copy2(self.root / "ui" / "src" / "engine" / "tier.js", self.root / "site" / "app" / "tier.js")
        self.assert_found("is a copy of ui/src/engine/tier.js")

    def test_a_copy_with_a_few_lines_changed(self):
        text = (self.root / "ui" / "src" / "engine" / "tier.js").read_text(encoding="utf-8").replace("Pure:", "Pure here:")
        self.write("site/app/tier.js", text)
        self.assert_found("repeats")

    def test_the_site_scene_does_not_use_the_shared_boot_module(self):
        self.edit("site/app/scene.js", lambda t: t.replace("ui/src/boot.js", "./own-boot.js"))
        self.assert_found("site/app/scene.js does not import ui/src/boot.js")

    def test_the_live_view_stops_using_the_shared_module(self):
        self.edit("ui/src/app.js", lambda t: t.replace("./scene.js", "./scene2.js"))
        self.assert_found("ui/src/app.js does not import ./scene.js")
        self.setUp()
        self.edit("ui/src/main.js", lambda t: t.replace("./boot.js", "./boot2.js"))
        self.assert_found("ui/src/main.js does not import ./boot.js")
        self.setUp()
        self.edit("site/app/scene.js", lambda t: t.replace("ui/src/app.js", "./own-app.js"))
        self.assert_found("site/app/scene.js does not import ui/src/app.js")

    def test_the_scene_module_gone(self):
        self.edit("ui/src/scene.js", lambda t: t.replace("export function createScene", "function createScene"))
        self.assert_found("does not export createScene")

    # headers
    def test_a_policy_without_default_src(self):
        self.edit("site/next.config.mjs", lambda t: t.replace('"default-src \'self\'",', ""))
        self.assert_found("does not start from default-src 'self'")

    def test_a_policy_with_a_remote_host(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("\"font-src 'self'\"", "\"font-src 'self' https://fonts.gstatic.com\""))
        self.assert_found("which is not the site's own origin")

    def test_a_policy_with_a_wildcard(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("\"img-src 'self' data: blob:\"", "\"img-src *\""))
        self.assert_found("which is not the site's own origin")

    def test_a_policy_with_unsafe_inline_in_styles_and_unsafe_eval(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("\"style-src 'self'\"", "\"style-src 'self' 'unsafe-inline'\""))
        self.assert_found("allows unsafe-inline in style-src")
        self.setUp()
        self.edit("site/next.config.mjs", lambda t: t.replace("\"script-src 'self' 'unsafe-inline'\"", "\"script-src 'self' 'unsafe-eval'\""))
        self.assert_found("allows unsafe-eval")

    def test_a_policy_that_is_not_sent(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("{ key: 'Content-Security-Policy', value: csp },", ""))
        self.assert_found("does not send the Content-Security-Policy")

    def test_a_missing_referrer_policy_and_nosniff(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("'no-referrer'", "'origin'"))
        self.assert_found("does not send Referrer-Policy: no-referrer")
        self.setUp()
        self.edit("site/next.config.mjs", lambda t: t.replace("'nosniff'", "'sniff'"))
        self.assert_found("does not send X-Content-Type-Options: nosniff")

    def test_a_missing_build_root_and_alias(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("root: repo,", ""))
        self.assert_found("does not set the build root")
        self.setUp()
        self.edit("site/next.config.mjs", lambda t: t.replace("resolveAlias", "resolveAliasX"))
        self.assert_found("three.js resolve to the site's own copy")

    def test_a_config_that_points_at_another_host(self):
        self.edit("site/next.config.mjs", lambda t: t.replace("reactStrictMode: true,", "reactStrictMode: true, assetPrefix: 'x',"))
        self.assert_found("points the site at another host")

    def test_an_em_dash(self):
        self.edit("site/README.md", lambda t: t + "\nA line " + EM_DASH + " here.\n")
        self.assert_found("site/README.md: an em dash")


class HelperTests(unittest.TestCase):
    def test_csp_items_reads_the_list(self):
        text = "const csp = [\n  \"default-src 'self'\",\n  \"object-src 'none'\",\n].join('; ');"
        self.assertEqual(csp_items(text), ["default-src 'self'", "object-src 'none'"])

    def test_no_list_gives_nothing(self):
        self.assertEqual(csp_items("const x = 1;"), [])


if __name__ == "__main__":
    unittest.main()
