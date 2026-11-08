import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import entry_text, without_run_lock, write_sealed_logbook
from umwayi import kill, logbook, publish, rules, taskqueue, workflow
from umwayi.cli import main
from umwayi.errors import ConfigError, UmwayiError, UsageError
from umwayi.logbook import parse

REPO = Path(__file__).resolve().parent.parent

RULES = """
rules:
  - id: helper-read
    title: Reads
    text: An AI helper may read.
    verdict: yes
    matchers:
      helper__exists: true
      type: [read_queue, read_logbook, read_article]
  - id: helper-draft
    title: Drafts
    text: An AI helper may write drafts.
    verdict: yes
    matchers:
      helper__exists: true
      type: write_draft
  - id: helper-no-post
    title: No posting
    text: An AI helper never posts, sends or publishes.
    verdict: no
    matchers:
      helper__exists: true
      type__contains: [post, send, publish]
  - id: run-safe-jobs
    title: Jobs
    text: Jobs are fine.
    verdict: yes
    matchers:
      type: run_job
      command: [report, check, queue-list]
  - id: publish-ask
    title: Publishing
    text: Publishing is Ask me first.
    verdict: ask
    matchers:
      type: publish_draft
  - id: workflow-steps
    title: Workflow steps
    text: A workflow may run its fixed steps.
    verdict: yes
    matchers:
      helper: workflow
      type: workflow_step
      command: [queue-list, steward, social-draft, report, check, approve]
  - id: read-ok
    title: Reads
    text: Reads are fine.
    verdict: yes
    matchers:
      type: read
  - id: money-no
    title: Money
    text: Never move money.
    verdict: no
    matchers:
      type: payment
"""

LOOP = """\
# the content loop
name: content-loop
steps:
  - name: collect
    command: queue-list
    status: open
  - name: brief
    command: steward
    waiting_days: 7
  - name: draft
    command: social-draft
    article: articles/week.md
  - name: approve
    command: approve
"""

ARTICLE = "---\ntitle: Week 45\nlink: https://example.org/week-45\n---\n\nThis week I built the workflows.\n"
QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n| Q-0001 | task | Write the post | open | | | |\n"
)
JOBS = "jobs:\n  - name: open-queue\n    command: queue-list\n    min_gap_days: 1\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        (self.root / "umwayi.json").write_text(json.dumps({
            "memory_dir": "memory", "private_paths": ["private"], "social_channels": ["linkedin", "mastodon"]}))
        (self.root / "articles").mkdir()
        (self.root / "articles" / "week.md").write_text(ARTICLE, encoding="utf-8")
        (self.root / "workflows").mkdir()
        self.wf("content-loop", LOOP)
        (self.root / "jobs.yaml").write_text(JOBS, encoding="utf-8")
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"
        self.queue = self.root / "queue.md"
        self.kill = self.root / ".umwayi" / "KILL"
        p = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)

    def wf(self, name, text):
        (self.root / "workflows" / f"{name}.yaml").write_text(text, encoding="utf-8")

    def cli(self, *argv, clock="2026-11-07"):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def run_loop(self, name="content-loop", clock="2026-11-07"):
        return self.cli("workflow", "run", name, clock=clock)

    def entries(self):
        if not self.log.exists():
            return []
        return [p.entry for p in parse(self.log.read_text(encoding="utf-8"))[0]]

    def snap(self):
        out = {}
        for dp, dn, fn in os.walk(self.root):
            for d in dn:
                out[os.path.relpath(os.path.join(dp, d), self.root) + "/"] = "folder"
            for f in fn:
                full = os.path.join(dp, f)
                out[os.path.relpath(full, self.root)] = (Path(full).read_bytes(), os.stat(full).st_mtime_ns)
        return without_run_lock(out)

    def changed(self, before):
        after = self.snap()
        return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

    def rules_with(self, extra="", without=None):
        text = RULES
        if without:
            blocks = text.split("\n  - ")
            text = "\n  - ".join(b for b in blocks if not b.startswith(f"id: {without}\n"))
        (self.root / "rules.yaml").write_text(text + extra, encoding="utf-8")

    def drafts(self):
        d = self.root / "drafts"
        return sorted(os.listdir(d)) if d.exists() else []


LOG_FILES = {"LOGBOOK.md", ".umwayi/", ".umwayi/logbook.sha256"}


# ================================================================ 8.1 the file


