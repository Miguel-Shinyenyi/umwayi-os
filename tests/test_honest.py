"""Layer 13, slice 4: Honest tension (requirement 13.R8, design.md "Slice 4", tasks L13.4.1 and L13.4.2).

Nothing in layer 13 may claim a state is perfect, safe or proven. This module checks that, and checks the pages that
say it plainly:

  * the note "No state is perfect" is in `docs/corrections.md` and `docs/autonomy.md`, in the exact words of the
    design;
  * the banned list (13.R8.2) finds no claim in the two pages, the layer 13 items of KNOWN-LIMITS, the `--help` of
    every layer 13 command built so far, the captured output and the logbook entries of a real run of those
    commands, and the messages in the layer 13 modules; the note itself is removed by its exact sentence first;
  * the scanner is not blind: a planted `guaranteed` is found in a copy of each page, in a planted command output
    and in the output of a real umwayi command; every word of the list is found, in any case and across a line break;
  * the stop criteria table lists exactly the rows of 13.R8.3 and 13.R8.4, each with the words that make it true;
  * every KNOWN-LIMITS item of the slices built exists, once, and the numbers the design planned but did not use
    are stated, not silently skipped.

The commands run as real child processes in a temporary root, with HOME in the temporary folder. Standard library
only, no network.
"""

import json
import re
import subprocess
import sys
import unittest

from tests.courts_support import REPO, TODAY, CourtsCase, rule, rules_file

DOCS = REPO / "docs"
CORRECTIONS = DOCS / "corrections.md"
AUTONOMY = DOCS / "autonomy.md"
KNOWN_LIMITS = DOCS / "KNOWN-LIMITS.md"

# 13.R8.2: the words of a claim of perfection or proof. Matched on lowercase text with white space made one space.
BANNED = ("guarantee", "guaranteed", "foolproof", "tamper proof", "tamper-proof", "unbreakable", "unhackable",
          "cannot fail", "perfectly", "100% safe")

# design.md, "Slice 4": the plain note, word for word. It is removed by this exact text before the search.
NOTE = ("The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be "
        "wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can "
        "be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first "
        "when it is not sure. It does not make any state perfect, and nothing in these pages says it does.")

# the layer 13 commands built so far (L13.1 to L13.3): the argument vector of their --help and one option each
HELP = [
    (["rules", "--help"], "due"),
    (["rules", "due", "--help"], "--within"),
    (["decision", "--help"], "reopen"),
    (["decision", "reopen", "--help"], "--reason"),
    (["queue", "answer", "--help"], "--revisit-if"),
    (["petition", "--help"], "--helper"),
]

# 13.R8.3 (the build) and 13.R8.4 (run time): the rows of the stop criteria table of docs/corrections.md, each with
# the words its row must hold, and the rows of docs/autonomy.md (run time only)
BUILD_ROWS = {
    "13.R8.3 (a)": ["Python 3.10 to 3.13", "docs are not current"],
    "13.R8.3 (b)": ["Nov 28", "specified, not built"],
    "13.R8.3 (c)": ["Nov 29 to Dec 2", "defect that a test finds"],
    "13.R8.3 (d)": ["earlier test", "13.R13.6"],
    "13.R8.3 (e)": ["owner", "slices before it stay"],
}
RUN_ROWS = {
    "13.R8.4 (a)": ["off by default", "enabled: false"],
    "13.R8.4 (b)": ["rejected", "reverted", "cooldown"],
    "13.R8.4 (c)": ["Ask me first", "not intact"],
    "13.R8.4 (d)": ["kill switch"],
}
PART_ROWS = ["an election", "a reopen", "a petition"]

# KNOWN-LIMITS items of the slices built so far: the number and a word its title must hold
BUILT_ITEMS = {160: "review_by", 161: "clock", 162: "hash", 163: "revisit", 192: "etition", 193: "weakening",
               194: "listed", 195: "dry run"}
# planned in design.md for the petition and rules log limits, but written as 192 and 193: not used
UNUSED_ITEMS = (164, 165)


def normal(text: str) -> str:
    return " ".join(text.lower().split())


