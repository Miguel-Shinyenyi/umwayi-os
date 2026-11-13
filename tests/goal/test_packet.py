"""W9.2 / W9.R4, W9.R6: the packet, the plan parser, the protected list, the scope check and the state table.

Tests first. The module under test is umwayi/goalpacket.py, which is pure.
"""

import ast
import json
import unittest
from pathlib import Path

from tests.goal import gen
from umwayi import goalpacket as gp

REPO = Path(__file__).resolve().parents[2]
EM = "\u2014"


def task(**kw):
    t = {"goal": "Add the pure packet parser with its tests.", "context": ["umwayi/taskqueue.py"],
         "checks": ["A plan with an unknown field is refused with the word field."], "size": 60,
         "files": ["umwayi/goalpacket.py", "tests/goal/test_packet.py"]}
    t.update(kw)
    return t


def plan(*tasks):
    return json.dumps({"tasks": list(tasks) or [task()]}).encode("utf-8")


def word_of(data, **kw):
    try:
        gp.parse_plan(data, **kw)
    except gp.PlanError as e:
        return e.word
    return None


class ParsePlanTests(unittest.TestCase):
    def test_a_good_plan_gives_packets_in_order_with_blank_owner_fields(self):
        ps = gp.parse_plan(plan(task(), task(goal="Add the second thing to the first one.")))
        self.assertEqual([p.id for p in ps], ["T-01", "T-02"])
        p = ps[0]
        self.assertEqual((p.model, p.effort, p.budget_uu), ("", "", None))
        self.assertEqual(p.outcome, {})  # umwayi sets it at approval, when the goal id is known
        self.assertEqual(p.size, 60)

    def test_unknown_field_is_refused_with_the_word_field(self):
        self.assertEqual(word_of(plan(task(extra=1))), "field")
        for owner_field in ("id", "outcome", "model", "effort", "budget_uu"):
            self.assertEqual(word_of(plan(task(**{owner_field: "x"}))), "field", owner_field)

    def test_top_level_must_be_tasks_only(self):
        self.assertEqual(word_of(json.dumps({"tasks": [task()], "x": 1}).encode()), "field")
        self.assertEqual(word_of(json.dumps([task()]).encode()), "type")
        self.assertEqual(word_of(json.dumps({"tasks": []}).encode()), "count")

    def test_nine_packets_are_refused_and_eight_are_allowed(self):
        eight = [task(size=15, goal=f"Do the numbered thing number {i} now.") for i in range(8)]
        self.assertIsNone(word_of(plan(*eight)))
        self.assertEqual(word_of(plan(*(eight + [task(size=15)]))), "count")

    def test_sizes(self):
        self.assertEqual(word_of(plan(task(size=91))), "size")
        self.assertEqual(word_of(plan(task(size=14))), "size")
        self.assertIsNone(word_of(plan(task(size=90))))
        self.assertIsNone(word_of(plan(task(size=15))))
        self.assertEqual(word_of(plan(task(size=60.0))), "json")  # whole numbers only
        self.assertEqual(word_of(plan(task(size=True))), "size")
        self.assertEqual(word_of(plan(task(size="60"))), "size")

    def test_the_plan_adds_up_to_at_most_480_minutes(self):
        six_90 = [task(size=90, goal=f"Do the numbered thing number {i} now.") for i in range(6)]
        self.assertEqual(word_of(plan(*six_90)), "total")
        self.assertIsNone(word_of(plan(*six_90[:5], task(size=30))))
        self.assertEqual(word_of(plan(*six_90[:5], task(size=31))), "total")

    def test_goal_and_check_text_rules(self):
        for bad in ("Too short", "x" * 201, "Line one.\nLine two is here.", "Add a thing. Then add another.",
                    "Has a tab\there ok", "Bell \x07 character in it", "Right\u2028side separator here"):
            self.assertEqual(word_of(plan(task(goal=bad))), "goal", repr(bad))
            self.assertEqual(word_of(plan(task(checks=[bad]))), "checks", repr(bad))
        self.assertIsNone(word_of(plan(task(goal="Add a thing, then add another one."))))
        self.assertIsNone(word_of(plan(task(goal="Add the parser and its tests."))))

    def test_check_counts(self):
        ok = "A plan with an unknown field is refused."
        self.assertEqual(word_of(plan(task(checks=[]))), "checks")
        self.assertEqual(word_of(plan(task(checks=[ok] * 9))), "checks")
        self.assertIsNone(word_of(plan(task(checks=[ok] * 8))))

    def test_context_rules(self):
        self.assertEqual(word_of(plan(task(context=["a.py"] * 13))), "context")
        self.assertIsNone(word_of(plan(task(context=[]))))
        sizes = {"umwayi/a.py": 150_000, "umwayi/b.py": 60_000}
        self.assertEqual(word_of(plan(task(context=list(sizes))), file_size=sizes.get), "context")
        self.assertIsNone(word_of(plan(task(context=["umwayi/a.py"])), file_size=sizes.get))
        self.assertEqual(word_of(plan(task(context=["umwayi/missing.py"])), file_size=sizes.get), "context")
        self.assertEqual(word_of(plan(task(context=["memory/private/x.md"])), file_size=lambda p: 1,
                                 is_private=lambda p: p.startswith("memory/private")), "context")
        for bad in ("/etc/passwd", "../x.py", "a\\b.py", "a/../b.py", "", "a\x00b"):
            self.assertEqual(word_of(plan(task(context=[bad]))), "context", repr(bad))

    def test_files_rules(self):
        self.assertEqual(word_of(plan(task(files=[]))), "files")
        self.assertEqual(word_of(plan(task(files=[f"umwayi/f{i}.py" for i in range(21)]))), "files")
        self.assertIsNone(word_of(plan(task(files=[f"umwayi/f{i}.py" for i in range(20)]))))
        for bad in ("/abs.py", "../x.py", "a/../b.py", "src/*.py", "a?b.py", "a[1].py", "a\\b", "", ".", "./", "a\x00b"):
            self.assertEqual(word_of(plan(task(files=[bad]))), "files", repr(bad))
        self.assertIsNone(word_of(plan(task(files=["umwayi/", "tests/goal/"]))))

    def test_protected_files_are_refused_in_a_plan(self):
        for name in gp.PROTECTED:
            self.assertEqual(word_of(plan(task(files=[name]))), "protected", name)

    def test_json_strictness(self):
        good = plan()
        self.assertEqual(word_of(b"\xef\xbb\xbf" + good), "encoding")
        self.assertEqual(word_of(b"\xff\xfe" + good), "encoding")
        self.assertEqual(word_of(good.replace(b"{", b"{\"tasks\":1,", 1)), "duplicate")
        self.assertEqual(word_of(b"{not json"), "json")
        self.assertEqual(word_of(b""), "json")
        self.assertEqual(word_of(b'{"tasks": NaN}'), "json")
        self.assertEqual(word_of(b"[" * 5 + b"]" * 5), "depth")
        self.assertEqual(word_of(b"[" * 30000), "depth")
        self.assertEqual(word_of(plan(task(goal="x" * 40000))), "bytes")

    def test_duplicate_key_inside_a_task(self):
        data = plan().replace(b'"size": 60', b'"size": 60, "size": 61')
        self.assertEqual(word_of(data), "duplicate")

    def test_error_carries_the_packet_number_and_never_the_text(self):
        secret = "SENTINEL-" + "z" * 12
        try:
            gp.parse_plan(plan(task(), task(goal=secret + "\nsecond line")))
        except gp.PlanError as e:
            self.assertEqual((e.word, e.index), ("goal", 2))
            self.assertNotIn("SENTINEL", str(e))
            self.assertNotIn("SENTINEL", repr(e))
        else:
            self.fail("no PlanError")

    def test_parse_plan_is_total_over_random_bytes_and_json(self):
        def check(case):
            try:
                gp.parse_plan(case)
            except gp.PlanError:
                pass
            return True

        gen.run_property(self, lambda g: g.data(0, 80), check, cases=1500, seeds=gen.SEEDS)
        gen.run_property(self, lambda g: json.dumps(g.json_value()).encode(), check, cases=1500, seeds=gen.SEEDS)

    def test_random_valid_plans_parse(self):
        def make(g):
            return [{"goal": g.sentence(10, 120).replace(".", ""), "context": [], "checks": [g.sentence(10, 60).replace(".", "")
                    for _ in range(g.between(1, 3))], "size": g.between(15, 60),
                    "files": ["umwayi/" + g.text("abcdefgh", 1, 8) + ".py" for _ in range(g.between(1, 4))]}
                    for _ in range(g.between(1, 5))]

        def check(tasks):
            ps = gp.parse_plan(json.dumps({"tasks": tasks}).encode())
            return len(ps) == len(tasks) and all(p.goal == t["goal"] for p, t in zip(ps, tasks))

        gen.run_property(self, make, check, cases=800, seeds=gen.SEEDS)


