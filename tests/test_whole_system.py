"""The whole-system test (tasks.md S.1, requirements S.R1 to S.R3; includes 9.11 and the test part of 10.21).

One ordered owner's day across every layer at once (test_01 to test_08), then each fault scenario from the day's end
state (test_2x to test_7x). Every step is a real child process: `python -m umwayi ...`, a layer 9 hook script, or a
rendered ExecStart= line, with HOME, XDG_CONFIG_HOME and TMPDIR in a temporary folder and only fakes for the agents.
No real agent, systemd, network or account is used. Each fault test restores the day's snapshot first; a day step
that failed skips everything after it.
"""

import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import unittest

from tests.budget.support import api_request, logs
from tests.whole_system_support import SECRET, STOP_WITHIN, World, permission, units_yaml

READ = {"do": "tool", "tool": "Read", "input": {"file_path": "/etc/hostname"}}
KIRO_READ = {"do": "tool", "tool": "read_file", "input": {"path": "/etc/hostname"}}
END = {"do": "exit", "code": 0}
LOOP = {"do": "loop_tools", "tool": "Read", "input": {"file_path": "/etc/hostname"}, "every": 0.3, "for": 90}
KIRO_LOOP = {"do": "loop_tools", "tool": "read_file", "input": {"path": "/etc/hostname"}, "every": 0.3, "for": 90}


def report(micros):
    return {"do": "otlp", "path": "/v1/logs", "body": logs(api_request(cost_micros=micros))}


def sources(entries):
    return [e.source for e in entries]


