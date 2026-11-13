"""W20: the shape of .github/workflows/ci.yml that the design rules depend on. A workflow cannot be run here, so
these tests read its text; the real run on GitHub is the record."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEXT = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
CODE = "\n".join(line for line in TEXT.splitlines() if not line.lstrip().startswith("#"))


def job(name):
    m = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", CODE + "\n", re.M)
    assert m, f"no job {name}"
    return m.group(1)


class TriggerTests(unittest.TestCase):
    def test_name_is_tests(self):
        self.assertRegex(CODE, re.compile(r"^name: tests$", re.M))

    def test_pull_request_and_push_to_main_only(self):
        on = re.search(r"^on:\n((?:  .*\n)+)", CODE, re.M).group(1)
        self.assertRegex(on, re.compile(r"^  pull_request:$", re.M))
        self.assertRegex(on, re.compile(r"^  push:\n    branches: \[main\]$", re.M))
        self.assertEqual(re.findall(r"^  (\w+):", on, re.M), ["pull_request", "push"])

    def test_a_push_to_main_is_never_cancelled(self):
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", CODE)
        self.assertIn("github.event.pull_request.number || github.sha", CODE)

    def test_read_only_permissions(self):
        self.assertRegex(CODE, re.compile(r"^permissions:\n  contents: read$", re.M))


class JobTests(unittest.TestCase):
    def test_the_four_jobs(self):
        self.assertEqual(re.findall(r"^  (\w+):\n    ", CODE.split("\njobs:")[1], re.M), ["plan", "test", "node", "result"])

    def test_plan_always_runs_and_reads_the_diff_with_full_history(self):
        j = job("plan")
        self.assertNotIn("\n    if:", "\n" + j)
        self.assertIn("fetch-depth: 0", j)
        self.assertIn("python -m tools.ci_plan", j)
        self.assertIn("EVENT: ${{ github.event_name }}", j)
        self.assertIn("BASE: ${{ github.event.pull_request.base.sha }}", j)

    def test_the_test_job_is_the_matrix_from_the_plan_with_a_stable_name(self):
        j = job("test")
        self.assertIn("needs: plan", j)
        self.assertIn("needs.plan.outputs.python == 'true'", j)
        self.assertIn("fromJSON(needs.plan.outputs.matrix)", j)
        self.assertIn("name: test (${{ matrix.python-version }}, shard ${{ matrix.shard }}/${{ matrix.of }})", j)
        self.assertIn("fail-fast: false", j)
        self.assertIn("python -m tools.ci_shards run", j)
        self.assertIn("actions/upload-artifact", j)

    def test_the_report_is_uploaded_even_when_the_tests_fail(self):
        j = job("test")
        step = j[j.index("Upload the shard report"):]
        self.assertIn("if: always()", step)

    def test_the_node_job_runs_only_when_planned_and_keeps_the_old_steps(self):
        j = job("node")
        self.assertIn("needs.plan.outputs.node == 'true'", j)
        self.assertIn("actions/cache@v4", j)
        self.assertIn("hashFiles('ui/package-lock.json', 'site/package-lock.json')", j)
        self.assertIn("(cd ui && npm ci --ignore-scripts && node --test)", j)
        self.assertIn("(cd site && npm ci --ignore-scripts && node --test)", j)

    def test_the_node_job_requires_a_browser_on_both_node_test_runs(self):
        """CI.2: a runner without Chrome must fail the phone tests, not skip them."""
        j = job("node")
        steps = ["      - " + x for x in j.split("      - ")[1:]]
        runs = [x for x in steps if "node --test" in x]
        self.assertTrue(runs, "no step runs node --test")
        for cmd in ("(cd ui && npm ci --ignore-scripts && node --test)", "(cd site && npm ci --ignore-scripts && node --test)"):
            covering = [x for x in runs if cmd in x]
            self.assertEqual(len(covering), 1, cmd)
            self.assertRegex(covering[0], re.compile(r"^\s+env:\n(?:\s+\w+: .*\n)*?\s+UMWAYI_REQUIRE_BROWSER: \"?1\"?\s*$", re.M), cmd)

    def test_the_result_job_is_always_on_and_waits_for_everything(self):
        j = job("result")
        self.assertIn("if: always()", j)
        self.assertIn("needs: [plan, test, node]", j)
        for name in ("PLAN_RESULT: ${{ needs.plan.result }}", "TEST_RESULT: ${{ needs.test.result }}",
                     "NODE_RESULT: ${{ needs.node.result }}", "CI_PLAN: ${{ needs.plan.outputs.plan }}"):
            self.assertIn(name, j)
        self.assertIn("python -m tools.ci_shards verify", j)
        self.assertIn("actions/download-artifact", j)

    def test_no_job_but_result_uses_always(self):
        for name in ("plan", "node"):
            self.assertNotIn("always()", job(name))

    def test_the_old_matrix_is_gone(self):
        self.assertNotIn('python-version: ["3.10"', CODE)
        self.assertNotIn("unittest discover", CODE)

    def test_changed_values_reach_the_shell_only_through_env(self):
        for run in re.findall(r"^\s+run: (.*)$", CODE, re.M):
            for risky in ("github.head_ref", "github.event.pull_request.title", "github.event.pull_request.body", "head.ref"):
                self.assertNotIn(risky, run)

    def test_no_em_dash(self):
        self.assertNotIn("\u2014", TEXT)

    def test_actions_are_the_same_majors_as_before(self):
        used = set(re.findall(r"uses: ([\w./-]+@v\d+)", CODE))
        self.assertTrue(used <= {"actions/checkout@v4", "actions/setup-python@v5", "actions/cache@v4",
                                 "actions/upload-artifact@v4", "actions/download-artifact@v4"}, used)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RequireBrowserTests(unittest.TestCase):
    """CI.2: with UMWAYI_REQUIRE_BROWSER=1 and no browser, the phone tests throw the how-to-run message."""

    def run_phone(self, rel, require):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, UMWAYI_BROWSER=os.path.join(tmp, "no-such-browser"), HOME=tmp)
            env.pop("UMWAYI_REQUIRE_BROWSER", None)
            if require:
                env["UMWAYI_REQUIRE_BROWSER"] = "1"
            return subprocess.run(["node", "--test", rel], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)

    def test_a_missing_browser_fails_the_phone_tests_when_required(self):
        for rel in ("ui/test/phone.test.mjs", "site/test/phone.test.mjs"):
            with self.subTest(rel):
                r = self.run_phone(rel, True)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("No Chromium found", r.stdout + r.stderr)

    def test_a_missing_browser_only_skips_when_not_required(self):
        r = self.run_phone("ui/test/phone.test.mjs", False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # the summary line differs between Node versions and reporters, so only the skip message is read
        self.assertIn("No Chromium found", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
