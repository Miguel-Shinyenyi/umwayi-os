"""W19.1: guidance.yaml loader and the first enforce checks (umwayi/guidance.py), `umwayi goal guard`.

Tests first. Every fail closed case of the loader, each enforce check (pass, missing, empty, whitespace only, wrong
type), a hand edited source_hash, the committed guidance.yaml, and the command. Standard library only, a temporary
folder per test.
"""

import contextlib
import hashlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from umwayi import guidance
from umwayi.cli import main
from umwayi.errors import ConfigError, UmwayiError

REPO = Path(__file__).resolve().parents[2]
EM = "\u2014"
DROP = object()

SOURCE_TEXT = """# Title

## Section A

1. first rule of A
2. second rule of A

## Section B

1. first rule of B

```
3. not a rule, inside a fence
```
"""


def sha(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def entry(**kw) -> str:
    d = {
        "id": "goal-sentence-present",
        "source": "rules.md#Section A#1",
        "text": "A task has a goal sentence.",
        "kind": "enforce",
        "check": "goal_sentence_present",
        "applies_to": "task",
        "source_hash": sha("1. first rule of A"),
        "tier": 3,
        "source_repo": "umwayi-os",
    }
    d.update(kw)
    lines = []
    first = True
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, bool):
            shown = "true" if v else "false"
        elif isinstance(v, int):
            shown = str(v)
        elif isinstance(v, list):
            shown = "[" + ", ".join(v) + "]"
        elif isinstance(v, str) and v.startswith("RAW:"):
            shown = v[4:]
        else:
            shown = f'"{v}"'
        lines.append(("  - " if first else "    ") + f"{k}: {shown}")
        first = False
    return "\n".join(lines)


def doc(*entries: str) -> str:
    return "version: 1\nguidance:\n" + "\n".join(entries) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)
        (self.root / "rules.md").write_text(SOURCE_TEXT, encoding="utf-8")

    def write(self, text: str) -> None:
        (self.root / "guidance.yaml").write_text(text, encoding="utf-8")

    def load(self, text: str):
        self.write(text)
        return guidance.load(self.root)


class LoaderFailClosed(Base):
    def test_good_file_loads(self):
        es = self.load(doc(entry()))
        self.assertEqual([e.id for e in es], ["goal-sentence-present"])
        self.assertEqual(es[0].kind, "enforce")

    def test_missing_file_is_ask_first(self):
        with self.assertRaises(guidance.AskFirst):
            guidance.load(self.root)

    def test_unknown_kind(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(kind="maybe")))

    def test_enforce_without_check(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(check=None)))

    def test_enforce_with_unregistered_check(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(check="no_such_check")))

    def test_enforce_with_prompt_line(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(prompt_line="Say it.")))

    def test_advise_needs_prompt_line_and_no_check(self):
        good = entry(kind="advise", check=None, prompt_line="Explain the output in plain words.")
        self.assertEqual(self.load(doc(good))[0].kind, "advise")
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(kind="advise", check=None)))
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(kind="advise", prompt_line="Say it.")))

    def test_owner_has_neither(self):
        self.assertEqual(self.load(doc(entry(kind="owner", check=None)))[0].kind, "owner")
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(kind="owner")))
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(kind="owner", check=None, prompt_line="Say it.")))

    def test_duplicate_id(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(), entry()))

    def test_unknown_key(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(colour="blue")))

    def test_missing_key(self):
        for k in ("id", "source", "text", "kind", "applies_to", "source_hash", "tier", "source_repo"):
            with self.subTest(k=k):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(**{k: None})))

    def test_bad_applies_to(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(applies_to="everything")))

    def test_bad_id(self):
        for bad in ("Goal", "a", "has space", "x" * 60):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(id=bad)))

    def test_text_limits(self):
        for bad in ("short", "x" * 201, "has " + EM + " dash in it", "ctrl\x01char in here"):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(text=bad)))

    def test_bad_hash_shape(self):
        for bad in ("abc", "Z" * 64, sha("1. first rule of A").upper()):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(source_hash=bad)))

    def test_bad_shape_of_file(self):
        for bad in ("", "guidance: []\n", "version: 1\nguidance: x\n", "version: 2\nguidance:\n  - id: a\n",
                    "version: 1\nguidance:\n", "- a\n- b\n", "version: 1\nextra: 1\nguidance:\n" + entry() + "\n",
                    "version: 1\nguidance:\n\t- id: a\n", "version: 1\nguidance:\n  - id: &a x\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(bad)

    def test_yaml_error_does_not_echo_content(self):
        try:
            self.load("version: 1\nguidance:\n  - id: SECRET-VALUE\n    id: again\n")
        except guidance.GuidanceError as e:
            self.assertNotIn("SECRET-VALUE", str(e))

    def test_errors_are_config_errors_with_exit_64(self):
        self.assertTrue(issubclass(guidance.GuidanceError, ConfigError))
        self.assertTrue(issubclass(guidance.AskFirst, UmwayiError))
        self.assertFalse(issubclass(guidance.AskFirst, ConfigError))

    def test_file_too_big_and_not_utf8(self):
        self.write(doc(entry()) + "# " + "x" * 300000 + "\n")
        with self.assertRaises(guidance.GuidanceError):
            guidance.load(self.root)
        (self.root / "guidance.yaml").write_bytes(b"version: 1\nguidance:\n\xff\xfe\n")
        with self.assertRaises(guidance.GuidanceError):
            guidance.load(self.root)

    def test_em_dash_in_file_refused(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry()) + "# a " + EM + " dash\n")

    def test_too_many_entries(self):
        many = [entry(id=f"rule-{i:03d}") for i in range(guidance.MAX_ENTRIES + 1)]
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(*many))


