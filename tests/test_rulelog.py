"""Layer 13, slice 3: the rules change log (requirement 13.R7, design.md "Slice 3", tasks L13.3.1 and L13.3.2).

Every check, and every other command that asks the rules, notices when the bytes of rules.yaml differ from the last
version that was logged. Before the new rules are used for the first time one `umwayi rules` entry is written: the
SHA-256 of the file, the rule counts, the ids added and removed, and every changed verdict or review_by. It holds no
rule title, text or cause. If that entry cannot be written, the new rules give No and Ask me first only: every Yes
becomes Ask me first. A No stays a No.

Planted faults of this part: the entry written after the rules are used (the order in LOGBOOK.md), a logbook that
cannot take the entry (the lock held, a broken chain, a hand edit), and a crash in the write.
"""

import ast
import sys

from tests.courts_support import (EM_DASH, REPO, RULES_CHECKED_HEAD, RULES_NOT_DONE, RULES_SOURCE, TODAY, CourtsCase,
                                  fullmatch, rule, rules_file, sha, snapshot)
from tests.helpers import hold_logbook_lock

SENTINELS = ("SENTINEL-RULE-TITLE-91", "SENTINEL-RULE-TEXT-91", "SENTINEL-RULE-CAUSE-91")
PAY = {"type": "payment"}
READ = {"type": "read"}
ASKED = {"type": "deploy"}

BASE = rules_file(
    rule("no-money", "no", "payment", title=SENTINELS[0], text=SENTINELS[1], cause=SENTINELS[2]),
    rule("ok-read", "yes", "read"),
    rule("ask-deploy", "ask", "deploy"),
)
STATE = "no-money no; ok-read yes; ask-deploy ask"


class Base(CourtsCase):
    def setUp(self):
        super().setUp()
        self.write_rules(BASE)

    def logged_base(self):
        """One check, so the rules of BASE are logged."""
        self.assertEqual(self.check(READ).returncode, 0)
        self.assertEqual(len(self.rule_entries()), 1)


# ============================================================ the baseline and "no change, no entry"


class BaselineTests(Base):
    def test_the_first_check_logs_the_rules_before_its_own_entry(self):
        r = self.check(READ)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [first, second] = self.entries()
        self.assertEqual((first["source"], second["source"]), (RULES_SOURCE, "umwayi check"))
        self.assertEqual(first["date"], TODAY)
        self.assertEqual(first["added"], f"rules.yaml first logged (sha256 {sha(self.rules_path.read_bytes())}); rules 3")
        self.assertEqual(first["checked"], RULES_CHECKED_HEAD + STATE)
        self.assertEqual(first["not_done"], RULES_NOT_DONE)
        self.assertEqual(self.u("logbook", "verify").returncode, 0)

    def test_the_check_entry_itself_is_the_same_bytes_as_before_layer_13(self):
        self.check(READ, "--date", TODAY)
        check = self.entries()[-1]
        self.assertEqual(check["added"], "Rule ok-read gave Yes; action type: read")
        self.assertEqual(check["checked"], "action read as a JSON object without duplicate keys: yes; rules.yaml "
                                           "loaded: yes (3 rules); rules matched: ok-read")

    def test_the_json_answer_has_no_new_key(self):
        code, data = self.check_json(READ)
        self.assertEqual((code, sorted(data)), (0, sorted(["answer", "rule_id", "reason", "matched", "rules_ok",
                                                           "action_ok", "logged", "kill_switch"])))

    def test_an_unchanged_file_is_not_logged_again(self):
        self.logged_base()
        for action in (READ, PAY, ASKED, READ):
            self.check(action)
        self.assertEqual(len(self.rule_entries()), 1)
        self.assertEqual(self.sources()[1:], ["umwayi check"] * 5)

    def test_no_rule_text_is_logged(self):
        self.check(PAY)
        for s in SENTINELS:
            self.assertNotIn(s, self.logtext())
        self.assertEqual(self.check(PAY).returncode, 2)  # the rule is still used: its text is in the answer only

    def test_a_review_by_is_in_the_state(self):
        self.write_rules(rules_file(rule("report-yes", "yes", "read", review_by="2026-12-01"), rule("no-x", "no", "x")))
        self.check(READ)
        self.assertEqual(self.rule_entries()[0]["checked"],
                         RULES_CHECKED_HEAD + "report-yes yes review_by 2026-12-01; no-x no")

    def test_an_empty_rules_list_is_logged_too(self):
        self.write_rules("rules: []\n")
        self.assertEqual(self.check(READ).returncode, 3)
        [e] = self.rule_entries()
        self.assertEqual((e["added"], e["checked"]),
                         (f"rules.yaml first logged (sha256 {sha(b'rules: []' + chr(10).encode())}); rules 0",
                          RULES_CHECKED_HEAD + "no rules"))

    def test_a_rules_file_that_does_not_parse_is_not_logged(self):
        self.logged_base()
        self.write_rules(BASE + "  - id: broken\n")
        code, data = self.check_json(READ)
        self.assertEqual((code, data["answer"], data["rules_ok"]), (3, "Ask me first", False))
        self.assertEqual(len(self.rule_entries()), 1)

    def test_the_entry_is_chained_when_the_chain_has_started(self):
        self.logged_base()
        self.assertEqual(self.u("logbook", "seal", "--chain", "--by", "Owner").returncode, 0)
        self.write_rules(BASE + rule("new-yes", "yes", "new"))
        self.check(READ)
        e = self.rule_entries()[-1]
        self.assertIsNotNone(e["chain"])
        self.assertEqual(self.u("logbook", "verify").returncode, 0)