def without_note(text: str, note: str = NOTE) -> str:
    """The text with the plain note taken out, found by its exact sentence (white space made one space)."""
    flat = " ".join(text.split())
    return flat.replace(" ".join(note.split()), "")


def find_banned(text: str, note: str = NOTE) -> list:
    """The banned words found in text, after the note is removed. Empty when there are none."""
    flat = normal(without_note(text, note))
    return [w for w in BANNED if re.search(r"(?<![a-z0-9])" + re.escape(w), flat)]


def section(text: str, heading: str) -> str:
    """From the line `heading` to the next heading of the same or a higher level."""
    level = heading.split(" ")[0]
    lines = text.split("\n")
    start = lines.index(heading)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        m = re.match(r"(#+) ", lines[i])
        if m and len(m.group(1)) <= len(level):
            end = i
            break
    return "\n".join(lines[start:end])


def table_rows(text: str) -> list:
    """The cells of every body row of the first table in text."""
    rows = []
    for line in text.split("\n"):
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(set(c) <= set("- :") for c in cells):
                rows.append(cells)
    return rows[1:]  # without the header


def layer_13_limits() -> str:
    """The layer 13 sections of KNOWN-LIMITS.md, by their headings."""
    text = KNOWN_LIMITS.read_text(encoding="utf-8")
    out = []
    parts = re.split(r"(?m)^(?=## )", text)
    for part in parts:
        if part.startswith("## Layer 13"):
            out.append(part)
    return "\n".join(out)


class Scanner(unittest.TestCase):
    """The banned list finds what it must, and only that."""

    def test_every_word_is_found_in_any_case_and_across_a_line_break(self):
        for word in BANNED:
            for form in (word, word.upper(), word.capitalize(), word.replace(" ", "\n  ")):
                with self.subTest(word=word, form=form[:12]):
                    self.assertIn(word, find_banned(f"This state is {form} for the owner."))

    def test_a_longer_form_of_a_word_is_found(self):
        for text in ("It guarantees nothing", "the guaranteed result", "It is unbreakable.", "This works perfectly."):
            with self.subTest(text=text):
                self.assertTrue(find_banned(text), text)

    def test_plain_words_are_not_found(self):
        for text in ("It does not make any state perfect.", "The check is imperfect.", "A safe default.",
                     "A tamper check and a hash chain.", "Nothing is promised.", "It can fail, and then it asks."):
            with self.subTest(text=text):
                self.assertEqual(find_banned(text), [], text)

    def test_the_note_is_taken_out_by_its_exact_sentence_only(self):
        self.assertEqual(find_banned("Intro.\n\n" + NOTE + "\n\nMore."), [])
        # white space inside the note does not matter
        self.assertEqual(find_banned(NOTE.replace(". ", ".\n")), [])
        # a banned word next to the note, or a note with a changed word, is still found
        self.assertEqual(find_banned(NOTE + " It is guaranteed."), ["guarantee", "guaranteed"])  # both list entries
        self.assertTrue(find_banned(NOTE.replace("perfect,", "perfect, tamper-proof,")))
        self.assertTrue(find_banned(NOTE.replace("It does not make", "It makes") + " This state is foolproof."))

    def test_the_exclusion_is_by_the_exact_sentence_and_nothing_else(self):
        """The real note holds no banned word, so the exclusion is tried with a note that does (13.R8.2)."""
        note = "Nothing in this layer is guaranteed, and no state is foolproof."
        page = f"Intro.\n\n### No state is perfect\n\n{note}\n\nOutro.\n"
        self.assertEqual(find_banned(page, note=note), [])  # the note's own words are not a claim
        self.assertEqual(find_banned(page), ["guarantee", "guaranteed", "foolproof"])  # without the exclusion
        self.assertEqual(find_banned(page.replace("Outro.", "Outro, guaranteed."), note=note), ["guarantee", "guaranteed"])
        self.assertEqual(find_banned(page.replace("foolproof", "very foolproof"), note=note),
                         ["guarantee", "guaranteed", "foolproof"])  # one changed word: not the exact sentence

    def test_the_list_is_the_one_of_the_requirement(self):
        src = (REPO / ".kiro" / "specs" / "umwayi-os" / "requirements.md").read_text(encoding="utf-8")
        line = next(l for l in src.split("\n") if l.startswith("2. **Nothing claims otherwise.**"))
        listed = re.findall(r"`([^`]+)`", line.split("uses a claim of perfection or proof:")[1])
        self.assertEqual(sorted(listed), sorted(BANNED))