class PacketTests(unittest.TestCase):
    def approved(self, **kw):
        p = gp.parse_plan(plan())[0]
        return gp.fill_packet(p, "G-0007", kw.get("model", "sonnet"), kw.get("effort", "high"), kw.get("budget", 30), 500)

    def test_outcome_and_own_files(self):
        self.assertEqual(gp.own_files("G-0007", "T-02"),
                         ("docs-parts/status-log/G-0007-T-02.md", "docs-parts/known-limits/G-0007-T-02.md"))
        self.assertEqual(gp.branch_name("G-0007", "T-02"), "umwayi/g-0007-t-02")
        for bad in (("G-7", "T-02"), ("G-0007", "T-2"), ("g-0007", "T-02"), ("G-0007", "T-02/../x"), ("G-0007\n", "T-02")):
            with self.assertRaises(ValueError):
                gp.own_files(*bad)
            with self.assertRaises(ValueError):
                gp.branch_name(*bad)

    def test_fill_packet_checks_the_owner_fields(self):
        p = self.approved()
        self.assertEqual((p.model, p.effort, p.budget_uu), ("sonnet", "high", 30))
        self.assertEqual(p.outcome, {"status_file": "docs-parts/status-log/G-0007-T-01.md",
                                     "limits_file": "docs-parts/known-limits/G-0007-T-01.md",
                                     "branch": "umwayi/g-0007-t-01"})
        base = gp.parse_plan(plan())[0]
        for kw in (dict(model="", effort="high", budget=30), dict(model="a b", effort="high", budget=30),
                   dict(model="x" * 65, effort="high", budget=30), dict(model="sonnet", effort="", budget=30),
                   dict(model="sonnet", effort="huge", budget=30), dict(model="sonnet", effort="high", budget=0),
                   dict(model="sonnet", effort="high", budget=501), dict(model="sonnet", effort="high", budget=None),
                   dict(model="sonnet", effort="high", budget=True)):
            with self.assertRaises(ValueError, msg=str(kw)):
                gp.fill_packet(base, "G-0007", kw["model"], kw["effort"], kw["budget"], 500)
        for e in ("low", "medium", "high", "xhigh", "max"):
            gp.fill_packet(base, "G-0007", "m", e, 1, 500)

    def test_an_approved_packet_has_exactly_the_ten_fields_and_a_stable_hash(self):
        p = self.approved()
        d = p.to_dict()
        self.assertEqual(set(d), {"id", "goal", "context", "checks", "outcome", "size", "model", "effort", "files",
                                  "budget_uu"})
        self.assertEqual(p.sha256(), gp.packet_from_dict(d).sha256())
        self.assertEqual(len(p.sha256()), 64)
        changed = dict(d, size=61)
        self.assertNotEqual(p.sha256(), gp.packet_from_dict(changed).sha256())
        reordered = dict(reversed(list(d.items())))
        self.assertEqual(gp.packet_from_dict(reordered).sha256(), p.sha256())

    def test_packet_from_dict_is_strict(self):
        d = self.approved().to_dict()
        for bad in (dict(d, extra=1), {k: v for k, v in d.items() if k != "files"}, dict(d, id="T-9"),
                    dict(d, size="60"), dict(d, files="x"), dict(d, outcome={"branch": "x"}), [], None):
            with self.assertRaises(ValueError):
                gp.packet_from_dict(bad)


