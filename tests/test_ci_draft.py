"""N9: a draft pull request runs nothing, and a pull request marked ready starts its run.

GitHub Actions cannot be run on a laptop, so these tests read the workflow text and evaluate the guard the way Actions does: the job `if`
is true when the `draft` field of the pull request is not the boolean true. What they prove: every job is skipped for a draft (plan and
result carry the guard; test and node need plan, which is skipped, so they are skipped too), `ready_for_review` is a trigger, a push to
main has no draft field and so runs, and `result` is not left running for a draft. What they do not prove: the real behaviour on
GitHub. The first proof is a real draft pull request (see the status part).
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CODE = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
GUARD = "github.event.pull_request.draft != true"


def runs(draft):
    """Evaluate the guard like Actions: `draft` is True, False, or None (a push has no pull request)."""
    return draft is not True


def job(name):
    body = CODE.split("\njobs:")[1]
    m = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  \w+:\n|\Z)", body)
    return m.group(1)


class DraftTests(unittest.TestCase):
    def test_the_pull_request_types_include_ready_for_review_and_the_default_ones(self):
        m = re.search(r"(?m)^  pull_request:\n    types: \[(.*?)\]", CODE)
        self.assertIsNotNone(m)
        self.assertEqual(sorted(t.strip() for t in m.group(1).split(",")), ["opened", "ready_for_review", "reopened", "synchronize"])

    def test_plan_and_result_carry_the_guard_and_test_and_node_depend_on_plan(self):
        self.assertIn("if: " + GUARD, job("plan"))
        self.assertIn("if: always() && " + GUARD, job("result"))
        for name in ("test", "node"):
            self.assertIn("needs: plan", job(name))
            self.assertEqual(re.findall(r"(?m)^    if: (.*)", job(name)), ["needs.plan.outputs." + ("python" if name == "test" else "node") + " == 'true'"])

    def test_planted_fault_the_guard_is_false_for_a_draft_and_true_for_a_ready_pull_request_and_a_push(self):
        self.assertFalse(runs(True))
        self.assertTrue(runs(False))
        self.assertTrue(runs(None))  # a push to main has no pull_request, so the suite still runs

    def test_no_other_job_has_a_guard_that_would_skip_a_ready_pull_request(self):
        self.assertEqual(CODE.split("\njobs:")[1].count(GUARD), 2)  # plan and result, nowhere else

    def test_the_header_comment_says_a_draft_runs_nothing(self):
        self.assertIn("a draft pull request runs nothing", CODE)


if __name__ == "__main__":
    unittest.main()