class PagesTests(unittest.TestCase):
    def setUp(self):
        self.pages = {p.name: p.read_text(encoding="utf-8") for p in (CORRECTIONS, AUTONOMY)}

    def test_the_exact_note_is_in_both_pages_under_its_heading(self):
        for name, text in self.pages.items():
            with self.subTest(page=name):
                self.assertIn("\n### No state is perfect\n", text)
                body = " ".join(section(text, "### No state is perfect").split())
                self.assertIn(NOTE, body)
                self.assertEqual(" ".join(text.split()).count(NOTE), 1, "the note must be in the page once")

    def test_the_note_says_what_13_R8_1_asks(self):
        for needle in ("correct itself and to be safe", "a way to be wrong", "visible and dated",
                       "falls back to Ask me first when it is not sure", "does not make any state perfect"):
            self.assertIn(needle, NOTE)

    def test_no_claim_in_the_pages(self):
        for name, text in self.pages.items():
            with self.subTest(page=name):
                self.assertEqual(find_banned(text), [])

    def test_a_planted_word_is_found_in_a_copy_of_each_page(self):
        for name, text in self.pages.items():
            with self.subTest(page=name):
                for planted in ("\nThe hash chain is guaranteed to hold.\n", "\nThis page is tamper-proof.\n"):
                    self.assertEqual(find_banned(text), [])
                    self.assertTrue(find_banned(text + planted), planted)
                    # in the middle of the note's own section, next to the exact note
                    marker = "### No state is perfect\n"
                    self.assertTrue(find_banned(text.replace(marker, marker + "It is foolproof.\n\n", 1)))

    def test_no_claim_in_the_layer_13_items_of_known_limits(self):
        text = layer_13_limits()
        self.assertIn("### 160.", text)
        self.assertEqual(find_banned(text), [])

    def test_no_claim_in_the_other_pages_of_layer_13(self):
        for name in ("rules.md", "queue.md", "logbook.md", "exit-codes.md"):
            with self.subTest(page=name):
                self.assertEqual(find_banned((DOCS / name).read_text(encoding="utf-8")), [])

    def test_the_pages_have_no_em_dash(self):
        for name, text in self.pages.items():
            self.assertNotIn("\u2014", text, name)


class StopCriteriaTests(unittest.TestCase):
    def table(self, path, heading):
        return table_rows(section(path.read_text(encoding="utf-8"), heading))

    def test_the_corrections_table_lists_exactly_the_rows_of_13_R8_3_and_13_R8_4(self):
        rows = self.table(CORRECTIONS, "### Stop criteria")
        keyed = {r[0]: r for r in rows if r[0].startswith("13.R8")}
        self.assertEqual(list(keyed), list(BUILD_ROWS) + list(RUN_ROWS))
        self.assertEqual(len(keyed), 9)
        for key, words in {**BUILD_ROWS, **RUN_ROWS}.items():
            with self.subTest(row=key):
                self.assertEqual(len(keyed[key]), 4, keyed[key])
                for w in words:
                    self.assertIn(w, " ".join(keyed[key][1:]))
        # the rows of the three built parts that have no stop of their own stay, in the words of the design
        parts = [r[0] for r in rows if not r[0].startswith("13.R8")]
        self.assertEqual(parts, PART_ROWS)

    def test_every_row_has_four_filled_cells_and_no_claim(self):
        for path in (CORRECTIONS, AUTONOMY):
            for row in self.table(path, "### Stop criteria"):
                with self.subTest(page=path.name, row=row[0]):
                    self.assertEqual(len(row), 4)
                    self.assertTrue(all(row), row)
                    self.assertEqual(find_banned(" ".join(row)), [])

    def test_the_autonomy_table_lists_the_run_time_rows_of_13_R8_4(self):
        rows = self.table(AUTONOMY, "### Stop criteria")
        keyed = {r[0]: r for r in rows if r[0].startswith("13.R8")}
        self.assertEqual(list(keyed), list(RUN_ROWS))
        for key, words in RUN_ROWS.items():
            with self.subTest(row=key):
                for w in words:
                    self.assertIn(w, " ".join(keyed[key][1:]))
        # the design's last row: graded autonomy by itself stops on its own gates
        own = [r for r in rows if not r[0].startswith("13.R8")]
        self.assertEqual([r[0] for r in own], ["graded autonomy, by itself"])
        for w in ("cooldown", "daily cap", "not intact", "kill switch"):
            self.assertIn(w, " ".join(own[0]))

    def test_the_two_pages_say_the_same_about_the_run_time_rows(self):
        a = {r[0]: r[2] for r in self.table(CORRECTIONS, "### Stop criteria") if r[0] in RUN_ROWS}
        b = {r[0]: r[2] for r in self.table(AUTONOMY, "### Stop criteria") if r[0] in RUN_ROWS}
        self.assertEqual(a, b)

    def test_the_pages_say_what_is_built(self):
        text = CORRECTIONS.read_text(encoding="utf-8")
        self.assertIn("Honest tension (L13.4", text)
        self.assertNotIn("Honest tension and graded autonomy are specified, not built", text)
        self.assertIn("graded autonomy", AUTONOMY.read_text(encoding="utf-8").lower())
        self.assertIn("Specified, not built", AUTONOMY.read_text(encoding="utf-8"))


