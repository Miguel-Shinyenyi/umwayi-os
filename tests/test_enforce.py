"""W78 step 1A: the enforcement mode and `umwayi enforce check|set` (umwayi/enforce.py, docs/enforced-default-design.md).

Real child processes for the command line, a temporary root, no network, standard library only.

A planted fault for each of W78.R1 to R5, R13, R14 and R16 (the design note's table): every rule has one oracle, a
function that raises AssertionError when the implementation it is given breaks the rule. The real module must pass it,
and a copy of the module with that one rule broken (a mutant) must fail it. A rule whose oracle accepts its mutant would
not catch the fault, so the mutant test is the check of the check.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from umwayi import agents, enforce  # noqa: E402
from umwayi.errors import ConfigError  # noqa: E402

TODAY = date(2026, 11, 17)
ENV = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}


def make_root(tmp):
    root = Path(tmp) / "root"
    work = Path(tmp) / "work"
    root.mkdir()
    work.mkdir()
    (root / "agents.yaml").write_text(
        f"agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
        f"  - name: kirohelper\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n", encoding="utf-8")
    return root


def tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def mutant(**changes):
    ns = types.SimpleNamespace(**vars(enforce))
    for k, v in changes.items():
        setattr(ns, k, v)
    return ns


def logbook_sources(root):
    path = Path(root) / "LOGBOOK.md"
    return re.findall(r"^- Source: (.+)$", path.read_text(encoding="utf-8"), re.M) if path.exists() else []


# ----------------------------------------------------------------------------------------------- the oracles


def rule_1_default_is_enforced(ns):
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        settings = ns.read(root, TODAY)  # no settings file at all
        for agent in (None, "reviewer"):
            mode = ns.mode_for(settings, agent, None, TODAY)[0]
            assert mode == "enforced", f"a missing settings file gave {mode}"
        assert ns.mode_text(root, today=TODAY) == "enforcement: enforced"


def rule_2_only_the_owner_at_a_terminal_switches(ns):
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        before = tree(root)
        r = ns.set_mode(root, "cooperative", until="2026-11-20", today=TODAY, tty=lambda: False, confirm=lambda: "cooperative")
        assert r.code == 3, f"not at a terminal gave exit {r.code}"
        r = ns.set_mode(root, "cooperative", until="2026-11-20", today=TODAY, tty=lambda: True, confirm=lambda: "yes")
        assert r.code == 3, f"a wrong typed word gave exit {r.code}"
        assert tree(root) == before, "a refused switch changed a file"
        r = ns.set_mode(root, "cooperative", until="2026-11-20", today=TODAY, tty=lambda: True, confirm=lambda: "cooperative")
        assert r.code == 0 and (root / enforce.FILE_REL).is_file(), "the owner's switch was not done"


def rule_3_a_switch_is_logged_and_the_mode_is_shown(ns):
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        ns.set_mode(root, "cooperative", until="2026-11-20", today=TODAY, tty=lambda: True, confirm=lambda: "cooperative")
        assert logbook_sources(root).count(enforce.SOURCE) == 1, "a switch to cooperative wrote no logbook entry"
        ns.set_mode(root, "enforced", today=TODAY)
        assert logbook_sources(root).count(enforce.SOURCE) == 2, "a switch to enforced wrote no logbook entry"
        ns.set_mode(root, "cooperative", agent="reviewer", until="2026-11-20", today=TODAY, tty=lambda: True,
                    confirm=lambda: "cooperative")
        assert ns.mode_text(root, "reviewer", today=TODAY) == "enforcement: cooperative (agent, until 2026-11-20)"
        assert ns.mode_text(root, "kirohelper", today=TODAY) == "enforcement: enforced"
        assert "enforcement: enforced" in ns.status_line(root, today=TODAY)
        assert "cooperative today and enforced where built" in ns.status_line(root, today=TODAY), "the status line does not say what is built"


def rule_4_cooperative_needs_until_and_expires(ns):
    cooperative = "enforcement: cooperative\n"
    try:
        ns.parse(cooperative, TODAY)
    except ConfigError:
        pass
    else:
        raise AssertionError("cooperative without until was accepted")
    settings = ns.parse(cooperative + "until: 2026-11-16\n", TODAY)  # yesterday
    assert ns.mode_for(settings, None, None, TODAY)[0] == "enforced", "an expired until stayed cooperative"
    settings = ns.parse(cooperative + "until: 2026-11-17\n", TODAY)
    assert ns.mode_for(settings, None, None, TODAY) == ("cooperative", "all", "2026-11-17"), "the last day is still cooperative"
    assert ns.mode_for(settings, None, None, TODAY + timedelta(days=1))[0] == "enforced"
    try:
        ns.parse(cooperative + "until: 2027-01-30\n", TODAY)
    except ConfigError:
        pass
    else:
        raise AssertionError("an until more than 30 days away was accepted")


def rule_5_the_mode_file_is_on_the_watched_list(ns):
    assert enforce.FILE_REL in ns.WATCHED_GUARD_FILES, "the mode file is not on the watched list"


def rule_13_a_start_that_cannot_be_enforced_is_refused_never_cooperative(ns):
    refused = lambda agent: {p: "unavailable" for p in enforce.PARTS}  # noqa: E731
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        r = ns.check(root, today=TODAY, probe_fn=refused)
        assert r.code == 2, f"an agent that cannot be enforced gave exit {r.code}"
        text = "\n".join(r.lines)
        assert "enforcement: enforced" in r.lines[0] and "cooperative (" not in text, "it fell back to cooperative"
        assert re.search(r"refused: not confined \((" + "|".join(enforce.REASONS) + r")\)\. Allowed next: ", text), text
        ns.set_mode(root, "cooperative", agent="reviewer", until="2026-11-20", today=TODAY, tty=lambda: True,
                    confirm=lambda: "cooperative")
        one = ns.check(root, today=TODAY, probe_fn=refused)
        assert one.code == 2, "the other agent is still refused"
        ns.set_mode(root, "cooperative", agent="kirohelper", until="2026-11-20", today=TODAY, tty=lambda: True,
                    confirm=lambda: "cooperative")
        assert ns.check(root, today=TODAY, probe_fn=refused).code == 0, "the owner's per agent switch was not offered"


def rule_14_check_writes_nothing_and_never_says_ready_when_it_is_not(ns):
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        before = tree(root)
        r = ns.check(root, today=TODAY)
        assert r.code in (0, 2, 3, 64), f"exit {r.code}"
        assert tree(root) == before, "the check wrote a file"
        text = "\n".join(r.lines)
        assert ": ready" not in text, "a part that is not built was called ready"
        assert text.count("refused (") == 2 * len(enforce.PARTS), text
        ready = ns.check(root, today=TODAY, probe_fn=lambda a: {p: None for p in enforce.PARTS})
        assert ready.code == 0 and "  environment: ready" in ready.lines, "a part that is ready was not shown ready"
        assert tree(root) == before


def rule_16_no_page_says_enforced_by_default_before_the_real_run(ns):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "README.md").write_text("umwayi-os is enforced by default.\n", encoding="utf-8")
        assert ns.pages_overclaim(tmp) == ["README.md"], "the overclaim was not found"
        (Path(tmp) / "README.md").write_text("Enforcement is cooperative today and enforced where built.\n", encoding="utf-8")
        assert ns.pages_overclaim(tmp) == []


def _check_stub(code, transform=None, write=False):
    real = enforce.check

    def stub(root, *a, **k):
        r = real(root, *a, **k)
        if write:
            (Path(root) / "stray.txt").write_text("x", encoding="utf-8")
        return agents.Result(code if code is not None else r.code, [transform(x) for x in r.lines] if transform else r.lines)
    return stub


def _set_without_log(*a, **k):
    with mock.patch.object(enforce.logbook, "append"):
        return enforce.set_mode(*a, **k)


def _set_ignoring_the_terminal(*a, **k):
    return enforce.set_mode(*a, **{**k, "tty": lambda: True, "confirm": lambda: "cooperative"})


def _set_with_no_checks(root, mode, **k):
    return enforce.set_mode(root, mode, **{**k, "tty": lambda: True, "confirm": lambda: "cooperative"})


RULES = {
    "R1": (rule_1_default_is_enforced, lambda: mutant(read=lambda root, today: enforce.Settings(enforce.Entry("cooperative", "2099-01-01")))),
    "R2": (rule_2_only_the_owner_at_a_terminal_switches, lambda: mutant(set_mode=_set_ignoring_the_terminal)),
    "R3": (rule_3_a_switch_is_logged_and_the_mode_is_shown, lambda: mutant(set_mode=_set_without_log)),
    "R3b": (rule_3_a_switch_is_logged_and_the_mode_is_shown, lambda: mutant(mode_text=lambda *a, **k: "")),
    "R4": (rule_4_cooperative_needs_until_and_expires, lambda: mutant(parse=lambda text, today: enforce.Settings())),
    "R4b": (rule_4_cooperative_needs_until_and_expires,
            lambda: mutant(mode_for=lambda s, a, g, t: enforce.mode_for(s, a, g, date(2000, 1, 1)))),
    "R5": (rule_5_the_mode_file_is_on_the_watched_list, lambda: mutant(WATCHED_GUARD_FILES=())),
    "R13": (rule_13_a_start_that_cannot_be_enforced_is_refused_never_cooperative,
            lambda: mutant(check=_check_stub(0, lambda line: line.replace("enforcement: enforced", "enforcement: cooperative (all, until 2026-11-20)")))),
    "R14": (rule_14_check_writes_nothing_and_never_says_ready_when_it_is_not,
            lambda: mutant(check=_check_stub(None, lambda line: line.replace("refused (unavailable)", "ready")))),
    "R14b": (rule_14_check_writes_nothing_and_never_says_ready_when_it_is_not, lambda: mutant(check=_check_stub(None, write=True))),
    "R14c": (rule_14_check_writes_nothing_and_never_says_ready_when_it_is_not, lambda: mutant(check=_check_stub(1))),
    "R16": (rule_16_no_page_says_enforced_by_default_before_the_real_run, lambda: mutant(pages_overclaim=lambda root: [])),
}


class RulesTests(unittest.TestCase):
    pass


def _add(name, oracle, make_mutant):
    def real(self):
        oracle(enforce)

    def planted(self):
        with self.assertRaises(AssertionError, msg=f"the oracle of {name} accepted its planted fault"):
            oracle(make_mutant())
    if not name.endswith(("b", "c")):
        setattr(RulesTests, f"test_{name.lower()}_the_rule_holds", real)
    setattr(RulesTests, f"test_{name.lower()}_planted_fault_is_caught", planted)


for _n, (_o, _m) in RULES.items():
    _add(_n, _o, _m)


# ----------------------------------------------------------------------------------------------- the file and the commands


class SettingsFileTests(unittest.TestCase):
    def test_a_malformed_file_is_a_config_error(self):
        for text in ("- a list\n", "enforcement: sometimes\n", "enforcement: enforced\nuntil: 2026-11-20\n", "hello: 1\n",
                     "enforcement: cooperative\nuntil: 2026-02-30\n", "enforcement: cooperative\nuntil: soon\n",
                     "enforcement: enforced\ngoals:\n  not-a-goal:\n    enforcement: enforced\n",
                     "enforcement: enforced\nagents:\n  Bad Name:\n    enforcement: enforced\n",
                     "enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n", "", "a: [\n"):
            with self.assertRaises(ConfigError, msg=text):
                enforce.parse(text, TODAY)

    def test_an_entry_per_agent_and_per_goal_wins_over_the_default(self):
        s = enforce.parse("enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n    until: 2026-11-20\n"
                          "goals:\n  G-0007:\n    enforcement: cooperative\n    until: 2026-11-19\n", TODAY)
        self.assertEqual(enforce.mode_for(s, "reviewer", None, TODAY), ("cooperative", "agent", "2026-11-20"))
        self.assertEqual(enforce.mode_for(s, "reviewer", "G-0007", TODAY), ("cooperative", "goal", "2026-11-19"))
        self.assertEqual(enforce.mode_for(s, "other", None, TODAY)[0], "enforced")

    def test_the_refusal_has_one_fixed_shape_and_an_unknown_step_is_refused(self):
        for step in enforce.STEPS:
            self.assertRegex(enforce.refusal("not confined (unavailable)", step), r"^refused: .+\. Allowed next: .+\.$")
        with self.assertRaises(KeyError):
            enforce.refusal("x", "anything the caller made up")

    def test_the_probe_names_only_reasons_of_the_fixed_list(self):
        listed = agents.Agent("a", "claude-code", "claude", "cli", "/tmp")
        for platform in ("linux", "darwin", "win32"):
            for agent in (listed, agents.Agent("b", "kiro", "kiro-cli", "cli", "/tmp")):
                got = enforce.probe(agent, platform)
                self.assertEqual(set(got), set(enforce.PARTS))
                self.assertTrue(all(v in enforce.REASONS for v in got.values()), got)

    def test_the_real_pages_do_not_say_enforced_by_default(self):
        self.assertEqual(enforce.pages_overclaim(REPO), [])
        self.assertFalse(enforce.REAL_ENFORCED_RUN_DONE)
        self.assertIn("cooperative today", (REPO / "docs" / "what-it-is.md").read_text(encoding="utf-8"))
        self.assertIn("cooperative today", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_no_em_dash_in_the_new_files(self):
        for name in ("umwayi/enforce.py", "tests/test_enforce.py"):
            self.assertNotIn("\u2014", (REPO / name).read_text(encoding="utf-8"), name)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="umwayi-enforce-")
        self.addCleanup(self.tmp.cleanup)
        self.root = make_root(self.tmp.name)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "enforce", *args], capture_output=True,
                              text=True, env=ENV, stdin=subprocess.DEVNULL, cwd=self.tmp.name, timeout=120)

    def test_check_is_read_only_and_every_part_is_refused_today(self):
        before = tree(self.root)
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(tree(self.root), before)
        self.assertIn("enforcement: enforced", r.stdout)
        self.assertNotIn(": ready", r.stdout)
        self.assertRegex(r.stdout, r"(?m)^ *refused: not confined \(\w+\)\. Allowed next: ")
        self.assertIn("agent reviewer (claude-code): enforcement: enforced", r.stdout)

    def test_set_cooperative_from_a_pipe_is_ask_me_first_and_changes_nothing(self):
        before = tree(self.root)
        r = self.run_cli("set", "cooperative", "--until", "2099-01-01")
        self.assertEqual(r.returncode, 64, r.stderr)  # too far ahead is usage, checked before the terminal
        r = self.run_cli("set", "cooperative", "--agent", "reviewer")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("Allowed next: run this command at your terminal", r.stdout)
        self.assertEqual(tree(self.root), before)

    def test_set_cooperative_usage_errors_are_64(self):
        for args in (("cooperative", "--until", "2020-01-01"), ("cooperative", "--until", "tomorrow"),
                     ("cooperative", "--agent", "nobody"), ("cooperative", "--goal", "G-0001"), ("cooperative", "--goal", "x"),
                     ("enforced", "--until", "2026-11-20"), ("cooperative", "--agent", "reviewer", "--goal", "G-0001")):
            r = self.run_cli("set", *args)
            self.assertIn(r.returncode, (64, 2), (args, r.stdout, r.stderr))
            self.assertEqual(r.returncode, 64, (args, r.stdout, r.stderr))
        self.assertFalse((self.root / enforce.FILE_REL).exists())

    def test_set_enforced_is_allowed_from_a_pipe_and_is_logged(self):
        r = self.run_cli("set", "enforced")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(logbook_sources(self.root), [enforce.SOURCE])
        self.assertEqual(self.run_cli("check").returncode, 2)  # the file matches its logbook entry: no exit 3

    def test_a_hand_written_settings_file_is_ask_me_first(self):
        (self.root / ".umwayi").mkdir()
        (self.root / enforce.FILE_REL).write_text("enforcement: enforced\n", encoding="utf-8")
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("does not match the last mode entry", r.stdout)

    def test_a_malformed_settings_file_is_64(self):
        (self.root / ".umwayi").mkdir()
        (self.root / enforce.FILE_REL).write_text("enforcement: maybe\n", encoding="utf-8")
        for args in (("check",), ("set", "enforced")):
            r = self.run_cli(*args)
            self.assertEqual(r.returncode, 64, (args, r.stdout, r.stderr))

    def test_the_owner_at_a_terminal_writes_the_file_and_one_entry(self):
        r = enforce.set_mode(self.root, "cooperative", agent="reviewer", until="2026-11-20", today=TODAY,
                             tty=lambda: True, confirm=lambda: "cooperative")
        self.assertEqual(r.code, 0, r.lines)
        text = (self.root / enforce.FILE_REL).read_text(encoding="utf-8")
        self.assertIn("reviewer:", text)
        self.assertIn("until: 2026-11-20", text)
        self.assertEqual(logbook_sources(self.root), [enforce.SOURCE])
        self.assertEqual(enforce.set_mode(self.root, "enforced", agent="reviewer", today=TODAY).code, 0)
        self.assertNotIn("reviewer", (self.root / enforce.FILE_REL).read_text(encoding="utf-8"))

    def test_the_default_is_seven_days_and_the_limit_is_thirty(self):
        enforce.set_mode(self.root, "cooperative", today=TODAY, tty=lambda: True, confirm=lambda: "cooperative")
        self.assertIn("until: 2026-11-24", (self.root / enforce.FILE_REL).read_text(encoding="utf-8"))
        from umwayi.errors import UsageError
        with self.assertRaises(UsageError):
            enforce.set_mode(self.root, "cooperative", until="2026-12-18", today=TODAY, tty=lambda: True, confirm=lambda: "cooperative")
        enforce.set_mode(self.root, "cooperative", until="2026-12-17", today=TODAY, tty=lambda: True, confirm=lambda: "cooperative")

    def test_a_logbook_that_cannot_record_puts_the_file_back(self):
        before = tree(self.root)
        with mock.patch.object(enforce.logbook, "append", side_effect=RuntimeError("no")):
            with self.assertRaises(RuntimeError):
                enforce.set_mode(self.root, "enforced", today=TODAY)
        self.assertEqual(tree(self.root), before)

    def test_the_mode_is_in_the_goal_status_the_prompts_and_the_start_entry_source(self):
        from umwayi import goal, goalrun
        ctx = goal.make_ctx(self.root, out=lambda s: None)
        self.assertTrue(goal.status_lines(ctx)[0].startswith("enforcement: enforced. Enforcement is cooperative today and enforced where built."))
        text = goalrun.tester_prompt(types.SimpleNamespace(goal="g", checks=("c",)), "b", "0" * 40, "N", mode="enforcement: enforced")
        self.assertIn("enforcement: enforced\nNonce: N", text)
        source = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        self.assertIn("enforce.mode_text(root, a.name, today=self.clock())", source)


if __name__ == "__main__":
    unittest.main()