class ProtectedSpellingTests(unittest.TestCase):
    def spellings(self):
        out = []
        for name in gp.PROTECTED:
            base = name.rstrip("/")
            out += [name, base, base.upper(), base.title(), "./" + base, base.replace("/", "//"), base + "/" if "/" not in name[-1:] else base,
                    base.swapcase(), "x/../" + base, "./" + base.upper(), base + " ", base + ".", base + "/.", base + "/x"]
            if name.endswith("/"):
                out += [name + "deep/file.txt", name.upper() + "a", "./" + name + "a"]
        return out

    def test_forty_or_more_spellings_are_all_protected(self):
        sp = self.spellings()
        self.assertGreaterEqual(len(sp), 40)
        for s in sp:
            self.assertTrue(gp.is_protected(s), repr(s))

    def test_protected_spellings_are_never_allowed_by_scope(self):
        for s in self.spellings():
            self.assertNotEqual(gp.scope_violations([s], ["umwayi/", "docs/", "tests/", "adapters/", ".kiro/", "workflows/"]), [], repr(s))

    def test_ordinary_paths_are_not_protected(self):
        for ok in ("umwayi/goalpacket.py", "tests/goal/test_packet.py", "docs/goals.md", "README.md", "rules.yaml.md",
                   "my-rules.yaml", "workflows2/x.md", "docs-parts2/x.md", ".umwayi2/x"):
            self.assertFalse(gp.is_protected(ok), ok)

    def test_the_four_adapter_example_rules_are_listed(self):
        for a in ("claude_code", "kiro", "stdio", "opencode"):
            self.assertIn(f"adapters/{a}/rules.example.yaml", gp.PROTECTED)

    def test_the_list_has_the_names_of_w9_r4_5(self):
        for name in ("rules.yaml", "autonomy.yaml", "agents.yaml", "units.yaml", "umwayi.json", "schedule.yaml", "jobs.yaml",
                     "workflows/", "LOGBOOK.md", "queue.md", ".umwayi/", ".kiro/steering/", ".github/",
                     "docs/status-log.md", "docs/KNOWN-LIMITS.md", ".gitignore", "docs-parts/"):
            self.assertIn(name, gp.PROTECTED)


