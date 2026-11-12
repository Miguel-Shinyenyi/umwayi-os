"""The High tier's asset files on the public site (tasks.md UI.7, requirements 12.R16.3, 12.R16.4).

Checks, on the repo and on temporary copies with a planted fault each:
- every file under site/public is listed in site/high-assets.json, and every listed file exists;
- each listed file has a free licence (CC0 1.0 only today) with the licence's own address, an author, a source page and a
  download address on Poly Haven, a size and a SHA-256 that match the file, and is a JPEG photograph;
- ui/src/high/assets.js loads exactly the listed files, from the site's own host only (the default base is /high/, and the
  code rejects anything with a scheme, a host or "//");
- no file of ui/src/high names a remote address, and the live view's built page carries no part of High;
- no file under site/public is a copy of a file of ui/src;
- adapters/NOTES-layer12.md lists every file with its licence and its author;
- no em dash in the listing.
Standard library only; no npm, no node, no browser, no network. The repo is never changed by the planted faults.
"""

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
EM_DASH = "\u2014"
LISTING = "site/high-assets.json"
PUBLIC = "site/public"
FREE = {"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/"}
SOURCE_HOSTS = {"polyhaven.com"}
DOWNLOAD_HOSTS = {"dl.polyhaven.org"}
LISTING_HOSTS = SOURCE_HOSTS | DOWNLOAD_HOSTS | {"creativecommons.org"}
FIELDS = ("file", "title", "author", "licence", "licence_url", "source", "download", "bytes", "sha256")
MAX_BYTES = 2_000_000
URL = re.compile(r"https?://[^\s\"'<>)\\`]*")


def public_files(root: Path) -> list:
    base = root / PUBLIC
    if not base.is_dir():
        return []
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


