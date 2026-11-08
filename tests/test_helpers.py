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
from umwayi import logbook, publish, rules, taskqueue
from umwayi.cli import main
from umwayi.errors import UmwayiError
from umwayi.helpers import base, social, steward
from umwayi.helpers.base import Helper, Outcome, Stop
from umwayi.logbook import parse

REPO = Path(__file__).resolve().parent.parent
HELPERS_DIR = REPO / "umwayi" / "helpers"
HELPER_FILES = sorted(HELPERS_DIR.glob("*.py"))

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
  - id: publish-ask
    title: Publishing
    text: Publishing is Ask me first.
    verdict: ask
    matchers:
      type: publish_draft
"""

QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| Q-0001 | decision | Pick a name | open | Use umwayi | | |\n"
    "| Q-0002 | task | Write docs | open | | | |\n"
    "| Q-0003 | decision | Old choice | answered | | Yes | 2026-11-01 |\n"
    "| Q-0004 | task | Done thing | closed | | | |\n"
    "| Q-0005 | task | Typed by hand | open | | | |\n"
)
# the logbook that would have been written when Q-0001 to Q-0004 were added
QUEUE_LOG = "# Logbook\n" + "".join([
    entry_text(date="2026-10-01", source="umwayi queue add", added="Q-0001 (decision) as open: Pick a name"),
    entry_text(date="2026-10-25", source="umwayi queue add", added="Q-0002 (task) as open: Write docs"),
    entry_text(date="2026-10-26", source="umwayi queue add", added="Q-0003 (decision) as open: Old choice"),
    entry_text(date="2026-10-27", source="umwayi queue add", added="Q-0004 (task) as open: Done thing"),
])

ARTICLE = (
    "---\n"
    "title: What I learned \u2014 week #45\n"
    "link: https://example.org/week-45\n"
    "---\n"
    "\n"
    "# A heading\n"
    "\n"
    "This week I built the #logbook and the *queue*. It was work \u2014 but it works.\n"
    "Second line of the same paragraph.\n"
    "\n"
    "Another paragraph that is not used.\n"
)
SECRET = "TOPSECRETWORDS"


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
        self.log = self.root / "LOGBOOK.md"
        self.queue = self.root / "queue.md"
        p = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)

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

    def rules_without(self, rule_id):
        blocks = RULES.split("\n  - ")
        kept = [b for b in blocks if not b.startswith(f"id: {rule_id}\n")]
        (self.root / "rules.yaml").write_text("\n  - ".join(kept), encoding="utf-8")

    def add_rule(self, text):
        (self.root / "rules.yaml").write_text(RULES + text, encoding="utf-8")


# ================================================================== base


class BaseStepTests(Base):
    def helper(self, name="steward"):
        # a started helper holds the run lock: finish the one before, as a real run would
        if getattr(self, "_started", None) is not None:
            self._started.finish()
        h = Helper(self.root, name, "2026-11-07")
        h.start()
        self._started = h
        self.addCleanup(h.finish)
        return h

    def ok_work(self):
        return Outcome("did the thing", "nothing else")

    def test_yes_runs_the_work_and_logs_one_entry(self):
        h = self.helper()
        calls = []
        h.step("read_queue", lambda: calls.append(1) or self.ok_work())
        self.assertEqual(calls, [1])
        e = self.entries()
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0].source, e[0].added, e[0].checked, e[0].not_done), (
            "umwayi steward", "Step 1 (read_queue): did the thing",
            "rule helper-read gave Yes for action type read_queue from AI helper steward", "nothing else"))

    def test_the_rules_see_the_action_built_by_the_base(self):
        seen = []
        real = rules.check
        with mock.patch("umwayi.helpers.base.rules.check", lambda t, p: seen.append(json.loads(t)) or real(t, p)):
            h = self.helper("social")
            h.step("write_draft", self.ok_work, channel="linkedin")
        self.assertEqual(seen, [{"type": "write_draft", "helper": "social", "channel": "linkedin"}])

    def test_no_stops_with_exit_2_without_running_the_work(self):
        h = self.helper()
        calls = []
        with self.assertRaises(Stop) as cm:
            h.step("post_update", lambda: calls.append(1) or self.ok_work())
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(cm.exception.lines[:2], ["No", "Rule: helper-no-post"])
        self.assertIn("AI helper steward stopped at step 1 (post_update).", cm.exception.lines)
        self.assertEqual([x.added for x in self.entries()], ["Step 1 (post_update) stopped: rule helper-no-post gave No"])
        self.assertFalse(self.queue.exists())  # No adds no queue item

    def test_post_send_and_publish_types_are_no_for_helpers(self):
        for t in ("post", "post_draft", "send", "send_email", "publish", "publish_draft", "repost", "autopublish"):
            with self.subTest(type=t):
                with self.assertRaises(Stop) as cm:
                    self.helper().step(t, self.ok_work)
                self.assertEqual(cm.exception.code, 2)

    def test_ask_me_first_stops_with_exit_3_and_adds_one_decision(self):
        h = self.helper()
        calls = []
        with self.assertRaises(Stop) as cm:
            h.step("read_calendar", lambda: calls.append(1) or self.ok_work())
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(calls, [])
        self.assertEqual(cm.exception.lines[:2], ["Ask me first", "Rule: (none)"])
        rows = taskqueue.list_rows(self.root)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r.id, r.kind, r.status, r.title), (
            "Q-0001", "decision", "open", "AI helper steward asks first: may it do read_calendar?"))
        self.assertEqual(r.recommendation, base.ASK_RECOMMENDATION)
        self.assertIn("umwayi queue answer Q-0001 --answer TEXT", "\n".join(cm.exception.lines))
        # one queue entry (layer 3) and one step entry (the helper)
        self.assertEqual([(x.source, x.added) for x in self.entries()], [
            ("umwayi queue add", "Q-0001 (decision) as open: AI helper steward asks first: may it do read_calendar?"),
            ("umwayi steward", "Step 1 (read_calendar) stopped: no rule gave Ask me first; queue item Q-0001 added"),
        ])

    def test_ask_verdict_from_a_rule_also_adds_a_decision(self):
        self.add_rule("  - id: ask-it\n    title: t\n    text: Ask about this.\n    verdict: ask\n"
                      "    matchers:\n      type: read_mail\n")
        with self.assertRaises(Stop) as cm:
            self.helper().step("read_mail", self.ok_work)
        self.assertEqual((cm.exception.code, cm.exception.lines[1]), (3, "Rule: ask-it"))
        self.assertEqual(len(taskqueue.list_rows(self.root)), 1)

    def test_the_same_question_is_not_added_twice_while_open(self):
        for _ in range(3):
            with self.assertRaises(Stop):
                self.helper().step("read_calendar", self.ok_work)
        self.assertEqual([r.id for r in taskqueue.list_rows(self.root)], ["Q-0001"])
        self.assertIn("queue item Q-0001 was already open", self.entries()[-1].added)
        # once answered, the next stop asks again
        taskqueue.answer(self.root, "Q-0001", "no", "2026-11-07")
        with self.assertRaises(Stop):
            self.helper().step("read_calendar", self.ok_work)
        self.assertEqual([r.id for r in taskqueue.list_rows(self.root)], ["Q-0001", "Q-0002"])

    def test_answering_the_queue_item_does_not_let_the_helper_go_on(self):
        with self.assertRaises(Stop):
            self.helper().step("read_calendar", self.ok_work)
        taskqueue.answer(self.root, "Q-0001", "Yes, go ahead", "2026-11-07")
        with self.assertRaises(Stop) as cm:
            self.helper().step("read_calendar", self.ok_work)
        self.assertEqual(cm.exception.code, 3)

    def test_a_queue_that_cannot_be_written_still_stops_with_3(self):
        self.queue.write_text("broken\n", encoding="utf-8")
        with self.assertRaises(Stop) as cm:
            self.helper().step("read_calendar", self.ok_work)
        self.assertEqual(cm.exception.code, 3)
        self.assertIn("The queue item could not be added", "\n".join(cm.exception.lines))
        self.assertEqual(self.queue.read_text(), "broken\n")
        self.assertIn("the queue item could not be added", self.entries()[-1].added)

    def test_work_that_fails_is_logged_and_stops_with_1(self):
        def bad():
            raise UmwayiError("the thing broke")
        with self.assertRaises(Stop) as cm:
            self.helper().step("read_queue", bad)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("the thing broke", cm.exception.lines[0])
        self.assertEqual(self.entries()[-1].added, "Step 1 (read_queue) failed after rule helper-read gave Yes")

    def test_an_unexpected_error_in_the_work_is_logged_then_raised_and_hides_its_text(self):
        # (until the hardening branch this was Stop(1); an unexpected error must exit 2, never 1)
        def bad():
            raise RuntimeError(SECRET)
        h = self.helper()
        with self.assertRaises(RuntimeError):
            h.step("read_queue", bad)
        h.finish()  # as run() does; it holds the run lock until then
        self.assertEqual(self.entries()[-1].added, "Step 1 (read_queue) failed after rule helper-read gave Yes")
        self.assertNotIn(SECRET, self.log.read_text())
        code, out, err = self.cli_crash()
        self.assertEqual(code, 2)
        self.assertNotIn(SECRET, out + err)

    def cli_crash(self):
        self.queue.write_text(QUEUE, encoding="utf-8")
        with mock.patch("umwayi.taskqueue.list_rows", side_effect=RuntimeError(SECRET)):
            return self.cli("steward")

    def test_failed_entry_after_yes_undoes_the_work_and_stops_with_3(self):
        h = self.helper()
        undone = []
        with mock.patch("umwayi.helpers.base.logbook.append", side_effect=UmwayiError("disk full")):
            with self.assertRaises(Stop) as cm:
                h.step("write_draft", lambda: Outcome("wrote x", "n", undo=lambda: undone.append(1)))
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(undone, [1])
        self.assertEqual(cm.exception.lines[:2], ["Ask me first", "Rule: (none)"])
        self.assertIn("disk full", cm.exception.lines[2])

    def test_failed_undo_is_reported_loudly(self):
        def boom():
            raise OSError("busy")
        with mock.patch("umwayi.helpers.base.logbook.append", side_effect=UmwayiError("x")):
            with self.assertRaises(UmwayiError) as cm:
                self.helper().step("write_draft", lambda: Outcome("w", "n", undo=boom))
        self.assertIn("could not be undone", str(cm.exception))

    def test_failed_entry_on_no_and_ask_keeps_the_verdict(self):
        for t, code in (("post", 2), ("read_calendar", 3)):
            with self.subTest(type=t):
                h = self.helper()
                with mock.patch("umwayi.helpers.base.logbook.append", side_effect=UmwayiError("boom")):
                    with self.assertRaises(Stop) as cm:
                        h.step(t, self.ok_work)
                self.assertEqual(cm.exception.code, code)
                self.assertIn("The logbook could not be written (boom). Nothing was logged.", cm.exception.lines)

    def test_step_numbers_count_up(self):
        h = self.helper()
        h.step("read_queue", self.ok_work)
        h.step("read_logbook", self.ok_work)
        self.assertEqual([x.added for x in self.entries()], ["Step 1 (read_queue): did the thing",
                                                             "Step 2 (read_logbook): did the thing"])

    # -- a helper cannot approve, or add anything to the action

    def test_a_helper_cannot_add_keys_to_an_action(self):
        h = self.helper()
        for fields in ({"approved_by": "Miguel"}, {"approved": True}, {"approval": "yes"}, {"helper": "owner"},
                       {"type": "read_queue"}, {"amount": 5}, {"note": "x"}):
            with self.subTest(fields=fields):
                with self.assertRaises((UmwayiError, TypeError)):
                    h.step("read_queue", self.ok_work, **fields)
        self.assertEqual(self.entries(), [])

    def test_action_types_and_channels_must_be_plain(self):
        h = self.helper()
        for t in ("", "Read", "read queue", "read-queue", "x" * 41, "read_queue;rm", 5):
            with self.subTest(type=t):
                with self.assertRaises(UmwayiError):
                    h.step(t, self.ok_work)
        for c in ("", "Linked In", "a/b", "x" * 21, 5):
            with self.subTest(channel=c):
                with self.assertRaises(UmwayiError):
                    h.step("write_draft", self.ok_work, channel=c)
        self.assertEqual(self.entries(), [])

    def test_unknown_helper_name_and_bad_date(self):
        with self.assertRaises(UmwayiError):
            Helper(self.root, "owner", "2026-11-07")
        with self.assertRaises(UmwayiError):
            Helper(self.root, "steward", "2026-02-30")


class StartTests(Base):
    """A broken rules file, or a broken logbook, means no helper runs."""

    def broken_rules_cases(self):
        return {
            "not yaml": "rules: [\n",
            "bad verdict": "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: maybe\n",
            "wrong top": "other: 1\n",
            "missing": None,
            "not utf8": b"\xff\xfe",
        }

    def set_rules(self, value):
        p = self.root / "rules.yaml"
        if value is None:
            p.unlink(missing_ok=True)
        elif isinstance(value, bytes):
            p.write_bytes(value)
        else:
            p.write_text(value, encoding="utf-8")

    def test_broken_rules_means_no_helper_runs(self):
        self.queue.write_text(QUEUE, encoding="utf-8")
        for name, value in self.broken_rules_cases().items():
            for argv in (["steward"], ["social", "draft", "articles/week.md"]):
                with self.subTest(rules=name, helper=argv[0]):
                    self.set_rules(value)
                    before = self.snap()
                    code, out, _ = self.cli(*argv)
                    self.assertEqual(code, 3)
                    self.assertTrue(out.startswith("Ask me first\nRule: (none)\nReason: Rules could not be loaded"))
                    self.assertIn("did not start", out)
                    # only the logbook changed: no draft, no queue item
                    self.assertEqual([c for c in self.changed(before) if c not in ("LOGBOOK.md", ".umwayi/", ".umwayi/logbook.sha256")], [])
                    self.assertFalse((self.root / "drafts").exists())
                    self.assertEqual(self.queue.read_text(), QUEUE)
                    last = self.entries()[-1]
                    self.assertIn("did not start: rules.yaml could not be loaded", last.added)
                    self.assertIn("No queue item was added", last.not_done)

    def test_no_step_is_checked_when_the_rules_are_broken(self):
        self.set_rules("rules: [\n")
        with mock.patch("umwayi.helpers.base.rules.check") as check:
            self.cli("steward")
        check.assert_not_called()

    def test_tampered_or_unsealed_logbook_means_no_helper_runs_and_nothing_is_written(self):
        cases = {
            "hand edit": lambda: (write_sealed_logbook(self.root, QUEUE_LOG),
                                  self.log.write_text(QUEUE_LOG.replace("Pick", "Pack"), encoding="utf-8")),
            "no record": lambda: self.log.write_text(QUEUE_LOG, encoding="utf-8"),
            "format": lambda: write_sealed_logbook(self.root, "# Logbook\nstray\n"),
        }
        for name, setup in cases.items():
            for argv in (["steward"], ["social", "draft", "articles/week.md"]):
                with self.subTest(case=name, helper=argv[0]):
                    import shutil
                    shutil.rmtree(self.root / ".umwayi", ignore_errors=True)
                    self.log.unlink(missing_ok=True)
                    setup()
                    before = self.snap()
                    with mock.patch("umwayi.helpers.base.rules.check") as check:
                        code, out, err = self.cli(*argv)
                    self.assertEqual((code, out), (1, ""))
                    self.assertIn("did not start", err)
                    self.assertEqual(self.changed(before), [])
                    check.assert_not_called()


# =============================================================== steward


class StewardTests(Base):
    def setUp(self):
        super().setUp()
        self.queue.write_text(QUEUE, encoding="utf-8")
        write_sealed_logbook(self.root, QUEUE_LOG)

    def test_writes_one_proposal_and_logs_three_steps(self):
        before = self.snap()
        code, out, err = self.cli("steward")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "Wrote drafts/steward-0001.md.\nQueue rows read: 5, open: 3.\n"
                              "It is a draft. Steward changed nothing in the queue and answered nothing.\n")
        self.assertEqual(self.changed(before), [".umwayi/logbook.sha256", "LOGBOOK.md", "drafts/", "drafts/steward-0001.md"])
        new = self.entries()[4:]
        self.assertEqual([(e.source, e.added) for e in new], [
            ("umwayi steward", "Step 1 (read_queue): read queue.md (5 rows)"),
            ("umwayi steward", "Step 2 (read_logbook): read LOGBOOK.md (5 entries)"),  # 4 earlier and step 1
            ("umwayi steward", "Step 3 (write_draft): wrote drafts/steward-0001.md (a proposal from the queue)"),
        ])

    def test_proposal_content(self):
        self.cli("steward")
        text = (self.root / "drafts" / "steward-0001.md").read_text(encoding="utf-8")
        self.assertEqual(text, (
            "# Steward proposal (draft)\n\n"
            "Date: 2026-11-07. Queue rows read: 5. Waiting longer than 7 days counts as late.\n\n"
            "## Open items (3)\n\n"
            "- Q-0001 decision, open since 2026-10-01 (37 days): Pick a name\n"
            "- Q-0002 task, open since 2026-10-25 (13 days): Write docs\n"
            "- Q-0005 task, added date not in the logbook: Typed by hand\n\n"
            "## Waiting longer than 7 days (2)\n\n"
            "- Q-0001 decision, 37 days: Pick a name\n"
            "- Q-0002 task, 13 days: Write docs\n\n"
            "## Answered but not closed (1)\n\n"
            "- Q-0003 decision, answered 2026-11-01: Old choice\n\n"
            "## Suggested next tasks\n\n"
            "1. Answer Q-0001 (decision, waiting 37 days): Pick a name. Recommendation: Use umwayi\n"
            "2. Do or close Q-0002 (task, open 13 days): Write docs.\n"
            "3. Close Q-0003: it was answered on 2026-11-01.\n"
            "4. Check Q-0005: its added date is not in the logbook.\n\n"
            "This is a draft from the AI helper Steward. It changed nothing in the queue and answered nothing. "
            "The owner decides what to do.\n"))

    def test_waiting_days_option(self):
        self.cli("steward", "--waiting-days", "20")
        text = (self.root / "drafts" / "steward-0001.md").read_text()
        self.assertIn("## Waiting longer than 20 days (1)", text)
        self.assertIn("2. Close Q-0003", text)
        self.cli("steward", "--waiting-days", "37")  # strictly longer than
        self.assertIn("## Waiting longer than 37 days (0)", (self.root / "drafts" / "steward-0002.md").read_text())

    def test_waiting_days_usage_errors(self):
        for v in ("0", "-1", "366", "seven", "1.5", ""):
            with self.subTest(v=v):
                self.assertEqual(self.cli("steward", "--waiting-days", v)[0], 64)

    def test_never_edits_or_answers_the_queue_and_runs_nothing_else(self):
        before_q = (self.queue.read_bytes(), os.stat(self.queue).st_mtime_ns)
        with mock.patch("umwayi.taskqueue.add") as add, mock.patch("umwayi.taskqueue.answer") as ans, \
                mock.patch("umwayi.taskqueue.close") as close, mock.patch("umwayi.taskqueue.migrate") as mig, \
                mock.patch("umwayi.publish.publish") as pub, mock.patch("subprocess.run") as sp, \
                mock.patch("subprocess.Popen") as po:
            self.assertEqual(self.cli("steward")[0], 0)
        for m in (add, ans, close, mig, pub, sp, po):
            m.assert_not_called()
        self.assertEqual((self.queue.read_bytes(), os.stat(self.queue).st_mtime_ns), before_q)

    def test_empty_and_missing_queue(self):
        self.queue.unlink()
        code, out, _ = self.cli("steward")
        self.assertEqual(code, 0)
        self.assertFalse(self.queue.exists())  # not created
        text = (self.root / "drafts" / "steward-0001.md").read_text()
        self.assertIn("Nothing waits. The queue has no open or answered rows.", text)
        self.assertIn("queue.md does not exist yet", self.entries()[-3].added)

    def test_malformed_queue_stops_at_step_1_with_exit_1(self):
        self.queue.write_text("broken\n", encoding="utf-8")
        code, out, _ = self.cli("steward")
        self.assertEqual(code, 1)
        self.assertIn("stopped at step 1 (read_queue)", out)
        self.assertFalse((self.root / "drafts").exists())
        self.assertEqual(self.entries()[-1].added, "Step 1 (read_queue) failed after rule helper-read gave Yes")

    def test_stops_on_no(self):
        self.add_rule("  - id: no-drafts-today\n    title: t\n    text: Not today.\n    verdict: no\n"
                      "    matchers:\n      type: write_draft\n")
        code, out, _ = self.cli("steward")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("No\nRule: no-drafts-today\n"))
        self.assertIn("stopped at step 3 (write_draft)", out)
        self.assertFalse((self.root / "drafts").exists())
        self.assertEqual(self.queue.read_text(), QUEUE)

    def test_stops_on_ask_me_first_at_each_step(self):
        for rule, step in (("helper-read", 1), ("helper-draft", 3)):
            with self.subTest(missing=rule):
                self.queue.write_text(QUEUE, encoding="utf-8")
                self.rules_without(rule)
                code, out, _ = self.cli("steward")
                self.assertEqual(code, 3)
                self.assertTrue(out.startswith("Ask me first\n"))
                self.assertIn(f"stopped at step {step}", out)
                self.assertFalse((self.root / "drafts").exists())
                rows = taskqueue.list_rows(self.root)
                self.assertEqual(rows[-1].kind, "decision")
                self.assertEqual(rows[-1].status, "open")
                self.assertTrue(rows[-1].title.startswith("AI helper steward asks first"))

    def test_proposal_is_pure(self):
        rows = taskqueue.parse(QUEUE).rows
        entries = [p.entry for p in parse(QUEUE_LOG)[0]]
        self.assertEqual(steward.proposal(rows, entries, "2026-11-07", 7), steward.proposal(rows, entries, "2026-11-07", 7))
        self.assertEqual(steward.added_dates(entries), {"Q-0001": "2026-10-01", "Q-0002": "2026-10-25",
                                                        "Q-0003": "2026-10-26", "Q-0004": "2026-10-27"})

    def test_the_first_add_entry_gives_the_date(self):
        entries = [logbook.Entry("2026-01-01", "umwayi queue add", "Q-0001 (task) as open: x", "c", "n"),
                   logbook.Entry("2026-03-01", "umwayi queue add", "Q-0001 (task) as open: x again", "c", "n")]
        self.assertEqual(steward.added_dates(entries), {"Q-0001": "2026-01-01"})

    def test_a_failed_entry_removes_the_real_draft_and_the_folder_it_made(self):
        real = logbook.append
        calls = {"n": 0}

        def third_fails(root, entry):
            calls["n"] += 1
            if calls["n"] == 3:  # step 3, write_draft
                raise UmwayiError("disk full")
            return real(root, entry)
        with mock.patch("umwayi.helpers.base.logbook.append", third_fails):
            code, out, _ = self.cli("steward")
        self.assertEqual(code, 3)
        self.assertIn("so the work was undone", out)
        self.assertFalse((self.root / "drafts").exists())

    def test_added_dates_only_from_queue_add_entries(self):
        entries = [logbook.Entry("2026-01-01", "umwayi check", "Q-0001 (task) as open: x", "c", "n"),
                   logbook.Entry("2026-01-02", "umwayi queue add", "see Q-0002 (task) as open: x", "c", "n")]
        self.assertEqual(steward.added_dates(entries), {})

    def test_draft_numbering(self):
        for _ in range(3):
            self.cli("steward")
        self.assertEqual(sorted(os.listdir(self.root / "drafts")),
                         ["steward-0001.md", "steward-0002.md", "steward-0003.md"])

    def test_many_suggestions_are_capped(self):
        rows = [taskqueue.Row(f"Q-{n:04d}", "task", f"t{n}", "answered", "", "a", "2026-11-01") for n in range(1, 30)]
        text = steward.proposal(rows, [], "2026-11-07", 7)
        self.assertIn("20. Close Q-0020", text)
        self.assertNotIn("21. ", text)
        self.assertIn("And 9 more.", text)


# ================================================================ social


class SocialTextTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(social.plain("A \u2014 B"), "A, B")
        self.assertEqual(social.plain("A\u2013B"), "A, B")
        self.assertEqual(social.plain("#tag and ##two #"), "tag and two")
        self.assertEqual(social.plain("**bold** and `code`"), "bold and code")
        self.assertEqual(social.plain("see [the post](https://x.org/a)"), "see the post")
        self.assertEqual(social.plain("  a\tb\x07c  "), "a b c")

    def test_template_exact(self):
        a = social.Article("Title here", "https://example.org/p", "A short summary.")
        self.assertEqual(social.build_post(a), "Title here\n\nA short summary.\n\nRead more: https://example.org/p\n")
        a = social.Article("Title here", "https://example.org/p", "")
        self.assertEqual(social.build_post(a), "Title here\n\nRead more: https://example.org/p\n")

    def test_long_summary_is_cut_at_a_word_and_the_post_is_short(self):
        a = social.Article("Title", "https://example.org/p", "word " * 200)
        post = social.build_post(a)
        self.assertLessEqual(len(post), social.MAX_POST)
        self.assertIn("word...\n\nRead more: https://example.org/p\n", post)

    def test_summary_left_out_if_too_little_room(self):
        title = "T" * 230
        post = social.build_post(social.Article(title, "https://example.org/p", "a long enough summary here"))
        self.assertEqual(post, f"{title}\n\nRead more: https://example.org/p\n")

    def test_title_and_link_too_long_is_refused(self):
        with self.assertRaises(UmwayiError):
            social.build_post(social.Article("T" * 200, "https://example.org/" + "p" * 100, ""))

    def test_check_post_fails_closed(self):
        link = "https://example.org/p"
        ok = f"T\n\nRead more: {link}\n"
        social.check_post(ok, link)
        for bad in (f"#T\n\nRead more: {link}\n", f"T \u2014 x\n\nRead more: {link}\n", "x" * 281,
                    f"T\x07\n\nRead more: {link}\n", "T\n\nno link\n"):
            with self.subTest(bad=bad[:12]):
                with self.assertRaises(UmwayiError):
                    social.check_post(bad, link)

    def test_parse_article(self):
        a = social.parse_article(ARTICLE)
        self.assertEqual(a.link, "https://example.org/week-45")
        self.assertEqual(a.summary, "This week I built the #logbook and the *queue*. It was work \u2014 but it works. "
                                    "Second line of the same paragraph.")
        a = social.parse_article("---\ntitle: 'Quoted: yes'\nlink: https://x.org\nsummary: Given\n---\nbody\n")
        self.assertEqual((a.title, a.summary), ("Quoted: yes", "Given"))

    def test_front_matter_refusals(self):
        good_link = "link: https://example.org/p"
        bad = {
            "no front matter": "title: x\n",
            "empty": "",
            "not closed": "---\ntitle: x\n" + good_link + "\n",
            "no title": f"---\n{good_link}\n---\n",
            "no link": "---\ntitle: x\n---\n",
            "unknown key": f"---\ntitle: x\n{good_link}\nauthor: me\n---\n",
            "repeated key": f"---\ntitle: x\ntitle: y\n{good_link}\n---\n",
            "not key value": f"---\ntitle: x\n{good_link}\njust words\n---\n",
            "empty value": f"---\ntitle:\n{good_link}\n---\n",
            "http link": "---\ntitle: x\nlink: http://example.org/p\n---\n",
            "link with space": "---\ntitle: x\nlink: https://example.org/a b\n---\n",
            "link with fragment": "---\ntitle: x\nlink: https://example.org/a#b\n---\n",
            "link with quote": "---\ntitle: x\nlink: https://example.org/a\"b\n---\n",
            "javascript link": "---\ntitle: x\nlink: javascript:alert(1)\n---\n",
            "title too long": f"---\ntitle: {'x' * 201}\n{good_link}\n---\n",
        }
        for name, text in bad.items():
            with self.subTest(name=name):
                with self.assertRaises(UmwayiError):
                    social.parse_article(text)


class SocialTests(Base):
    def test_one_draft_per_channel_and_one_entry_per_step(self):
        before = self.snap()
        code, out, err = self.cli("social", "draft", "articles/week.md")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, (
            "Wrote drafts/post-linkedin-0001.md\nWrote drafts/post-mastodon-0001.md\n"
            "These are drafts. Nothing was posted.\n"
            "To publish one, the owner runs: umwayi publish-draft drafts/post-linkedin-0001.md (Ask me first).\n"))
        expected = "What I learned, week 45\n\n" \
                   "This week I built the logbook and the queue. It was work, but it works. " \
                   "Second line of the same paragraph.\n\nRead more: https://example.org/week-45\n"
        for c in ("linkedin", "mastodon"):
            text = (self.root / "drafts" / f"post-{c}-0001.md").read_text(encoding="utf-8")
            self.assertEqual(text, expected)
            self.assertNotIn("#", text)
            self.assertNotIn("\u2014", text)
            self.assertLessEqual(len(text), 280)
        self.assertEqual(self.changed(before), [".umwayi/", ".umwayi/logbook.sha256", "LOGBOOK.md", "drafts/",
                                                "drafts/post-linkedin-0001.md", "drafts/post-mastodon-0001.md"])
        e = self.entries()
        self.assertEqual(len(e), 3)
        self.assertTrue(e[0].added.startswith("Step 1 (read_article): read articles/week.md ("))
        self.assertIn("SHA-256", e[0].added)
        self.assertEqual(e[1].added, "Step 2 (write_draft): wrote drafts/post-linkedin-0001.md "
                                     "(a post draft for linkedin from articles/week.md)")
        self.assertEqual(e[2].added, "Step 3 (write_draft): wrote drafts/post-mastodon-0001.md "
                                     "(a post draft for mastodon from articles/week.md)")
        self.assertTrue(all(x.source == "umwayi social" for x in e))

    def test_numbering_per_channel_never_overwrites(self):
        self.cli("social", "draft", "articles/week.md")
        (self.root / "drafts" / "post-linkedin-0001.md").write_text("edited by the owner\n")
        self.cli("social", "draft", "articles/week.md")
        self.assertEqual(sorted(os.listdir(self.root / "drafts")), [
            "post-linkedin-0001.md", "post-linkedin-0002.md", "post-mastodon-0001.md", "post-mastodon-0002.md"])
        self.assertEqual((self.root / "drafts" / "post-linkedin-0001.md").read_text(), "edited by the owner\n")

    def test_never_posts_or_runs_anything(self):
        with mock.patch("umwayi.publish.publish") as pub, mock.patch("subprocess.run") as sp, \
                mock.patch("subprocess.Popen") as po:
            self.assertEqual(self.cli("social", "draft", "articles/week.md")[0], 0)
        for m in (pub, sp, po):
            m.assert_not_called()
        self.assertFalse((self.root / "outbox").exists())

    def test_publishing_a_social_draft_stays_ask_me_first(self):
        self.cli("social", "draft", "articles/week.md")
        code, out, _ = self.cli("publish-draft", "drafts/post-linkedin-0001.md")
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("Ask me first\nRule: publish-ask\n"))
        self.assertFalse((self.root / "outbox").exists())

    def test_a_helper_publish_action_is_no_even_though_publishing_is_ask(self):
        d = rules.check(json.dumps({"type": "publish_draft", "helper": "social"}), self.root / "rules.yaml")
        self.assertEqual((d.answer, d.rule_id), ("No", "helper-no-post"))

    def test_stops_on_no_for_one_channel(self):
        self.add_rule("  - id: no-mastodon\n    title: t\n    text: Not there.\n    verdict: no\n"
                      "    matchers:\n      channel: mastodon\n")
        code, out, _ = self.cli("social", "draft", "articles/week.md")
        self.assertEqual(code, 2)
        self.assertIn("stopped at step 3 (write_draft)", out)
        # the draft from the step before stays; it has its own entry
        self.assertEqual(sorted(os.listdir(self.root / "drafts")), ["post-linkedin-0001.md"])
        self.assertEqual(self.entries()[-1].added, "Step 3 (write_draft) stopped: rule no-mastodon gave No")

    def test_stops_on_ask_me_first_before_reading(self):
        self.rules_without("helper-read")
        with mock.patch("umwayi.helpers.social.read_article") as read:
            code, out, _ = self.cli("social", "draft", "articles/week.md")
        read.assert_not_called()
        self.assertEqual(code, 3)
        self.assertFalse((self.root / "drafts").exists())
        rows = taskqueue.list_rows(self.root)
        self.assertEqual([(r.kind, r.title) for r in rows],
                         [("decision", "AI helper social asks first: may it do read_article?")])

    def test_bad_article_content_stops_at_step_1_and_is_logged(self):
        too_big = ARTICLE.encode() + b"word " * 40_001
        for name, data in {"no front matter": b"just text\n", "not utf8": b"\xff\xfe", "too big": too_big}.items():
            with self.subTest(name=name):
                (self.root / "articles" / "bad.md").write_bytes(data)
                code, out, _ = self.cli("social", "draft", "articles/bad.md")
                self.assertEqual(code, 1)
                self.assertIn("stopped at step 1 (read_article)", out)
                self.assertFalse((self.root / "drafts").exists())
                self.assertEqual(self.entries()[-1].added, "Step 1 (read_article) failed after rule helper-read gave Yes")
                if name == "too big":
                    self.assertIn("larger than 200000 bytes", out)

    def test_path_refusals_before_any_step(self):
        (self.root / "private").mkdir()
        (self.root / "private" / "a.md").write_text(ARTICLE)
        (self.root / "articles" / "dir.md").mkdir()
        (self.root / ".git").mkdir()
        (self.root / ".git" / "a.md").write_text(ARTICLE)
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        (outside / "a.md").write_text(ARTICLE)
        cases = [
            ("articles/nope.md", "not found"),
            ("private/a.md", "private path"),
            ("articles/dir.md", "regular file"),
            ("../a.md", "'..'"),
            (str(outside / "a.md"), "inside the root"),
            (".git/a.md", ".git or .umwayi"),
        ]
        for article, fragment in cases:
            with self.subTest(article=article):
                before = self.snap()
                with mock.patch("umwayi.helpers.base.rules.check") as check:
                    code, out, err = self.cli("social", "draft", article)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(fragment, err)
                check.assert_not_called()
                self.assertEqual(self.changed(before), [])

    def test_symlinked_article_refused(self):
        try:
            (self.root / "articles" / "link.md").symlink_to(self.root / "articles" / "week.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        code, _, err = self.cli("social", "draft", "articles/link.md")
        self.assertEqual(code, 1)
        self.assertIn("symbolic link", err)

    def test_channels_config(self):
        cfg = self.root / "umwayi.json"
        base_cfg = {"memory_dir": "memory", "private_paths": []}
        cases = {
            "no key": (dict(base_cfg), "no social_channels"),
            "empty": (dict(base_cfg, social_channels=[]), "no social_channels"),
            "too many": (dict(base_cfg, social_channels=["a", "b", "c", "d", "e", "f"]), "more than 5"),
            "bad name": (dict(base_cfg, social_channels=["Linked In"]), "lowercase"),
            "repeated": (dict(base_cfg, social_channels=["a", "a"]), "twice"),
            "not a list": (dict(base_cfg, social_channels="linkedin"), "must be a list"),
        }
        for name, (data, fragment) in cases.items():
            with self.subTest(name=name):
                cfg.write_text(json.dumps(data))
                before = self.snap()
                code, out, err = self.cli("social", "draft", "articles/week.md")
                self.assertEqual((code, out), (64, ""))
                self.assertIn(fragment, err)
                self.assertEqual(self.changed(before), [])

    def test_usage_errors(self):
        for argv in (["social"], ["social", "draft"], ["social", "post", "articles/week.md"],
                     ["social", "draft", "articles/week.md", "--channel", "x"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 64)


# ======================================================== a helper cannot approve


class NoApprovalTests(Base):
    def test_helper_commands_do_not_accept_approved_by(self):
        self.queue.write_text(QUEUE, encoding="utf-8")
        for argv in (["steward", "--approved-by", "Miguel"], ["social", "draft", "articles/week.md", "--approved-by", "M"],
                     ["steward", "--approved_by", "Miguel"]):
            with self.subTest(argv=argv):
                before = self.snap()
                self.assertEqual(self.cli(*argv)[0], 64)
                self.assertEqual(self.changed(before), [])

    def test_helper_code_never_mentions_approved_or_imports_publish(self):
        for f in HELPER_FILES:
            src = f.read_text(encoding="utf-8")
            with self.subTest(file=f.name):
                self.assertNotRegex(src.lower(), r"approved", "helper code must not accept, build or pass --approved-by")
                tree = ast.parse(src)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
                    elif isinstance(node, ast.Import):
                        names = [a.name for a in node.names]
                    else:
                        continue
                    for n in names:
                        for banned in ("umwayi.publish", "umwayi.cli", "umwayi.jobs", "umwayi.report"):
                            self.assertFalse(n == banned or n.startswith(banned + "."), n)

    def test_helpers_never_call_publish_even_when_rules_say_yes_to_everything(self):
        (self.root / "rules.yaml").write_text("rules:\n  - id: all\n    title: t\n    text: t\n    verdict: yes\n"
                                              "    matchers:\n      helper__exists: true\n", encoding="utf-8")
        self.queue.write_text(QUEUE, encoding="utf-8")
        with mock.patch.object(publish, "publish") as pub:
            self.assertEqual(self.cli("steward")[0], 0)
            self.assertEqual(self.cli("social", "draft", "articles/week.md")[0], 0)
        pub.assert_not_called()
        self.assertFalse((self.root / "outbox").exists())


# =========================================================== code guards


def _imports(path):
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


class CodeGuardTests(unittest.TestCase):
    ALLOWED_IMPORTS = {"__future__", "contextlib", "hashlib", "json", "os", "re", "dataclasses", "datetime", "pathlib", "typing",
                       "umwayi", "umwayi.config", "umwayi.drafts", "umwayi.errors", "umwayi.memory",
                       "umwayi.helpers.base"}

    def test_helpers_import_only_from_an_allow_list(self):
        for f in HELPER_FILES:
            with self.subTest(file=f.name):
                self.assertLessEqual(_imports(f), self.ALLOWED_IMPORTS, _imports(f) - self.ALLOWED_IMPORTS)

    def test_no_network_or_program_runner_is_loaded_by_the_helpers(self):
        code = ("import sys\nimport umwayi.helpers.steward, umwayi.helpers.social\n"
                "bad = {'subprocess', 'socket', 'ssl', 'http', 'http.client', 'urllib.request', 'ftplib', 'smtplib',"
                " 'asyncio', 'selectors', 'select', 'umwayi.publish', 'umwayi.report', 'umwayi.jobs', 'umwayi.cli'}\n"
                "print(sorted(bad & set(sys.modules)))\n")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(REPO)), cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "[]")

    def test_helpers_write_files_only_through_drafts_queue_and_logbook(self):
        write_attrs = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "rename", "touch", "chmod",
                       "symlink_to", "hardlink_to", "replace", "truncate"}
        os_writes = {"open", "write", "replace", "rename", "remove", "unlink", "mkdir", "makedirs", "rmdir",
                     "symlink", "link", "chmod", "truncate", "fdopen", "system", "popen"}
        for f in HELPER_FILES:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                with self.subTest(file=f.name, line=node.lineno):
                    if isinstance(fn, ast.Name):
                        self.assertNotIn(fn.id, {"open", "exec", "eval", "__import__"})
                    if isinstance(fn, ast.Attribute):
                        if isinstance(fn.value, ast.Name) and fn.value.id == "os":
                            self.assertNotIn(fn.attr, os_writes)
                        elif not (isinstance(fn.value, ast.Name) and fn.value.id in ("s", "text", "value", "line")):
                            self.assertNotIn(fn.attr, write_attrs)

    def test_only_the_base_logs_or_adds_queue_items(self):
        for f in HELPER_FILES:
            if f.name == "base.py":
                continue
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    with self.subTest(file=f.name, line=node.lineno):
                        if node.value.id == "logbook":
                            self.assertNotIn(node.attr, {"append", "seal"})
                        if node.value.id == "taskqueue":
                            self.assertNotIn(node.attr, {"add", "answer", "close", "migrate"})


class DraftsModuleTests(Base):
    def test_prefix_must_be_plain_so_no_path_can_escape_drafts(self):
        from umwayi import drafts
        for prefix in ("", "../x", "a/b", "Post", "post_x", "-x", "x" * 42, ".hidden"):
            with self.subTest(prefix=prefix):
                with self.assertRaises(UmwayiError):
                    drafts.create(self.root, prefix, "text")
        self.assertFalse((self.root / "drafts").exists())
        d = drafts.create(self.root, "post-linkedin", "text")
        self.assertEqual((d.rel, d.made_folder), ("drafts/post-linkedin-0001.md", True))


class HelperWritesTests(Base):
    """No helper writes outside drafts/, except the logbook and (for Ask me first) one queue item."""

    def run_all(self):
        self.queue.write_text(QUEUE, encoding="utf-8")
        before = self.snap()
        self.cli("steward")
        self.cli("social", "draft", "articles/week.md")
        return [c for c in self.changed(before)
                if not c.startswith("drafts/") and c not in ("LOGBOOK.md", ".umwayi/", ".umwayi/logbook.sha256")]

    def test_yes_writes_only_drafts_and_the_logbook(self):
        self.assertEqual(self.run_all(), [])

    def test_ask_me_first_also_writes_the_queue_and_nothing_else(self):
        (self.root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
        self.assertEqual(self.run_all(), ["queue.md"])
        self.assertFalse((self.root / "drafts").exists())


class StarterRulesTests(unittest.TestCase):
    def check(self, action):
        return rules.check(json.dumps(action), REPO / "rules.yaml")

    def test_repo_rules_for_helpers(self):
        for t in ("read_queue", "read_logbook", "read_article", "write_draft"):
            with self.subTest(type=t):
                self.assertEqual(self.check({"type": t, "helper": "steward"}).answer, "Yes")
        for t in ("post", "post_update", "send", "send_email", "publish", "publish_draft"):
            with self.subTest(type=t):
                self.assertEqual(self.check({"type": t, "helper": "social"}).answer, "No")
        self.assertEqual(self.check({"type": "read_calendar", "helper": "steward"}).answer, "Ask me first")
        # the owner's own publish-draft is still Ask me first
        self.assertEqual(self.check({"type": "publish_draft"}).answer, "Ask me first")

    def test_repo_config_has_a_small_channel_list(self):
        from umwayi.config import load_config
        self.assertTrue(1 <= len(load_config(REPO).social_channels) <= 5)


if __name__ == "__main__":
    unittest.main()