class ValidateTests(Base):
    def problems(self, text, name="t"):
        self.wf(name, text)
        before = self.snap()
        code, out, err = self.cli("workflow", "validate", name)
        self.assertEqual(self.changed(before), [], "validate changed a file")
        return code, out, err

    def test_the_content_loop_is_valid(self):
        code, out, err = self.cli("workflow", "validate", "content-loop")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "ok: workflow content-loop has 4 steps: collect (queue-list), brief (steward), "
                              "draft (social-draft), approve (approve)\n")

    def test_every_command_on_the_allow_list_is_valid(self):
        text = ("name: t\nsteps:\n"
                "  - name: a\n    command: report\n    since_days: 7\n"
                "  - name: b\n    command: steward\n"
                "  - name: c\n    command: social-draft\n    article: articles/week.md\n"
                "  - name: d\n    command: queue-list\n"
                "  - name: e\n    command: check\n    action_type: read\n"
                "  - name: f\n    command: approve\n")
        code, out, _ = self.problems(text)
        self.assertEqual(code, 0, out)
        self.assertEqual(workflow.COMMANDS, ("report", "steward", "social-draft", "queue-list", "check"))

    def test_each_problem_has_its_line(self):
        cases = {
            "not on the allow list": ("name: t\nsteps:\n  - name: a\n    command: shell\n", 4, "not on the allow list"),
            "a shell string": ("name: t\nsteps:\n  - name: a\n    command: \"rm -rf /\"\n", 4, "not on the allow list"),
            "publish-draft is not a step": ("name: t\nsteps:\n  - name: a\n    command: publish-draft\n", 4, "not on the allow list"),
            "git push": ("name: t\nsteps:\n  - name: a\n    command: \"git push\"\n", 4, "not on the allow list"),
            "run": ("name: t\nsteps:\n  - name: a\n    command: run\n", 4, "not on the allow list"),
            "approved_by key": ("name: t\nsteps:\n  - name: a\n    command: approve\n    approved_by: me\n", 5, "'approved_by' is not allowed"),
            "args key": ("name: t\nsteps:\n  - name: a\n    command: queue-list\n    args: [x]\n", 5, "'args' is not allowed"),
            "shell key": ("name: t\nsteps:\n  - name: a\n    command: queue-list\n    shell: ls\n", 5, "'shell' is not allowed"),
            "option of another command": ("name: t\nsteps:\n  - name: a\n    command: queue-list\n    since_days: 3\n", 5, "not allowed for queue-list"),
            "unknown top key": ("name: t\napproved_by: me\nsteps:\n  - name: a\n    command: approve\n", 2, "not allowed at the top"),
            "missing name": ("steps:\n  - name: a\n    command: approve\n", 1, "needs a name"),
            "bad name": ("name: Bad Name\nsteps:\n  - name: a\n    command: approve\n", 1, "lowercase"),
            "name is not the file": ("name: other\nsteps:\n  - name: a\n    command: approve\n", 1, "file name"),
            "missing steps": ("name: t\n", 1, "needs a list of steps"),
            "empty steps": ("name: t\nsteps: []\n", 2, "at least one step"),
            "steps not a list": ("name: t\nsteps: 5\n", 2, "at least one step"),
            "step not a mapping": ("name: t\nsteps:\n  - just text\n", 3, "must be a mapping"),
            "step without name": ("name: t\nsteps:\n  - command: approve\n", 3, "needs a name"),
            "bad step name": ("name: t\nsteps:\n  - name: Step_One\n    command: approve\n", 3, "lowercase"),
            "step name twice": ("name: t\nsteps:\n  - name: a\n    command: queue-list\n  - name: a\n    command: approve\n", 5, "used twice"),
            "missing command": ("name: t\nsteps:\n  - name: a\n", 3, "needs a command"),
            "report without since_days": ("name: t\nsteps:\n  - name: a\n    command: report\n", 3, "needs since_days"),
            "since_days zero": ("name: t\nsteps:\n  - name: a\n    command: report\n    since_days: 0\n", 5, "since_days"),
            "since_days text": ("name: t\nsteps:\n  - name: a\n    command: report\n    since_days: week\n", 5, "since_days"),
            "since_days bool": ("name: t\nsteps:\n  - name: a\n    command: report\n    since_days: true\n", 5, "since_days"),
            "waiting_days too big": ("name: t\nsteps:\n  - name: a\n    command: steward\n    waiting_days: 400\n", 5, "waiting_days"),
            "bad status": ("name: t\nsteps:\n  - name: a\n    command: queue-list\n    status: done\n", 5, "status"),
            "check without action_type": ("name: t\nsteps:\n  - name: a\n    command: check\n", 3, "needs action_type"),
            "bad action_type": ("name: t\nsteps:\n  - name: a\n    command: check\n    action_type: \"a b\"\n", 5, "action_type"),
            "social without article": ("name: t\nsteps:\n  - name: a\n    command: social-draft\n", 3, "needs article"),
            "article with ..": ("name: t\nsteps:\n  - name: a\n    command: social-draft\n    article: ../x.md\n", 5, "'..'"),
            "absolute article": ("name: t\nsteps:\n  - name: a\n    command: social-draft\n    article: /etc/passwd\n", 5, "relative"),
            "article missing": ("name: t\nsteps:\n  - name: a\n    command: social-draft\n    article: articles/nope.md\n", 5, "not found"),
            "private article": ("name: t\nsteps:\n  - name: a\n    command: social-draft\n    article: private/a.md\n", 5, "private path"),
            "approve not last": ("name: t\nsteps:\n  - name: a\n    command: approve\n  - name: b\n    command: queue-list\n", 4, "must be the last step"),
            "two approves": ("name: t\nsteps:\n  - name: a\n    command: queue-list\n  - name: b\n    command: approve\n  - name: c\n    command: approve\n", 8, "at most one approve"),
            "yaml syntax": ("name: t\nsteps:\n  - name: a\n\tcommand: approve\n", 4, "tabs"),
            "yaml duplicate key": ("name: t\nname: t\nsteps:\n  - name: a\n    command: approve\n", 2, "duplicate key"),
            "flow mapping": ("name: t\nsteps:\n  - {name: a}\n", 3, "unsupported"),
            "not a mapping": ("- a\n- b\n", 1, "must be a mapping"),
        }
        for name, (text, line, fragment) in cases.items():
            with self.subTest(case=name):
                code, out, err = self.problems(text)
                self.assertEqual(code, 64, out + err)
                self.assertIn(f"problem: line {line}: ", out)
                first = [l for l in out.splitlines() if l.startswith(f"problem: line {line}: ")]
                self.assertTrue(any(fragment in l for l in first), out)

    def test_every_problem_is_reported_at_once(self):
        text = ("name: wrong\n"
                "extra: 1\n"
                "steps:\n"
                "  - name: a\n    command: shell\n"
                "  - name: b\n    command: approve\n    approved_by: me\n"
                "  - name: b\n    command: report\n    since_days: 0\n")
        code, out, _ = self.problems(text)
        self.assertEqual(code, 64)
        lines = [l for l in out.splitlines() if l.startswith("problem:")]
        self.assertEqual([l.split(":")[1].strip() for l in lines],
                         ["line 1", "line 2", "line 5", "line 7", "line 8", "line 9", "line 11"])
        self.assertIn("7 problem(s) found in workflows/t.yaml", out)

    def test_article_shape_is_checked_by_the_workflow_itself(self):
        # without a root, only the workflow's own checks run (not the social helper's path checks)
        for article, fragment in (("../x.md", "must not contain '..'"), ("/etc/passwd", "relative"),
                                  ("a\\b.md", "forward slashes"), ("C:/x.md", "relative")):
            with self.subTest(article=article):
                text = f"name: t\nsteps:\n  - name: a\n    command: social-draft\n    article: '{article}'\n"
                wf, problems = workflow.check_text(text, "t")
                self.assertIsNone(wf)
                self.assertEqual([(p.line, fragment in p.message) for p in problems], [(5, True)])

    def test_social_config_problems(self):
        text = "name: t\nsteps:\n  - name: a\n    command: social-draft\n    article: articles/week.md\n"
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "m", "private_paths": []}))
        code, out, _ = self.problems(text)
        self.assertEqual(code, 64)
        self.assertIn("line 5: step 1: umwayi.json has no social_channels", out)
        (self.root / "umwayi.json").write_text("{broken")
        code, out, _ = self.problems(text)
        self.assertEqual(code, 64)
        self.assertIn("line 5: step 1: config:", out)

    def test_file_refusals_exit_64(self):
        self.assertEqual(self.cli("workflow", "validate", "nope")[0], 64)
        (self.root / "workflows" / "big.yaml").write_text("name: big\n" + "# x\n" * 20000)
        self.assertEqual(self.cli("workflow", "validate", "big")[0], 64)
        (self.root / "workflows" / "bin.yaml").write_bytes(b"\xff\xfe")
        self.assertEqual(self.cli("workflow", "validate", "bin")[0], 64)
        (self.root / "workflows" / "dir.yaml").mkdir()
        self.assertEqual(self.cli("workflow", "validate", "dir")[0], 64)
        try:
            (self.root / "workflows" / "link.yaml").symlink_to(self.root / "workflows" / "content-loop.yaml")
        except (OSError, NotImplementedError):
            return
        code, _, err = self.cli("workflow", "validate", "link")
        self.assertEqual(code, 64)
        self.assertIn("symbolic link", err)

    def test_workflows_folder_symlink_is_refused(self):
        other = self.root / "elsewhere"
        (self.root / "workflows").rename(other)
        try:
            (self.root / "workflows").symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.assertEqual(self.cli("workflow", "validate", "content-loop")[0], 64)
        self.assertEqual(self.run_loop()[0], 64)

    def test_bad_names_are_usage_errors(self):
        for name in ("Content", "../x", "a/b", "a.b", "x" * 21, ""):
            with self.subTest(name=name):
                self.assertEqual(self.cli("workflow", "validate", name)[0], 64)
                self.assertEqual(self.cli("workflow", "run", name)[0], 64)
        with self.assertRaises(UsageError):
            workflow.check_name("../x")

    def test_problems_never_print_unknown_key_text(self):
        code, out, _ = self.problems("name: t\nsteps:\n  - name: a\n    command: approve\n    \"sk-live-SECRET!\": 1\n")
        self.assertEqual(code, 64)
        self.assertNotIn("SECRET", out)
        self.assertIn("a key is not allowed", out)

    def test_line_map(self):
        m = workflow._line_map(LOOP)
        self.assertEqual(m[("name",)], 2)
        self.assertEqual(m[("steps",)], 3)
        self.assertEqual([m[("steps", i)] for i in (1, 2, 3, 4)], [4, 7, 10, 13])
        self.assertEqual(m[("steps", 3, "article")], 12)
        flat = workflow._line_map("name: t\nsteps:\n- name: a\n  command: approve\n")
        self.assertEqual((flat[("steps", 1)], flat[("steps", 1, "command")]), (3, 4))

    def test_load_raises_config_error(self):
        self.wf("bad", "name: bad\nsteps:\n  - name: a\n    command: shell\n")
        with self.assertRaises(ConfigError):
            workflow.load(self.root, "bad")