class ScopeTests(unittest.TestCase):
    OWN = ("docs-parts/status-log/G-0007-T-02.md", "docs-parts/known-limits/G-0007-T-02.md")

    def test_allowed_file_folder_and_own_files(self):
        allowed = ["umwayi/goalpacket.py", "tests/goal/"]
        self.assertEqual(gp.scope_violations(["umwayi/goalpacket.py", "tests/goal/a.py", "tests/goal/sub/b.py"], allowed), [])
        self.assertEqual(gp.scope_violations(list(self.OWN), allowed, own=self.OWN), [])
        self.assertEqual(gp.scope_violations(["umwayi/other.py"], allowed), ["umwayi/other.py"])
        self.assertEqual(gp.scope_violations(["tests/goalx/a.py"], allowed), ["tests/goalx/a.py"])
        self.assertEqual(gp.scope_violations(["docs-parts/status-log/G-0007-T-03.md"], allowed, own=self.OWN),
                         ["docs-parts/status-log/G-0007-T-03.md"])

    def test_tricks_are_always_violations(self):
        allowed = ["umwayi/", "/"]
        for bad in ("/etc/passwd", "../x", "umwayi/../../x", "umwayi/../rules.yaml", "a\\b", "umwayi/a\x00b", "",
                    "umwayi/a\nb", "..", "umwayi/..", b"umwayi/\xff.py", "umwayi\\x.py"):
            self.assertEqual(len(gp.scope_violations([bad], allowed)), 1, repr(bad))

    def test_case_and_normalization(self):
        allowed = ["umwayi/goalpacket.py"]
        self.assertNotEqual(gp.scope_violations(["umwayi/GoalPacket.py"], allowed), [])
        self.assertNotEqual(gp.scope_violations(["UMWAYI/goalpacket.py"], allowed), [])
        self.assertEqual(gp.scope_violations(["./umwayi/goalpacket.py"], allowed), [])
        self.assertEqual(gp.scope_violations(["umwayi//goalpacket.py"], allowed), [])

    def test_renamed_deleted_and_mode_changed_paths_are_checked_as_paths(self):
        self.assertEqual(gp.scope_violations(["umwayi/a.py", "docs/status-log.md"], ["umwayi/", "docs/"]), ["docs/status-log.md"])

    def test_random_paths_never_raise_and_inside_means_allowed(self):
        def make(g):
            changed = [g.pick(["umwayi/", "tests/", "x/", "../", "/", "./", "a\\", "UMWAYI/", ""]) + g.path()
                       for _ in range(g.between(0, 6))]
            return changed, ["umwayi/", "tests/goal/", "README.md"]

        def check(case):
            changed, allowed = case
            out = gp.scope_violations(changed, allowed)
            return isinstance(out, list) and all(c in changed for c in out)

        gen.run_property(self, make, check, cases=1200, seeds=gen.SEEDS)