# ============================================================ a change, logged before use


class ChangeTests(Base):
    def test_a_weakened_no_is_logged_before_the_check_that_uses_it(self):
        """The weakening of no-money to yes (L13-Q11: logged and used at once). The entry order is the proof."""
        self.logged_base()
        self.write_rules(BASE.replace("    verdict: no\n", "    verdict: yes\n", 1))
        new_sha = sha(self.rules_path.read_bytes())
        code, data = self.check_json(PAY)
        self.assertEqual((code, data["answer"], data["rule_id"]), (0, "Yes", "no-money"))
        tail = self.entries()[-2:]
        self.assertEqual([b["source"] for b in tail], [RULES_SOURCE, "umwayi check"])
        self.assertEqual(tail[0]["added"], f"rules.yaml changed (sha256 {new_sha}); rules 3 to 3; "
                                           "changed no-money verdict no to yes")
        self.assertEqual(tail[0]["checked"], RULES_CHECKED_HEAD + "no-money yes; ok-read yes; ask-deploy ask")
        self.assertEqual(tail[1]["added"], "Rule no-money gave Yes; action type: payment")
        for s in SENTINELS:
            self.assertNotIn(s, self.logtext())
        self.check(PAY)
        self.assertEqual(len(self.rule_entries()), 2, "the next check logged the same change again")

    def test_added_removed_and_changed_ids(self):
        self.logged_base()
        self.write_rules(rules_file(
            rule("no-money", "ask", "payment"),
            rule("ask-deploy", "ask", "deploy"),
            rule("new-one", "yes", "a"),
            rule("new-two", "no", "b"),
        ))
        self.check(READ)
        e = self.rule_entries()[-1]
        self.assertEqual(e["added"], f"rules.yaml changed (sha256 {sha(self.rules_path.read_bytes())}); rules 3 to 4; "
                                     "added new-one, new-two; removed ok-read; changed no-money verdict no to ask")

    def test_a_review_by_added_and_moved(self):
        self.logged_base()
        self.write_rules(BASE.replace("    verdict: yes\n", "    verdict: yes\n    review_by: 2026-12-01\n", 1))
        self.check(ASKED)
        self.assertTrue(self.rule_entries()[-1]["added"].endswith("; changed ok-read review_by none to 2026-12-01"))
        self.write_rules(BASE.replace("    verdict: yes\n", "    verdict: yes\n    review_by: 2027-01-01\n", 1))
        self.check(ASKED)
        self.assertTrue(self.rule_entries()[-1]["added"].endswith(
            "; changed ok-read review_by 2026-12-01 to 2027-01-01"))
        self.write_rules(BASE)
        self.check(ASKED)
        self.assertTrue(self.rule_entries()[-1]["added"].endswith("; changed ok-read review_by 2027-01-01 to none"))

    def test_a_comment_spacing_or_order_only_edit_logs_no_rule_changed(self):
        self.logged_base()
        for text in ("# a comment\n" + BASE, BASE + "\n\n",
                     rules_file(rule("ok-read", "yes", "read"), rule("ask-deploy", "ask", "deploy"),
                                rule("no-money", "no", "payment", title=SENTINELS[0], text=SENTINELS[1],
                                     cause=SENTINELS[2]))):
            with self.subTest(text=text[:12]):
                self.write_rules(text)
                self.check(READ)
                e = self.rule_entries()[-1]
                self.assertEqual(e["added"], f"rules.yaml changed (sha256 {sha(text.encode())}); rules 3 to 3; "
                                             "no rule changed")

    def test_going_back_to_an_older_file_is_a_change_too(self):
        self.logged_base()
        self.write_rules(BASE.replace("    verdict: no\n", "    verdict: yes\n", 1))
        self.check(READ)
        self.write_rules(BASE)
        self.check(READ)
        self.assertTrue(self.rule_entries()[-1]["added"].endswith("; changed no-money verdict yes to no"))
        self.assertEqual(len(self.rule_entries()), 3)

    def test_a_rules_entry_in_another_shape_is_not_read(self):
        """A forged entry with the right hash but the wrong shape does not count as the logged version."""
        from umwayi import logbook
        logbook.append(self.root, logbook.Entry(TODAY, RULES_SOURCE, f"rules.yaml first logged (sha256 "
                                                f"{sha(self.rules_path.read_bytes())}) by hand", "x", "y"))
        self.check(READ)
        self.assertEqual(len(self.rule_entries()), 2)
        self.assertTrue(self.rule_entries()[-1]["added"].startswith("rules.yaml first logged (sha256 "))


