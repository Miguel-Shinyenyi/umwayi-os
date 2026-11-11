"""The layer 12 package and the built page (tasks.md UI.1.1, requirements 12.R1, 12.R2, 12.R10.2, 12.R10.3).

Checks, on the repo and on temporary copies with a planted fault each:
- ui/package.json has exact versions (three 0.187.0, esbuild 0.28.2) and no range;
- ui/package-lock.json is lockfile version 3 and every package has a sha512 and comes from registry.npmjs.org;
- ui/.gitignore keeps node_modules out and the root .gitignore has the exception that lets ui/dist be committed;
- ui/dist/build.json holds the SHA-256 of every source file, of build.mjs, of package.json, of the lockfile and of the
  page: a source changed without a rebuild, or a page edited by hand, is found without npm;
- the built page makes no request: no script, link, image or other file loaded from anywhere, none of the calls that
  would make one, no storage, and every http:// or https:// string is a named XML namespace, not an address;
- the page carries a Content-Security-Policy that denies everything except its own inline script and style, and the
  hashes in it are the hashes of the page's inline script and style;
- the page is under about 2 MB; its only addresses are the XML namespace name and the listed home links; the Devpost and
  demo video entries are marked placeholders and are not anchors; every Copy button has its command;
- the page holds the 11 buttons over the features, the list view, the home sections, the Calm mode button and the reduced motion rule;
- no em dash in anything under ui/.
Standard library only; no npm, no node, no browser, no network. The repo is never changed by the planted faults.
"""

import base64
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EM_DASH = "\u2014"
PINS = {"three": "0.187.0", "esbuild": "0.28.2"}
EXACT = re.compile(r"^\d+\.\d+\.\d+$")
# XML namespace names three.js carries. They name a vocabulary and are never fetched.
# The home page links (12.R15): the repo and its docs folder, plain anchors the owner clicks, and the clone command's address.
REPO_URL = "https://github.com/Miguel-Shinyenyi/umwayi-os"
ALLOWED_URLS = {"http://www.w3.org/1999/xhtml", REPO_URL, REPO_URL + ".git", REPO_URL + "/tree/main/docs"}
MAX_PAGE_BYTES = 2_000_000  # 12.R1.6: under about 2 MB
STATIONS = ("memory", "rules", "queue", "archive", "logbook", "automation", "helpers", "workflows", "adapters",
            "killswitch", "budget")
# calls and names that would make a request, load a file or keep something; none may be in the built page
FORBIDDEN = ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "import(", "//cdn", "localStorage",
             "sessionStorage", "indexedDB", "document.cookie", "FileLoader", "ImageLoader", "TextureLoader",
             "EventSource", "importScripts", "new Worker", "navigator.serviceWorker")