class StateTableTests(unittest.TestCase):
    def test_the_table_is_the_one_of_w9_r6(self):
        self.assertEqual(set(gp.STATES), {"queued", "running", "in review", "needs owner", "merged", "failed", "stopped"})
        T = gp.TRANSITIONS
        self.assertEqual(set(T["queued"]), {"running", "needs owner", "stopped"})
        self.assertEqual(set(T["running"]), {"in review", "failed", "needs owner", "stopped"})
        self.assertEqual(set(T["in review"]), {"merged"})
        self.assertEqual(set(T["needs owner"]), {"queued", "stopped"})
        for end in ("merged", "failed", "stopped"):
            self.assertEqual(set(T[end]), set())

    def test_a_random_walk_accepts_only_table_transitions(self):
        def make(g):
            return [g.pick(gp.STATES + ("plan", "bogus", "")) for _ in range(g.between(2, 12))]

        def check(walk):
            for old, new in zip(walk, walk[1:]):
                ok = gp.can_move(old, new)
                expect = new in gp.TRANSITIONS.get(old, ()) or (old == "plan" and new == "queued")
                if ok != expect:
                    return False
            return True

        gen.run_property(self, make, check, cases=1500, seeds=gen.SEEDS)

    def test_reasons_are_a_closed_list_per_state(self):
        failed = {"builder", "outcome", "scope", "tests", "rejected", "stalled", "looping", "budget", "timeout", "readonly"}
        stopped = {"kill", "owner", "log", "signal", "unanswered", "supervisor"}
        needs = {"ask", "unclear", "busy", "dirty", "leftover", "stale", "config"}
        self.assertEqual(set(gp.REASONS["failed"]), failed)
        self.assertEqual(set(gp.REASONS["stopped"]), stopped)
        self.assertEqual(set(gp.REASONS["needs owner"]), needs)
        self.assertEqual(set(gp.REASONS["merged"]), {"observed", "declared"})
        self.assertIn("start", gp.REASONS["running"])
        self.assertIn("checked", gp.REASONS["in review"])

    def test_reason_for_each_cause_gives_a_valid_state_and_reason(self):
        self.assertGreaterEqual(len(gp.CAUSES), 30)
        seen = set()
        for cause in gp.CAUSES:
            state, reason = gp.reason_for(cause)
            self.assertIn(reason, gp.REASONS[state], cause)
            seen.add((state, reason))
        for state in ("failed", "stopped", "needs owner"):
            for reason in gp.REASONS[state]:
                self.assertIn((state, reason), seen, f"no cause gives {state}/{reason}")
        with self.assertRaises(ValueError):
            gp.reason_for("no such cause")

    def test_goal_state_is_derived_from_the_tasks(self):
        g = gp.goal_state
        self.assertEqual(g([]), "plan")
        self.assertEqual(g([], stopped=True), "stopped")
        self.assertEqual(g(["queued", "queued"]), "active")
        self.assertEqual(g(["merged", "running", "queued"]), "active")
        self.assertEqual(g(["merged", "queued", "queued"]), "active")
        self.assertEqual(g(["merged", "in review", "queued"]), "waiting")
        self.assertEqual(g(["needs owner", "queued"]), "waiting")
        self.assertEqual(g(["merged", "merged"]), "merged")
        self.assertEqual(g(["merged", "failed", "queued"]), "failed")
        self.assertEqual(g(["merged", "stopped", "queued"]), "stopped")
        self.assertEqual(g(["failed", "stopped"]), "failed")


class PureModuleGuard(unittest.TestCase):
    def test_goalpacket_imports_only_five_modules(self):
        tree = ast.parse((REPO / "umwayi" / "goalpacket.py").read_text(encoding="utf-8"))
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or "").split(".")[0])
        names.discard("__future__")
        self.assertLessEqual(names, {"json", "re", "hashlib", "dataclasses", "posixpath"})


if __name__ == "__main__":
    unittest.main()