class CapTests(Base):
    def test_more_than_200_rules_are_counted_not_listed_and_the_next_change_is_a_baseline(self):
        many = rules_file(*[rule(f"r{n:03d}", "no", f"t{n}") for n in range(201)])
        self.write_rules(many)
        self.check(READ)
        e = self.rule_entries()[-1]
        self.assertEqual(e["added"], f"rules.yaml first logged (sha256 {sha(many.encode())}); rules 201")
        self.assertEqual(e["checked"], RULES_CHECKED_HEAD + "too many rules to list")
        self.write_rules(BASE)
        self.check(READ)
        e = self.rule_entries()[-1]
        self.assertEqual(e["added"], f"rules.yaml changed (sha256 {sha(BASE.encode())}); rules 201 to 3; the earlier "
                                     "state was not listed, so this entry is a new baseline")
        self.assertEqual(e["checked"], RULES_CHECKED_HEAD + STATE)

    def test_exactly_200_rules_are_listed(self):
        many = rules_file(*[rule(f"r{n:03d}", "no", f"t{n}") for n in range(200)])
        self.write_rules(many)
        self.check(READ)
        self.assertTrue(self.rule_entries()[-1]["checked"].endswith("; r199 no"))


# ============================================================ the entry cannot be written: no Yes


class CannotLogTests(Base):
    def changed(self):
        self.logged_base()
        self.write_rules(BASE.replace("    verdict: no\n", "    verdict: yes\n", 1)
                         + rule("still-no", "no", "transfer"))

    def assert_no_yes(self, why):
        before = snapshot(self.root)
        code, data = self.check_json(PAY)
        self.assertEqual((code, data["answer"], data["logged"]), (3, "Ask me first", False), data)
        self.assertIn(why, data["reason"])  # the check entry cannot be written either, so layer 2 gives the reason
        code, data = self.check_json({"type": "transfer"})
        self.assertEqual((code, data["answer"], data["rule_id"]), (2, "No", "still-no"))
        code, data = self.check_json(ASKED)
        self.assertEqual((code, data["answer"]), (3, "Ask me first"))
        self.assertEqual(snapshot(self.root), before, "something was written")

    def test_the_logbook_lock_is_held(self):
        self.changed()
        release = hold_logbook_lock(self.root)
        try:
            self.assert_no_yes("holds the logbook lock")
        finally:
            release()
        self.assertEqual(self.check(PAY).returncode, 0)  # the next check logs the change, then uses it
        self.assertEqual(self.sources()[-2:], [RULES_SOURCE, "umwayi check"])

    def test_the_chain_is_broken(self):
        self.logged_base()
        self.assertEqual(self.u("logbook", "seal", "--chain", "--by", "Owner").returncode, 0)
        self.check(READ)
        self.log.write_text(self.logtext().replace("gave Yes; action type: read", "gave Yes; action type: READ", 1),
                            encoding="utf-8")
        self.rerecord()
        self.write_rules(BASE.replace("    verdict: no\n", "    verdict: yes\n", 1) + rule("still-no", "no", "transfer"))
        self.assert_no_yes("hash chain is broken")

    def test_the_logbook_was_edited_by_hand(self):
        self.changed()
        self.log.write_text(self.logtext() + "\n", encoding="utf-8")
        self.assert_no_yes("does not match its recorded hash")

    def test_a_known_error_in_the_write(self):
        self.changed()
        code, data = self.check_json(PAY, fault="umwayi.logbook:append_with:error")
        self.assertEqual((code, data["answer"], data["logged"]), (3, "Ask me first", True))
        self.assertIn("rules.yaml changed and the change could not be logged before use (planted: this write fails)",
                      data["reason"])
        self.assertEqual(self.entries()[-1]["added"], "Rule no-money gave Ask me first; action type: payment")
        code, data = self.check_json({"type": "transfer"}, fault="umwayi.logbook:append_with:error")
        self.assertEqual((code, data["answer"]), (2, "No"))

    def test_a_crash_in_the_write_exits_2(self):
        self.changed()
        before = snapshot(self.root)
        r = self.check(PAY, fault="umwayi.logbook:append_with:crash")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("stopped by an unexpected error (RuntimeError)", r.stderr)
        self.assertEqual(snapshot(self.root), before)

    def test_unchanged_rules_still_give_yes_while_the_lock_is_held_for_a_dry_run(self):
        self.logged_base()
        release = hold_logbook_lock(self.root)
        try:
            code, data = self.check_json(READ, "--no-log")
        finally:
            release()
        self.assertEqual((code, data["answer"]), (0, "Yes"))


