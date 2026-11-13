"""W19 part 3a: every numbered rule of the builder workflow and of steering rules 1 to 13 has a guidance entry.

A rule is covered by an entry in guidance.yaml (source_repo umwayi-os, same file, same section, same number) or is
listed in EXCLUDED below with a reason. A new numbered rule in either steering file fails these tests until it is
covered. Also pins the tiers of the umwayi-os entries and the loader's reading of an indented rule line.
Standard library only.
"""

import re
import tempfile
import unittest
from pathlib import Path

from umwayi import guidance
from umwayi.errors import UmwayiError

REPO = Path(__file__).resolve().parents[2]
BUILDER = ".kiro/steering/builder-workflow.md"
PRODUCT = ".kiro/steering/product.md"
SAFETY_HEADING = "Safety rules"
LAYER13_HEADING = "Layer 13: correction"

# (path, section heading or None, number) -> why no entry covers it. Empty on purpose: all 23 rules have entries.
EXCLUDED: dict = {}


def scan_builder(text: str) -> set:
    """Numbered rules at the start of a line outside code fences."""
    found, fence = set(), False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fence = not fence
        elif not fence:
            m = re.match(r"^(\d{1,3})\. ", ln)
            if m:
                found.add((BUILDER, None, int(m.group(1))))
    return found


def scan_product(text: str) -> set:
    """Steering rules: numbered lines of the section 'Safety rules', and the indented numbered lines of the section
    'Layer 13' (the rules layer 13 adds). Other numbered lists of the file (the build order) are not rules."""
    found, fence, section = set(), False, None
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if ln.startswith("## "):
            title = ln[3:].strip()
            if title == SAFETY_HEADING:
                section = SAFETY_HEADING
            elif title.startswith(LAYER13_HEADING):
                section = LAYER13_HEADING
            else:
                section = None
            continue
        if section == SAFETY_HEADING:
            m = re.match(r"^\s*(\d{1,3})\. ", ln)
        elif section == LAYER13_HEADING:
            m = re.match(r"^ +(\d{1,3})\. ", ln)
        else:
            m = None
        if m:
            found.add((PRODUCT, section, int(m.group(1))))
    return found


def covered_keys(entries) -> set:
    keys = set()
    for e in entries:
        if e.source_repo != "umwayi-os":
            continue
        path, heading, n = guidance._parse_source(e.source)
        if path in (BUILDER, PRODUCT):
            keys.add((path, heading if path == PRODUCT else None, n))
    return keys


def uncovered(builder_text: str, product_text: str, entries) -> list:
    rules = scan_builder(builder_text) | scan_product(product_text)
    have = covered_keys(entries) | set(EXCLUDED)
    return sorted(rules - have, key=lambda k: (k[0], str(k[1]), k[2]))


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


class Coverage(unittest.TestCase):
    def test_every_numbered_rule_is_covered_or_excluded(self):
        entries = guidance.load(REPO)
        missing = uncovered(read(BUILDER), read(PRODUCT), entries)
        self.assertEqual(missing, [], "a numbered rule has no guidance entry and is not in EXCLUDED")

    def test_the_scan_finds_the_known_rules(self):
        self.assertEqual({n for _, _, n in scan_builder(read(BUILDER))}, set(range(1, 11)))
        prod = scan_product(read(PRODUCT))
        self.assertEqual({n for _, _, n in prod}, set(range(1, 14)))
        self.assertEqual(len(prod), 13)

    def test_a_new_builder_rule_fails_until_covered(self):
        entries = guidance.load(REPO)
        text = read(BUILDER).rstrip("\n") + "\n11. A new rule.\n"
        self.assertEqual(uncovered(text, read(PRODUCT), entries), [(BUILDER, None, 11)])

    def test_a_new_safety_rule_fails_until_covered(self):
        entries = guidance.load(REPO)
        text = read(PRODUCT)
        marker = "11. Layer 13 never changes"
        self.assertIn(marker, text)
        added = text.replace("  11. Layer 13 never changes", "  14. A new rule.\n  11. Layer 13 never changes")
        self.assertEqual(uncovered(read(BUILDER), added, entries), [(PRODUCT, LAYER13_HEADING, 14)])
        safety = text.replace("\n\n## Exit codes", "\n11. A new safety rule.\n\n## Exit codes")
        self.assertEqual(uncovered(read(BUILDER), safety, entries), [(PRODUCT, SAFETY_HEADING, 11)])

    def test_a_numbered_list_outside_the_rule_sections_is_not_a_rule(self):
        text = read(PRODUCT).replace("## Schedule to Dec 3", "## Schedule to Dec 3\n\n99. not a rule")
        self.assertEqual(uncovered(read(BUILDER), text, guidance.load(REPO)), [])

    def test_excluded_rules_have_reasons_and_are_not_also_covered(self):
        have = covered_keys(guidance.load(REPO))
        rules = scan_builder(read(BUILDER)) | scan_product(read(PRODUCT))
        for key, why in EXCLUDED.items():
            self.assertIn(key, rules, "an excluded rule no longer exists in the file")
            self.assertNotIn(key, have, "an excluded rule also has an entry")
            self.assertTrue(isinstance(why, str) and len(why) >= 20 and "\u2014" not in why)