# ============================================================ 8.2 the content loop


class RunTests(Base):
    def test_content_loop_end_to_end(self):
        before = self.snap()
        code, out, err = self.run_loop()
        self.assertEqual(code, 3, err)
        self.assertEqual(out.splitlines()[:5], [
            "Step 1 collect (queue-list): 1 rows with status open.",
            "  Q-0001  task      open      Write the post",
            "Step 2 brief (steward): wrote drafts/steward-0001.md.",
            "Step 3 draft (social-draft): wrote drafts/post-linkedin-0001.md, drafts/post-mastodon-0001.md.",
            "Step 4 approve (approve): added queue item Q-0002 (decision) for the owner.",
        ])
        self.assertIn("Ask me first\nRule: (none)\nReason: The approve step never approves.", out)
        self.assertEqual(self.drafts(), ["post-linkedin-0001.md", "post-mastodon-0001.md", "steward-0001.md"])
        # only drafts, the queue and the logbook changed
        self.assertEqual([c for c in self.changed(before) if not c.startswith("drafts/") and c not in LOG_FILES],
                         ["queue.md"])

    def test_one_logbook_entry_per_step(self):
        self.run_loop()
        e = [(x.source, x.added) for x in self.entries()]
        self.assertEqual(e, [
            ("umwayi workflow", "Step 1 (workflow_step): collect (queue-list): listed 1 rows with status open"),
            ("umwayi workflow", "Step 2 (workflow_step): brief (steward): wrote drafts/steward-0001.md from 1 queue rows"),
            ("umwayi workflow", "Step 3 (workflow_step): draft (social-draft): wrote drafts/post-linkedin-0001.md, "
                                "drafts/post-mastodon-0001.md from articles/week.md with the fixed template"),
            ("umwayi queue add", "Q-0002 (decision) as open: Workflow content-loop waits for the owner: "
                                 "review 3 drafts from 2026-11-07"),
            ("umwayi workflow", "Step 4 (workflow_step): approve (approve): added queue item Q-0002 (decision) "
                                "listing 3 drafts; it gives no approval"),
        ])
        for x in self.entries():
            if x.source == "umwayi workflow":
                self.assertIn("rule workflow-steps gave Yes for action type workflow_step from Workflow content-loop",
                              x.checked)
        self.assertEqual(self.cli("logbook", "verify")[0], 0)

    def test_the_rules_see_one_fixed_action_per_step(self):
        seen = []
        real = rules.check

        def spy(text, path):
            seen.append(json.loads(text))
            return real(text, path)
        with mock.patch("umwayi.helpers.base.rules.check", spy):
            self.run_loop()
        self.assertEqual(seen, [
            {"type": "workflow_step", "helper": "workflow", "workflow": "content-loop", "step": s, "command": c}
            for s, c in (("collect", "queue-list"), ("brief", "steward"), ("draft", "social-draft"), ("approve", "approve"))
        ])

    def test_a_workflow_without_approve_finishes_with_0(self):
        self.wf("quick", "name: quick\nsteps:\n  - name: collect\n    command: queue-list\n"
                         "  - name: gate\n    command: check\n    action_type: read\n")
        code, out, _ = self.run_loop("quick")
        self.assertEqual(code, 0)
        self.assertIn("Workflow quick finished 2 steps.", out)
        self.assertEqual(len(self.entries()), 2)

    def test_report_step(self):
        env = dict(os.environ, GIT_AUTHOR_NAME="x", GIT_AUTHOR_EMAIL="x@example.org", GIT_COMMITTER_NAME="x",
                   GIT_COMMITTER_EMAIL="x@example.org", GIT_AUTHOR_DATE="2026-11-05T12:00:00+0000",
                   GIT_COMMITTER_DATE="2026-11-05T12:00:00+0000", HOME=str(self.root), TZ="UTC")
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True, env=env)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "--allow-empty", "-m", "a change"], check=True, env=env)
        self.wf("weekly", "name: weekly\nsteps:\n  - name: report\n    command: report\n    since_days: 7\n")
        with mock.patch.dict(os.environ, {"TZ": "UTC"}):
            code, out, err = self.run_loop("weekly")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.drafts(), ["report-0001.md"])
        self.assertIn("1 commits", out)

    def test_missing_queue_is_zero_rows_and_not_created_until_approve(self):
        self.queue.unlink()
        self.wf("quick", "name: quick\nsteps:\n  - name: collect\n    command: queue-list\n"
                         "  - name: brief\n    command: steward\n")
        self.assertEqual(self.run_loop("quick")[0], 0)
        self.assertFalse(self.queue.exists())

    def test_invalid_workflow_at_run_is_64_and_writes_nothing(self):
        self.wf("bad", "name: bad\nsteps:\n  - name: a\n    command: shell\n")
        before = self.snap()
        code, out, err = self.run_loop("bad")
        self.assertEqual((code, out), (64, ""))
        self.assertIn("umwayi workflow validate bad", err)
        self.assertEqual(self.changed(before), [])

    def test_missing_article_at_run_is_64(self):
        (self.root / "articles" / "week.md").unlink()
        before = self.snap()
        self.assertEqual(self.run_loop()[0], 64)
        self.assertEqual(self.changed(before), [])

    def test_article_removed_between_validate_and_step_fails_the_step(self):
        real = workflow._Run.social_draft

        def gone(self_, step, k):
            (self.root / "articles" / "week.md").unlink()
            return real(self_, step, k)
        with mock.patch.object(workflow._Run, "social_draft", gone):
            code, out, _ = self.run_loop()
        self.assertEqual(code, 1)
        self.assertIn("stopped at step 3", out)
        self.assertEqual(self.drafts(), ["steward-0001.md"])

    # -- No and Ask me first

    def test_a_no_stops_with_2(self):
        self.rules_with("  - id: no-steward\n    title: t\n    text: Not today.\n    verdict: no\n"
                        "    matchers:\n      helper: workflow\n      command: steward\n")
        code, out, _ = self.run_loop()
        self.assertEqual(code, 2)
        self.assertIn("No\nRule: no-steward\n", out)
        self.assertIn("Workflow content-loop stopped at step 2 (workflow_step).", out)
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.entries()[-1].added, "Step 2 (workflow_step) stopped: rule no-steward gave No")
        self.assertEqual(len(taskqueue.list_rows(self.root)), 1)  # a No adds no queue item

    def test_an_ask_me_first_stops_with_3_and_adds_a_decision(self):
        self.rules_with(without="workflow-steps")
        code, out, _ = self.run_loop()
        self.assertEqual(code, 3)
        self.assertIn("stopped at step 1 (workflow_step)", out)
        rows = taskqueue.list_rows(self.root)
        self.assertEqual([(r.kind, r.status, r.title) for r in rows[1:]], [
            ("decision", "open", "Workflow content-loop asks first: may it do workflow_step (queue-list)?")])
        self.assertEqual(self.drafts(), [])

    def test_a_check_step_gates_the_workflow(self):
        for action_type, code in (("payment", 2), ("dance", 3), ("read", None)):
            with self.subTest(action_type=action_type):
                self.wf("gate", f"name: gate\nsteps:\n  - name: gate\n    command: check\n    action_type: {action_type}\n"
                                "  - name: brief\n    command: steward\n")
                got, out, _ = self.run_loop("gate")
                if code is None:
                    self.assertEqual(got, 0)
                else:
                    self.assertEqual(got, code)
                    self.assertIn("stopped after step 1 (gate)", out)

    def test_broken_rules_means_no_run(self):
        for text in ("rules: [\n", None):
            with self.subTest(rules=text):
                p = self.root / "rules.yaml"
                p.unlink(missing_ok=True) if text is None else p.write_text(text)
                before = self.snap()
                code, out, _ = self.run_loop()
                self.assertEqual(code, 3)
                self.assertIn("Rules could not be loaded", out)
                self.assertEqual([c for c in self.changed(before) if c not in LOG_FILES], [])

    def test_tampered_logbook_means_no_run_and_no_write(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-01"))
        self.log.write_text(self.log.read_text().replace("- Added: x", "- Added: EDITED"), encoding="utf-8")
        before = self.snap()
        code, out, err = self.run_loop()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("did not start", err)
        self.assertEqual(self.changed(before), [])

    # -- a failed logbook stops the run

    def test_a_failed_logbook_entry_stops_the_run_and_undoes_that_step(self):
        real = logbook.append
        calls = {"n": 0}

        def third_fails(root, entry):
            calls["n"] += 1
            if calls["n"] == 3:  # the entry of step 3, after its drafts were written
                raise UmwayiError("disk full")
            return real(root, entry)
        with mock.patch("umwayi.helpers.base.logbook.append", third_fails):
            code, out, _ = self.run_loop()
        self.assertEqual(code, 3)
        self.assertIn("The logbook could not be written (disk full)", out)
        self.assertEqual(self.drafts(), ["steward-0001.md"])  # step 3's drafts were removed again
        self.assertEqual(len(taskqueue.list_rows(self.root)), 1)  # approve never ran

    def test_every_step_entry_failing_stops_at_step_1(self):
        with mock.patch("umwayi.helpers.base.logbook.append", side_effect=UmwayiError("nope")):
            code, out, _ = self.run_loop()
        self.assertEqual(code, 3)
        self.assertIn("stopped at step 1", out)
        self.assertEqual(self.drafts(), [])


# ======================================================= the approve step never approves


class ApproveTests(Base):
    def test_approve_adds_an_open_decision_listing_the_drafts(self):
        self.run_loop()
        row = taskqueue.list_rows(self.root)[-1]
        self.assertEqual((row.id, row.kind, row.status, row.answer, row.answered),
                         ("Q-0002", "decision", "open", "", ""))
        self.assertEqual(row.title, "Workflow content-loop waits for the owner: review 3 drafts from 2026-11-07")
        self.assertIn("Drafts: drafts/steward-0001.md, drafts/post-linkedin-0001.md, drafts/post-mastodon-0001.md.",
                      row.recommendation)
        self.assertIn("This item approves nothing.", row.recommendation)
        self.assertIn("umwayi publish-draft DRAFT, which is Ask me first", row.recommendation)

    def test_approve_never_publishes_or_copies(self):
        with mock.patch.object(publish, "publish") as pub:
            self.run_loop()
        pub.assert_not_called()
        self.assertFalse((self.root / "outbox").exists())

    def test_publishing_stays_ask_me_first_even_after_the_owner_answers(self):
        self.run_loop()
        self.cli("queue", "answer", "Q-0002", "--answer", "Yes, publish them")
        code, out, _ = self.cli("publish-draft", "drafts/post-linkedin-0001.md")
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("Ask me first\nRule: publish-ask\n"))
        self.assertFalse((self.root / "outbox").exists())

    def test_the_workflow_waits_until_the_owner_answers(self):
        self.run_loop()
        before = self.snap()
        code, out, _ = self.run_loop()
        self.assertEqual(code, 3)
        self.assertIn("Queue item Q-0002 from an earlier run still waits for the owner", out)
        changed = [c for c in self.changed(before) if c not in LOG_FILES]
        self.assertEqual(changed, [])
        self.assertEqual(self.entries()[-1].added, "Workflow content-loop did not start: queue item Q-0002 still waits for the owner")
        self.cli("queue", "answer", "Q-0002", "--answer", "seen")
        self.assertEqual(self.run_loop()[0], 3)  # a new loop ran and stopped at its own approve
        self.assertEqual(taskqueue.list_rows(self.root)[-1].id, "Q-0003")

    def test_closing_also_lets_the_next_run_start(self):
        self.run_loop()
        self.cli("queue", "close", "Q-0002")
        self.run_loop()
        self.assertEqual(taskqueue.list_rows(self.root)[-1].id, "Q-0003")

    def test_another_workflow_is_not_blocked(self):
        self.run_loop()
        self.wf("quick", "name: quick\nsteps:\n  - name: collect\n    command: queue-list\n")
        self.assertEqual(self.run_loop("quick")[0], 0)

    def test_approve_with_no_drafts(self):
        self.wf("solo", "name: solo\nsteps:\n  - name: approve\n    command: approve\n")
        self.assertEqual(self.run_loop("solo")[0], 3)
        row = taskqueue.list_rows(self.root)[-1]
        self.assertIn("review 0 drafts", row.title)
        self.assertIn("No drafts were written in this run.", row.recommendation)

    def test_many_drafts_fit_the_recommendation(self):
        rels = [f"drafts/post-channel-{n:04d}.md" for n in range(40)]
        text = workflow._drafts_text(rels)
        self.assertLessEqual(len(text), 330)
        self.assertTrue(text.endswith("more."))

    def test_a_malformed_queue_stops_the_run_before_anything(self):
        self.queue.write_text("broken\n")
        before = self.snap()
        code, out, _ = self.run_loop()
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(self.changed(before), [])


