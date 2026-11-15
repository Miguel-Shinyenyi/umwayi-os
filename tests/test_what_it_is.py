"""W39: README.md links docs/what-it-is.md, the page has its six headings in order, and the words "full operating system"
appear only in the "What it is not" part of the page (and, in README, only in the sentence that says what it is not).
Planted faults prove each check can fail."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "what-it-is.md"
README = REPO / "README.md"
HEADINGS = ("What it is", "What it is not", "What it does", "What it does not do",
            "Where it has been proven and where not", "Status")
PHRASE = re.compile(r"full\s+operating\s+system", re.I)


def sections(text):
    """{heading: body} for the ### headings of the page, and the list of headings in order."""
    out, order, cur = {}, [], None
    for line in text.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*?)\s*$", line)
        if m and m.group(1) == "###":
            cur = m.group(2)
            order.append(cur)
            out[cur] = []
            continue
        if m:  # a ## heading ends the ### part
            cur = None
            continue
        if cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}, order


def problems(page, readme):
    out = []
    if "(docs/what-it-is.md)" not in readme:
        out.append("README does not link docs/what-it-is.md")
    if not re.search(r"^## What this is and is not$", readme, re.M):
        out.append("README has no section 'What this is and is not'")
    secs, order = sections(page)
    if [h for h in order if h in HEADINGS] != list(HEADINGS):
        out.append(f"the headings are {order}, not {list(HEADINGS)} in order")
    if len(PHRASE.findall(secs.get("What it is not", ""))) < 1:
        out.append("the 'What it is not' part does not say it is not a full operating system")
    outside = len(PHRASE.findall(page)) - len(PHRASE.findall(secs.get("What it is not", "")))
    if outside:
        out.append(f"the page says 'full operating system' {outside} time(s) outside 'What it is not'")
    for sentence in re.split(r"(?<=[.!?])\s+", readme):
        if PHRASE.search(sentence) and not re.search(r"\bnot\b", sentence):
            out.append("README says 'full operating system' in a sentence that is not a 'not'")
    if "(KNOWN-LIMITS.md)" not in page.strip().splitlines()[-1]:
        out.append("the page does not end with a pointer to KNOWN-LIMITS.md")
    return out


class WhatItIsTests(unittest.TestCase):
    page = PAGE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    def test_the_page_and_the_readme(self):
        self.assertEqual(problems(self.page, self.readme), [])

    def test_PLANTED_FAULT_the_readme_without_the_link(self):
        self.assertTrue(problems(self.page, self.readme.replace("(docs/what-it-is.md)", "(docs/x.md)")))

    def test_PLANTED_FAULT_a_heading_missing_or_out_of_order(self):
        self.assertTrue(problems(self.page.replace("### What it does not do", "### Other"), self.readme))
        swapped = self.page.replace("### What it is not", "### TMP").replace("### What it does\n", "### What it is not\n").replace("### TMP", "### What it does")
        self.assertTrue(problems(swapped, self.readme))

    def test_PLANTED_FAULT_the_phrase_outside_the_is_not_part(self):
        self.assertTrue(problems(self.page.replace("### Status\n", "### Status\n\nIt is a full operating system.\n"), self.readme))
        self.assertTrue(problems(self.page, self.readme + "\numwayi-os is a full operating system.\n"))

    def test_PLANTED_FAULT_no_pointer_to_the_known_limits_at_the_end(self):
        self.assertTrue(problems(self.page.rstrip() + "\n\nOne more line.\n", self.readme))

if __name__ == "__main__":
    unittest.main()