class KnownLimitsTests(unittest.TestCase):
    def setUp(self):
        self.text = KNOWN_LIMITS.read_text(encoding="utf-8")
        self.items = re.findall(r"(?m)^### (\d+)\. (.+)$", self.text)

    def test_every_item_of_the_built_slices_exists_once_with_a_title(self):
        numbers = [int(n) for n, _ in self.items]
        titles = {int(n): t for n, t in self.items}
        self.assertEqual(len(numbers), len(set(numbers)), "a KNOWN-LIMITS number is used twice")
        for n, word in BUILT_ITEMS.items():
            with self.subTest(item=n):
                self.assertIn(n, titles)
                self.assertIn(word.lower(), (titles[n] + " " + self.item_body(n)).lower())
                self.assertTrue(len(self.item_body(n)) > 80, "the item has no text")

    def item_body(self, n):
        m = re.search(rf"(?ms)^### {n}\. .*?\n(.*?)(?=^### |^## |\Z)", self.text)
        return m.group(1).strip() if m else ""

    def test_the_layer_13_items_sit_in_layer_13_sections(self):
        sections = {m.group(1): m.group(2) for m in re.finditer(r"(?ms)^## (Layer 13[^\n]*)\n(.*?)(?=^## |\Z)",
                                                                self.text)}
        found = sorted(int(n) for body in sections.values() for n in re.findall(r"(?m)^### (\d+)\.", body))
        self.assertEqual(found, sorted(BUILT_ITEMS))

    def test_the_planned_numbers_that_are_not_used_are_not_there_and_the_pages_say_so(self):
        numbers = {int(n) for n, _ in self.items}
        # in the paragraph that follows the note, not only in the decisions log
        text = " ".join(section(CORRECTIONS.read_text(encoding="utf-8"), "### No state is perfect").split())
        for n in UNUSED_ITEMS:
            self.assertNotIn(n, numbers)
        self.assertIn("164 and 165 are not used", text)
        for needle in ("items 192 and 193", "166 to 170", "graded autonomy"):
            self.assertIn(needle, text)

    def test_the_numbers_after_the_built_ones_are_free_for_the_next_slice(self):
        numbers = {int(n) for n, _ in self.items}
        self.assertFalse(numbers & set(range(166, 180)), "166 to 179 are left for L13.5 and later")

    def test_the_corrections_page_names_the_items_of_each_slice(self):
        text = " ".join(section(CORRECTIONS.read_text(encoding="utf-8"), "### No state is perfect").split())
        for needle in ("Elections added 160 and 161", "Reversal added 162 and 163", "Courts added 192 to 195"):
            self.assertIn(needle, text)

    def test_items_say_what_13_R8_5_asks_for_the_built_parts(self):
        # review_by depends on the owner renewing honestly (160); the others of 13.R8.5 belong to graded autonomy
        self.assertIn("renewing honestly", self.text)
        text = " ".join(AUTONOMY.read_text(encoding="utf-8").split())
        for needle in ("statistic of the past", "same user", "owner's record"):
            self.assertIn(needle, text)