class Tiers(Base):
    def test_tier_is_kept(self):
        self.assertEqual(self.load(doc(entry(tier=4)))[0].tier, 4)
        for t in range(1, 7):
            self.assertEqual(self.load(doc(entry(tier=t)))[0].tier, t)

    def test_missing_tier(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(tier=None)))

    def test_out_of_range_tier(self):
        for bad in (0, 7, -1, 100):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(tier=bad)))

    def test_tier_that_is_not_an_integer(self):
        for bad in ("RAW:3.0", "RAW:three", '"3"', "RAW:true", "RAW:null", "RAW:[3]", "RAW:2.5"):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(tier=bad if bad.startswith("RAW:") else "RAW:" + bad)))

    def test_tier_is_required_for_every_kind(self):
        advise = entry(kind="advise", check=None, prompt_line="Explain the output in plain words.", tier=None)
        owner = entry(kind="owner", check=None, tier=None)
        for e in (advise, owner):
            with self.assertRaises(guidance.GuidanceError):
                self.load(doc(e))

    def test_overrides_are_optional_and_kept(self):
        a = entry(id="rule-aaa", tier=3)
        b = entry(id="rule-bbb", tier=4, overrides=["rule-ccc"])
        c = entry(id="rule-ccc", tier=5)
        es = self.load(doc(a, b, c))
        self.assertEqual(es[0].overrides, ())
        self.assertEqual(es[1].overrides, ("rule-ccc",))

    def test_same_tier_override_is_allowed(self):
        a = entry(id="rule-aaa", tier=3, overrides=["rule-bbb"])
        b = entry(id="rule-bbb", tier=3)
        self.assertEqual(len(self.load(doc(a, b))), 2)

    def test_override_of_a_lower_tier_number_is_refused(self):
        a = entry(id="rule-aaa", tier=4, overrides=["rule-bbb"])
        b = entry(id="rule-bbb", tier=3)
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(a, b))

    def test_override_order_in_the_file_does_not_matter(self):
        a = entry(id="rule-aaa", tier=3)
        b = entry(id="rule-bbb", tier=6, overrides=["rule-aaa"])
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(a, b))
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(b, a))

    def test_bad_overrides(self):
        a = entry(id="rule-aaa", tier=3)
        for label, bad in (("unknown id", ["rule-zzz"]), ("itself", ["rule-bbb"]), ("twice", ["rule-aaa", "rule-aaa"]),
                           ("bad id", ["Bad Id"]), ("not a list", "RAW:rule-aaa"), ("empty item", "RAW:[rule-aaa, ]"),
                           ("number", "RAW:[3]"), ("too many", ["rule-aaa"] * 21)):
            with self.subTest(case=label):
                b = entry(id="rule-bbb", tier=4, overrides=bad)
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(a, b))

    def test_empty_overrides_list_is_fine(self):
        b = entry(id="rule-bbb", tier=4, overrides="RAW:[]")
        self.assertEqual(self.load(doc(b))[0].overrides, ())

    def test_error_does_not_echo_ids(self):
        try:
            self.load(doc(entry(id="rule-aaa", overrides=["secret-name"])))
        except guidance.GuidanceError as e:
            self.assertNotIn("secret-name", str(e))


