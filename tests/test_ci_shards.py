"""W20: the shard assignment, the shard runner and the final check (tools/ci_shards.py), with the planted faults:
a shard that drops a test, a test in no shard, a shard that did not run."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import ci_map, ci_plan, ci_shards, generated_files

REPO = Path(__file__).resolve().parent.parent
ASSIGN_PATH = REPO / "tools" / "ci_shards.json"
ASSIGN = json.loads(ASSIGN_PATH.read_text(encoding="utf-8"))

TEST_A = "import unittest\n\n\nclass A(unittest.TestCase):\n    def test_one(self):\n        pass\n\n    def test_two(self):\n        pass\n"
TEST_B = "import unittest\n\n\nclass B(unittest.TestCase):\n    def test_three(self):\n        pass\n"
TEST_C = "import unittest\n\n\nclass C(unittest.TestCase):\n    def test_four(self):\n        pass\n\n    @unittest.skip('later')\n    def test_five(self):\n        pass\n"
# The planted fault: a test that is found by discovery and silently never runs (run() does nothing).
TEST_DROP = ("import unittest\n\n\nclass Drop(unittest.TestCase):\n    def run(self, result=None):\n        return None\n\n"
             "    def test_never(self):\n        self.fail('must not be reached')\n")
TEST_FAIL = "import unittest\n\n\nclass F(unittest.TestCase):\n    def test_bad(self):\n        self.fail('x')\n"
TEST_BROKEN = "import does_not_exist_anywhere\n"


def fixture(files, shards=2, assign=None):
    tmp = tempfile.TemporaryDirectory(prefix="umwayi-cishards-")
    root = Path(tmp.name)
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("")
    for name, text in files.items():
        (root / "tests" / name).write_text(text)
    if assign is None:
        assign = {n: 1 + i % shards for i, n in enumerate(sorted(files))}
    data = {"shards": shards, "files": {f"tests/{n}": {"shard": s, "seconds": 1.0} for n, s in assign.items()}}
    (root / "assign.json").write_text(json.dumps(data))
    return tmp, root


def run_cli(root, *args, env=None, cwd=None):
    e = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    e.pop("CI_PLAN", None)
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "tools.ci_shards", *args], cwd=cwd or root, capture_output=True, text=True,
                          env=e, timeout=120)


def run_shard(root, shard, version="3.12", select=None, report="r.json"):
    args = ["run", "--root", str(root), "--assignments", str(root / "assign.json"), "--shard", str(shard),
            "--python-version", version, "--report", str(root / report)]
    env = {}
    if select is not None:
        env["CI_PLAN"] = json.dumps({"schema": 1, "python": {"files": select}})
    return run_cli(root, *args, env=env)


class AssignmentFileTests(unittest.TestCase):
    def test_every_test_file_is_in_exactly_one_shard(self):
        problems = ci_shards.assignment_problems(ASSIGN, REPO)
        self.assertEqual(problems, [], generated_files.stale_message("tools/ci_shards.json", problems))

    def test_the_file_is_the_fixed_point_of_balance(self):
        seconds = {f: v["seconds"] for f, v in ASSIGN["files"].items()}
        again = ci_shards.balance(seconds, ASSIGN["shards"])
        self.assertEqual(again, {f: v["shard"] for f, v in ASSIGN["files"].items()})

    def test_balance_is_deterministic_and_order_free(self):
        seconds = {f"tests/t{i}.py": float((i * 37) % 11 + 1) for i in range(40)}
        a = ci_shards.balance(seconds, 3)
        b = ci_shards.balance(dict(reversed(list(seconds.items()))), 3)
        self.assertEqual(a, b)

    def test_the_shards_are_balanced_by_measured_time(self):
        totals = {}
        for v in ASSIGN["files"].values():
            totals[v["shard"]] = totals.get(v["shard"], 0) + v["seconds"]
        self.assertEqual(sorted(totals), list(range(1, ASSIGN["shards"] + 1)))
        self.assertLessEqual(max(totals.values()) / (sum(totals.values()) / len(totals)), 1.12, totals)

    def test_there_are_two_or_three_shards(self):
        self.assertIn(ASSIGN["shards"], (2, 3))

    def test_the_slow_suites_are_spread_over_the_shards(self):
        shards = {v["shard"] for f, v in ASSIGN["files"].items() if f.startswith(("tests/agents/", "tests/adapters/", "tests/serve/"))}
        self.assertGreater(len(shards), 1)

    def test_a_new_test_file_in_no_shard_is_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("")
            (root / "tests" / "test_new.py").write_text(TEST_A)
            problems = ci_shards.assignment_problems({"shards": 2, "files": {}}, root)
        self.assertTrue(any("test_new.py" in p and "no shard" in p for p in problems), problems)

    def test_a_listed_file_that_does_not_exist_is_a_problem(self):
        data = copy.deepcopy(ASSIGN)
        data["files"]["tests/test_gone.py"] = {"shard": 1, "seconds": 1.0}
        self.assertTrue(any("test_gone.py" in p for p in ci_shards.assignment_problems(data, REPO)))

    def test_a_shard_number_out_of_range_is_a_problem(self):
        data = copy.deepcopy(ASSIGN)
        first = sorted(data["files"])[0]
        for bad in (0, data["shards"] + 1, "1", None, True):
            data["files"][first]["shard"] = bad
            self.assertTrue(ci_shards.assignment_problems(data, REPO), bad)

    def test_an_empty_shard_is_a_problem(self):
        data = copy.deepcopy(ASSIGN)
        for v in data["files"].values():
            v["shard"] = 1
        self.assertTrue(any("empty" in p for p in ci_shards.assignment_problems(data, REPO)))


class RunShardTests(unittest.TestCase):
    def test_a_shard_runs_its_files_and_reports(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_b.py": TEST_B})
        self.addCleanup(tmp.cleanup)
        r = run_shard(root, 1)
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((root / "r.json").read_text())
        self.assertTrue(rep["ok"])
        self.assertEqual(len(rep["expected"]), 2)
        self.assertEqual(rep["expected"], sorted(rep["executed"]))
        self.assertEqual(rep["python"], "3.12")
        self.assertEqual(sum(len(v) for v in rep["discovered"].values()), 3)

    def test_the_other_shard_runs_the_rest(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_b.py": TEST_B})
        self.addCleanup(tmp.cleanup)
        self.assertEqual(run_shard(root, 2).returncode, 0)
        self.assertEqual(json.loads((root / "r.json").read_text())["expected"], ["tests.test_b.B.test_three"])

    def test_a_skip_is_counted_as_run_and_reported(self):
        tmp, root = fixture({"test_c.py": TEST_C}, shards=1)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(run_shard(root, 1).returncode, 0)
        rep = json.loads((root / "r.json").read_text())
        self.assertEqual((len(rep["executed"]), rep["counts"]["skipped"]), (2, 1))

    def test_a_failing_test_exits_2(self):
        tmp, root = fixture({"test_f.py": TEST_FAIL}, shards=1)
        self.addCleanup(tmp.cleanup)
        r = run_shard(root, 1)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(json.loads((root / "r.json").read_text())["ok"])

    def test_a_module_that_does_not_import_exits_2(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_x.py": TEST_BROKEN}, shards=1)
        self.addCleanup(tmp.cleanup)
        r = run_shard(root, 1)
        self.assertEqual(r.returncode, 2)
        rep = json.loads((root / "r.json").read_text())
        self.assertFalse(rep["ok"])

    def test_PLANTED_FAULT_a_shard_that_silently_drops_a_test_fails(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_drop.py": TEST_DROP}, shards=1)
        self.addCleanup(tmp.cleanup)
        r = run_shard(root, 1)
        self.assertEqual(r.returncode, 2, "unittest alone would report OK here")
        rep = json.loads((root / "r.json").read_text())
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["missing"], ["tests.test_drop.Drop.test_never"])
        self.assertIn("did not run", r.stdout + r.stderr)

    def test_PLANTED_FAULT_a_test_file_in_no_shard_fails(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_b.py": TEST_B}, assign={"test_a.py": 1, "test_b.py": 2})
        self.addCleanup(tmp.cleanup)
        (root / "tests" / "test_new.py").write_text(TEST_B.replace("class B", "class N"))
        r = run_shard(root, 1)
        self.assertEqual(r.returncode, 2)
        rep = json.loads((root / "r.json").read_text())
        self.assertEqual(rep["unassigned_files"], ["tests/test_new.py"])
        self.assertIn("no shard", r.stdout + r.stderr)

    def test_a_selection_runs_only_the_selected_files_of_the_shard(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_b.py": TEST_B}, shards=1)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(run_shard(root, 1, select=["tests/test_b.py"]).returncode, 0)
        self.assertEqual(json.loads((root / "r.json").read_text())["expected"], ["tests.test_b.B.test_three"])

    def test_a_shard_with_nothing_to_run_fails(self):
        tmp, root = fixture({"test_a.py": TEST_A, "test_b.py": TEST_B}, shards=2)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(run_shard(root, 1, select=["tests/test_b.py"]).returncode, 2)

    def test_a_selected_file_that_does_not_exist_fails(self):
        tmp, root = fixture({"test_a.py": TEST_A}, shards=1)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(run_shard(root, 1, select=["tests/test_ghost.py"]).returncode, 2)

    def test_usage_errors_exit_64(self):
        tmp, root = fixture({"test_a.py": TEST_A}, shards=1)
        self.addCleanup(tmp.cleanup)
        base = ["--root", str(root), "--assignments", str(root / "assign.json")]
        for args in ([], ["run"], ["run", *base, "--shard", "0", "--python-version", "3.12", "--report", "r"],
                     ["run", *base, "--shard", "9", "--python-version", "3.12", "--report", "r"],
                     ["run", *base, "--shard", "x", "--python-version", "3.12", "--report", "r"],
                     ["run", *base, "--shard", "1", "--report", "r"], ["nope"], ["verify", "--bogus"],
                     ["run", "--root", str(root / "nowhere"), "--assignments", str(root / "assign.json"), "--shard", "1",
                      "--python-version", "3.12", "--report", "r"]):
            self.assertEqual(run_cli(root, *args).returncode, 64, args)

    def test_a_bad_plan_in_the_environment_exits_64(self):
        tmp, root = fixture({"test_a.py": TEST_A}, shards=1)
        self.addCleanup(tmp.cleanup)
        args = ["run", "--root", str(root), "--assignments", str(root / "assign.json"), "--shard", "1",
                "--python-version", "3.12", "--report", str(root / "r.json")]
        for bad in ("not json", "[]", json.dumps({"schema": 2}), json.dumps({"schema": 1, "python": {"files": "x"}})):
            self.assertEqual(run_cli(root, *args, env={"CI_PLAN": bad}).returncode, 64, bad)


def report(version, shard, expected, executed=None, discovered=None, of=2, ok=True, unassigned=(), missing=()):
    executed = expected if executed is None else executed
    discovered = discovered if discovered is not None else {"tests/test_a.py": ["a1", "a2"], "tests/test_b.py": ["b1"]}
    return {"schema": 1, "python": version, "shard": shard, "of": of, "ok": ok, "expected": sorted(expected),
            "executed": sorted(executed), "discovered": discovered, "unassigned_files": list(unassigned),
            "missing": list(missing), "counts": {"run": len(executed), "failures": 0, "errors": 0, "skipped": 0},
            "seconds": {}}


A2 = {"shard": 1, "seconds": 1.0}
B1 = {"shard": 2, "seconds": 1.0}
SMALL = {"shards": 2, "files": {"tests/test_a.py": A2, "tests/test_b.py": B1}}


def full_plan(versions=("3.12",), node=False):
    include = [{"python-version": v, "shard": s, "of": 2} for v in versions for s in (1, 2)]
    return {"schema": 1, "full": False, "reason": "x", "python": {"run": True, "files": None, "versions": list(versions),
            "shards": [1, 2], "of": 2}, "node": node, "matrix": {"include": include}, "not_run": []}


def good_reports(versions=("3.12",)):
    out = {}
    for v in versions:
        out[(v, 1)] = report(v, 1, ["a1", "a2"])
        out[(v, 2)] = report(v, 2, ["b1"])
    return out


OK = {"plan": "success", "test": "success", "node": "skipped"}


class VerifyTests(unittest.TestCase):
    def check(self, plan=None, results=None, reports=None, assign=SMALL):
        return ci_shards.verify_all(plan or full_plan(), dict(results or OK), reports if reports is not None else good_reports(),
                                    assign)

    def test_all_good(self):
        self.assertEqual(self.check(), [])

    def test_all_good_on_four_versions(self):
        vs = ("3.10", "3.11", "3.12", "3.13")
        self.assertEqual(self.check(plan=full_plan(vs), reports=good_reports(vs)), [])

    def test_PLANTED_FAULT_a_shard_drops_a_test(self):
        reps = good_reports()
        reps[("3.12", 1)]["executed"] = ["a1"]
        reps[("3.12", 1)]["ok"] = True  # the shard lied or its own check failed to see it
        problems = self.check(reports=reps)
        self.assertTrue(any("a2" in p and "not run" in p for p in problems), problems)

    def test_a_shard_that_drops_a_test_and_says_so_fails(self):
        reps = good_reports()
        reps[("3.12", 1)].update(executed=["a1"], missing=["a2"], ok=False)
        self.assertTrue(self.check(reports=reps))

    def test_PLANTED_FAULT_a_file_in_no_shard_fails_even_if_every_shard_is_green(self):
        reps = good_reports()
        for r in reps.values():
            r["discovered"] = {**r["discovered"], "tests/test_new.py": ["n1"]}
        problems = self.check(reports=reps)
        self.assertTrue(any("test_new.py" in p and "no shard" in p for p in problems), problems)

    def test_a_missing_report_fails(self):
        reps = good_reports()
        del reps[("3.12", 2)]
        self.assertTrue(any("no report" in p for p in self.check(reports=reps)))

    def test_PLANTED_FAULT_a_shard_that_did_not_run_fails(self):
        for state in ("skipped", "cancelled", "failure", "", "weird"):
            self.assertTrue(self.check(results={**OK, "test": state}), state)

    def test_a_failed_plan_fails(self):
        for state in ("failure", "skipped", "cancelled", ""):
            self.assertTrue(self.check(results={**OK, "plan": state}), state)

    def test_a_shard_report_that_says_not_ok_fails(self):
        reps = good_reports()
        reps[("3.12", 2)]["ok"] = False
        self.assertTrue(self.check(reports=reps))

    def test_a_shard_that_lists_a_missing_test_fails(self):
        reps = good_reports()
        reps[("3.12", 2)]["missing"] = ["b1"]
        self.assertTrue(self.check(reports=reps))

    def test_shards_that_disagree_on_what_exists_fail(self):
        reps = good_reports()
        reps[("3.12", 2)]["discovered"] = {"tests/test_a.py": ["a1", "a2"], "tests/test_b.py": ["b1", "b2"]}
        self.assertTrue(any("disagree" in p for p in self.check(reports=reps)))

    def test_a_test_found_by_discovery_but_expected_by_no_shard_fails(self):
        reps = good_reports()
        for r in reps.values():
            r["discovered"]["tests/test_b.py"] = ["b1", "b2"]
        problems = self.check(reports=reps)
        self.assertTrue(any("b2" in p for p in problems), problems)

    def test_a_report_for_the_wrong_cell_fails(self):
        reps = good_reports()
        reps[("3.12", 2)]["shard"] = 1
        self.assertTrue(self.check(reports=reps))
        reps = good_reports()
        reps[("3.12", 2)]["python"] = "3.11"
        self.assertTrue(self.check(reports=reps))

    def test_an_empty_discovery_fails(self):
        reps = good_reports()
        for r in reps.values():
            r.update(discovered={}, expected=[], executed=[])
        self.assertTrue(self.check(reports=reps))

    def test_node_expected_must_succeed(self):
        for state, bad in (("success", False), ("skipped", True), ("failure", True), ("cancelled", True), ("", True)):
            problems = self.check(plan=full_plan(node=True), results={**OK, "node": state})
            self.assertEqual(bool(problems), bad, state)

    def test_node_not_expected_must_be_skipped(self):
        self.assertEqual(self.check(), [])
        self.assertTrue(self.check(results={**OK, "node": "failure"}))

    def test_a_partial_plan_passes_when_the_selection_ran(self):
        plan = full_plan()
        plan.update(full=False, not_run=["x"])
        plan["python"].update(files=["tests/test_b.py"], shards=[2])
        plan["matrix"] = {"include": [{"python-version": "3.12", "shard": 2, "of": 2}]}
        reps = {("3.12", 2): report("3.12", 2, ["b1"])}
        self.assertEqual(ci_shards.verify_all(plan, OK, reps, SMALL), [])

    def test_a_partial_plan_still_fails_when_a_selected_test_was_dropped(self):
        plan = full_plan()
        plan.update(full=False)
        plan["python"].update(files=["tests/test_b.py"], shards=[2])
        plan["matrix"] = {"include": [{"python-version": "3.12", "shard": 2, "of": 2}]}
        reps = {("3.12", 2): report("3.12", 2, ["b1"], executed=[])}
        self.assertTrue(ci_shards.verify_all(plan, OK, reps, SMALL))

    def test_no_python_planned_and_the_job_skipped_is_fine(self):
        plan = full_plan()
        plan["python"].update(run=False, files=[], versions=[], shards=[])
        plan["matrix"] = {"include": []}
        self.assertEqual(ci_shards.verify_all(plan, {**OK, "test": "skipped"}, {}, SMALL), [])

    def test_no_python_planned_but_the_job_ran_fails(self):
        plan = full_plan()
        plan["python"].update(run=False, files=[], versions=[], shards=[])
        plan["matrix"] = {"include": []}
        self.assertTrue(ci_shards.verify_all(plan, OK, {}, SMALL))

    def test_the_plan_may_not_skip_python_on_a_full_plan(self):
        plan = full_plan()
        plan.update(full=True, node=True)
        plan["python"]["run"] = False
        self.assertTrue(self.check(plan=plan, results={**OK, "node": "success", "test": "skipped"}))

    def test_a_full_plan_without_node_is_refused(self):
        plan = full_plan()
        plan["full"] = True
        self.assertTrue(any("node" in p for p in self.check(plan=plan)))

    def test_the_summary_says_what_was_not_run(self):
        plan = full_plan()
        plan.update(full=False, not_run=["python 3.11 and 3.12: not run on this pull request"])
        text = ci_shards.summary(plan, [], good_reports())
        self.assertIn("NOT RUN", text)
        self.assertIn("python 3.11 and 3.12", text)
        self.assertNotIn("\u2014", text)


class VerifyCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="umwayi-civerify-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "assign.json").write_text(json.dumps(SMALL))
        (self.dir / "reports").mkdir()

    def write_reports(self, reports):
        for (v, s), rep in reports.items():
            (self.dir / "reports" / f"report-{v}-{s}.json").write_text(json.dumps(rep))

    def verify(self, plan, results=OK):
        env = {"CI_PLAN": json.dumps(plan), "PLAN_RESULT": results["plan"], "TEST_RESULT": results["test"],
               "NODE_RESULT": results["node"]}
        return run_cli(self.dir, "verify", "--assignments", str(self.dir / "assign.json"),
                       "--reports", str(self.dir / "reports"), env=env)

    def test_exit_0_when_everything_ran(self):
        self.write_reports(good_reports())
        r = self.verify(full_plan())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("3 tests", r.stdout)

    def test_exit_2_when_a_test_was_dropped(self):
        reps = good_reports()
        reps[("3.12", 1)]["executed"] = ["a1"]
        self.write_reports(reps)
        r = self.verify(full_plan())
        self.assertEqual(r.returncode, 2)
        self.assertIn("a2", r.stdout + r.stderr)

    def test_exit_2_for_a_garbled_report(self):
        self.write_reports(good_reports())
        (self.dir / "reports" / "report-3.12-1.json").write_text("{not json")
        self.assertEqual(self.verify(full_plan()).returncode, 2)

    def test_exit_2_for_a_missing_plan(self):
        self.write_reports(good_reports())
        r = run_cli(self.dir, "verify", "--assignments", str(self.dir / "assign.json"), "--reports", str(self.dir / "reports"),
                    env={"PLAN_RESULT": "success", "TEST_RESULT": "success", "NODE_RESULT": "skipped"})
        self.assertEqual(r.returncode, 2)

    def test_exit_2_for_an_unknown_job_result(self):
        self.write_reports(good_reports())
        self.assertEqual(self.verify(full_plan(), {**OK, "test": "banana"}).returncode, 2)

    def test_exit_64_for_usage(self):
        self.assertEqual(run_cli(self.dir, "verify").returncode, 64)

    def test_the_summary_file_is_written(self):
        self.write_reports(good_reports())
        out = self.dir / "summary.md"
        e = {"CI_PLAN": json.dumps(full_plan()), "PLAN_RESULT": "success", "TEST_RESULT": "success", "NODE_RESULT": "skipped",
             "GITHUB_STEP_SUMMARY": str(out)}
        r = run_cli(self.dir, "verify", "--assignments", str(self.dir / "assign.json"), "--reports", str(self.dir / "reports"), env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("tests", out.read_text())


class PlanAndAssignmentFitTests(unittest.TestCase):
    def test_a_real_plan_matrix_cells_all_have_a_shard_in_the_file(self):
        p = ci_plan.build_plan([], "push", ci_map.load_map(), ASSIGN)
        self.assertEqual({m["shard"] for m in p["matrix"]["include"]}, set(range(1, ASSIGN["shards"] + 1)))


if __name__ == "__main__":
    unittest.main()


class AssignMissingTests(unittest.TestCase):
    """W21, Part B: the small repair. `balance` stays the full rebalance."""

    def make(self, names, entries, shards=3):
        tmp = tempfile.TemporaryDirectory(prefix="umwayi-assign-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("")
        for n in names:
            (root / "tests" / n).write_text(TEST_B)
        data = {"shards": shards, "files": {f"tests/{n}": {"shard": s, "seconds": sec} for n, (s, sec) in entries.items()}}
        (root / "assign.json").write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
        return root

    def assign(self, root):
        r = run_cli(root, "assign-missing", "--assignments", str(root / "assign.json"), "--root", str(root))
        return r, json.loads((root / "assign.json").read_text())["files"]

    def test_a_new_file_goes_to_the_shard_with_the_least_seconds(self):
        root = self.make(["test_a.py", "test_b.py", "test_c.py", "test_new.py"],
                         {"test_a.py": (1, 10.0), "test_b.py": (2, 2.0), "test_c.py": (3, 6.0)})
        r, files = self.assign(root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files["tests/test_new.py"]["shard"], 2)
        self.assertEqual(files["tests/test_new.py"]["seconds"], 6.0)  # the average of 10, 2 and 6
        self.assertEqual(files["tests/test_a.py"], {"shard": 1, "seconds": 10.0})

    def test_ties_go_to_the_lowest_shard_and_files_go_in_name_order(self):
        root = self.make(["test_a.py", "test_y.py", "test_x.py"], {"test_a.py": (3, 4.0)})
        _, files = self.assign(root)
        # shards 1 and 2 are empty (tie, lowest first); then shard 2 is lighter than shard 3 and shard 1 now
        self.assertEqual((files["tests/test_x.py"]["shard"], files["tests/test_y.py"]["shard"]), (1, 2))

    def test_a_file_with_no_seconds_counts_as_the_average_when_the_file_is_empty(self):
        root = self.make(["test_a.py", "test_b.py"], {}, shards=2)
        _, files = self.assign(root)
        self.assertEqual({f: v["shard"] for f, v in files.items()}, {"tests/test_a.py": 1, "tests/test_b.py": 2})
        self.assertEqual(files["tests/test_a.py"]["seconds"], 1.0)

    def test_the_entry_of_a_deleted_file_is_removed_and_the_others_stay(self):
        root = self.make(["test_a.py"], {"test_a.py": (2, 3.0), "test_gone.py": (1, 9.0)})
        r, files = self.assign(root)
        self.assertEqual(files, {"tests/test_a.py": {"shard": 2, "seconds": 3.0}})
        self.assertIn("removed tests/test_gone.py", r.stdout)

    def test_the_bytes_are_deterministic_and_a_second_run_changes_nothing(self):
        root = self.make(["test_a.py", "test_b.py", "test_c.py"], {"test_a.py": (1, 5.0)})
        self.assign(root)
        first = (root / "assign.json").read_bytes()
        r, _ = self.assign(root)
        self.assertEqual((root / "assign.json").read_bytes(), first)
        self.assertIn("nothing to assign", r.stdout)
        other = self.make(["test_c.py", "test_b.py", "test_a.py"], {"test_a.py": (1, 5.0)})
        self.assign(other)
        self.assertEqual((other / "assign.json").read_bytes(), first)

    def test_the_layout_is_the_one_balance_writes_and_check_passes(self):
        root = self.make(["test_a.py", "test_b.py", "test_c.py"], {"test_a.py": (1, 5.0)})
        self.assign(root)
        data = json.loads((root / "assign.json").read_text())
        self.assertEqual((root / "assign.json").read_text(), json.dumps(data, indent=1, sort_keys=True) + "\n")
        self.assertEqual(list(data), ["files", "shards"])
        r = run_cli(root, "check", "--assignments", str(root / "assign.json"), "--root", str(root))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_missing_file_is_found_by_check_and_repaired(self):
        root = self.make(["test_a.py", "test_new.py"], {"test_a.py": (1, 5.0)}, shards=1)
        check = ["check", "--assignments", str(root / "assign.json"), "--root", str(root)]
        self.assertEqual(run_cli(root, *check).returncode, 2)
        self.assign(root)
        self.assertEqual(run_cli(root, *check).returncode, 0)

    def test_it_never_rebalances(self):
        root = self.make(["test_a.py", "test_b.py", "test_c.py", "test_n.py"],
                         {"test_a.py": (1, 50.0), "test_b.py": (1, 40.0), "test_c.py": (1, 30.0)})
        _, files = self.assign(root)
        self.assertEqual([files[f"tests/test_{n}.py"]["shard"] for n in "abc"], [1, 1, 1])

    def test_a_bad_option_and_a_bad_file_are_usage_errors(self):
        root = self.make(["test_a.py"], {"test_a.py": (1, 1.0)})
        self.assertEqual(run_cli(root, "assign-missing", "--nope", "x").returncode, 64)
        (root / "assign.json").write_text("[]")
        r = run_cli(root, "assign-missing", "--assignments", str(root / "assign.json"), "--root", str(root))
        self.assertEqual(r.returncode, 64)

    def test_the_real_file_needs_nothing_and_stays_byte_for_byte(self):
        before = ASSIGN_PATH.read_bytes()
        new, done = ci_shards.assign_missing(ASSIGN, REPO)
        self.assertEqual(done, [])
        self.assertEqual((json.dumps(new, indent=1, sort_keys=True) + "\n").encode(), before)


class HintTests(unittest.TestCase):
    """W21, Part D: a failing check ends with the exact regenerate command from tools/generated_files.json."""

    def test_check_names_the_file_and_ends_with_the_command(self):
        root = AssignMissingTests.make(self, ["test_a.py", "test_new.py"], {"test_a.py": (1, 1.0)}, shards=1)
        r = run_cli(root, "check", "--assignments", str(root / "assign.json"), "--root", str(root))
        self.assertEqual(r.returncode, 2)
        lines = r.stderr.strip().split("\n")
        self.assertIn("tests/test_new.py is in no shard", lines[0])
        self.assertEqual(lines[-1], "ci_shards: To fix it, run: python -m tools.ci_shards assign-missing")

    def test_the_hint_is_the_one_in_the_list(self):
        self.assertEqual(ci_shards.regenerate_hint(), generated_files.regenerate_hint("tools/ci_shards.json"))