class OutputTests(CourtsCase):
    """The captured output and the logbook of a real run of every layer 13 command built so far."""

    RULES = rules_file(
        rule("old-yes", "yes", "read", review_by="2026-11-01"),
        rule("ok-yes", "yes", "list"),
        rule("no-money", "no", "payment"),
        rule("ask-deploy", "ask", "deploy"),
    )

    def setUp(self):
        super().setUp()
        self.write_rules(self.RULES)
        self.captured = []

    def run_cmd(self, *args, code=None, **kw):
        r = self.u(*args, **kw)
        self.captured.append((args, r.returncode, r.stdout, r.stderr))
        if code is not None:
            self.assertEqual(r.returncode, code, (args, r.stdout, r.stderr))
        return r

    def acceptance_run(self):
        """Every layer 13 command built so far, in every way it answers: done, refused, usage error."""
        u = self.run_cmd
        u("queue", "add", "--kind", "decision", "Pick a name", code=0)
        u("queue", "add", "--kind", "decision", "Pick a colour", code=0)
        u("logbook", "seal", "--chain", "--by", "Owner", code=0)
        u("queue", "answer", "Q-0001", "--answer", "Use umwayi", "--revisit-if", "the name is taken", code=0)
        u("queue", "answer", "Q-0002", "--answer", "Blue", code=64)  # a decision needs --revisit-if
        u("queue", "answer", "Q-0002", "--answer", "Blue", "--revisit-if", "none", code=0)
        u("check", json.dumps({"type": "read"}), code=3)  # old-yes lapsed: an election fallback
        u("check", json.dumps({"type": "read"}), "--json", code=3)
        u("check", json.dumps({"type": "payment"}), code=2)
        u("rules", "due", code=3)
        u("rules", "due", "--within", "400", code=3)
        u("rules", "due", "--within", "x", code=64)
        u("decision", "reopen", "Q-0001", "--reason", "New facts", "--by", "Owner", code=0)
        u("decision", "reopen", "Q-0001", "--reason", "Again", "--by", "Owner", code=1)  # already reopened
        u("decision", "reopen", "Q-0099", "--reason", "No such", "--by", "Owner", code=1)
        u("decision", "reopen", "Q-1", "--reason", "Bad id", "--by", "Owner", code=64)
        u("petition", "no-money", "--helper", "steward", "--reason", "It blocks a safe read.", code=0)
        u("petition", "no-money", "--helper", "steward", "--reason", "Again.", code=0)  # already open
        u("petition", "ok-yes", "--helper", "steward", "--reason", "A Yes.", code=1)
        u("petition", "no-money", "--helper", "Bad Name", "--reason", "x", code=64)
        u("queue", "list", code=0)
        u("logbook", "verify", code=0)
        # a changed rules file: the rules change log writes its entry
        self.write_rules(self.RULES.replace("    verdict: no\n", "    verdict: yes\n", 1))
        u("check", json.dumps({"type": "payment"}), code=0)
        u("logbook", "verify", code=0)

    def test_the_output_and_the_logbook_of_a_real_run_hold_no_claim(self):
        self.acceptance_run()
        self.assertGreaterEqual(len(self.captured), 24)
        for args, code, out, err in self.captured:
            with self.subTest(command=" ".join(args[:3]), code=code):
                self.assertEqual(find_banned(out + "\n" + err), [], out + err)
        log = self.logtext()
        self.assertEqual(find_banned(log), [])
        sources = {b["source"] for b in self.entries()}
        for s in ("umwayi rules", "umwayi check", "umwayi decision reopen", "umwayi petition", "umwayi queue answer"):
            self.assertIn(s, sources)
        self.assertGreaterEqual(len(self.entries()), 10)

    def test_the_run_covered_what_it_claims(self):
        self.acceptance_run()
        text = "\n".join(out + err for _a, _c, out, err in self.captured)
        for needle in ("Election fallbacks: old-yes", "lapsed", "Reopened Q-0001 as", "Already open, nothing added",
                       "only a No rule can be petitioned", "--revisit-if", "rules.yaml changed"):
            self.assertIn(needle, text + self.logtext())
        codes = {c for _a, c, _o, _e in self.captured}
        self.assertEqual(codes, {0, 1, 2, 3, 64})

    def test_a_planted_word_in_a_command_output_is_found(self):
        """The same capture the run above uses, on a command that prints a planted claim."""
        r = subprocess.run([sys.executable, "-c", "print('The rules are guaranteed.')"], capture_output=True, text=True)
        self.assertIn("guaranteed", find_banned(r.stdout + r.stderr))
        clean = subprocess.run([sys.executable, "-c", "print('The rules are read.')"], capture_output=True, text=True)
        self.assertEqual(find_banned(clean.stdout), [])

    def test_a_planted_word_in_the_output_of_a_real_umwayi_command_is_found(self):
        self.write_rules(rules_file(rule("planted", "yes", "read", text="This answer is guaranteed safe.")))
        r = self.run_cmd("check", json.dumps({"type": "read"}), "--no-log", code=0)
        self.assertEqual(find_banned(r.stdout), ["guarantee", "guaranteed"])
        self.assertEqual(find_banned(self.run_cmd("rules", "due", code=0).stdout), [])

    def test_a_planted_word_in_the_logbook_is_found(self):
        self.acceptance_run()
        self.assertEqual(find_banned(self.logtext() + "- Added: this is tamper-proof\n"), ["tamper-proof"])

    def test_a_planted_word_in_a_petition_reason_reaches_queue_md_and_the_listing_only(self):
        """The reason is the helper's own text, untrusted. The scanner finds it where it shows, and it is not in the
        logbook or in the petition command's own output."""
        r = self.run_cmd("petition", "no-money", "--helper", "steward", "--reason", "This is foolproof.", code=0)
        self.assertEqual(find_banned(r.stdout + r.stderr), [])
        self.assertEqual(find_banned(self.logtext()), [])
        self.assertEqual(find_banned(self.q.read_text(encoding="utf-8")), ["foolproof"])
        self.assertEqual(find_banned(self.run_cmd("queue", "list", code=0).stdout), ["foolproof"])