class Resolve(Base):
    def entries(self):
        adv = dict(kind="advise", check=None, prompt_line="Explain the output in plain words.")
        own = dict(kind="owner", check=None)
        return self.load(doc(
            entry(id="enf-tier3-a", tier=3),
            entry(id="enf-tier3-b", tier=3, check="one_open_pr"),
            entry(id="enf-tier4", tier=4),
            entry(id="adv-tier3", tier=3, **adv),
            entry(id="adv-tier3-b", tier=3, **adv),
            entry(id="adv-tier6", tier=6, **adv),
            entry(id="own-tier2", tier=2, **own),
            entry(id="own-tier3", tier=3, **own),
        ))

    def win(self, a, b):
        return guidance.resolve(self.entries(), a, b).id

    def test_lower_tier_number_wins_either_order(self):
        self.assertEqual(self.win("enf-tier3-a", "enf-tier4"), "enf-tier3-a")
        self.assertEqual(self.win("enf-tier4", "enf-tier3-a"), "enf-tier3-a")

    def test_lower_tier_wins_over_kind(self):
        self.assertEqual(self.win("adv-tier3", "enf-tier4"), "adv-tier3")
        self.assertEqual(self.win("enf-tier4", "adv-tier3"), "adv-tier3")
        self.assertEqual(self.win("own-tier2", "enf-tier3-a"), "own-tier2")
        self.assertEqual(self.win("adv-tier6", "enf-tier4"), "enf-tier4")

    def test_same_tier_enforce_beats_advise(self):
        self.assertEqual(self.win("enf-tier3-a", "adv-tier3"), "enf-tier3-a")
        self.assertEqual(self.win("adv-tier3", "enf-tier3-a"), "enf-tier3-a")

    def test_same_tier_two_enforce_is_ask_me_first(self):
        with self.assertRaises(guidance.AskFirst) as cm:
            self.win("enf-tier3-a", "enf-tier3-b")
        self.assertNotIsInstance(cm.exception, ConfigError)
        self.assertNotIn("\n", str(cm.exception))
        self.assertNotIn("enf-tier3", str(cm.exception))

    def test_same_tier_other_pairs_are_ask_me_first(self):
        for a, b in (("adv-tier3", "adv-tier3-b"), ("own-tier3", "enf-tier3-a"), ("own-tier3", "adv-tier3")):
            with self.subTest(a=a, b=b):
                with self.assertRaises(guidance.AskFirst):
                    self.win(a, b)

    def test_same_entry_wins_over_itself(self):
        self.assertEqual(self.win("enf-tier4", "enf-tier4"), "enf-tier4")

    def test_unknown_id_is_ask_me_first(self):
        for a, b in (("enf-tier4", "nope-nope"), ("nope-nope", "enf-tier4"), ("nope-nope", "nope-nope")):
            with self.subTest(a=a, b=b):
                with self.assertRaises(guidance.AskFirst):
                    self.win(a, b)

    def test_the_answer_is_the_same_both_ways(self):
        es = self.entries()
        for x in es:
            for y in es:
                try:
                    r1 = guidance.resolve(es, x.id, y.id).id
                except guidance.AskFirst:
                    r1 = None
                try:
                    r2 = guidance.resolve(es, y.id, x.id).id
                except guidance.AskFirst:
                    r2 = None
                self.assertEqual(r1, r2)