FORBIDDEN_TAGS = re.compile(r"<(link|img|iframe|object|embed|base|form|audio|video|source|track)\b", re.I)
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
STYLE = re.compile(r"<style\b([^>]*)>(.*?)</style>", re.S | re.I)
# a CSS url(...) that is not a data: address; "getDataURL(" in a script is a method name and is not matched
URL_FN = re.compile(r"(?<![\w$])url\(\s*(?!['\"]?data:)", re.I)
ANY_URL = re.compile(r"https?://[^\s\"'<>)\\]*")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def csp_hash(text: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


def input_files(ui: Path) -> list:
    """Relative names (forward slashes, sorted) of every file build.json covers except the page."""
    names = ["build.mjs", "package.json", "package-lock.json"]
    src = ui / "src"
    if src.is_dir():
        names += sorted(p.relative_to(ui).as_posix() for p in src.rglob("*") if p.is_file())
    return sorted(set(names))


def expected_build_json(ui: Path) -> dict:
    files = {}
    for name in input_files(ui):
        p = ui / name
        files[name] = sha256(p.read_bytes()) if p.is_file() else None
    page = ui / "dist" / "index.html"
    return {"files": files, "page": sha256(page.read_bytes()) if page.is_file() else None}


def write_build_json(ui: Path) -> None:
    (ui / "dist" / "build.json").write_text(json.dumps(expected_build_json(ui), indent=2, sort_keys=True) + "\n",
                                            encoding="utf-8")


def check_package(root: Path) -> list:
    ui = root / "ui"
    problems = []
    pkg_path = ui / "package.json"
    if not pkg_path.is_file():
        return ["ui/package.json is missing"]
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if sorted(deps) != sorted(PINS):
        problems.append(f"ui/package.json has the packages {sorted(deps)}, not {sorted(PINS)}")
    for name, version in deps.items():
        if not EXACT.match(version):
            problems.append(f"ui/package.json: {name} is {version!r}, not an exact version")
        elif PINS.get(name) not in (None, version):
            problems.append(f"ui/package.json: {name} is {version}, not the pinned {PINS[name]}")
    lock_path = ui / "package-lock.json"
    if not lock_path.is_file():
        problems.append("ui/package-lock.json is missing")
    else:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if lock.get("lockfileVersion") != 3:
            problems.append("ui/package-lock.json is not lockfile version 3")
        for name, entry in lock.get("packages", {}).items():
            if name == "":
                continue
            if not str(entry.get("integrity", "")).startswith("sha512-"):
                problems.append(f"ui/package-lock.json: {name} has no sha512 integrity")
            if not str(entry.get("resolved", "")).startswith("https://registry.npmjs.org/"):
                problems.append(f"ui/package-lock.json: {name} does not come from registry.npmjs.org")
        root_deps = {**lock.get("packages", {}).get("", {}).get("dependencies", {}),
                     **lock.get("packages", {}).get("", {}).get("devDependencies", {})}
        if root_deps != deps:
            problems.append("ui/package-lock.json does not list the same packages as ui/package.json")
    inner = ui / ".gitignore"
    if not inner.is_file() or "node_modules/" not in inner.read_text(encoding="utf-8").split():
        problems.append("ui/.gitignore does not keep node_modules/ out")
    outer = root / ".gitignore"
    lines = outer.read_text(encoding="utf-8").split("\n") if outer.is_file() else []
    if "!ui/dist/" not in lines:
        problems.append(".gitignore has no !ui/dist/ exception, so the built page would be ignored")
    elif "dist/" in lines and lines.index("!ui/dist/") < lines.index("dist/"):
        problems.append(".gitignore: !ui/dist/ comes before dist/ and does nothing")
    for name in ("README.md", "build.mjs"):
        if not (ui / name).is_file():
            problems.append(f"ui/{name} is missing")
    return problems


def check_build_json(root: Path) -> list:
    ui = root / "ui"
    path = ui / "dist" / "build.json"
    if not path.is_file():
        return ["ui/dist/build.json is missing"]
    have = json.loads(path.read_text(encoding="utf-8"))
    want = expected_build_json(ui)
    problems = []
    for name in sorted(set(have.get("files", {})) | set(want["files"])):
        if have.get("files", {}).get(name) != want["files"].get(name):
            problems.append(f"ui/dist/build.json: {name} changed since the last build (run the build)")
    if have.get("page") != want["page"]:
        problems.append("ui/dist/build.json: ui/dist/index.html is not the page that was built (edited by hand, or "
                        "not rebuilt)")
    return problems


def check_page(root: Path) -> list:
    page = root / "ui" / "dist" / "index.html"
    if not page.is_file():
        return ["ui/dist/index.html is missing"]
    html = page.read_text(encoding="utf-8")
    problems = []
    scripts = SCRIPT.findall(html)
    styles = STYLE.findall(html)
    for attrs, _body in scripts:
        if re.search(r"\bsrc\s*=", attrs, re.I):
            problems.append("the page loads a script from a file (<script src>)")
    if len(scripts) != 1:
        problems.append(f"the page has {len(scripts)} scripts, not exactly one inline script")
    if len(styles) != 1:
        problems.append(f"the page has {len(styles)} style elements, not exactly one")
    for token in FORBIDDEN:
        if token in html:
            problems.append(f"the page contains {token!r}")
    for m in FORBIDDEN_TAGS.finditer(html):
        problems.append(f"the page has a <{m.group(1)}> element, which loads or sends something")
    if "@import" in html:
        problems.append("the page contains '@import'")
    if URL_FN.search(html):
        problems.append("the page has a url() that is not a data: address")
    if len(html.encode("utf-8")) >= MAX_PAGE_BYTES:
        problems.append(f"the page is {len(html.encode('utf-8'))} bytes, not under {MAX_PAGE_BYTES}")
    for url in sorted(set(ANY_URL.findall(html))):
        if url not in ALLOWED_URLS:
            problems.append(f"the page contains the address {url}, which is not a named XML namespace")
    # the Content-Security-Policy
    m = re.search(r"<meta\s+http-equiv=\"Content-Security-Policy\"\s+content=\"([^\"]*)\"", html, re.I)
    if not m:
        problems.append("the page has no Content-Security-Policy meta tag")
    else:
        csp = m.group(1)
        for need in ("default-src 'none'", "base-uri 'none'", "form-action 'none'"):
            if need not in csp:
                problems.append(f"the Content-Security-Policy lacks {need}")
        if scripts and f"script-src '{csp_hash(scripts[0][1])}'" not in csp:
            problems.append("the Content-Security-Policy does not hold the hash of the inline script")
        if styles and f"style-src '{csp_hash(styles[0][1])}'" not in csp:
            problems.append("the Content-Security-Policy does not hold the hash of the inline style")
        if "unsafe-inline" in csp or "unsafe-eval" in csp or "*" in csp:
            problems.append("the Content-Security-Policy allows more than its own hashed script and style")
    # the pieces of 12.R6 and 12.R5 that live in the HTML
    nav = re.search(r"<nav[^>]*id=\"labels\"[^>]*>(.*?)</nav>", html, re.S)
    labels = re.findall(r"<button[^>]*\bdata-station=\"([a-z]+)\"", nav.group(1)) if nav else []
    if labels != list(STATIONS):
        problems.append(f"the label buttons are {labels}, not {list(STATIONS)}")
    ul = re.search(r"<ul[^>]*id=\"station-list\"[^>]*>(.*?)</ul>", html, re.S)
    items = re.findall(r"<li[^>]*\bdata-station=\"([a-z]+)\"", ul.group(1)) if ul else []
    if items != list(STATIONS):
        problems.append(f"the list view items are {items}, not {list(STATIONS)}")
    # the label buttons and the list view carry the same names
    label_names = re.findall(r"<button[^>]*\bdata-station=\"[a-z]+\"[^>]*>([^<]*)</button>", nav.group(1)) if nav else []
    list_names = re.findall(r"<h3>([^<]*)</h3>", ul.group(1)) if ul else []
    if label_names != list_names:
        problems.append(f"the label names {label_names} are not the list view names {list_names}")
    # the home content (12.R15)
    strip = re.findall(r"<li data-strip=\"([a-z]+)\"", html)
    if strip != ["killswitch", "budget", "queue", "logbook"]:
        problems.append(f"the status strip is {strip}")
    if "sample" not in (re.search(r"<li data-strip=\"killswitch\">.*?</li>", html, re.S) or re.match("", "")).group(0):
        problems.append("the status strip shows a value without the word sample")
    copies = re.findall(r"data-copy=\"(cmd-[a-z]+)\"", html)
    if len(copies) != 7 or any(f'id="{c}"' not in html for c in copies):
        problems.append(f"the Copy buttons are {copies}, not seven with their commands")
    markup = STYLE.sub("", SCRIPT.sub("", html))  # the markup only: a "<a" inside the minified script is not a link
    anchors = re.findall(r"<a\b[^>]*href=\"([^\"]*)\"[^>]*>([^<]*)</a>", markup)
    if sorted(n for _h, n in anchors) != ["Docs", "Repo"]:
        problems.append(f"the links are {[n for _h, n in anchors]}, not Repo and Docs only")
    for h, n in anchors:
        if h not in ALLOWED_URLS:
            problems.append(f"the link {n} goes to {h}, which is not listed")
    for a in re.findall(r"<a\b[^>]*>", markup):
        if 'rel="noopener noreferrer"' not in a:
            problems.append("a link has no rel noopener noreferrer")
    holds = re.findall(r"<li data-placeholder><span class=\"name\">([^<]*)</span><span class=\"note\">([^<]*)</span>", html)
    if holds != [("Devpost", "link to come"), ("Demo video", "link to come")]:
        problems.append(f"the placeholders are {holds}, not Devpost and Demo video marked link to come")
    if not re.search(r"<h1>umwayi-os</h1>", html) or "id=\"hero\"" not in html:
        problems.append("the page has no hero with the title")
    if not re.search(r"<button[^>]*id=\"calm-toggle\"[^>]*aria-pressed=", html):
        problems.append("the page has no Calm mode button with aria-pressed")
    # no name is written in the picture at rest (12.R3.3): the buttons over the features are invisible until hover, focus or selection
    label_css = re.search(r"\.label\{([^}]*)\}", STYLE.search(html).group(2)) if STYLE.search(html) else None
    if not label_css or not re.search(r"opacity:0(;|$)", label_css.group(1)):
        problems.append("the buttons over the features are not invisible at rest (.label has no opacity:0)")
    if "prefers-reduced-motion" not in html:
        problems.append("the page has no prefers-reduced-motion rule")
    if re.search(r"<html[^>]*\blang=\"[a-z]", html) is None:
        problems.append("the page has no lang")
    if not re.search(r"<title>[^<]+</title>", html):
        problems.append("the page has no title")
    return problems


def check_no_em_dash(root: Path) -> list:
    problems = []
    ui = root / "ui"
    for p in sorted(ui.rglob("*")):
        if p.is_file() and "node_modules" not in p.parts and p.name != "package-lock.json":
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if EM_DASH in text:
                problems.append(f"{p.relative_to(root).as_posix()}: an em dash")
    return problems


def check(root: Path) -> list:
    """Every problem of the ui package and the built page under root, as text. Empty when all is well."""
    root = Path(root).resolve()
    return check_package(root) + check_build_json(root) + check_page(root) + check_no_em_dash(root)


class RepoTests(unittest.TestCase):
    def test_the_ui_package_and_the_built_page_have_no_problem(self):
        self.assertEqual(check(REPO), [])

    def test_node_modules_is_not_in_the_repo_listing(self):
        # the folder may exist on the owner's machine after npm ci; the check never looks inside it
        self.assertNotIn("node_modules", " ".join(input_files(REPO / "ui")))


class PlantedFaultTests(unittest.TestCase):
    """Each planted fault, in a temporary copy, is found. build.json is rewritten after a plant that is not about
    the build itself, so only the planted fault can fail."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-ui-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        shutil.copytree(REPO / "ui", self.root / "ui", ignore=shutil.ignore_patterns("node_modules"))
        shutil.copy2(REPO / ".gitignore", self.root / ".gitignore")

    def edit(self, rel: str, fn, rebuild: bool = True):
        p = self.root / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")
        if rebuild:
            write_build_json(self.root / "ui")

    def assert_found(self, fragment: str):
        problems = check(self.root)
        self.assertTrue(any(fragment in x for x in problems), f"{fragment!r} not in {problems}")

    def test_the_copy_is_clean_before_any_plant(self):
        self.assertEqual(check(self.root), [])

    def test_a_version_with_a_range(self):
        self.edit("ui/package.json", lambda t: t.replace('"0.187.0"', '"^0.187.0"'))
        self.assert_found("not an exact version")

    def test_another_version_than_the_pinned_one(self):
        self.edit("ui/package.json", lambda t: t.replace('"0.28.2"', '"0.28.3"'))
        self.assert_found("not the pinned 0.28.2")

    def test_a_lockfile_entry_without_sha512(self):
        def drop(t):
            lock = json.loads(t)
            name = next(k for k in lock["packages"] if k)
            lock["packages"][name]["integrity"] = "sha1-abc"
            return json.dumps(lock, indent=2)
        self.edit("ui/package-lock.json", drop)
        self.assert_found("has no sha512 integrity")

    def test_a_lockfile_entry_from_another_registry(self):
        def move(t):
            lock = json.loads(t)
            name = next(k for k in lock["packages"] if k)
            lock["packages"][name]["resolved"] = "https://example.invalid/x.tgz"
            return json.dumps(lock, indent=2)
        self.edit("ui/package-lock.json", move)
        self.assert_found("does not come from registry.npmjs.org")

    def test_a_missing_gitignore_exception(self):
        self.edit(".gitignore", lambda t: t.replace("!ui/dist/\n", ""))
        self.assert_found("no !ui/dist/ exception")

    def test_a_source_changed_without_a_rebuild(self):
        self.edit("ui/src/main.js", lambda t: t + "\n// changed\n", rebuild=False)
        self.assert_found("src/main.js changed since the last build")

    def test_a_page_edited_by_hand(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</body>", "<!-- hand -->\n</body>"), rebuild=False)
        self.assert_found("is not the page that was built")

    def test_a_fetch_in_the_page(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</script>", ";fetch('x')</script>", 1))
        self.assert_found("contains 'fetch('")

    def test_storage_in_the_page(self):
        for word in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            with self.subTest(word=word):
                self.edit("ui/dist/index.html", lambda t: t.replace("</script>", f";{word}</script>", 1))
                self.assert_found(f"contains '{word}'")
                self.setUp()

    def test_a_file_loader_in_the_page(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</script>", ";new TextureLoader()</script>", 1))
        self.assert_found("contains 'TextureLoader'")

    def test_an_address_that_is_not_a_namespace(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</script>", ";'https://example.invalid/a'</script>", 1))
        self.assert_found("https://example.invalid/a")

    def test_a_cdn_script_tag(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("<body", '<script src="x.js"></script><body', 1))
        self.assert_found("loads a script from a file")

    def test_a_link_element(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("<body", '<link rel="stylesheet" href="a.css"><body', 1))
        self.assert_found("<link> element")

    def test_an_import_rule_and_a_remote_url_function(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</style>", "@import 'a.css';</style>", 1))
        self.assert_found("'@import'")
        self.setUp()
        self.edit("ui/dist/index.html", lambda t: t.replace("</style>", "a{background:url(b.png)}</style>", 1))
        self.assert_found("url() that is not a data: address")

    def test_a_missing_content_security_policy(self):
        self.edit("ui/dist/index.html", lambda t: re.sub(r"<meta http-equiv=\"Content-Security-Policy\"[^>]*>", "", t))
        self.assert_found("no Content-Security-Policy meta tag")

    def test_a_policy_that_does_not_match_the_script(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</script>", ";var a=1</script>", 1))
        self.assert_found("does not hold the hash of the inline script")

    def test_a_policy_with_unsafe_inline(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("default-src 'none'", "default-src 'none'; x 'unsafe-inline'"))
        self.assert_found("allows more than its own hashed script and style")

    def test_a_missing_label_button(self):
        self.edit("ui/dist/index.html", lambda t: re.sub(r"<button[^>]*data-station=\"budget\"[^>]*>.*?</button>", "", t, count=1, flags=re.S))
        self.assert_found("the label buttons are")

    def test_a_missing_calm_button_and_reduced_motion_rule(self):
        self.edit("ui/dist/index.html", lambda t: t.replace('id="calm-toggle"', 'id="x"'))
        self.assert_found("no Calm mode button")
        self.setUp()
        self.edit("ui/dist/index.html", lambda t: t.replace("prefers-reduced-motion", "prefers-nothing"))
        self.assert_found("no prefers-reduced-motion rule")

    def test_an_address_in_a_link_that_is_not_listed(self):
        self.edit("ui/dist/index.html", lambda t: t.replace('href="' + REPO_URL + '"', 'href="https://example.invalid/x"', 1))
        self.assert_found("not listed")

    def test_a_placeholder_made_into_a_real_link(self):
        self.edit("ui/dist/index.html", lambda t: t.replace('<li data-placeholder><span class="name">Devpost</span>', '<li><a href="' + REPO_URL + '" rel="noopener noreferrer">Devpost</a>', 1).replace('<span class="note">link to come</span></li>', '</li>', 1))
        self.assert_found("not Repo and Docs only")

    def test_a_missing_copy_button_and_a_strip_without_sample(self):
        self.edit("ui/dist/index.html", lambda t: re.sub(r"<button[^>]*data-copy=\"cmd-verify\"[^>]*>Copy</button>", "", t, count=1))
        self.assert_found("not seven")
        self.setUp()
        self.edit("ui/dist/index.html", lambda t: t.replace('<span class="t">sample</span>', '<span class="t"></span>', 1))
        self.assert_found("without the word sample")

    def test_a_page_over_two_megabytes(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("</body>", "<!--" + "x" * 2_100_000 + "-->\n</body>"))
        self.assert_found("not under 2000000")

    def test_a_link_without_noopener(self):
        self.edit("ui/dist/index.html", lambda t: t.replace(' rel="noopener noreferrer"', "", 1))
        self.assert_found("rel noopener noreferrer")

    def test_a_label_and_a_list_item_with_different_words(self):
        self.edit("ui/dist/index.html", lambda t: t.replace("<h3>Memory</h3>", "<h3>Remembering</h3>", 1))
        self.assert_found("are not the list view names")

    def test_a_name_visible_at_rest(self):
        self.edit("ui/dist/index.html", lambda t: t.replace(".label{position:absolute;left:0;top:0;display:block;white-space:nowrap;opacity:0;", ".label{position:absolute;left:0;top:0;display:block;white-space:nowrap;opacity:1;", 1))
        self.assert_found("not invisible at rest")

    def test_an_em_dash(self):
        self.edit("ui/README.md", lambda t: t + "\nA line " + EM_DASH + " here.\n", rebuild=False)
        self.assert_found("ui/README.md: an em dash")


class HelperTests(unittest.TestCase):
    def test_csp_hash_is_the_browsers_form(self):
        # sha256 of the empty string, base64
        self.assertEqual(csp_hash(""), "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=")


if __name__ == "__main__":
    unittest.main()