class HelpTests(CourtsCase):
    def test_the_help_of_every_layer_13_command_built_so_far(self):
        for argv, option in HELP:
            with self.subTest(command=" ".join(argv)):
                r = self.u(*argv)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(option, r.stdout)
                self.assertTrue(r.stdout.startswith("usage: umwayi"))
                self.assertEqual(find_banned(r.stdout + r.stderr), [])
                self.assertNotIn("\u2014", r.stdout)

    def test_a_planted_word_in_a_help_text_is_found(self):
        r = self.u("petition", "--help")
        self.assertEqual(find_banned(r.stdout), [])
        self.assertEqual(find_banned(r.stdout + "\n  --safe   a perfectly safe option\n"), ["perfectly"])

    def test_the_list_of_commands_is_the_list_of_the_slices_built(self):
        r = self.u("--help")
        for name in ("petition", "decision", "rules"):
            self.assertIn(name, r.stdout)
        built = {" ".join(argv[:-1]) for argv, _o in HELP}
        self.assertEqual(built, {"rules", "rules due", "decision", "decision reopen", "queue answer", "petition"})
        # no layer 13 command that is not built yet answers --help
        for name in ("autonomy",):
            self.assertNotEqual(self.u(name, "--help").returncode, 0, name)


class SourceTests(unittest.TestCase):
    """The messages in the modules of layer 13 are text too."""

    MODULES = ("elections.py", "decisions.py", "rulelog.py", "petition.py")

    def test_no_claim_in_the_layer_13_modules(self):
        for name in self.MODULES:
            with self.subTest(module=name):
                self.assertEqual(find_banned((REPO / "umwayi" / name).read_text(encoding="utf-8")), [])

    def test_no_claim_in_the_example_rules_of_the_adapters(self):
        for adapter in ("claude_code", "kiro", "stdio"):
            path = REPO / "adapters" / adapter / "rules.example.yaml"
            with self.subTest(adapter=adapter):
                self.assertEqual(find_banned(path.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