class SourceHash(Base):
    def test_hand_edited_hash_is_refused_and_asks_the_owner(self):
        with self.assertRaises(guidance.SourceChanged) as cm:
            self.load(doc(entry(source_hash="0" * 64)))
        self.assertIsInstance(cm.exception, guidance.AskFirst)

    def test_edited_source_line_is_refused(self):
        self.load(doc(entry()))
        (self.root / "rules.md").write_text(SOURCE_TEXT.replace("first rule of A", "first rule of A, edited"),
                                            encoding="utf-8")
        with self.assertRaises(guidance.SourceChanged):
            guidance.load(self.root)

    def test_other_lines_may_change(self):
        self.load(doc(entry()))
        (self.root / "rules.md").write_text(SOURCE_TEXT.replace("second rule of A", "another words"),
                                            encoding="utf-8")
        self.assertEqual(len(guidance.load(self.root)), 1)

    def test_source_without_heading(self):
        (self.root / "flat.md").write_text("1. only rule\n2. next\n", encoding="utf-8")
        e = entry(source="flat.md#2", source_hash=sha("2. next"))
        self.assertEqual(len(self.load(doc(e))), 1)

    def test_source_that_cannot_be_found_asks_the_owner(self):
        for src in ("gone.md#1", "rules.md#Section A#9", "rules.md#Section Z#1", "rules.md#Section B#3"):
            with self.subTest(src=src):
                with self.assertRaises(guidance.SourceChanged):
                    self.load(doc(entry(source=src)))

    def test_rule_number_must_be_unique_in_its_scope(self):
        (self.root / "dup.md").write_text("1. one\n1. again\n", encoding="utf-8")
        with self.assertRaises(guidance.SourceChanged):
            self.load(doc(entry(source="dup.md#1", source_hash=sha("1. one"))))

    def test_bad_source_strings(self):
        for src in ("rules.md", "#1", "/etc/passwd#1", "../x.md#1", "a\\b.md#1", "rules.md#x", "rules.md#0",
                    "rules.md#a#b#1", "rules.md##1", "rules.md#Section A#"):
            with self.subTest(src=src):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(source=src)))

    def test_source_that_is_a_link_out_of_the_folder_is_refused(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name) / "o.md").write_text("1. outside\n", encoding="utf-8")
        (self.root / "link.md").symlink_to(Path(outside.name) / "o.md")
        with self.assertRaises(guidance.AskFirst):
            self.load(doc(entry(source="link.md#1", source_hash=sha("1. outside"))))

    def test_fence_lines_are_not_rules(self):
        with self.assertRaises(guidance.SourceChanged):
            self.load(doc(entry(source="rules.md#Section B#3", source_hash=sha("3. not a rule, inside a fence"))))

    def test_error_does_not_echo_source_text(self):
        try:
            self.load(doc(entry(source_hash="0" * 64)))
        except guidance.SourceChanged as e:
            self.assertNotIn("first rule", str(e))


GOOD = {
    "goal": "Add a guidance loader.",
    "consequences": "A bad file blocks the goal flow.",
    "undo": "Revert the pull request.",
    "acceptance_checks": ["The loader refuses a bad file."],
    "open_prs": [],
}


def rec(**kw):
    d = dict(GOOD)
    d.update(kw)
    for k, v in list(d.items()):
        if v is DROP:
            del d[k]
    return d


