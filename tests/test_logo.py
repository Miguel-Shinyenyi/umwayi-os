"""W51: the owner's logo on the local pages, in the pull request template, and nowhere it would need a request.

The logo file ui/assets/amwayi-logo-512.png stays as the owner made it (D-70): its SHA-256 is pinned here. The pages draw it as
one inline SVG of the same shapes (ui/src/logo.svg), put into the header by ui/build.mjs, so no page policy changes and no page
needs img-src or a request. Standard library only.
"""
import hashlib
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
PNG = UI / "assets" / "amwayi-logo-512.png"
SVG = UI / "src" / "logo.svg"
PNG_SHA256 = "7926530e9df33602d6aa7f60632e08b332e835e70558ebbcb82ff4468cca7883"
TEMPLATE = REPO / ".github" / "pull_request_template.md"
RAW = "https://raw.githubusercontent.com/Miguel-Shinyenyi/umwayi-os/main/ui/assets/amwayi-logo-512.png"
# the page, the template it is built from, where the logo goes (just before this text), and its policy as before W51
PAGES = {
    "index.html": ("index.html", '<span class="mark"><!--@logo-->umwayi-os</span>', '<span class="mark">{logo}umwayi-os</span>',
                   ["default-src 'none'", "script-src", "style-src", "img-src data:", "base-uri 'none'", "form-action 'none'",
                    "connect-src 'self'"]),
    "goal-map.html": ("goal-map.html", "<h1><!--@logo-->umwayi goal map ", "<h1>{logo}umwayi goal map ",
                      ["default-src 'none'", "script-src", "style-src", "base-uri 'none'", "form-action 'none'", "connect-src 'self'"]),
    "cli-map.html": ("cli-map.html", '<h1><!--@logo--><span class="hub">', '<h1>{logo}<span class="hub">',
                     ["default-src 'none'", "style-src", "base-uri 'none'", "form-action 'none'"]),
    "progress.html": ("progress.html", "<h1><!--@logo-->umwayi progress</h1>", "<h1>{logo}umwayi progress</h1>",
                      ["default-src 'none'", "style-src", "base-uri 'none'", "form-action 'none'"]),
}
UNSAFE = re.compile(r"https?:|<script|<image|<use|<foreignObject|\bhref\b|\bsrc\s*=|url\(|\bon[a-z]+\s*=|style\s*=", re.I)


def logo_problems(text):
    """What is wrong with a logo mark, or [] when it is the plain mark the pages may hold."""
    problems = []
    t = text.strip()
    if not re.fullmatch(r'<svg class="logo" [^>]*aria-hidden="true" focusable="false">[\s\S]*</svg>', t):
        problems.append("the mark is not one svg of class logo, hidden from assistive technology")
    if UNSAFE.search(t):
        problems.append("the mark holds an address, a link, a script, an event, a style attribute or an outside picture")
    if not re.findall(r'fill="#e9a23b"', t) or not re.findall(r'#1e2520', t):
        problems.append("the mark does not use the two colours of the logo")
    if len(t.encode("utf-8")) > 2048:
        problems.append("the mark is larger than 2 KB")
    return problems


def policy_parts(html):
    csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', html).group(1)
    return [p.split(" 'sha256-")[0] for p in csp.split("; ")]


class LogoFileTests(unittest.TestCase):
    def test_the_logo_file_is_the_owners_and_unchanged(self):
        self.assertEqual(hashlib.sha256(PNG.read_bytes()).hexdigest(), PNG_SHA256)

    def test_the_mark_is_the_plain_logo(self):
        self.assertEqual(logo_problems(SVG.read_text(encoding="utf-8")), [])

    def test_PLANTED_FAULT_a_mark_with_an_address_a_link_a_script_or_a_picture_is_found(self):
        good = SVG.read_text(encoding="utf-8").strip()
        for bad in (good.replace("<path", '<image href="https://example.invalid/x.png"/><path', 1),
                    good.replace("<path", "<script>alert(1)</script><path", 1),
                    good.replace('aria-hidden="true" ', "", 1),
                    good.replace('<rect ', '<rect onclick="x()" ', 1),
                    good.replace("<path", '<path style="fill:red"', 1),
                    good.replace('fill="#e9a23b"', 'fill="#000000"'),
                    good.replace("</svg>", "<!--" + "x" * 2100 + "--></svg>")):
            self.assertTrue(logo_problems(bad), bad[-80:])


class PageTests(unittest.TestCase):
    MARK = SVG.read_text(encoding="utf-8").strip()

    def test_every_template_has_the_placeholder_once_in_its_header(self):
        for page, (src, before, _after, _p) in PAGES.items():
            text = (UI / "src" / src).read_text(encoding="utf-8")
            self.assertEqual(text.count("<!--@logo-->"), 1, page)
            self.assertIn(before, text, page)

    def test_every_built_page_has_the_mark_once_before_its_title(self):
        for page, (_src, _before, after, _p) in PAGES.items():
            path = UI / "dist" / page
            if not path.is_file():  # the progress page is built, not committed (W22); the node tests build it
                continue
            html = path.read_text(encoding="utf-8")
            self.assertEqual(html.count('<svg class="logo"'), 1, page)
            self.assertIn(after.format(logo=self.MARK), html, page)
            self.assertNotIn("<!--@logo-->", html, page)

    def test_no_page_policy_changed_and_no_page_holds_an_img_or_an_address_for_it(self):
        for page, (_src, _b, _a, parts) in PAGES.items():
            path = UI / "dist" / page
            if not path.is_file():
                continue
            html = path.read_text(encoding="utf-8")
            self.assertEqual(policy_parts(html), parts, page)
            self.assertNotRegex(html, r"<img\b", page)
            # the file name may be words on a page (the progress page shows status rows), never a place to load from
            self.assertNotRegex(html, r"(src|href|srcset)\s*=\s*[\"'][^\"']*amwayi-logo|url\([^)]*amwayi-logo", page)

    def test_the_build_puts_the_mark_into_all_four_pages_and_checks_it(self):
        code = (UI / "build.mjs").read_text(encoding="utf-8")
        self.assertIn("readFileSync(join(root, 'src/logo.svg'), 'utf8')", code)
        for src in ("index.html", "cli-map.html", "progress.html", "goal-map.html"):
            self.assertIn(f"withLogo(readFileSync(join(root, 'src/{src}'), 'utf8'))", code, src)
        self.assertIn("is not the plain logo mark", code)

    def test_the_build_record_covers_the_mark(self):
        files = json.loads((UI / "dist" / "build.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(files["src/logo.svg"], hashlib.sha256(SVG.read_bytes()).hexdigest())

    def test_every_page_style_sizes_the_mark(self):
        for css in ("style.css", "goal-map.css", "progress.css", "cli-map.css"):
            self.assertRegex((UI / "src" / css).read_text(encoding="utf-8"), r"\.logo \{[^}]*width: 1\.1em", css)


class TemplateTests(unittest.TestCase):
    def test_the_pull_request_template_has_the_logo_by_raw_address_and_the_one_line(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(f'<img src="{RAW}"', text)
        self.assertEqual(text.count("Made with umwayi-os"), 1)
        self.assertEqual([u for u in re.findall(r"https?://[^\s\"'<>]+", text)], [RAW])
        self.assertNotIn("\u2014", text)


if __name__ == "__main__":
    unittest.main()