class WholeSystemTests(unittest.TestCase):
    """Test names sort in the order they run: the day, then the faults."""

    world: World = None
    done: list = []
    failed: str | None = None
    anchor_morning = anchor_evening = None

    @classmethod
    def setUpClass(cls):
        cls.world = World()
        cls.world.build()
        cls.done, cls.failed = [], None

    @classmethod
    def tearDownClass(cls):
        cls.world.cleanup()

    # ------------------------------------------------------------ the day, in order

    def day(self, upto: int):
        """Run every day step up to `upto` that has not run yet; a step that failed skips the rest."""
        for n in range(1, upto + 1):
            if n in type(self).done:
                continue
            if type(self).failed:
                self.skipTest(f"day step {type(self).failed} failed, so this step cannot run")
            try:
                getattr(self, f"_step_{n}")()
            except BaseException:
                type(self).failed = str(n)
                raise
            type(self).done.append(n)

    def after_day(self):
        """A fault scenario starts from the day's end state (S-Q2)."""
        self.day(8)
        self.world.restore()

    def u(self, *args, code=None, **kw):
        r = self.world.u(*args, **kw)
        if code is not None:
            self.assertEqual(r.returncode, code, f"umwayi {' '.join(args)}\n{r.stdout}\n{r.stderr}")
        self.assertNotIn("Traceback", r.stdout + r.stderr, " ".join(args))
        return r

    def new(self, before: int):
        """The entries added since there were `before` of them."""
        return self.world.entries()[before:]

    def count(self) -> int:
        return len(self.world.entries())

    def end_checks(self, verify=0, status=0):
        """After every scenario (S.R1.5)."""
        w = self.world
        r = self.u("logbook", "verify")
        self.assertEqual(r.returncode, verify, r.stdout)
        r = self.u("budget", "status")
        self.assertEqual(r.returncode, status, r.stdout + r.stderr)
        w.wait_quiet()
        self.assertEqual(w.agent_pids_alive(), [], "a process the scenario started is still alive")
        self.assertEqual(w.bad_codes(), [], "a command gave an exit code it may not give")
        for word in (SECRET,):
            self.assertNotIn(word, w.log_text())

    # --- step 1: a fresh root (S.R2.1)

    def _step_1(self):
        w = self.world
        for args in (("agent", "validate"), ("budget", "validate"), ("schedule", "validate"),
                     ("workflow", "validate", "content-loop")):
            self.u(*args, code=0)
        self.assertFalse((w.root / "LOGBOOK.md").exists(), "validating wrote a logbook")

    def test_01_a_fresh_root_validates(self):
        self.day(1)

    # --- step 2: memory, queue, archive (S.R2.2)

    def _step_2(self):
        w = self.world
        r = self.u("memory", "bundle", code=0)
        self.assertIn("I am the owner.", r.stdout)
        self.assertNotIn(SECRET, r.stdout)
        self.assertNotIn("bank.md", r.stdout)
        self.u("queue", "add", "--kind", "task", "Write the week 46 post", code=0)
        self.u("queue", "add", "--kind", "decision", "Ship the scan first?", code=0)
        self.u("queue", "answer", "Q-0002", "--answer", "Yes, the scan first", "--revisit-if", "none", code=0)
        r = self.u("archive", "move", "notes.md", "--lines", "4-5", "--reason", "old plan", code=0)
        self.assertIn("A-0001", r.stdout)
        self.assertIn("[archived A-0001: archive/A-0001.txt]", (w.root / "notes.md").read_text(encoding="utf-8"))
        self.u("archive", "verify", code=0)
        self.assertEqual(sources(w.entries()), ["umwayi queue add", "umwayi queue add", "umwayi queue answer",
                                                "umwayi archive move"])

    def test_02_memory_queue_and_archive(self):
        self.day(2)

    # --- step 3: the rules, then the chain is started and anchored (S.R2.3)

    def _step_3(self):
        n = self.count()
        self.u("check", json.dumps({"type": "read_memory"}), code=0)
        self.u("check", json.dumps({"type": "payment", "card": SECRET}), code=2)
        self.u("check", json.dumps({"type": "launch_rocket"}), code=3)
        self.u("logbook", "seal", "--chain", "--by", "Owner", code=0)
        r = self.u("logbook", "anchor", code=0)
        type(self).anchor_morning = r.stdout.split("\n")[0].strip()
        self.assertRegex(type(self).anchor_morning, r"^1:[0-9a-f]{64}$")
        self.assertEqual(sources(self.new(n)), ["umwayi rules"] + ["umwayi check"] * 3 + ["umwayi logbook seal"])  # L13.3 (13.R7.2): the rules entry before the first check
        self.assertIn("- Chain: ", self.world.log_text())

    def test_03_rules_and_the_chain(self):
        self.day(3)

    # --- step 4: a job and a workflow (S.R2.4)

    def _step_4(self):
        n = self.count()
        r = self.u("run", str(self.world.root / "jobs.yaml"), "--job", "open-queue", code=0)
        self.assertIn("Q-0001", r.stdout)
        r = self.u("workflow", "run", "content-loop", code=3)
        self.assertIn("The approve step never approves.", r.stdout)
        got = sources(self.new(n))
        self.assertEqual(got[0], "umwayi run")
        self.assertEqual(got[1:], ["umwayi workflow"] * 3 + ["umwayi queue add", "umwayi workflow"])

    def test_04_a_job_and_a_workflow(self):
        self.day(4)

    # --- step 5: the layer 9 hooks, each as its platform runs it (S.R2.5, 9.11)

    def _step_5(self):
        w = self.world
        n = self.count()
        r = w.hook("claude_code", {"hook_event_name": "PreToolUse", "tool_name": "Read",
                                   "tool_input": {"file_path": "/etc/hostname"}, "session_id": "s1", "cwd": str(w.work)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
        r = w.hook("kiro", {"hook_event_name": "PreToolUse", "tool_name": "read_file", "tool_input": {"path": "/a"}})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = w.hook("stdio", {"tool_name": "lookup", "tool_input": {"q": "x"}}, ("--platform", "mytool"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["decision"]), (0, "allow"), r.stdout + r.stderr)
        r = w.hook("claude_code", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                   "tool_input": {"command": "rm -rf / " + SECRET}})
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny", r.stdout)
        got = self.new(n)
        self.assertEqual(sources(got), ["umwayi check"] * 4)
        self.assertNotIn(SECRET, w.log_text())

    def test_05_the_layer_9_hooks(self):
        self.day(5)

    # --- step 6: the front door, every kind of start, with telemetry (S.R2.6, 10.21's test part)

    def assert_one_start(self, got, agent, tag, change=False):
        """One start's entries: agent_run and budget_check asked, reserve, start, the tool checks, end, settle. The
        first start of the day also logs units.yaml before its values are first used (B.R1.5)."""
        changes = [e for e in got if e.added.startswith("units.yaml changed")]
        self.assertEqual(len(changes), 1 if change else 0, [e.added for e in got])
        got = [e for e in got if e not in changes]
        src = sources(got)
        self.assertEqual(src[:4], ["umwayi check", "umwayi check", "umwayi budget", "umwayi agent run"], src)
        self.assertTrue(got[0].added.endswith("; action type: agent_run"), got[0].added)
        self.assertTrue(got[1].added.endswith("; action type: budget_check"), got[1].added)
        self.assertTrue(got[2].added.startswith(f"Reserved run "), got[2].added)
        self.assertTrue(got[3].added.startswith(f"Started agent {agent} "), got[3].added)
        self.assertEqual(src[-1], "umwayi budget")
        self.assertRegex(got[-1].added, rf"^Settled run [0-9a-f]{{16}} for agent {agent} \([a-z-]+\): {tag} ")
        self.assertIn("umwayi check", src[4:-1], "no tool call went through the hook")

    def _step_6(self):
        w = self.world
        r = self.u("agent", "check", "reviewer", code=0)
        self.assertIn("ok: login: Claude subscription (plan: max)", r.stdout)
        # agent run, Claude Code, with a measured report
        n = self.count()
        r = self.u("agent", "run", "reviewer", "--prompt", f"Read it {SECRET}", code=0,
                   extra={"FAKE_SCRIPT": json.dumps([report(123456), READ, END])})
        self.assertIn("settled, measured 13 UU (123456 micros).", r.stdout)
        self.assert_one_start(self.new(n), "reviewer", "measured 123456 micros", change=True)
        # agent run, Kiro: declared at run_micros
        n = self.count()
        r = self.u("agent", "run", "kiro", "--prompt", "Read it", code=0,
                   extra={"FAKE_SCRIPT": json.dumps([KIRO_READ])})
        self.assertIn("settled, declared 40 UU (400000 micros).", r.stdout)
        self.assert_one_start(self.new(n), "kiro", "declared 400000 micros")
        # the cli chat, Claude Code: a report, then one tool call through the hook from the owner's line
        n = self.count()
        r = self.u("agent", "chat", "reviewer", input="/tool Read\n/quit\n", code=0,
                   extra={"FAKE_SCRIPT": json.dumps([report(5000)])})
        self.assertIn("settled, measured 1 UU (5000 micros).", r.stdout)
        self.assert_one_start(self.new(n), "reviewer", "measured 5000 micros")
        # the ACP chat, Claude Code: the canary, a tool call through the inline hook, a permission, a report
        w.node_answers({"turns": [[{"claude_tool": {"tool": "Read", "input": {"file_path": "/etc/hostname"}}},
                                   permission(), {"otlp": {"body": logs(api_request(cost_micros=7000))}},
                                   {"chunk": "done"}]]})
        n = self.count()
        r = self.u("agent", "chat", "acp-reviewer", input="go\n:quit\n", code=0)
        self.assertIn("settled, measured 1 UU (7000 micros).", r.stdout)
        got = self.new(n)
        self.assert_one_start(got, "acp-reviewer", "measured 7000 micros")
        self.assertTrue(any("acp_permission" in e.added for e in got), [e.added for e in got])
        # the ACP chat, Kiro: a tool call through the Kiro hook and a permission; declared
        n = self.count()
        spec = {"turns": [[{"claude_tool": {"tool": "read_file", "input": {"path": "/etc/hostname"}}}, permission(),
                           {"chunk": "done"}]]}
        r = self.u("agent", "chat", "kiro-acp", input="go\n:quit\n", code=0, extra={"FAKE_ACP": json.dumps(spec)})
        got = self.new(n)
        self.assert_one_start(got, "kiro-acp", "declared 400000 micros")
        self.assertTrue(any("acp_permission" in e.added for e in got))
        answers = [c["answer"]["result"]["outcome"] for c in w.calls() if c.get("event") == "permission_answer"]
        self.assertEqual([a.get("optionId") for a in answers], ["o-allow", "o-allow"])
        self.assertNotIn(SECRET, w.log_text())

    def test_06_the_front_door(self):
        self.day(6)

    # --- step 7: a schedule, end to end with no systemd (S.R2.7)

    def _step_7(self):
        w = self.world
        self.u("schedule", "validate", code=0)
        r = self.u("schedule", "show", "answered-queue", code=0)
        self.assertIn("ExecStart=", r.stdout)
        n = self.count()
        r = self.u("schedule", "install", "answered-queue", "--approved-by", "Owner", code=0)
        self.assertIn("systemctl --user daemon-reload", r.stdout)
        for kind in ("service", "timer"):
            self.assertEqual(stat.S_IMODE(os.lstat(w.unit_file("answered-queue", kind)).st_mode), 0o644)
        r = self.u("schedule", "check", "answered-queue")
        self.assertIn("not enabled", r.stdout)
        r = w.run_unit("answered-queue")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Q-0002", r.stdout)
        r = self.u("schedule", "remove", "answered-queue", code=0)
        self.assertIn("systemctl --user daemon-reload", r.stdout)
        self.assertFalse(w.unit_file("answered-queue", "service").exists())
        got = sources(self.new(n))
        self.assertEqual(got.count("umwayi schedule"), 2, got)
        self.assertIn("umwayi run", got)

    def test_07_a_schedule(self):
        self.day(7)

    # --- step 8: the budget and the anchors (S.R2.8), then the snapshot of the day's end

    def _step_8(self):
        w = self.world
        r = self.u("budget", "status", code=0)
        self.assertIn("unknown 0%", r.stdout)
        shares = re.search(r"Of used: measured (\d+)%, declared (\d+)%, unknown 0%", r.stdout)
        self.assertTrue(shares and int(shares.group(1)) > 0 and int(shares.group(2)) > 0, r.stdout)
        r = self.u("budget", "calibrate", code=0)
        self.assertIn("Not enough data", r.stdout)
        # the morning's anchor is a prefix of today's chain, so it still verifies; a new anchor verifies too
        self.u("logbook", "verify", "--anchor", type(self).anchor_morning, code=0)
        r = self.u("logbook", "anchor", code=0)
        type(self).anchor_evening = r.stdout.split("\n")[0].strip()
        count = int(type(self).anchor_evening.split(":")[0])
        self.assertGreater(count, 30)
        self.u("logbook", "verify", "--anchor", type(self).anchor_evening, code=0)
        self.end_checks()
        w.save()

    def test_08_the_budget_and_the_anchors(self):
        self.day(8)

    # ------------------------------------------------------------ S.R3.1 a tampered logbook

    def refused_everywhere(self):
        """With the logbook broken: every start, check, job, workflow, schedule install and budget status refused;
        kill on still turns the switch on; schedule remove puts both files back; nothing written by a refusal."""
        w = self.world
        before = w.tree()
        r = self.u("agent", "run", "reviewer", "--prompt", "go", code=2, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.assertEqual([c for c in w.calls() if c.get("started") and c.get("t", 0) > self.t0], [])
        self.u("check", json.dumps({"type": "read_memory"}), code=3)
        self.assertIn(self.u("run", str(w.root / "jobs.yaml"), "--job", "closed-queue").returncode, (1, 2))
        self.assertIn(self.u("workflow", "run", "content-loop").returncode, (1, 2))
        self.u("schedule", "install", "answered-queue", "--approved-by", "Owner", code=2)
        self.u("budget", "status", code=2)
        # remove asks the rules first, and that check cannot be logged, so it stops before it touches the unit files
        # (11.R4.2 puts them back when the removal's own entry fails; here nothing was removed to put back)
        r = self.u("schedule", "remove", "closed-queue", code=2)
        self.assertIn("The logbook could not record the check, so nothing was changed", r.stdout)
        for kind in ("service", "timer"):
            self.assertTrue(w.unit_file("closed-queue", kind).exists())
        after = w.tree()
        self.assertEqual({k for k in set(before) | set(after) if before.get(k) != after.get(k)}, set(),
                         "a refusal wrote something")
        r = self.u("kill", "on", "--reason", "tampered", code=0)
        self.assertIn("The logbook could not be written", r.stdout)
        self.assertTrue((w.root / ".umwayi" / "KILL").exists())

    def install_closed_queue(self):
        self.u("schedule", "install", "closed-queue", "--approved-by", "Owner", code=0)

    def test_20_tampered_an_old_chained_entry(self):
        self.after_day()
        w = self.world
        self.install_closed_queue()
        self.t0 = time.time()
        text = w.log_text()
        old = "- Added: Rule read-memory gave Yes; action type: read_memory"
        self.assertEqual(text.count(old), 1)
        w.rewrite_logbook(text.replace(old, old + " (edited)"), rechain=False)
        r = self.u("logbook", "verify", code=1)
        self.assertIn("the Chain value does not match", r.stdout)
        self.refused_everywhere()
        self.u("logbook", "verify", code=1)
        self.assertEqual(w.agent_pids_alive(), [])
        self.assertEqual(w.bad_codes(), [])

    def edited_settle(self, consistent: bool):
        w = self.world
        text = w.log_text()
        m = re.search(r"(- Added: Settled run [0-9a-f]{16} for agent reviewer \(claude-code\): measured )123456 micros "
                      r"\(13 UU\)(; .*?; released )876544( micros)", text)
        self.assertTrue(m, "the day's measured settle")
        if consistent:
            new = m.group(1) + "23456 micros (3 UU)" + m.group(2) + "976544" + m.group(3)
        else:
            new = m.group(0).replace("released 876544", "released 876545")
        w.rewrite_logbook(text.replace(m.group(0), new))

    def test_21_tampered_a_budget_settle_out_of_shape(self):
        self.after_day()
        self.edited_settle(consistent=False)
        self.u("logbook", "verify", code=0)  # the chain and the record were rewritten too
        r = self.u("agent", "run", "reviewer", "--prompt", "go", code=2, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.assertIn("is not the one settle of an earlier reservation", r.stdout)
        self.assertNotIn("876545", r.stdout + r.stderr)
        self.u("budget", "status", code=2)
        self.assertEqual(self.world.bad_codes(), [])

    def test_22_tampered_a_budget_settle_consistently(self):
        self.after_day()
        before = self.u("budget", "status", code=0).stdout
        self.edited_settle(consistent=True)
        self.u("logbook", "verify", code=0)
        after = self.u("budget", "status", code=0).stdout
        self.assertNotEqual(before, after)  # the edited number is what status shows (KNOWN-LIMITS 115)
        r = self.u("logbook", "verify", "--anchor", type(self).anchor_evening, code=1)
        self.assertIn("the chain differs from the anchor", r.stdout)
        self.u("agent", "run", "reviewer", "--prompt", "go", code=0, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.end_checks()

    def test_23_tampered_a_truncated_tail(self):
        self.after_day()
        w = self.world
        text = w.log_text()
        heads = [m.start() for m in re.finditer(r"(?m)^## \d{4}-\d{2}-\d{2}$", text)]
        w.rewrite_logbook(text[:heads[-2]].rstrip("\n") + "\n", rechain=False)
        self.u("logbook", "verify", code=0)
        r = self.u("logbook", "verify", "--anchor", type(self).anchor_evening, code=1)
        self.assertIn("the chain is shorter than the anchor", r.stdout)
        self.u("agent", "run", "reviewer", "--prompt", "go", code=0, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.end_checks()

    # ------------------------------------------------------------ S.R3.2 a lost reservation

    def test_30_a_lost_reservation(self):
        self.after_day()
        w = self.world
        since = time.time()
        p = w.start("agent", "run", "reviewer", "--prompt", "a long task", extra={"FAKE_SCRIPT": json.dumps([LOOP])})
        w.wait_for(lambda c: c.get("event") == "tool", "the first tool call", proc=p, since=since)
        os.kill(p.pid, signal.SIGKILL)  # umwayi itself: no settle can be written
        p.wait(timeout=30)
        w.record(("agent", "run"), 2)  # a SIGKILL is not an exit code umwayi gave
        for pid in w.agent_pids_alive():
            os.killpg(pid, signal.SIGKILL)
        w.wait_quiet()
        r = self.u("budget", "status", code=0)
        self.assertIn("1 reservation(s) of this day have no settle and count in full", r.stdout)
        used, reserved = map(int, re.search(r"per_agent_per_day reviewer: used (\d+) UU, reserved (\d+) UU",
                                            r.stdout).groups())
        self.assertEqual(reserved, 100)
        (w.root / "units.yaml").write_text(units_yaml(per_agent=used + reserved + 50), encoding="utf-8")
        r = self.u("agent", "run", "reviewer", "--prompt", "go", code=3, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.assertIn("the budget limit per_agent_per_day has 50 UU left, a run needs 100 UU", r.stdout)
        holder = subprocess.Popen([sys.executable, "-c", "import sys, time\nfrom pathlib import Path\n"
                                   "from umwayi import runlock\nwith runlock.held(Path(sys.argv[1])):\n"
                                   "    print('held', flush=True)\n    time.sleep(60)\n", str(w.root)],
                                  stdout=subprocess.PIPE, text=True, env=w.env())
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            r = self.u("budget", "settle-lost", "--by", "Owner", code=3)
            self.assertIn("holds the run lock", r.stdout)
        finally:
            holder.kill()
            holder.wait(timeout=30)
            holder.stdout.close()
        r = self.u("budget", "settle-lost", "--by", "Owner", code=0)
        self.assertIn("1 lost reservation(s) settled.", r.stdout)
        self.assertNotIn("have no settle", self.u("budget", "status", code=0).stdout)
        (w.root / "units.yaml").write_text(units_yaml(), encoding="utf-8")
        self.u("agent", "run", "reviewer", "--prompt", "go", code=0, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.end_checks()

    # ------------------------------------------------------------ S.R3.3 the kill switch in the middle of a run

    def kill_mid_run(self, args, extra=None, owner=None, settled=None, acp=None):
        w = self.world
        if acp is not None:
            w.node_answers(acp)
        settles = len([e for e in w.entries() if e.added.startswith("Settled run ")])
        since = time.time()
        p = w.start(*args, extra=extra)
        if owner:
            p.stdin.write(owner)
            p.stdin.flush()
        w.wait_for(lambda c: c.get("event") == "tool", "the first tool call", proc=p, since=since)
        t = time.monotonic()
        self.u("kill", "on", "--reason", "mid run", code=0)
        code, out, err, left = w.finish(p, timeout=STOP_WITHIN + 60)
        took = time.monotonic() - t
        self.assertEqual(code, 3, out + err)
        self.assertLess(took, STOP_WITHIN, f"the stop took {took:.1f} s")
        self.assertEqual(left, [], "an agent process was alive when umwayi exited")
        got = [e for e in w.entries() if e.added.startswith("Settled run ")]
        self.assertEqual(len(got), settles + 1)
        if settled:
            self.assertIn(settled, got[-1].added)
        self.u("kill", "off", code=0)
        self.u("agent", "run", "reviewer", "--prompt", "go", code=0, extra={"FAKE_SCRIPT": json.dumps([END])})

    def test_40_kill_switch_mid_agent_run_claude_code(self):
        self.after_day()
        self.kill_mid_run(("agent", "run", "reviewer", "--prompt", "long"),
                          extra={"FAKE_SCRIPT": json.dumps([report(4242), LOOP])}, settled=": measured 4242 micros")
        self.end_checks()

    def test_41_kill_switch_mid_agent_run_kiro(self):
        self.after_day()
        self.kill_mid_run(("agent", "run", "kiro", "--prompt", "long"), extra={"FAKE_SCRIPT": json.dumps([KIRO_LOOP])},
                          settled=": declared 400000 micros")
        self.end_checks()

    def test_42_kill_switch_mid_cli_chat_claude_code(self):
        self.after_day()
        self.kill_mid_run(("agent", "chat", "reviewer"), owner="/tool Read\n",
                          extra={"FAKE_SCRIPT": json.dumps([report(3000)])}, settled=": measured 3000 micros")
        self.end_checks()

    def test_43_kill_switch_mid_cli_chat_kiro(self):
        self.after_day()
        self.kill_mid_run(("agent", "chat", "kiro"), owner="/tool read_file\n", settled=": declared 400000 micros")
        self.end_checks()

    def test_44_kill_switch_mid_acp_chat_claude_code(self):
        self.after_day()
        acp = {"turns": [[{"otlp": {"body": logs(api_request(cost_micros=2500))}},
                          {"claude_tool": {"tool": "Read", "input": {"file_path": "/etc/hostname"}}}, {"sleep": 90}]]}
        self.kill_mid_run(("agent", "chat", "acp-reviewer"), owner="go\n", acp=acp, settled=": measured 2500 micros")
        self.end_checks()

    def test_45_kill_switch_mid_acp_chat_kiro(self):
        self.after_day()
        spec = {"turns": [[{"claude_tool": {"tool": "read_file", "input": {"path": "/etc/hostname"}}}, {"sleep": 90}]]}
        self.kill_mid_run(("agent", "chat", "kiro-acp"), owner="go\n", extra={"FAKE_ACP": json.dumps(spec)},
                          settled=": declared 400000 micros")
        self.end_checks()

    def test_46_kill_switch_and_a_scheduled_job(self):
        # A job runs for a moment and checks the kill switch at its start (layer 6), so "in the middle" of a scheduled
        # run is its start: with the switch on it stops with 3 and one entry, and after kill off it runs.
        self.after_day()
        w = self.world
        self.install_closed_queue()
        self.u("kill", "on", "--reason", "scheduled", code=0)
        n = self.count()
        r = w.run_unit("closed-queue")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        [stop] = self.new(n)
        self.assertIn("kill switch", stop.added)
        self.u("kill", "off", code=0)
        r = w.run_unit("closed-queue")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.end_checks()

    # ------------------------------------------------------------ S.R3.4 a schedule install with no systemd

    def test_50_a_schedule_with_no_systemd(self):
        self.after_day()
        w = self.world
        bare = str(w.bin)  # the fakes only: no systemctl, systemd-analyze or crontab
        recorder = w.base / "recorder"
        recorder.mkdir()
        mark = w.base / "systemctl-calls"
        for prog in ("systemctl", "systemd-analyze", "crontab", "loginctl"):
            p = recorder / prog
            p.write_text(f"#!{sys.executable}\nimport sys\nopen({str(mark)!r}, 'a').write(' '.join(sys.argv) + '\\n')\n",
                         encoding="utf-8")
            p.chmod(0o755)
        for path in (bare, os.pathsep.join([str(recorder), bare])):
            with self.subTest(path="recorder" if "recorder" in path else "bare"):
                r = self.u("schedule", "install", "closed-queue", "--approved-by", "Owner", code=0, path=path)
                self.assertIn(f"systemctl --user enable --now {w.unit_base('closed-queue')}.timer", r.stdout)
                for kind in ("service", "timer"):
                    self.assertEqual(stat.S_IMODE(os.lstat(w.unit_file("closed-queue", kind)).st_mode), 0o644)
                r = self.u("schedule", "check", "closed-queue", path=path)
                self.assertIn("not enabled", r.stdout)
                n = self.count()
                r = w.run_unit("closed-queue")
                [e] = self.new(n)
                if "recorder" in path:  # the second run of the day meets the gap rule: exit 1, and one entry says so
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertTrue(e.added.startswith("Job closed-queue did not run: the gap rule"), e.added)
                else:
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertTrue(e.added.startswith("Job closed-queue ran (command queue-list)"), e.added)
                self.u("schedule", "remove", "closed-queue", code=0, path=path)
                self.assertFalse(w.unit_file("closed-queue", "timer").exists())
        self.assertFalse(mark.exists(), "umwayi ran a scheduler program")
        self.end_checks()

    # ------------------------------------------------------------ S.R3.5 a limit in the middle of a chat

    def test_60_a_limit_in_the_middle_of_an_acp_chat(self):
        self.after_day()
        w = self.world
        (w.root / "units.yaml").write_text(units_yaml(per_run=1), encoding="utf-8")
        w.node_answers({"turns": [[{"otlp": {"body": logs(api_request(cost_micros=5000))}}, {"chunk": "one"}],
                                  [{"otlp": {"body": logs(api_request(cost_micros=20000))}}, {"sleep": 60}]]})
        r = self.u("agent", "chat", "acp-reviewer", input="one\ntwo\n", code=3, timeout=240)
        self.assertIn("it passed its budget of 1 UU for one run", r.stdout)
        settle = [e for e in w.entries() if e.added.startswith("Settled run ")][-1]
        self.assertIn(": measured 25000 micros (3 UU);", settle.added)
        (w.root / "units.yaml").write_text(units_yaml(), encoding="utf-8")
        self.end_checks()

    # ------------------------------------------------------------ S.R3.6 a crash in umwayi

    def test_70_a_crash_in_an_append_is_recovered(self):
        self.after_day()
        r = self.u("queue", "add", "--kind", "task", "Crash me", fault="umwayi.logbook:_record_hash:crash")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        r = self.u("logbook", "verify")
        self.assertIn(r.returncode, (0, 1))
        n = self.count()
        self.u("queue", "add", "--kind", "task", "After the crash", code=0)
        self.assertIn("umwayi logbook recover", sources(self.new(n)))
        self.end_checks()

    def test_71_a_crash_before_the_reservation(self):
        self.after_day()
        w = self.world
        n = self.count()
        r = self.u("agent", "run", "reviewer", "--prompt", "go", code=2, fault="umwayi.budget:reserve_text:crash",
                   extra={"FAKE_SCRIPT": json.dumps([END])})
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertFalse([e for e in self.new(n) if e.source == "umwayi budget"], "a reservation was written")
        self.assertFalse([c for c in w.calls() if c.get("started") and c.get("argv", [""])[-1:] == ["go"]])
        self.u("agent", "run", "reviewer", "--prompt", "go", code=0, extra={"FAKE_SCRIPT": json.dumps([END])})
        self.end_checks()

    def test_72_a_crash_in_the_settle_leaves_a_lost_reservation(self):
        self.after_day()
        r = self.u("agent", "run", "reviewer", "--prompt", "go", code=2, fault="umwayi.budget:settle_text:crash",
                   extra={"FAKE_SCRIPT": json.dumps([END])})
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertIn("1 reservation(s) of this day have no settle", self.u("budget", "status", code=0).stdout)
        self.u("budget", "settle-lost", "--by", "Owner", code=0)
        self.end_checks()

    def test_73_a_crash_in_a_schedule_install_leaves_no_unit_file(self):
        self.after_day()
        w = self.world
        r = self.u("schedule", "install", "closed-queue", "--approved-by", "Owner", code=2,
                   fault="umwayi.schedule:fsync_dir:crash")
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        for kind in ("service", "timer"):
            self.assertFalse(w.unit_file("closed-queue", kind).exists())
        self.u("schedule", "install", "closed-queue", "--approved-by", "Owner", code=0)
        self.u("schedule", "remove", "closed-queue", code=0)
        self.end_checks()


class SupportTests(unittest.TestCase):
    """S.1.1: the world itself. The snapshot restores byte for byte, links kept; the end checks see a leftover
    process and an exit code a command may not give."""

    def setUp(self):
        self.w = World()
        self.addCleanup(self.w.cleanup)
        self.w.build()

    def test_the_snapshot_restores_byte_for_byte_with_links_kept(self):
        w = self.w
        (w.root / "a-link").symlink_to(w.root / "notes.md")
        before = {**w.tree(), **{str(p): p.read_bytes() for p in w.bin.iterdir()}}
        w.save()
        (w.root / "notes.md").write_text("changed\n", encoding="utf-8")
        (w.root / "new.txt").write_text("new\n", encoding="utf-8")
        (w.root / "a-link").unlink()
        w.restore()
        self.assertTrue((w.root / "a-link").is_symlink())
        self.assertEqual({**w.tree(), **{str(p): p.read_bytes() for p in w.bin.iterdir()}}, before)

    def test_the_end_checks_see_a_bad_exit_code(self):
        w = self.w
        w.record(("agent", "run", "x"), 1)
        w.record(("budget", "status"), 1)
        w.record(("run", "jobs.yaml"), 1)  # layer 6 may give 1
        w.record(("check", "{}"), 5)
        self.assertEqual(w.bad_codes(), [("agent run x", 1), ("budget status", 1), ("check {}", 5)])

    def test_the_end_checks_see_a_leftover_process(self):
        w = self.w
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (p.kill(), p.wait(timeout=30)))
        with open(w.fake_log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"started": True, "pid": p.pid, "t": time.time()}) + "\n")
        self.assertEqual(w.agent_pids_alive(), [p.pid])
        w.stop_all()
        p.wait(timeout=30)
        self.assertEqual(w.agent_pids_alive(), [])

    def test_a_wait_ignores_calls_made_before_it(self):
        w = self.w
        with open(w.fake_log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "tool", "t": time.time() - 60}) + "\n")
        with self.assertRaises(AssertionError):
            w.wait_for(lambda c: c.get("event") == "tool", "a new tool call", timeout=0.5, since=time.time())


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------------------------------- W9.10: umwayi goal

from tests.goal import wholesupport as gw  # noqa: E402

SENTINEL = "SENTINEL-HELPER-OUTPUT-never-in-a-record"


class GoalWholeSystemTests(unittest.TestCase):
    """W9.10 (W9.R21.4): the owner's day through `umwayi goal`, then one fault scenario for each pitfall of the design.

    Every step is a real child process. The owner's commands run as `python -m umwayi goal ...`; below them the
    supervisor starts `python -m umwayi agent run NAME - --workdir PATH`, which starts a fake `kiro-cli`. Git is real
    (the system `git`, a temporary repo with a local main). Three commands need a terminal and get a pseudo terminal.
    After every scenario: `logbook verify` and `budget status` are ok, nothing a scenario started is still alive, only
    the codes each command may give appeared (0, 2, 3 or 64 for `goal`), and no planted word is in the logbook.
    """

    def setUp(self):
        self.w = gw.GoalWorld()
        self.addCleanup(self.w.cleanup)

    # ---- helpers

    def goal_cmd(self, *args, code=None, **kw):
        r = self.w.u("goal", *args, **kw)
        if code is not None:
            self.assertEqual(r.returncode, code, f"umwayi goal {' '.join(args)}\n{r.stdout}\n{r.stderr}")
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        return r

    def start(self, tasks=1, size=40):
        self.w.script(guide=[gw.plan_line(tasks, size)])
        r = self.goal_cmd("start", gw.GOAL_TEXT, "--guide", "kiro-guide", "--plan-budget-uu", "20", code=0)
        goal = self.w.goals()[-1]
        self.assertIn(f"Goal {goal} has a plan that waits for you.", r.stdout)
        return goal

    def approve(self, goal, code=0, **kw):
        a = ["--builder", "kiro-build", "--tester", "kiro-test", "--model", "sonnet", "--effort", "high",
             "--task-budget-uu", "30", "--goal-budget-uu", "100"]
        for key, val in kw.items():
            a[a.index("--" + key.replace("_", "-")) + 1] = str(val)
        rc, out = self.w.tty("goal", "approve", goal, *a)
        self.assertEqual(rc, code, out)
        return out

    def approved(self, tasks=1, **kw):
        goal = self.start(tasks)
        self.approve(goal, **kw)
        return goal

    def good(self, goal, task, n, builder_extra=(), tester=("pass",), check="accept"):
        self.w.script(builder=gw.builder_steps(goal, task, n, extra=builder_extra), tester=gw.tester_steps(tester),
                      check=gw.check_steps(check))

    def roles(self):
        return [d["role"] for d in self.w.starts()]

    def merge(self, goal, task="T-01"):
        self.w.git("merge", "-q", "--no-ff", "-m", "merge", f"umwayi/{goal.lower()}-{task.lower()}")

    def wait_for_role(self, role, timeout=120):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if role in self.roles():
                return
            time.sleep(0.2)
        self.fail(f"the {role} never started: {self.w.starts()}")

    def end_checks(self, verify=0, budget=0):
        """After every scenario (S.R1.5, W9.R21.4)."""
        w = self.w
        r = w.u("logbook", "verify")
        self.assertEqual(r.returncode, verify, r.stdout + r.stderr)
        self.assertEqual(w.u("budget", "status").returncode, budget)
        w.wait_quiet()
        self.assertEqual(w.alive(), [], "a process the scenario started is still alive")
        bad = [(c, rc) for c, rc in w.seen if rc not in gw.GOAL_CODES]
        self.assertEqual(bad, [], "a goal command gave a code it may not give")
        for word in (gw.SECRET, SENTINEL):
            self.assertNotIn(word, w.logbook_text())

    # ---- the owner's day (W9.R21.4)

    def test_01_the_owners_day_from_a_goal_to_every_task_merged(self):
        w = self.w
        goal = self.start(tasks=2)
        r = self.goal_cmd("status", code=0)
        self.assertIn(f"Goal {goal} has a plan that waits for you.", r.stdout)
        self.assertIn("Waiting for you", r.stdout.splitlines()[0])
        self.goal_cmd("show", goal, code=0)
        self.approve(goal)
        self.assertEqual([w.state(goal, t)[0] for t in ("T-01", "T-02")], ["queued", "queued"])
        self.assertEqual(self.roles(), ["guide"])  # approving started nothing
        # the first task, run to in review
        self.good(goal, "T-01", 1, builder_extra=[{"print": SENTINEL}])
        r = self.goal_cmd("run", goal, code=0)
        self.assertEqual(w.state(goal), ("in review", "checked"))
        self.assertEqual(self.roles(), ["guide", "builder", "tester", "check"])
        self.assertIn(f"# Report of goal {goal}", r.stdout)  # run prints the report at its end
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)
        self.assertEqual(w.state(goal, "T-02"), ("queued", "approved"))  # one task per run
        # a run before the owner merges does nothing new
        self.goal_cmd("run", goal, code=0)
        self.assertEqual(len(self.roles()), 4)
        # the owner merges; the next run observes it, cleans up, and runs the second task from the new main
        self.merge(goal)
        main_tip = w.git("rev-parse", "main")
        self.good(goal, "T-02", 2)
        self.goal_cmd("run", goal, code=0)
        self.assertEqual(w.state(goal), ("merged", "observed"))
        self.assertEqual(w.state(goal, "T-02"), ("in review", "checked"))
        self.assertEqual(w.task(goal, "T-02")["base"], main_tip)
        self.assertFalse((Path(str(w.root) + "-worktrees") / f"{goal.lower()}-t-01").exists())
        self.assertIn(f"umwayi/{goal.lower()}-t-01", w.git("branch", "--list"))
        self.assertTrue((Path(str(w.root) + "-worktrees") / f"{goal.lower()}-t-02" / "umwayi" / "piece1.py").exists())
        self.merge(goal, "T-02")
        r = self.goal_cmd("run", goal, code=0)
        self.assertEqual(w.state(goal, "T-02"), ("merged", "observed"))
        r = self.goal_cmd("status", goal, code=0)
        self.assertIn("2 of 2 tasks merged", r.stdout)
        r = self.goal_cmd("report", goal, code=0)
        self.assertIn("## T-02: merged (observed)", r.stdout)
        self.assertTrue((w.root / ".umwayi" / "goals" / goal / "report.md").exists())
        self.assertEqual(w.git("status", "--porcelain", "--untracked-files=no"), "")  # the owner's copy was never touched
        self.assertEqual(len(self.roles()), 7)
        self.end_checks()

    def test_02_the_owner_commands_need_a_terminal_and_change_nothing_without_one(self):
        w = self.w
        goal = self.start()
        before = w.snapshot()
        for args in (("approve", goal, "--builder", "kiro-build", "--tester", "kiro-test", "--model", "m", "--effort", "high",
                      "--task-budget-uu", "30", "--goal-budget-uu", "100"),
                     ("answer", goal, "T-01", "yes"), ("merged", goal, "T-01")):
            with self.subTest(command=args[0]):
                r = self.goal_cmd(*args, code=2)
                self.assertIn("needs a terminal", r.stderr)
        self.assertEqual(w.snapshot(), before)
        self.assertEqual(self.roles(), ["guide"])
        self.end_checks()

    def test_03_with_no_rule_for_goal_start_nothing_starts_and_the_owner_is_asked(self):
        w = self.w
        goal = self.approved()
        (w.root / "rules.yaml").write_text(gw.RULES.replace("goal_start", "goal_other"), encoding="utf-8")
        self.good(goal, "T-01", 1)
        r = self.goal_cmd("run", goal, code=3)
        self.assertEqual(self.roles(), ["guide"])
        self.assertEqual(w.state(goal), ("needs owner", "ask"))
        self.assertIn(f"Answer with: umwayi goal answer {goal} T-01 yes", r.stdout)
        q = w.u("queue", "list", "--status", "open")
        self.assertIn(f"Goal {goal} task T-01 needs you (ask)", q.stdout)
        self.end_checks()

    # ---- pitfall 1: an approval that waits silently

    def test_10_an_approval_nobody_answers_is_visible_and_then_denied_by_the_next_command(self):
        w = self.w
        goal = self.approved()
        (w.root / "rules.yaml").write_text(gw.RULES.replace("goal_start", "goal_other"), encoding="utf-8")
        self.good(goal, "T-01", 1)
        self.goal_cmd("run", goal, code=3)
        # visible in four places: the entry, the queue row, status, the terminal of run
        self.assertIn("Approval requested: task T-01", w.logbook_text())
        self.assertIn(f"Goal {goal} task T-01 needs you", w.u("queue", "list").stdout)
        r = self.goal_cmd("status", extra={"UMWAYI_TEST_TIME_OFFSET": str(3 * 3600)}, code=0)
        # 3 h plus the real seconds since the ask (0 or more): the time left is 21 h less those seconds, shown as 21 or 20 h
        self.assertRegex(r.stdout, rf"Goal {goal} task T-01 needs you \(ask\)\. Asked 3 h ago, denied in 2[01] h\.")
        # an answer 25 hours later is refused, and the denial is written once, though no process ran in between
        late = {"UMWAYI_TEST_TIME_OFFSET": str(25 * 3600)}
        rc, out = w.tty("goal", "answer", goal, "T-01", "yes", extra=late)
        self.assertEqual(rc, 2, out)
        self.assertIn("timed out", out)
        rc, out = w.tty("goal", "answer", goal, "T-01", "yes", extra=late)
        self.assertEqual(rc, 2, out)
        self.assertEqual(w.state(goal), ("stopped", "unanswered"))
        self.assertEqual(w.logbook_text().count("Approval denied"), 1)
        self.assertEqual(self.roles(), ["guide"])
        self.end_checks()

    # ---- pitfall 2: a stalled or looping builder

    def test_11_a_silent_builder_is_stopped_as_stalled_and_nothing_is_left_running(self):
        w = self.w
        goal = self.approved()
        w.script(builder=[{"silent": 120}])
        self.goal_cmd("run", goal, code=2, extra={"UMWAYI_TEST_STALL_SECONDS": "5"})
        self.assertEqual(w.state(goal), ("failed", "stalled"))
        self.assertEqual(self.roles(), ["guide", "builder"])  # no tester after a stalled builder
        self.end_checks()

    def test_12_the_same_error_twice_is_looping(self):
        w = self.w
        goal = self.approved()
        w.script(builder=[{"error": "Error: could not open file 12"}, {"error": "Error: could not open file 99"},
                          {"silent": 120}])
        self.goal_cmd("run", goal, code=2)
        self.assertEqual(w.state(goal), ("failed", "looping"))
        self.end_checks()

    # ---- pitfall 3: a status that shows only "connected"

    def test_13_status_while_a_builder_works_shows_the_last_real_event_and_none_of_its_words(self):
        w = self.w
        goal = self.approved()
        w.script(builder=[{"print": SENTINEL}, {"error": f"Error: {SENTINEL} 77"}, {"change": "README.md", "every": 1, "times": 6},
                          {"exit": 0}])
        p = w.bg("goal", "run", goal)
        self.wait_for_role("builder")
        time.sleep(3)
        r = self.goal_cmd("status", goal, code=0)
        text = r.stdout
        self.assertIn("Task T-01  running", text)
        self.assertIn("Last event:", text)
        self.assertLess(text.index("Last event:"), text.index("Supervisor:"))  # the process line is never alone
        self.assertIn("Supervisor: alive", text)
        self.assertNotIn(SENTINEL, text)
        rc, _out, _err = w.finish(p)
        self.assertEqual(rc, 2)  # the builder made no commit: failed (outcome)
        self.assertEqual(w.state(goal), ("failed", "outcome"))
        self.end_checks()

    # ---- pitfall 4: one malformed log line stalling the log

    def test_14_a_bad_line_in_an_event_log_is_skipped_counted_and_never_stalls_status_or_report(self):
        w = self.w
        goal = self.approved()
        self.good(goal, "T-01", 1)
        self.goal_cmd("run", goal, code=0)
        events = w.root / ".umwayi" / "goals" / goal / "T-01.events.jsonl"
        with open(events, "ab") as f:
            f.write(b"this is not an event\n\xff\xfe\x00 binary noise\n")
        r = self.goal_cmd("status", goal, code=0)
        self.assertIn("Skipped log lines: 2", r.stdout)
        r = self.goal_cmd("report", goal, code=0)
        self.assertIn("Skipped log lines: 2", r.stdout)
        self.assertEqual(w.state(goal), ("in review", "checked"))
        self.end_checks()

    # ---- pitfall 5: a failed log write that lets work continue

    def test_15_a_goal_that_cannot_write_its_event_log_starts_no_helper(self):
        w = self.w
        goal = self.approved()
        os.mkdir(w.root / ".umwayi" / "goals" / goal / "T-01.events.jsonl")  # a folder where the log must be
        self.good(goal, "T-01", 1)
        self.goal_cmd("run", goal, code=2)
        self.assertEqual(self.roles(), ["guide"])  # the builder never got its prompt
        self.assertNotIn(w.state(goal), (("in review", "checked"), ("merged", "observed")))
        self.end_checks()

    def test_16_a_hand_edited_logbook_stops_every_goal_command_that_writes(self):
        w = self.w
        goal = self.approved()
        with open(w.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("\nedited by hand\n")
        self.good(goal, "T-01", 1)
        before = w.snapshot()
        self.goal_cmd("run", goal, code=2)
        self.assertEqual(self.roles(), ["guide"])
        self.goal_cmd("stop", goal, code=2)
        self.assertEqual(w.snapshot(), before, "a refused command wrote something")
        self.goal_cmd("status", code=0)  # reading still works and says why
        v = w.u("logbook", "verify").returncode
        self.assertIn(v, (1, 2))  # the edit is found, never passed
        self.end_checks(verify=v, budget=2)  # and the budget ledger refuses a logbook it cannot trust

    # ---- pitfall 6: parallel edits of shared files

    def test_17_a_task_that_edits_a_shared_docs_file_fails_on_scope_and_the_owners_copy_is_untouched(self):
        w = self.w
        goal = self.approved()
        w.script(builder=gw.builder_steps(goal, "T-01", 1, files={"umwayi/piece1.py": "x = 1\n", "docs/status-log.md": "edited\n"}),
                 tester=gw.tester_steps(), check=gw.check_steps())
        self.goal_cmd("run", goal, code=2)
        self.assertEqual(w.state(goal), ("failed", "scope"))
        self.assertEqual(self.roles(), ["guide", "builder"])
        self.assertEqual((w.root / "docs" / "status-log.md").read_text(), "shared\n")

        self.end_checks()

    # ---- pitfall 7: cost growing with autonomy

    def test_18_a_task_budget_that_cannot_pay_for_the_next_run_stops_it_and_total_spend_stays_inside_the_goal(self):
        w = self.w
        goal = self.start()
        self.approve(goal, task_budget_uu=15, goal_budget_uu=40)
        self.good(goal, "T-01", 1)
        self.goal_cmd("run", goal, code=3)  # the tester's cap is 5 UU and a Kiro run is declared at 10: refused
        self.assertEqual(w.state(goal), ("needs owner", "ask"))
        self.assertEqual(self.roles(), ["guide", "builder"])
        led = w.u("budget", "status").stdout
        self.assertIn("20 UU", led)  # the plan and the builder, 10 each, and nothing more
        self.assertEqual(w.task(goal)["spent_uu"], 10)
        self.end_checks()

    # ---- the kill switch and stop (W9.R16)

    def test_20_the_kill_switch_stops_a_running_builder_and_nothing_restarts_after_it(self):
        w = self.w
        goal = self.approved(tasks=2)
        w.script(builder=[{"silent": 120}])
        p = w.bg("goal", "run", goal)
        self.wait_for_role("builder")
        t0 = time.monotonic()
        self.assertEqual(w.u("kill", "on").returncode, 0)
        rc, _o, _e = w.finish(p, timeout=60)
        self.assertEqual(rc, 2)
        self.assertLess(time.monotonic() - t0, 40)  # within a second, the stop grace and room for a slow machine
        self.assertEqual(w.state(goal), ("stopped", "kill"))
        self.assertEqual(w.state(goal, "T-02")[0], "queued")  # queued tasks stay queued
        self.assertEqual(w.u("kill", "off").returncode, 0)
        n = len(self.roles())
        self.goal_cmd("run", goal, code=2)  # a stopped goal does not run again by itself
        self.assertEqual(len(self.roles()), n)
        self.end_checks()

    def test_21_goal_stop_ends_a_running_goal_and_its_queued_tasks(self):
        w = self.w
        goal = self.approved(tasks=2)
        w.script(builder=[{"silent": 120}])
        p = w.bg("goal", "run", goal)
        self.wait_for_role("builder")
        self.goal_cmd("stop", goal, code=0)  # open to everyone: no terminal
        rc, _o, _e = w.finish(p, timeout=60)
        self.assertEqual(rc, 2)
        self.assertEqual(w.state(goal), ("stopped", "owner"))
        self.assertEqual(w.state(goal, "T-02"), ("stopped", "owner"))
        self.goal_cmd("stop", goal, code=0)  # idempotent
        self.end_checks()

    # ---- the tester, the guide and the owner's merge

    def test_30_a_failed_check_fails_the_task_and_an_unclear_one_waits_for_the_owner_who_says_no(self):
        w = self.w
        goal = self.approved(tasks=2)
        self.good(goal, "T-01", 1, tester=("fail",))
        self.goal_cmd("run", goal, code=2)
        self.assertEqual(w.state(goal), ("failed", "tests"))
        self.assertEqual(self.roles(), ["guide", "builder", "tester"])  # the guide's check never ran
        w2 = self.approved()  # a second goal in the same root, its own worktree
        self.good(w2, "T-01", 1, tester=("unclear",))
        self.goal_cmd("run", w2, code=3)
        self.assertEqual(w.state(w2), ("needs owner", "unclear"))
        rc, out = w.tty("goal", "answer", w2, "T-01", "no")
        self.assertEqual(rc, 0, out)
        self.assertEqual(w.state(w2), ("stopped", "owner"))
        self.end_checks()

    def test_31_a_squash_merge_is_declared_with_its_commit_and_the_worktree_goes(self):
        w = self.w
        goal = self.approved()
        self.good(goal, "T-01", 1)
        self.goal_cmd("run", goal, code=0)
        w.git("merge", "-q", "--squash", f"umwayi/{goal.lower()}-t-01")
        w.git("commit", "-q", "-m", "squashed")
        sha = w.git("rev-parse", "HEAD")
        self.goal_cmd("run", goal, code=0)  # the check cannot see a squash
        self.assertEqual(w.state(goal), ("in review", "checked"))
        rc, out = w.tty("goal", "merged", goal, "T-01", "--commit", "a" * 40)
        self.assertEqual(rc, 2, out)  # not a commit
        rc, out = w.tty("goal", "merged", goal, "T-01", "--commit", sha)
        self.assertEqual(rc, 0, out)
        self.assertEqual(w.state(goal), ("merged", "declared"))
        self.assertFalse((Path(str(w.root) + "-worktrees") / f"{goal.lower()}-t-01").exists())
        self.end_checks()


from pathlib import Path  # noqa: E402