class Checks(unittest.TestCase):
    def test_registered_names(self):
        self.assertEqual(sorted(guidance.CHECKS), ["acceptance_checks_present", "consequences_and_undo_present",
                                                    "goal_sentence_present", "one_open_pr"])

    def test_all_pass_on_a_good_record(self):
        for name, fn in guidance.CHECKS.items():
            with self.subTest(name=name):
                self.assertIsNone(fn(rec()))

    def test_text_field_checks(self):
        cases = {
            "goal_sentence_present": ["goal"],
            "consequences_and_undo_present": ["consequences", "undo"],
        }
        for name, fields in cases.items():
            for f in fields:
                for label, bad in (("missing", DROP), ("empty", ""), ("spaces", "   "),
                                   ("whitespace", " \t\n\u00a0 "), ("none", None), ("number", 5), ("list", ["x"])):
                    with self.subTest(check=name, field=f, case=label):
                        reason = guidance.CHECKS[name](rec(**{f: bad}))
                        self.assertIsInstance(reason, str)
                        self.assertTrue(reason)
                        self.assertNotIn("\n", reason)

    def test_acceptance_checks(self):
        fn = guidance.CHECKS["acceptance_checks_present"]
        for label, bad in (("missing", DROP), ("empty list", []), ("none", None), ("string", "a check"),
                           ("blank item", ["ok one", "  "]), ("empty item", [""]), ("number item", [3]),
                           ("dict", {"a": "b"}), ("tuple like", "x")):
            with self.subTest(case=label):
                self.assertTrue(fn(rec(acceptance_checks=bad)))
        self.assertIsNone(fn(rec(acceptance_checks=["one", "two"])))

    def test_one_open_pr(self):
        fn = guidance.CHECKS["one_open_pr"]
        self.assertIsNone(fn(rec(open_prs=[])))
        self.assertIsNone(fn(rec(open_prs=[12])))
        self.assertIsNone(fn(rec(open_prs=["12"])))
        for label, bad in (("missing", DROP), ("two", [1, 2]), ("none", None), ("number", 1),
                           ("blank item", [" "]), ("bool item", [True]), ("dict item", [{}])):
            with self.subTest(case=label):
                self.assertTrue(fn(rec(open_prs=bad)))

    def test_a_reason_never_echoes_the_record(self):
        secret = "TOP-SECRET-TEXT"
        for name, fn in guidance.CHECKS.items():
            for r in (rec(goal=[secret], consequences=[secret], undo=[secret], acceptance_checks=[secret, " "],
                          open_prs=[secret, secret])):
                reason = fn(r)
                if reason:
                    self.assertNotIn(secret, reason)

    def test_not_a_dict(self):
        for name, fn in guidance.CHECKS.items():
            for bad in (None, [], "x", 3):
                with self.subTest(check=name, bad=bad):
                    self.assertTrue(fn(bad))


class CheckTask(Base):
    def entries(self):
        e2 = entry(id="consequences-and-undo", check="consequences_and_undo_present", applies_to="task")
        e3 = entry(id="advice-explain", kind="advise", check=None, prompt_line="Explain the output in plain words.")
        e4 = entry(id="owner-batch", kind="owner", check=None)
        e5 = entry(id="release-only", check="one_open_pr", applies_to="release")
        return self.load(doc(entry(), e2, e3, e4, e5))

    def test_pass(self):
        self.assertEqual(guidance.check_task(self.entries(), rec()), [])

    def test_first_refusal_is_reported_in_file_order(self):
        out = guidance.check_task(self.entries(), rec(goal="", undo=""))
        self.assertEqual([i for i, _ in out], ["goal-sentence-present", "consequences-and-undo"])

    def test_advise_and_owner_never_refuse(self):
        es = [e for e in self.entries() if e.kind != "enforce"]
        self.assertEqual(guidance.check_task(es, {}), [])

    def test_release_entry_is_not_run_for_a_task(self):
        out = guidance.check_task(self.entries(), rec(open_prs=[1, 2]))
        self.assertEqual(out, [])

    def test_a_check_that_crashes_refuses(self):
        es = self.entries()
        orig = guidance.CHECKS["goal_sentence_present"]
        guidance.CHECKS["goal_sentence_present"] = lambda r: 1 / 0
        self.addCleanup(guidance.CHECKS.__setitem__, "goal_sentence_present", orig)
        out = guidance.check_task(es, rec())
        self.assertEqual(out[0][0], "goal-sentence-present")


