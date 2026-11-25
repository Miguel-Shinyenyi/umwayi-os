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


def group_of(workflow, number, sha, draft):
    """The concurrency group, evaluated from the text of the workflow the way Actions does for the three forms it uses: a bare name, an
    `a || b` (the first that is not empty), and a boolean that prints as true or false (and as nothing on a push, which has no pull request)."""
    line = next(l for l in CODE.split("\n") if l.startswith("  group:"))
    ctx = {"github.workflow": workflow, "github.event.pull_request.number": str(number or ""), "github.sha": sha,
           "github.event.pull_request.draft": "" if draft is None else ("true" if draft else "false")}

    def value(expr):
        parts = [e.strip() for e in expr.split("||")]
        for e in parts:
            if ctx[e]:
                return ctx[e]
        return ""
    out = line.split("group:", 1)[1].strip()
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: value(m.group(1)), out)


class ConcurrencyGroupTests(unittest.TestCase):
    """B-0005: a skipped draft run cancelled the real run of a pull request marked ready a second later (PR 217)."""

    def test_planted_fault_a_draft_run_and_a_ready_run_of_the_same_pull_request_are_in_different_groups(self):
        draft = group_of("tests", 217, "aaa", True)
        ready = group_of("tests", 217, "aaa", False)
        self.assertNotEqual(draft, ready)  # with the old group they were equal, and the skipped run cancelled the real one

    def test_two_ready_runs_of_one_pull_request_share_a_group_so_a_newer_push_still_cancels_the_older(self):
        self.assertEqual(group_of("tests", 217, "aaa", False), group_of("tests", 217, "bbb", False))
        self.assertEqual(group_of("tests", 217, "aaa", True), group_of("tests", 217, "bbb", True))

    def test_pull_requests_do_not_share_a_group_and_a_push_to_main_has_its_own_group_per_commit(self):
        self.assertNotEqual(group_of("tests", 217, "a", False), group_of("tests", 218, "a", False))
        self.assertNotEqual(group_of("tests", None, "sha1", None), group_of("tests", None, "sha2", None))
        self.assertTrue(group_of("tests", None, "sha1", None).startswith("tests-sha1"))

    def test_the_group_text_ends_with_the_draft_state_and_the_cancel_rule_is_unchanged(self):
        self.assertIn("-${{ github.event.pull_request.draft }}", CODE)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", CODE)

    def test_the_header_comment_names_the_reason(self):
        self.assertIn("a skipped run of a draft must never cancel the real run", CODE)


if __name__ == "__main__":
    unittest.main()