# ============================================================ cannot approve


class NoApprovalTests(Base):
    def test_workflow_run_does_not_accept_approved_by(self):
        before = self.snap()
        for argv in (["workflow", "run", "content-loop", "--approved-by", "me"],
                     ["workflow", "validate", "content-loop", "--approved-by", "me"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 64)
        self.assertEqual(self.changed(before), [])

    def test_a_workflow_file_cannot_set_approved_by_anywhere(self):
        for text in ("name: t\napproved_by: me\nsteps:\n  - name: a\n    command: approve\n",
                     "name: t\nsteps:\n  - name: a\n    command: approve\n    approved_by: me\n",
                     "name: t\nsteps:\n  - name: a\n    command: queue-list\n    approved-by: me\n"):
            with self.subTest(text=text):
                self.wf("t", text)
                self.assertEqual(self.cli("workflow", "validate", "t")[0], 64)
                self.assertEqual(self.run_loop("t")[0], 64)

    def test_workflow_and_kill_code_never_mention_approval_or_import_publish(self):
        for name in ("workflow.py", "kill.py"):
            src = (REPO / "umwayi" / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertNotIn("approved", src.lower())
                for node in ast.walk(ast.parse(src)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                        for n in names:
                            for banned in ("umwayi.publish", "umwayi.cli", "umwayi.jobs"):
                                self.assertFalse(n == banned or n.startswith(banned + "."), n)

    def test_a_helper_action_cannot_carry_an_approval(self):
        from umwayi.helpers.base import Helper
        h = Helper(self.root, "workflow", "2026-11-07", label="Workflow t")
        for fields in ({"approved_by": "me"}, {"approved": "yes"}, {"workflow": "Content Loop"}, {"command": "rm -rf"},
                       {"step": "a/b"}):
            with self.subTest(fields=fields):
                with self.assertRaises(UmwayiError):
                    h.step("workflow_step", lambda: None, **fields)
        self.assertEqual(self.entries(), [])


# ================================================================ 8.3 kill switch


class KillStateTests(Base):
    def test_states(self):
        self.assertEqual(kill.state(self.root), kill.OFF)  # no .umwayi at all
        (self.root / ".umwayi").mkdir()
        self.assertEqual(kill.state(self.root), kill.OFF)
        self.kill.write_text("on\n")
        self.assertEqual(kill.state(self.root), kill.ON)
        self.kill.write_bytes(b"")  # any content, even empty, means on
        self.assertEqual(kill.state(self.root), kill.ON)
        self.kill.unlink()
        self.kill.mkdir()
        self.assertEqual(kill.state(self.root), kill.ON)
        self.kill.rmdir()
        try:
            self.kill.symlink_to(self.root / "nowhere")
            self.assertEqual(kill.state(self.root), kill.ON)  # a dangling link still means on
            self.kill.unlink()
        except (OSError, NotImplementedError):
            pass

    def test_unknown_states_fail_closed(self):
        (self.root / ".umwayi").write_text("a file, not a folder")
        self.assertEqual(kill.state(self.root), kill.UNKNOWN)
        (self.root / ".umwayi").unlink()
        try:
            (self.root / "real").mkdir()
            (self.root / ".umwayi").symlink_to(self.root / "real")
            self.assertEqual(kill.state(self.root), kill.UNKNOWN)
            (self.root / ".umwayi").unlink()
        except (OSError, NotImplementedError):
            pass
        (self.root / ".umwayi").mkdir()
        with mock.patch("umwayi.kill.os.listdir", side_effect=PermissionError):
            self.assertEqual(kill.state(self.root), kill.UNKNOWN)
        real = os.lstat

        def lstat(p, *a, **k):
            if str(p).endswith("KILL"):
                raise PermissionError
            return real(p, *a, **k)
        with mock.patch("umwayi.kill.os.lstat", lstat):
            self.assertEqual(kill.state(self.root), kill.UNKNOWN)
        with mock.patch("umwayi.kill.os.lstat", side_effect=PermissionError):
            self.assertEqual(kill.state(self.root), kill.UNKNOWN)
        for st in (kill.ON, kill.UNKNOWN):
            self.assertTrue(kill.stopped(st))
        self.assertFalse(kill.stopped(kill.OFF))
        self.assertTrue(kill.stopped("anything else"))


class KillCommandTests(Base):
    def test_on_status_off(self):
        self.assertEqual(self.cli("kill", "status"), (0, "off\n", ""))
        code, out, _ = self.cli("kill", "on", "--reason", "taking a break")
        self.assertEqual(code, 0)
        self.assertTrue(self.kill.is_file())
        code, out, _ = self.cli("kill", "status")
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("on\n"))
        self.assertEqual(self.cli("kill", "on")[1], "The kill switch is already on. Nothing was changed.\n")
        self.assertEqual(self.cli("kill", "off"), (0, "The kill switch is off.\n", ""))
        self.assertFalse(self.kill.exists())
        self.assertEqual(self.cli("kill", "off")[1], "The kill switch is already off. Nothing was changed.\n")
        self.assertEqual([(e.source, e.added) for e in self.entries()], [
            ("umwayi kill", "the kill switch was turned on: taking a break"),
            ("umwayi kill", "the kill switch was turned off"),
        ])

    def test_status_unknown_is_3(self):
        (self.root / ".umwayi").write_text("x")
        code, out, _ = self.cli("kill", "status")
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("unknown\n"))

    def test_on_works_even_when_the_logbook_is_broken(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-01"))
        self.log.write_text("tampered")
        code, out, _ = self.cli("kill", "on")
        self.assertEqual(code, 0)
        self.assertTrue(self.kill.exists())
        self.assertIn("Nothing was logged, but the switch is on.", out)

    def test_off_with_a_broken_logbook_keeps_the_switch_on(self):
        self.cli("kill", "on")
        content = self.kill.read_bytes()
        self.log.write_text(self.log.read_text().replace("turned on", "TURNED ON"))
        code, out, err = self.cli("kill", "off")
        self.assertEqual(code, 1)
        self.assertIn("so it stays on", err)
        self.assertTrue(self.kill.exists())
        self.assertEqual(self.kill.read_bytes(), content)

    def test_off_refuses_when_the_state_is_unknown_or_not_a_file(self):
        (self.root / ".umwayi").write_text("x")
        self.assertEqual(self.cli("kill", "off")[0], 1)
        (self.root / ".umwayi").unlink()
        self.kill.parent.mkdir()
        self.kill.mkdir()
        code, _, err = self.cli("kill", "off")
        self.assertEqual(code, 1)
        self.assertIn("not a normal file", err)
        self.assertTrue(self.kill.is_dir())

    def test_on_refuses_when_the_state_folder_is_wrong(self):
        (self.root / ".umwayi").write_text("x")
        self.assertEqual(self.cli("kill", "on")[0], 1)

    def test_usage(self):
        for argv in (["kill"], ["kill", "maybe"], ["kill", "on", "--reason", ""], ["kill", "on", "--reason", "x" * 201],
                     ["kill", "status", "--now"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 64)
        self.assertFalse(self.kill.exists())


class KillStopsEveryRunnerTests(Base):
    RUNNERS = {
        "steward": (["steward"], "umwayi steward", "AI helper steward did not start: "),
        "social": (["social", "draft", "articles/week.md"], "umwayi social", "AI helper social did not start: "),
        "workflow": (["workflow", "run", "content-loop"], "umwayi workflow", "Workflow content-loop did not start: "),
        "job": (["run", "jobs.yaml", "--job", "open-queue"], "umwayi run",
                "A job run was stopped before the jobs file was read: "),
    }

    def set_state(self, st):
        import shutil
        d = self.root / ".umwayi"
        if d.is_symlink() or d.is_file():
            d.unlink()
        if st == kill.ON:
            d.mkdir(exist_ok=True)
            self.kill.write_text("on\n")
        elif st == kill.UNKNOWN:
            shutil.rmtree(d, ignore_errors=True)
            d.write_text("not a folder")

    def test_on_and_unknown_stop_all_runners_with_3_and_one_entry(self):
        for st in (kill.ON, kill.UNKNOWN):
            for name, (argv, source, added) in self.RUNNERS.items():
                with self.subTest(state=st, runner=name):
                    self.set_state(st)
                    n_before = len(self.entries()) if st == kill.ON else None
                    before = self.snap()
                    with mock.patch("umwayi.rules.check") as check, mock.patch("umwayi.helpers.base.rules.check") as bcheck:
                        code, out, _ = self.cli(*argv)
                    check.assert_not_called()
                    bcheck.assert_not_called()
                    self.assertEqual(code, 3)
                    self.assertTrue(out.startswith("Ask me first\nRule: (none)\nReason: "))
                    self.assertFalse((self.root / "drafts").exists())
                    self.assertEqual(self.queue.read_text(), QUEUE)
                    if st == kill.ON:
                        new = self.entries()[n_before:]
                        self.assertEqual(len(new), 1)
                        self.assertEqual(new[0].source, source)
                        self.assertEqual(new[0].added, added + "the kill switch is on")
                        self.assertEqual([c for c in self.changed(before) if c not in LOG_FILES], [])
                    else:
                        # .umwayi is a file, so the checked append cannot record it: still a stop
                        self.assertIn("Nothing was logged", out)
                        self.assertEqual(self.changed(before), [])

    def test_the_kill_switch_is_checked_before_the_jobs_or_workflow_file_is_read(self):
        self.set_state(kill.ON)
        with mock.patch("umwayi.jobs.load_jobs") as lj, mock.patch("umwayi.workflow.read_file") as rf:
            self.assertEqual(self.cli("run", "jobs.yaml", "--job", "open-queue")[0], 3)
            self.assertEqual(self.cli("workflow", "run", "content-loop")[0], 3)
        lj.assert_not_called()
        rf.assert_not_called()

    def test_kill_switch_turned_on_during_a_run_stops_at_the_next_step(self):
        calls = {"n": 0}
        real = kill.state

        def flips(root):
            calls["n"] += 1
            return kill.ON if calls["n"] >= 4 else real(root)  # start, step 1, step 2 off; step 3 on
        with mock.patch("umwayi.helpers.base.kill.state", flips):
            code, out, _ = self.cli("workflow", "run", "content-loop")
        self.assertEqual(code, 3)
        self.assertIn("Workflow content-loop stopped at step 3 (workflow_step).", out)
        self.assertEqual(self.drafts(), ["steward-0001.md"])
        self.assertEqual(self.entries()[-1].added, "Step 3 (workflow_step) stopped before it ran: the kill switch is on")
        self.assertEqual(len(taskqueue.list_rows(self.root)), 1)

    def test_a_kill_stop_with_a_broken_logbook_still_stops_with_3(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-01"))
        self.log.write_text("tampered")
        self.set_state(kill.ON)
        for name, (argv, _s, _a) in self.RUNNERS.items():
            with self.subTest(runner=name):
                code, out, _ = self.cli(*argv)
                self.assertEqual(code, 3)
                self.assertIn("The logbook could not be written", out)

    def test_runs_work_again_after_kill_off(self):
        self.set_state(kill.ON)
        self.assertEqual(self.cli("workflow", "run", "content-loop")[0], 3)
        self.cli("kill", "off")
        self.assertEqual(self.cli("steward")[0], 0)
        self.assertEqual(self.cli("run", "jobs.yaml", "--job", "open-queue")[0], 0)

    def test_owner_commands_are_not_stopped(self):
        self.set_state(kill.ON)
        self.assertEqual(self.cli("queue", "list")[0], 0)
        self.assertEqual(self.cli("check", '{"type": "read"}')[0], 0)
        self.assertEqual(self.cli("workflow", "validate", "content-loop")[0], 0)


# ============================================================== code guards


class CodeGuardTests(unittest.TestCase):
    def test_no_network_module_is_loaded(self):
        code = ("import sys\nimport umwayi.workflow, umwayi.kill\n"
                "bad = {'socket', 'ssl', 'http', 'http.client', 'urllib.request', 'ftplib', 'smtplib', 'asyncio',"
                " 'umwayi.publish', 'umwayi.jobs', 'umwayi.cli'}\n"
                "print(sorted(bad & set(sys.modules)))\n")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(REPO)), cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "[]")

    def test_kill_module_runs_no_program(self):
        imported = set()
        for node in ast.walk(ast.parse((REPO / "umwayi" / "kill.py").read_text())):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse(imported & {"subprocess", "shutil", "pty", "multiprocessing"})

    def test_the_workflow_runs_only_its_own_step_functions(self):
        src = (REPO / "umwayi" / "workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", src)
        for bad in ("os.system", "eval(", "exec(", "__import__", "importlib"):
            self.assertNotIn(bad, src)
        self.assertEqual(set(workflow.STEP_FUNCTIONS), set(workflow.STEP_WORDS))
        for word, fn in workflow.STEP_FUNCTIONS.items():
            self.assertTrue(callable(getattr(workflow._Run, fn)), word)

    def test_workflow_writes_only_through_drafts_queue_and_logbook(self):
        tree = ast.parse((REPO / "umwayi" / "workflow.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                with self.subTest(line=node.lineno):
                    self.assertNotIn(node.func.attr, {"write_text", "write_bytes", "mkdir", "unlink", "rename",
                                                      "replace", "rmdir", "symlink_to", "chmod"})
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        self.fail("workflow.py must not call os functions directly")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotEqual(node.func.id, "open")


class StarterFilesTests(unittest.TestCase):
    def test_repo_content_loop_validates(self):
        r = workflow.validate_file(REPO, "content-loop")
        self.assertEqual(r.code, 0, r.lines)

    def test_repo_rules_allow_workflow_steps_and_nothing_else(self):
        def check(action):
            return rules.check(json.dumps(action), REPO / "rules.yaml").answer
        for c in workflow.STEP_WORDS:
            self.assertEqual(check({"type": "workflow_step", "helper": "workflow", "workflow": "w", "step": "s",
                                    "command": c}), "Yes")
        self.assertEqual(check({"type": "workflow_step", "helper": "workflow", "command": "publish-draft"}), "No")
        self.assertEqual(check({"type": "workflow_step", "helper": "workflow", "command": "other"}), "Ask me first")
        self.assertEqual(check({"type": "workflow_step", "command": "steward"}), "Ask me first")  # no helper field


if __name__ == "__main__":
    unittest.main()