class Committed(unittest.TestCase):
    def test_guidance_yaml_loads_and_has_no_em_dash(self):
        text = (REPO / "guidance.yaml").read_text(encoding="utf-8")
        self.assertNotIn(EM, text)
        es = guidance.load(REPO)
        self.assertTrue(es)
        self.assertEqual(len({e.id for e in es}), len(es))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", e.source_hash) for e in es))
        self.assertTrue(all(1 <= e.tier <= 6 for e in es))

    def test_committed_tiers_follow_the_brief(self):
        es = {e.id: e for e in guidance.load(REPO)}
        for i in ("goal-sentence-present", "consequences-and-undo-present", "acceptance-checks-present"):
            self.assertEqual((es[i].kind, es[i].tier), ("enforce", 3))
        self.assertEqual((es["one-open-pr-per-task"].kind, es["one-open-pr-per-task"].tier), ("enforce", 4))
        for e in es.values():
            if e.kind == "advise":
                self.assertEqual(e.tier, 6)
            if e.kind == "owner":
                self.assertEqual(e.tier, 2)

    def test_committed_hub_entries_use_the_recorded_hashes(self):
        want = {"understanding-first.md": "2f0405e879b6615f34c5168161153363896e26eab43981dc6db1d96b0c1f6bc0",
                "agent-practices.md": "a0086e0806ce824a5ace7a9a9c3d102eaadab07c7644c41f0c7f74565af715be"}
        sources = {}
        for e in guidance.load(REPO):
            if e.source_repo == "hub":
                name, rule = e.source.split("#")
                self.assertEqual(e.source_hash, want[name])
                sources[e.id] = (name, rule)
        self.assertEqual(sources["goal-sentence-present"], ("understanding-first.md", "3"))
        self.assertEqual(sources["consequences-and-undo-present"], ("understanding-first.md", "13"))
        self.assertEqual(sources["record-state-before-change"], ("understanding-first.md", "12"))
        self.assertEqual(sources["check-output-against-goal"], ("understanding-first.md", "4"))
        self.assertEqual(sources["explain-ai-output"], ("understanding-first.md", "1"))
        self.assertEqual(sources["rewrite-broken-base"], ("understanding-first.md", "7"))
        self.assertEqual(sources["batch-interruptions"], ("understanding-first.md", "8"))
        self.assertEqual(sources["acceptance-checks-present"][0], "agent-practices.md")

    def test_a_hand_edited_hash_in_the_committed_file_is_refused(self):
        text = (REPO / "guidance.yaml").read_text(encoding="utf-8")
        mine = [e for e in guidance.load(REPO) if e.source_repo == "umwayi-os"]
        self.assertTrue(mine)
        bad = text.replace(mine[0].source_hash, "0" * 64, 1)
        self.assertNotEqual(bad, text)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "guidance.yaml").write_text(bad, encoding="utf-8")
            for e in mine:
                rel = e.source.split("#")[0]
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes((REPO / rel).read_bytes())
            with self.assertRaises(guidance.SourceChanged):
                guidance.load(root)