def read_listing(root: Path):
    p = root / LISTING
    if not p.is_file():
        return None, [f"{LISTING} is missing"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return None, [f"{LISTING} is not JSON: {e}"]
    if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
        return None, [f"{LISTING} has no list of assets"]
    return data, []


def asset_names_in_code(text: str) -> list:
    """The file names that ui/src/high/assets.js loads, in its order."""
    m = re.search(r"export const ASSETS = \[(.*?)\];", text, re.S)
    return re.findall(r"file:\s*'([^']+)'", m.group(1)) if m else []


def check_listing(root: Path) -> list:
    data, problems = read_listing(root)
    if data is None:
        return problems
    text = (root / LISTING).read_text(encoding="utf-8")
    for url in sorted(set(URL.findall(text))):
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in LISTING_HOSTS:
            problems.append(f"{LISTING} names {url}, which is not a source, download or licence address")
    if EM_DASH in text or EM_DASH in json.dumps(data, ensure_ascii=False):  # also when written as \u2014
        problems.append(f"{LISTING}: an em dash")
    listed = []
    for i, a in enumerate(data["assets"]):
        name = a.get("file", f"entry {i}") if isinstance(a, dict) else f"entry {i}"
        if not isinstance(a, dict):
            problems.append(f"{LISTING}: {name} is not an object")
            continue
        for f in FIELDS:
            if not a.get(f):
                problems.append(f"{LISTING}: {name} has no {f}")
        listed.append(name)
        lic = a.get("licence")
        if lic and lic not in FREE:
            problems.append(f"{LISTING}: {name} has the licence {lic!r}, which is not a free licence on the list")
        elif lic and a.get("licence_url") != FREE[lic]:
            problems.append(f"{LISTING}: {name} names the wrong address for {lic}")
        src = urlparse(str(a.get("source", "")))
        if a.get("source") and (src.scheme != "https" or src.hostname not in SOURCE_HOSTS):
            problems.append(f"{LISTING}: {name} has a source that is not a Poly Haven page")
        dl = urlparse(str(a.get("download", "")))
        if a.get("download") and (dl.scheme != "https" or dl.hostname not in DOWNLOAD_HOSTS or not dl.path.endswith("/" + name.split("/")[-1])):
            problems.append(f"{LISTING}: {name} has a download address that is not this file on Poly Haven")
        p = root / PUBLIC / name
        if not p.is_file():
            problems.append(f"{LISTING}: {name} is listed but site/public/{name} does not exist")
            continue
        blob = p.read_bytes()
        if a.get("bytes") and a["bytes"] != len(blob):
            problems.append(f"{LISTING}: {name} is {len(blob)} bytes, not the listed {a['bytes']}")
        if a.get("sha256") and a["sha256"] != hashlib.sha256(blob).hexdigest():
            problems.append(f"{LISTING}: {name} does not match its SHA-256")
        if not blob.startswith(b"\xff\xd8\xff"):
            problems.append(f"site/public/{name} is not a JPEG")
        if len(blob) > MAX_BYTES:
            problems.append(f"site/public/{name} is over {MAX_BYTES} bytes")
    if len(set(listed)) != len(listed):
        problems.append(f"{LISTING} lists a file twice")
    for name in public_files(root):
        if name not in listed:
            problems.append(f"site/public/{name} is not listed in {LISTING}")
    return problems


def check_code(root: Path) -> list:
    problems = []
    data, _ = read_listing(root)
    listed = sorted(a.get("file", "") for a in data["assets"] if isinstance(a, dict)) if data else []
    assets = root / "ui" / "src" / "high" / "assets.js"
    if not assets.is_file():
        return ["ui/src/high/assets.js is missing"]
    text = assets.read_text(encoding="utf-8")
    names = asset_names_in_code(text)
    if sorted("high/" + n for n in names) != listed:
        problems.append(f"ui/src/high/assets.js loads {sorted(names)}, not the listed files")
    if not re.search(r"export function loadTextures\(base = '/high/'", text):
        problems.append("ui/src/high/assets.js does not load from /high/ on the site's own host by default")
    if "base.includes('//')" not in text or not re.search(r"/\^\\/\[a-z0-9_/-\]\*\\/\$/\.test\(base\)", text):
        problems.append("ui/src/high/assets.js does not refuse a base with a scheme or a host")
    index = root / "ui" / "src" / "high" / "index.js"
    if not index.is_file() or "base = '/high/'" not in index.read_text(encoding="utf-8"):
        problems.append("ui/src/high/index.js does not default to /high/")
    for p in sorted((root / "ui" / "src" / "high").rglob("*.js")):
        code = p.read_text(encoding="utf-8")
        if URL.search(code) or re.search(r"['\"`]//[a-z0-9]", code, re.I):
            problems.append(f"{p.relative_to(root).as_posix()} names a remote address")
    for rel in ("site/app/scene.js",):
        p = root / rel
        if p.is_file():
            loads = re.findall(r"loadHigh:\s*\(\)\s*=>\s*import\('([^']+)'\)", p.read_text(encoding="utf-8"))
            if loads != ["../../ui/src/high/index.js"]:
                problems.append(f"{rel} does not load High on demand from ui/src/high/index.js")
    built = root / "ui" / "dist" / "index.html"
    if built.is_file():
        page = built.read_text(encoding="utf-8")
        for token in ["/high/"] + [n for n in names]:
            if token in page:
                problems.append(f"ui/dist/index.html contains {token!r}; the live view has no High")
    return problems


def check_copies(root: Path) -> list:
    problems = []
    ui_src = root / "ui" / "src"
    digests = {}
    if ui_src.is_dir():
        for p in ui_src.rglob("*"):
            if p.is_file():
                digests[hashlib.sha256(p.read_bytes()).hexdigest()] = p.relative_to(ui_src).as_posix()
    for name in public_files(root):
        d = hashlib.sha256((root / PUBLIC / name).read_bytes()).hexdigest()
        if d in digests:
            problems.append(f"site/public/{name} is a copy of ui/src/{digests[d]}")
    return problems


def check_notes(root: Path) -> list:
    data, _ = read_listing(root)
    notes = root / "adapters" / "NOTES-layer12.md"
    if data is None or not notes.is_file():
        return [] if data is None else ["adapters/NOTES-layer12.md is missing"]
    text = notes.read_text(encoding="utf-8")
    problems = []
    for a in data["assets"]:
        if not isinstance(a, dict) or not a.get("file"):
            continue
        base = a["file"].split("/")[-1]
        lines = [ln for ln in text.splitlines() if base in ln]
        if not lines:
            problems.append(f"adapters/NOTES-layer12.md does not list {base}")
        elif not any(str(a.get("licence", "")).replace("-", " ") in ln.replace("-", " ") and str(a.get("author", "")) in ln for ln in lines):
            problems.append(f"adapters/NOTES-layer12.md does not give the licence and the author of {base}")
    return problems


def check(root: Path) -> list:
    """Every problem of the High asset files under root, as text. Empty when all is well."""
    root = Path(root).resolve()
    return check_listing(root) + check_code(root) + check_copies(root) + check_notes(root)


class RepoTests(unittest.TestCase):
    def test_the_assets_have_no_problem(self):
        self.assertEqual(check(REPO), [])

    def test_the_listing_is_not_served(self):
        # the listing sits beside public/, not in it, so the site does not serve it; the photographs are the only files served
        self.assertFalse((REPO / PUBLIC / "high-assets.json").exists())
        self.assertTrue((REPO / LISTING).is_file())

    def test_there_is_at_least_one_asset_and_all_are_under_high(self):
        files = public_files(REPO)
        self.assertTrue(files)
        self.assertTrue(all(f.startswith("high/") for f in files), files)


class PlantedFaultTests(unittest.TestCase):
    """Each planted fault, in a temporary copy, is found."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-assets-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "site").mkdir(parents=True)
        shutil.copytree(REPO / PUBLIC, self.root / PUBLIC)
        shutil.copy2(REPO / LISTING, self.root / LISTING)
        (self.root / "site" / "app").mkdir()
        shutil.copy2(REPO / "site" / "app" / "scene.js", self.root / "site" / "app" / "scene.js")
        shutil.copytree(REPO / "ui" / "src", self.root / "ui" / "src")
        (self.root / "ui" / "dist").mkdir()
        shutil.copy2(REPO / "ui" / "dist" / "index.html", self.root / "ui" / "dist" / "index.html")
        (self.root / "adapters").mkdir()
        shutil.copy2(REPO / "adapters" / "NOTES-layer12.md", self.root / "adapters" / "NOTES-layer12.md")

    def edit(self, rel: str, fn):
        p = self.root / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")

    def edit_listing(self, fn):
        p = self.root / LISTING
        data = json.loads(p.read_text(encoding="utf-8"))
        fn(data)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def assert_found(self, fragment: str):
        problems = check(self.root)
        self.assertTrue(any(fragment in x for x in problems), f"{fragment!r} not in {problems}")

    def test_the_copy_is_clean_before_any_plant(self):
        self.assertEqual(check(self.root), [])

    def test_an_unlisted_file(self):
        shutil.copy2(self.root / PUBLIC / "high" / "dark_rock_02_diff_1k.jpg", self.root / PUBLIC / "high" / "extra.jpg")
        self.assert_found("site/public/high/extra.jpg is not listed")

    def test_an_unlisted_file_outside_high(self):
        (self.root / PUBLIC / "logo.svg").write_text("<svg/>", encoding="utf-8")
        self.assert_found("site/public/logo.svg is not listed")

    def test_a_listed_file_that_is_gone(self):
        (self.root / PUBLIC / "high" / "grass_ground_diff_1k.jpg").unlink()
        self.assert_found("is listed but site/public/high/grass_ground_diff_1k.jpg does not exist")

    def test_a_licence_that_is_not_free(self):
        self.edit_listing(lambda d: d["assets"][0].update(licence="CC-BY-NC-4.0"))
        self.assert_found("which is not a free licence on the list")

    def test_no_licence(self):
        self.edit_listing(lambda d: d["assets"][1].pop("licence"))
        self.assert_found("has no licence")

    def test_the_wrong_licence_address(self):
        self.edit_listing(lambda d: d["assets"][2].update(licence_url="https://creativecommons.org/licenses/by/4.0/"))
        self.assert_found("names the wrong address for CC0-1.0")

    def test_no_author_and_no_source(self):
        self.edit_listing(lambda d: d["assets"][0].update(author=""))
        self.assert_found("has no author")
        self.setUp()
        self.edit_listing(lambda d: d["assets"][0].pop("source"))
        self.assert_found("has no source")

    def test_a_source_or_download_on_another_host(self):
        self.edit_listing(lambda d: d["assets"][0].update(source="https://example.invalid/a/grass_ground"))
        self.assert_found("has a source that is not a Poly Haven page")
        self.setUp()
        self.edit_listing(lambda d: d["assets"][0].update(download="http://dl.polyhaven.org/x/grass_ground_diff_1k.jpg"))
        self.assert_found("has a download address that is not this file on Poly Haven")
        self.setUp()
        self.edit_listing(lambda d: d["assets"][0].update(download="https://dl.polyhaven.org/x/other_1k.jpg"))
        self.assert_found("has a download address that is not this file on Poly Haven")

    def test_another_address_in_the_listing(self):
        self.edit_listing(lambda d: d.update(note="see https://cdn.example.invalid/x"))
        self.assert_found("names https://cdn.example.invalid/x")

    def test_a_file_that_was_changed(self):
        p = self.root / PUBLIC / "high" / "dark_rock_02_diff_1k.jpg"
        blob = bytearray(p.read_bytes())
        blob[-10] ^= 0xFF
        p.write_bytes(bytes(blob))
        self.assert_found("dark_rock_02_diff_1k.jpg does not match its SHA-256")

    def test_a_wrong_size(self):
        self.edit_listing(lambda d: d["assets"][0].update(bytes=d["assets"][0]["bytes"] + 1))
        self.assert_found("not the listed")

    def test_a_file_that_is_not_a_jpeg_and_one_too_large(self):
        p = self.root / PUBLIC / "high" / "grass_ground_diff_1k.jpg"
        p.write_bytes(b"GIF89a" + b"\0" * 10)
        self.assert_found("site/public/high/grass_ground_diff_1k.jpg is not a JPEG")
        self.setUp()
        p = self.root / PUBLIC / "high" / "grass_ground_diff_1k.jpg"
        big = p.read_bytes() + b"\0" * MAX_BYTES
        p.write_bytes(big)
        self.edit_listing(lambda d: [a.update(bytes=len(big), sha256=hashlib.sha256(big).hexdigest())
                                     for a in d["assets"] if a["file"].endswith("grass_ground_diff_1k.jpg")])
        self.assert_found("is over 2000000 bytes")

    def test_a_file_listed_twice(self):
        self.edit_listing(lambda d: d["assets"].append(dict(d["assets"][0])))
        self.assert_found("lists a file twice")

    def test_an_em_dash_in_the_listing(self):
        self.edit_listing(lambda d: d["assets"][0].update(title="Grass " + EM_DASH + " ground"))
        self.assert_found(f"{LISTING}: an em dash")

    def test_the_code_loads_a_file_that_is_not_listed(self):
        self.edit("ui/src/high/assets.js", lambda t: t.replace("dark_rock_02_nor_gl_1k.jpg", "dark_rock_03_nor_gl_1k.jpg"))
        self.assert_found("not the listed files")

    def test_the_code_loads_from_another_host(self):
        self.edit("ui/src/high/assets.js", lambda t: t.replace("base = '/high/'", "base = 'https://cdn.example.invalid/high/'"))
        self.assert_found("does not load from /high/")
        self.assert_found("ui/src/high/assets.js names a remote address")

    def test_the_host_check_removed(self):
        self.edit("ui/src/high/assets.js", lambda t: t.replace(" || base.includes('//')", ""))
        self.assert_found("does not refuse a base with a scheme or a host")

    def test_a_remote_address_in_the_high_code(self):
        self.edit("ui/src/high/build.js", lambda t: t + "\nexport const X = '//cdn.example.invalid/x.js';\n")
        self.assert_found("ui/src/high/build.js names a remote address")

    def test_the_index_default_changed(self):
        self.edit("ui/src/high/index.js", lambda t: t.replace("base = '/high/'", "base = '/other/'"))
        self.assert_found("ui/src/high/index.js does not default to /high/")

    def test_high_loaded_eagerly_or_from_elsewhere(self):
        self.edit("site/app/scene.js", lambda t: t.replace("'../../ui/src/high/index.js'", "'./high.js'"))
        self.assert_found("does not load High on demand")

    def test_high_in_the_live_view(self):
        self.edit("ui/dist/index.html", lambda t: t + "<!-- /high/grass_ground_diff_1k.jpg -->")
        self.assert_found("the live view has no High")

    def test_a_copy_of_ui_src_in_public(self):
        shutil.copy2(self.root / "ui" / "src" / "engine" / "tier.js", self.root / PUBLIC / "high" / "tier.js")
        self.assert_found("site/public/high/tier.js is a copy of ui/src/engine/tier.js")

    def test_the_notes_miss_a_file_or_its_licence(self):
        self.edit("adapters/NOTES-layer12.md", lambda t: "\n".join(ln for ln in t.splitlines() if "dark_rock_02_nor_gl_1k.jpg" not in ln))
        self.assert_found("does not list dark_rock_02_nor_gl_1k.jpg")
        self.setUp()
        self.edit("adapters/NOTES-layer12.md", lambda t: "\n".join(
            ln.replace("CC0 1.0", "CC BY 4.0") if "grass_ground_diff_1k.jpg" in ln else ln for ln in t.splitlines()))
        self.assert_found("does not give the licence and the author of grass_ground_diff_1k.jpg")


class HelperTests(unittest.TestCase):
    def test_asset_names_in_code_reads_the_list(self):
        text = "export const ASSETS = [\n  { key: 'a', file: 'a.jpg', colour: true },\n  { key: 'b', file: 'b.jpg' },\n];"
        self.assertEqual(asset_names_in_code(text), ["a.jpg", "b.jpg"])

    def test_no_list_gives_nothing(self):
        self.assertEqual(asset_names_in_code("const x = 1;"), [])


if __name__ == "__main__":
    unittest.main()