class Tiers(unittest.TestCase):
    def test_umwayi_os_entry_tiers_and_kinds(self):
        for e in guidance.load(REPO):
            if e.source_repo != "umwayi-os":
                continue
            path, heading, n = guidance._parse_source(e.source)
            if path == BUILDER:
                self.assertEqual(e.tier, 4, e.id)
            elif path == PRODUCT:
                self.assertEqual(e.tier, 2 if n in (5, 10) else 1, e.id)
            if e.id != "one-open-pr-per-task":
                self.assertNotEqual(e.kind, "enforce", e.id)

    def test_only_the_four_checks_exist(self):
        self.assertEqual(sorted(guidance.CHECKS), ["acceptance_checks_present", "consequences_and_undo_present",
                                                   "goal_sentence_present", "one_open_pr"])
        enforced = sorted(e.check for e in guidance.load(REPO) if e.kind == "enforce")
        self.assertEqual(enforced, sorted(guidance.CHECKS))

    def test_texts_are_ours_and_short(self):
        for e in guidance.load(REPO):
            self.assertLessEqual(len(e.text), 200)
            self.assertNotIn("\u2014", e.text)


class IndentedRule(unittest.TestCase):
    def source(self, text: str):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        (Path(d.name) / "r.md").write_text(text, encoding="utf-8")
        return Path(d.name)

    def test_an_indented_rule_is_found_and_the_hash_keeps_the_spaces(self):
        root = self.source("# T\n\n## A\n\n- item\n  3. indented rule  \n")
        import hashlib
        want = hashlib.sha256("  3. indented rule".encode("utf-8")).hexdigest()
        self.assertEqual(guidance.compute_hash(root, "r.md#A#3"), want)

    def test_an_indented_rule_with_another_text_has_another_hash(self):
        a = guidance.compute_hash(self.source("## A\n\n  3. one\n"), "r.md#A#3")
        b = guidance.compute_hash(self.source("## A\n\n  3. two\n"), "r.md#A#3")
        c = guidance.compute_hash(self.source("## A\n\n3. one\n"), "r.md#A#3")
        self.assertEqual(len({a, b, c}), 3)

    def test_a_flush_and_an_indented_rule_of_one_number_in_one_section_is_ambiguous(self):
        root = self.source("## A\n\n3. one\n\n  3. two\n")
        with self.assertRaises(guidance.SourceChanged):
            guidance.compute_hash(root, "r.md#A#3")

    def test_a_flush_rule_keeps_its_old_hash(self):
        import hashlib
        root = self.source("## A\n\n3. one\n")
        self.assertEqual(guidance.compute_hash(root, "r.md#A#3"), hashlib.sha256(b"3. one").hexdigest())

    def test_an_indented_line_in_a_code_fence_is_not_a_rule(self):
        root = self.source("## A\n\n```\n  3. in fence\n```\n")
        with self.assertRaises(UmwayiError):
            guidance.compute_hash(root, "r.md#A#3")


if __name__ == "__main__":
    unittest.main()