class HubEntries(Base):
    HUB_TEXT = "the pretend hub file\n1. a rule\n"

    def hub(self, **kw):
        h = hashlib.sha256(self.HUB_TEXT.encode()).hexdigest()
        d = dict(source_repo="hub", source="core-rules.md#3", source_hash=h)
        d.update(kw)
        return entry(**d)

    def hubdir(self, text=None):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        if text is not None:
            (Path(t.name) / "core-rules.md").write_text(text, encoding="utf-8")
        return t.name

    def test_hub_entry_loads_without_reading_any_file(self):
        es = self.load(doc(self.hub()))
        self.assertEqual((es[0].source_repo, es[0].source), ("hub", "core-rules.md#3"))

    def test_source_repo_is_required_and_closed(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(source_repo=None)))
        for bad in ("private", "HUB", "", "umwayi", "RAW:3"):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(entry(source_repo=bad)))

    def test_hub_source_shapes(self):
        for ok in ("understanding-first.md#13", "agent-practices.md#verification-first"):
            self.assertEqual(len(self.load(doc(self.hub(source=ok)))), 1)
        for bad in ("core-rules.md", "core-rules#3", "../core-rules.md#3", "a/b.md#3", "/core-rules.md#3",
                    "core-rules.md#0", "core-rules.md#", "core-rules.md#A", ".md#3", "core-rules.md#3#4"):
            with self.subTest(bad=bad):
                with self.assertRaises(guidance.GuidanceError):
                    self.load(doc(self.hub(source=bad)))

    def test_hub_hash_shape_is_checked(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(self.hub(source_hash="abc")))

    def test_two_hashes_for_one_hub_file_are_refused(self):
        a = self.hub(id="rule-aaa", source="core-rules.md#1")
        b = self.hub(id="rule-bbb", source="core-rules.md#2", source_hash="1" * 64)
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(a, b))
        c = self.hub(id="rule-bbb", source="core-rules.md#2")
        self.assertEqual(len(self.load(doc(a, c))), 2)

    def test_a_umwayi_os_source_does_not_accept_a_hub_shape_and_the_other_way(self):
        with self.assertRaises(guidance.GuidanceError):
            self.load(doc(entry(source="core-rules.md#verification-first")))

    def test_hub_entry_never_touches_the_source_file_check(self):
        (self.root / "rules.md").unlink()
        self.assertEqual(len(self.load(doc(self.hub()))), 1)

    def test_status_unverified_verified_mismatch(self):
        es = self.load(doc(self.hub(), entry(id="local-rule")))
        self.assertEqual(guidance.hub_status(es, None), {"goal-sentence-present": "unverified",
                                                          "local-rule": "verified"})
        self.assertEqual(guidance.hub_status(es, Path(self.hubdir(self.HUB_TEXT)))["goal-sentence-present"],
                         "verified")
        self.assertEqual(guidance.hub_status(es, Path(self.hubdir(self.HUB_TEXT + "x")))["goal-sentence-present"],
                         "mismatch")
        self.assertEqual(guidance.hub_status(es, Path(self.hubdir()))["goal-sentence-present"], "mismatch")

    def test_hub_file_that_is_a_link_out_of_the_checkout_is_a_mismatch(self):
        d = Path(self.hubdir())
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        (Path(out.name) / "x.md").write_text(self.HUB_TEXT, encoding="utf-8")
        (d / "core-rules.md").symlink_to(Path(out.name) / "x.md")
        es = self.load(doc(self.hub()))
        self.assertEqual(guidance.hub_status(es, d)["goal-sentence-present"], "mismatch")

    def cli(self, *args):
        return run(["guidance", *args], self.root)

    def test_list_shows_unverified_never_verified(self):
        self.write(doc(self.hub(), entry(id="local-rule")))
        code, out, err = self.cli("list")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("goal-sentence-present  enforce  tier 3  hub  unverified", out)
        self.assertIn("local-rule  enforce  tier 3  umwayi-os  verified", out)
        self.assertIn("2 entries, 1 unverified, 0 mismatch.", out)

    def test_list_with_hub_shows_verified_or_asks(self):
        self.write(doc(self.hub()))
        code, out, _ = self.cli("list", "--hub", self.hubdir(self.HUB_TEXT))
        self.assertEqual(code, 0)
        self.assertIn("hub  verified", out)
        self.assertNotIn("unverified", out.split("\n")[0])
        code, _, err = self.cli("list", "--hub", self.hubdir(self.HUB_TEXT + "x"))
        self.assertEqual(code, 3)
        self.assertIn("mismatch", err)

    def test_verify_yes_and_ask_me_first(self):
        self.write(doc(self.hub()))
        code, out, _ = self.cli("verify", "--hub", self.hubdir(self.HUB_TEXT))
        self.assertEqual(code, 0)
        self.assertIn("Yes", out)
        code, out, err = self.cli("verify", "--hub", self.hubdir(self.HUB_TEXT + "changed"))
        self.assertEqual((code, out), (3, ""))
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("Ask me first", err)
        self.assertIn("goal-sentence-present", err)
        self.assertNotIn("pretend", err)

    def test_verify_with_a_missing_hub_file_is_ask_me_first(self):
        self.write(doc(self.hub()))
        self.assertEqual(self.cli("verify", "--hub", self.hubdir())[0], 3)

    def test_verify_usage_and_bad_guidance(self):
        self.write(doc(self.hub()))
        self.assertEqual(self.cli("verify", "--hub", str(self.root / "nope"))[0], 64)
        self.assertEqual(self.cli("verify", "--hub", str(self.root / "guidance.yaml"))[0], 64)
        self.assertEqual(self.cli("verify")[0], 64)
        self.assertEqual(self.cli("list", "--hub", str(self.root / "nope"))[0], 64)
        self.write("version: 1\nguidance: x\n")
        self.assertEqual(self.cli("list")[0], 64)
        self.assertEqual(self.cli("verify", "--hub", self.hubdir(self.HUB_TEXT))[0], 64)
        (self.root / "guidance.yaml").unlink()
        self.assertEqual(self.cli("list")[0], 3)

    def test_verify_with_no_hub_entries_is_yes(self):
        self.write(doc(entry()))
        self.assertEqual(self.cli("verify", "--hub", self.hubdir())[0], 0)

    def test_crash_is_2(self):
        from unittest import mock
        self.write(doc(self.hub()))
        with mock.patch("umwayi.guidance.listing", side_effect=RuntimeError("x")):
            self.assertEqual(self.cli("list")[0], 2)