class DryRunTests(Base):
    """L13-Q19 (new, proposal used): a dry run writes nothing, so it logs no rules change either, and its answer is
    the one the rules give. A dry run approves nothing: no gate of umwayi uses --no-log."""

    def test_a_dry_run_writes_nothing_and_answers_from_the_rules(self):
        before = snapshot(self.root)
        code, data = self.check_json(READ, "--no-log")
        self.assertEqual((code, data["answer"], data["logged"]), (0, "Yes", False))
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.log.exists())

    def test_the_change_is_logged_by_the_next_real_check(self):
        self.logged_base()
        self.write_rules(BASE.replace("    verdict: no\n", "    verdict: yes\n", 1))
        self.check(PAY, "--no-log")
        self.assertEqual(len(self.rule_entries()), 1)
        self.check(PAY)
        self.assertEqual(len(self.rule_entries()), 2)


# ============================================================ every caller that asks the rules


class CallerTests(Base):
    def test_a_job_logs_a_rules_change_before_its_own_entry(self):
        self.write_rules(rules_file(rule("run-check", "yes", "run_job"), rule("ok-read", "yes", "read")))
        (self.root / "jobs.yaml").write_text("jobs:\n  - name: probe\n    command: check\n    action_type: read\n"
                                             "    min_gap_days: 1\n", encoding="utf-8")
        r = self.u("run", str(self.root / "jobs.yaml"), "--job", "probe")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sources(), [RULES_SOURCE, "umwayi run"])

    def test_a_job_gives_no_yes_when_the_change_cannot_be_logged(self):
        self.write_rules(rules_file(rule("run-check", "yes", "run_job"), rule("ok-read", "yes", "read")))
        (self.root / "jobs.yaml").write_text("jobs:\n  - name: probe\n    command: check\n    action_type: read\n"
                                             "    min_gap_days: 1\n", encoding="utf-8")
        release = hold_logbook_lock(self.root)
        try:
            r = self.u("run", str(self.root / "jobs.yaml"), "--job", "probe")
        finally:
            release()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("Ask me first\n"), r.stdout)

    def test_an_agent_gate_and_the_schedule_go_through_the_same_check(self):
        """check_and_log is the one path of `umwayi check`, the agent gates and the schedule (design.md, Facts)."""
        from umwayi import rules
        src = (REPO / "umwayi" / "rules.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        [fn] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check_and_log"]
        calls = [n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertIn("check", calls)
        self.assertTrue(callable(rules.check))


# ============================================================ two checks at once


class ConcurrencyTests(Base):
    def test_four_checks_at_once_write_one_rules_entry(self):
        self.logged_base()
        self.write_rules(BASE + rule("new-yes", "yes", "new"))
        procs = [self.popen("check", '{"type": "read"}', fault="umwayi.logbook:read_checked:pause",
                            extra={"UMWAYI_FAULT_PAUSE": "0.5"}) for _ in range(4)]
        codes = [p.wait(timeout=120) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(codes, [0] * 4)
        self.assertEqual(len(self.rule_entries()), 2)
        self.assertEqual(self.sources().count("umwayi check"), 5)
        self.assertEqual(self.u("logbook", "verify").returncode, 0)


# ============================================================ code guards


class CodeGuardTests(CourtsCase):
    SRC = REPO / "umwayi" / "rulelog.py"

    def imports(self):
        names = set()
        for node in ast.walk(ast.parse(self.SRC.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                if node.module == "umwayi":
                    names |= {f"umwayi.{a.name}" for a in node.names}
        return names

    def test_rulelog_imports_only_the_standard_library_and_the_logbook(self):
        for name in self.imports():
            top = name.split(".")[0]
            if top == "umwayi":
                self.assertIn(name, {"umwayi", "umwayi.logbook", "umwayi.errors"}, name)
            else:
                self.assertIn(top, sys.stdlib_module_names, name)
                self.assertNotIn(top, {"socket", "http", "urllib", "ssl", "subprocess"}, name)

    def test_rulelog_never_writes_rules_yaml(self):
        src = self.SRC.read_text(encoding="utf-8")
        for word in ("write_bytes", "write_text", "atomic_write", "open(", "unlink", "rename"):
            self.assertNotIn(word, src, word)
        self.assertIn("logbook.append_with(", src)

    def test_no_em_dash(self):
        for name in ("rulelog.py", "rules.py", "logbook.py"):
            self.assertNotIn(EM_DASH, (REPO / "umwayi" / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    import unittest
    unittest.main()