def run(args, root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--root", str(root)] + args)
    return code, out.getvalue(), err.getvalue()


class Command(Base):
    def setUp(self):
        super().setUp()
        self.write(doc(entry(), entry(id="consequences-and-undo", check="consequences_and_undo_present")))
        self.task = self.root / "task.json"

    def put(self, d):
        self.task.write_text(json.dumps(d), encoding="utf-8")

    def test_good_task_is_yes(self):
        self.put(GOOD)
        code, out, err = run(["goal", "guard", str(self.task)], self.root)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Yes", out)

    def test_missing_field_is_ask_me_first_with_one_line(self):
        d = dict(GOOD)
        del d["undo"]
        self.put(d)
        code, out, err = run(["goal", "guard", str(self.task)], self.root)
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("Ask me first", err)
        self.assertIn("consequences-and-undo", err)

    def test_goal_missing_is_ask_me_first(self):
        d = dict(GOOD, goal="  ")
        self.put(d)
        self.assertEqual(run(["goal", "guard", str(self.task)], self.root)[0], 3)

    def test_unreadable_or_bad_record_is_ask_me_first(self):
        self.assertEqual(run(["goal", "guard", str(self.root / "nope.json")], self.root)[0], 3)
        self.task.write_text("{not json", encoding="utf-8")
        self.assertEqual(run(["goal", "guard", str(self.task)], self.root)[0], 3)
        self.task.write_text("[1]", encoding="utf-8")
        self.assertEqual(run(["goal", "guard", str(self.task)], self.root)[0], 3)

    def test_bad_guidance_is_64_and_changed_source_is_3(self):
        self.put(GOOD)
        self.write("version: 1\nguidance:\n" + entry(kind="maybe") + "\n")
        self.assertEqual(run(["goal", "guard", str(self.task)], self.root)[0], 64)
        self.write(doc(entry(source_hash="0" * 64)))
        code, _, err = run(["goal", "guard", str(self.task)], self.root)
        self.assertEqual(code, 3)
        self.assertIn("Ask me first", err)
        (self.root / "guidance.yaml").unlink()
        self.assertEqual(run(["goal", "guard", str(self.task)], self.root)[0], 3)

    def test_no_file_only_checks_guidance(self):
        code, out, _ = run(["goal", "guard"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("2 entries", out)

    def test_crash_is_2(self):
        self.put(GOOD)
        from unittest import mock
        with mock.patch("umwayi.guidance.guard", side_effect=RuntimeError("x")):
            self.assertEqual(run(["goal", "guard", str(self.task)], self.root)[0], 2)

    def test_goal_docs_still_works(self):
        self.assertEqual(run(["goal", "docs", "check"], REPO)[0], 0)


if __name__ == "__main__":
    unittest.main()
