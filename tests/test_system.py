"""Whole-system test: the umwayi command run as real processes in a fresh folder.

Every call here is `python -m umwayi --root ROOT ...` in its own process (the same
main() as the `umwayi` script). Faults are made by editing files, or, for an
unexpected crash, by a sitecustomize.py that patches one function in the child
process only.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "umwayi"
D1, D2 = "2026-11-07", "2026-11-08"
SECRET = "sk-live-SYSTEM-TEST-SECRET"

# Loaded in the child at start up when UMWAYI_FAULT is set: "module:function:effect".
SITECUSTOMIZE = r'''
import os
fault = os.environ.get("UMWAYI_FAULT")
if fault:
    import importlib, time
    module, name, effect = fault.split(":")
    mod = importlib.import_module(module)
    real = getattr(mod, name)
    def patched(*a, **k):
        if effect == "crash":
            raise RuntimeError(os.environ.get("UMWAYI_FAULT_TEXT", "injected"))
        if effect == "slow":
            if not getattr(patched, "slept", False):
                patched.slept = True
                time.sleep(1.5)
            return real(*a, **k)
        if effect == "record":
            open(os.environ["UMWAYI_FAULT_MARK"], "a").write("called\n")
            return real(*a, **k)
        raise SystemExit("unknown effect")
    setattr(mod, name, patched)
'''


class SystemBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-system-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "home"
        self.root.mkdir()
        # the starter files shipped in the repo, unchanged
        for name in ("rules.yaml", "umwayi.json", "jobs.yaml"):
            shutil.copy(REPO / name, self.root / name)
        shutil.copytree(REPO / "workflows", self.root / "workflows")
        shutil.copytree(REPO / "articles", self.root / "articles")
        self.site = Path(self._tmp.name) / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"

    def u(self, *args, fault=None, extra_env=None, timeout=60):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(self.site), str(REPO)]))
        env.pop("UMWAYI_FAULT", None)
        if fault:
            env["UMWAYI_FAULT"] = fault
            env["UMWAYI_FAULT_TEXT"] = SECRET
        env.update(extra_env or {})
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env, cwd=self.root, timeout=timeout)

    def expect(self, args, code, contains=(), lacks=(), **kw):
        r = self.u(*args, **kw)
        text = r.stdout + r.stderr
        self.assertEqual(r.returncode, code, f"umwayi {' '.join(args)}\n{text}")
        for c in ([contains] if isinstance(contains, str) else contains):
            self.assertIn(c, text, f"umwayi {' '.join(args)}")
        for c in ([lacks] if isinstance(lacks, str) else lacks):
            self.assertNotIn(c, text, f"umwayi {' '.join(args)}")
        self.assertNotIn("Traceback", text)
        return r

    def drafts(self):
        d = self.root / "drafts"
        return sorted(os.listdir(d)) if d.exists() else []

    def sources(self):
        return [line[len("- Source: "):] for line in self.log.read_text(encoding="utf-8").splitlines()
                if line.startswith("- Source: ")]

    def queue_rows(self):
        return [line for line in (self.root / "queue.md").read_text().splitlines() if line.startswith("| Q-")]


# ================================================================ the scripted run


class ScriptedRunTests(SystemBase):
    def test_one_scripted_run(self):
        # --- memory: there is no "memory add" command; memory is plain files the owner writes
        (self.root / "memory" / "projects").mkdir(parents=True)
        (self.root / "memory" / "journal").mkdir()
        (self.root / "memory" / "private").mkdir()
        (self.root / "memory" / "master.md").write_text("I am the owner. AI helpers draft only.\n")
        (self.root / "memory" / "projects" / "umwayi.md").write_text("Project umwayi-os: layers 1 to 8.\n")
        (self.root / "memory" / "journal" / "2026-11-07.md").write_text("Built the system test.\n")
        # private paths in the repo umwayi.json: memory/private and memory/journal/*-private.md
        (self.root / "memory" / "journal" / "2026-11-07-private.md").write_text(f"card {SECRET}\n")
        (self.root / "memory" / "private" / "bank.md").write_text(f"card {SECRET}\n")
        r = self.expect(["memory", "bundle"], 0, ["I am the owner.", "Project umwayi-os", "Built the system test."],
                        lacks=[SECRET, "bank.md", "-private.md"])
        self.assertIn("private files left out: 1", r.stdout)

        # --- queue
        self.expect(["queue", "add", "--kind", "task", "Write the week 45 post", "--date", D1], 0, "Added Q-0001")

        # --- check: Yes, No, Ask me first for an action no rule lists
        self.expect(["check", '{"type": "read_memory"}', "--date", D1], 0, ["Yes", "Rule: read-memory"])
        self.expect(["check", json.dumps({"type": "payment", "card": SECRET}), "--date", D1], 2,
                    ["No", "Rule: no-money"], lacks=SECRET)
        self.expect(["check", '{"type": "launch_rocket"}', "--date", D1], 3, ["Ask me first", "No rule matches"])

        # --- a job from the allow list
        self.expect(["run", "jobs.yaml", "--job", "open-queue", "--date", D1], 0, ["Job open-queue ran.", "Q-0001"])

        # --- AI helpers
        self.expect(["steward", "--date", D1], 0, "Wrote drafts/steward-0001.md")
        self.assertIn("Q-0001", (self.root / "drafts" / "steward-0001.md").read_text())
        self.expect(["social", "draft", "articles/example.md", "--date", D1], 0,
                    ["Wrote drafts/post-linkedin-0001.md", "Wrote drafts/post-mastodon-0001.md", "Nothing was posted."])
        channels = json.loads((self.root / "umwayi.json").read_text())["social_channels"]
        self.assertEqual(sorted(d for d in self.drafts() if d.startswith("post-")),
                         sorted(f"post-{c}-0001.md" for c in channels))

        # --- the content loop stops at approve with exit 3 and adds a queue item
        self.expect(["workflow", "validate", "content-loop"], 0, "ok: workflow content-loop has 4 steps")
        self.expect(["workflow", "run", "content-loop", "--date", D1], 3,
                    ["Step 4 approve (approve): added queue item Q-0002 (decision)", "The approve step never approves."])
        self.assertIn("| Q-0002 | decision | Workflow content-loop waits for the owner:", self.queue_rows()[1])
        self.assertIn("| open |", self.queue_rows()[1])

        # --- publish-draft: refused without approval, works with --approved-by
        self.expect(["publish-draft", "drafts/post-linkedin-0001.md", "--date", D1], 3,
                    ["Ask me first", "Rule: publish-ask", "Nothing was copied."])
        self.assertFalse((self.root / "outbox").exists())
        self.expect(["publish-draft", "drafts/post-linkedin-0001.md", "--approved-by", "The owner", "--date", D1], 0,
                    ["Copied drafts/post-linkedin-0001.md to outbox/post-linkedin-0001.txt", "Post it by hand."])
        self.assertEqual((self.root / "outbox" / "post-linkedin-0001.txt").read_bytes(),
                         (self.root / "drafts" / "post-linkedin-0001.md").read_bytes())

        # --- kill on stops helpers, jobs and workflows with exit 3
        self.expect(["kill", "on", "--reason", "system test", "--date", D1], 0, "The kill switch is on.")
        self.expect(["kill", "status"], 3, "on")
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.name not in ("LOGBOOK.md", "logbook.sha256"))
        for args in (["steward"], ["social", "draft", "articles/example.md"], ["run", "jobs.yaml", "--job", "open-queue"],
                     ["workflow", "run", "content-loop"]):
            self.expect([*args, "--date", D1], 3, ["Ask me first", "The kill switch is on"])
        after = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.name not in ("LOGBOOK.md", "logbook.sha256"))
        self.assertEqual(before, after, "a stopped run changed something")

        # --- kill off lets them run again
        self.expect(["kill", "off", "--date", D2], 0, "The kill switch is off.")
        # the content loop already wrote steward-0002 and post-*-0002, so these are 0003
        self.expect(["steward", "--date", D2], 0, "Wrote drafts/steward-0003.md")
        self.expect(["social", "draft", "articles/example.md", "--date", D2], 0, "Wrote drafts/post-linkedin-0003.md")
        self.expect(["run", "jobs.yaml", "--job", "open-queue", "--date", D2], 0, "Job open-queue ran.")
        self.expect(["workflow", "run", "content-loop", "--date", D2], 3, "still waits for the owner")  # Q-0002 is open
        self.expect(["queue", "answer", "Q-0002", "--answer", "Seen, I publish by hand", "--revisit-if", "none", "--date", D2], 0)
        self.expect(["workflow", "run", "content-loop", "--date", D2], 3, "added queue item Q-0003 (decision)",
                    lacks="kill switch")

        # --- the logbook is whole, with the expected entries
        expected = (
            ["umwayi queue add"]
            + ["umwayi check"] * 3
            + ["umwayi run"]
            + ["umwayi steward"] * 3
            + ["umwayi social"] * 3
            + ["umwayi workflow"] * 3 + ["umwayi queue add", "umwayi workflow"]
            + ["umwayi publish-draft"] * 2
            + ["umwayi kill"]
            + ["umwayi steward", "umwayi social", "umwayi run", "umwayi workflow"]  # the four kill stops
            + ["umwayi kill"]
            + ["umwayi steward"] * 3 + ["umwayi social"] * 3 + ["umwayi run"]
            + ["umwayi workflow"]  # stopped: Q-0002 still waits
            + ["umwayi queue answer"]
            + ["umwayi workflow"] * 3 + ["umwayi queue add", "umwayi workflow"]
        )
        self.assertEqual(self.sources(), expected)
        self.expect(["logbook", "verify"], 0, f"ok: {len(expected)} entries, the format is valid and the hash matches")
        self.assertEqual(len(expected), 38)
        self.assertNotIn(SECRET, self.log.read_text())
        self.expect(["archive", "verify"], 1, "no archive folder")  # nothing was archived in this run


# ================================================================== one run at a time


class OneRunAtATimeTests(SystemBase):
    def test_two_steward_runs_started_together_write_once(self):
        (self.root / "queue.md").write_text(
            "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n| Q-0001 | task | One | open | | | |\n")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(self.site), str(REPO)]),
                   UMWAYI_FAULT="umwayi.logbook:read_checked:slow")  # hold the run a moment so the two overlap
        start = Path(self._tmp.name) / "go"
        wrapper = ("import os, sys, time, runpy\n"
                   f"while not os.path.exists({str(start)!r}): time.sleep(0.002)\n"
                   "sys.argv = ['umwayi'] + sys.argv[1:]\n"
                   "runpy.run_module('umwayi', run_name='__main__')\n")
        procs = [subprocess.Popen([sys.executable, "-c", wrapper, "--root", str(self.root), "steward", "--date", D1],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env) for _ in range(2)]
        time.sleep(0.8)  # both are up and waiting
        start.touch()
        results = []
        for p in procs:
            out, err = p.communicate(timeout=60)  # also closes the pipes
            results.append((p.returncode, out, err))
        codes = sorted(c for c, _, _ in results)
        self.assertEqual(codes, [0, 3], results)
        self.assertEqual(self.drafts(), ["steward-0001.md"], results)
        busy = [out for c, out, _ in results if c == 3]
        self.assertIn("holds the run lock", busy[0])
        self.expect(["logbook", "verify"], 0, "ok: 4 entries")  # 3 steps and 1 refused run


# ======================================================================= faults


class FaultTests(SystemBase):
    def seed(self):
        self.expect(["queue", "add", "--kind", "task", "One", "--date", D1], 0)
        self.expect(["check", '{"type": "read_memory"}', "--date", D1], 0)

    def test_editing_the_logbook_makes_verify_fail(self):
        self.seed()
        self.expect(["logbook", "verify"], 0, "ok: 2 entries")
        self.log.write_text(self.log.read_text().replace("- Added: Q-0001 (task) as open: One", "- Added: Q-0001 (task) as open: Two"))
        self.expect(["logbook", "verify"], 1, "does not match its recorded hash")
        self.expect(["queue", "add", "--kind", "task", "x", "--date", D1], 1, "does not match its recorded hash")
        self.expect(["check", '{"type": "read_memory"}', "--date", D1], 3, "The logbook could not be written")
        self.expect(["check", '{"type": "payment"}', "--date", D1], 2, "The logbook could not be written")
        lines = self.log.read_text().splitlines()
        self.log.write_text("\n".join(l for l in lines if not l.startswith("- Checked:")) + "\n")
        r = self.expect(["logbook", "verify"], 1, "problem: line")
        self.assertNotIn("Q-0001", r.stdout)

    def test_a_broken_rules_file_gives_ask_me_first(self):
        (self.root / "rules.yaml").write_text("rules:\n  - id: broken\n    verdict: maybe\n")
        self.expect(["check", '{"type": "read_memory"}', "--date", D1], 3, ["Ask me first", "Rules could not be loaded"])
        self.expect(["check", '{"type": "payment"}', "--date", D1], 3, "Ask me first")
        for args in (["steward"], ["social", "draft", "articles/example.md"], ["run", "jobs.yaml", "--job", "open-queue"],
                     ["workflow", "run", "content-loop"]):
            self.expect([*args, "--date", D1], 3, "Ask me first")
        self.assertEqual(self.drafts(), [])
        (self.root / "rules.yaml").unlink()
        self.expect(["check", '{"type": "read_memory"}', "--date", D1], 3, "Ask me first")

    def test_an_unknown_action_gives_ask_me_first(self):
        # (a list field matches if any item matches, so {"type": ["read_memory"]} is not unknown: layer 2 design)
        for action in ('{"type": "launch_rocket"}', '{"type": "read_memory2"}', '{}', '{"kind": "read_memory"}',
                       '{"type": ["launch_rocket"], "x": 1}', 'not json', '[]', '{"a": 1, "a": 2}'):
            with self.subTest(action=action):
                self.expect(["check", action, "--date", D1], 3, "Ask me first")
        self.expect(["logbook", "verify"], 0, "ok: 8 entries")

    def test_a_bad_config_or_workflow_file_gives_64(self):
        (self.root / "notes.md").write_text("a b\nc d\n")
        (self.root / "drafts").mkdir()
        (self.root / "drafts" / "a.md").write_text("a draft\n")
        for bad in ("{broken", '{"memory_dir": "memory"}', '{"memory_dir": "memory", "private_paths": [], "x": 1}'):
            (self.root / "umwayi.json").write_text(bad)
            for args in (["memory", "bundle"], ["social", "draft", "articles/example.md", "--date", D1],
                         ["publish-draft", "drafts/a.md", "--approved-by", "me", "--date", D1],
                         ["archive", "move", "notes.md", "--lines", "1-1", "--reason", "r", "--date", D1],
                         ["workflow", "run", "content-loop", "--date", D1]):
                with self.subTest(config=bad, command=args[0]):
                    self.expect(args, 64)
            self.expect(["workflow", "validate", "content-loop"], 64, "problem: line 20")
        shutil.copy(REPO / "umwayi.json", self.root / "umwayi.json")
        (self.root / "workflows" / "bad.yaml").write_text("name: bad\nsteps:\n  - name: a\n    command: shell\n")
        self.expect(["workflow", "validate", "bad"], 64, "problem: line 4: step 1: the command is not on the allow list")
        self.expect(["workflow", "run", "bad", "--date", D1], 64, "umwayi workflow validate bad")
        self.expect(["workflow", "run", "nope", "--date", D1], 64, "was not found")
        (self.root / "jobs.yaml").write_text("jobs: [\n")
        self.expect(["run", "jobs.yaml", "--job", "open-queue", "--date", D1], 64)
        self.assertFalse(self.log.exists())

    # every command, and a function deep inside it that is made to crash
    CRASHES = [
        (["memory", "bundle"], "umwayi.memory:is_private"),
        (["queue", "list"], "umwayi.taskqueue:parse"),
        (["queue", "add", "--kind", "task", "x", "--date", D1], "umwayi.taskqueue:parse"),
        (["queue", "answer", "Q-0001", "--answer", "y", "--date", D1], "umwayi.taskqueue:parse"),
        (["queue", "close", "Q-0001", "--date", D1], "umwayi.taskqueue:parse"),
        (["queue", "migrate", "--date", D1], "umwayi.taskqueue:parse"),
        (["check", '{"type": "read_memory"}', "--date", D1], "umwayi.rules:load_rules"),
        (["check", '{"type": "read_memory"}', "--date", D1], "umwayi.rules:decide"),
        (["check", '{"type": "read_memory"}', "--date", D1], "umwayi.logbook:render"),
        (["archive", "move", "notes.md", "--lines", "1-1", "--reason", "r", "--date", D1], "umwayi.archive:sha256_hex"),
        (["archive", "verify"], "umwayi.archive:parse_index"),
        (["logbook", "verify"], "umwayi.logbook:parse"),
        (["logbook", "seal", "--by", "me", "--date", D1], "umwayi.logbook:_record_state"),
        (["run", "jobs.yaml", "--job", "open-queue", "--date", D1], "umwayi.jobs:parse_jobs"),
        (["run", "jobs.yaml", "--job", "open-queue", "--date", D1], "umwayi.taskqueue:list_rows"),
        (["report", "--since", "2026-11-01", "--date", D1], "umwayi.report:read_git_log"),
        (["publish-draft", "drafts/steward-0001.md", "--approved-by", "me", "--date", D1], "umwayi.publish:_read_draft"),
        (["steward", "--date", D1], "umwayi.helpers.steward:proposal"),
        (["steward", "--date", D1], "umwayi.taskqueue:list_rows"),  # inside a step's work
        (["social", "draft", "articles/example.md", "--date", D1], "umwayi.helpers.social:build_post"),  # inside a step
        (["workflow", "validate", "content-loop"], "umwayi.workflow:_line_map"),
        (["workflow", "run", "content-loop", "--date", D1], "umwayi.workflow:_line_map"),
        (["workflow", "run", "content-loop", "--date", D1], "umwayi.helpers.steward:proposal"),  # inside a step
        (["kill", "on", "--date", D1], "umwayi.kill:state"),
        # a crash while writing the logbook entry, in every command that writes one
        (["queue", "add", "--kind", "task", "x", "--date", D1], "umwayi.logbook:render"),
        (["archive", "move", "notes.md", "--lines", "1-1", "--reason", "r", "--date", D1], "umwayi.logbook:render"),
        (["publish-draft", "drafts/steward-0001.md", "--approved-by", "me", "--date", D1], "umwayi.logbook:render"),
        (["run", "jobs.yaml", "--job", "open-queue", "--date", D1], "umwayi.logbook:render"),
        (["steward", "--date", D1], "umwayi.logbook:render"),
        (["workflow", "run", "content-loop", "--date", D1], "umwayi.logbook:render"),
        (["kill", "on", "--date", D1], "umwayi.logbook:render"),
        (["kill", "off", "--date", D1], "umwayi.kill:state"),
        (["kill", "status"], "umwayi.kill:state"),
        (["view", "snapshot", "--date", D1], "umwayi.logbook:read_checked_chain"),
        (["view", "snapshot", "--date", D1], "umwayi.fsutil:atomic_write"),
        (["view", "snapshot", "--date", D1], "umwayi.logbook:render"),  # while writing its logbook entry
    ]

    def test_an_unexpected_error_in_every_command_exits_2_never_1(self):
        (self.root / "notes.md").write_text("a b\nc d\n")
        (self.root / "memory").mkdir()
        (self.root / "memory" / "master.md").write_text("me\n")
        self.expect(["queue", "add", "--kind", "task", "One", "--date", D1], 0)
        self.expect(["steward", "--date", D1], 0)
        self.expect(["archive", "move", "notes.md", "--lines", "2-2", "--reason", "r", "--date", D1], 0)
        for args, target in self.CRASHES:
            with self.subTest(command=" ".join(args[:2]), crash=target):
                r = self.u(*args, fault=f"{target}:crash")
                text = r.stdout + r.stderr
                self.assertEqual(r.returncode, 2, text)
                self.assertIn("stopped by an unexpected error (RuntimeError)", r.stderr)
                self.assertNotIn(SECRET, text)
                self.assertNotIn("Traceback", text)
        self.expect(["logbook", "verify"], 0)  # crashes left the logbook whole
        outbox = self.root / "outbox"
        self.assertEqual(sorted(os.listdir(outbox)) if outbox.exists() else [], [])  # the publish crash removed its copy

    def test_corrupt_state_files_never_give_1_for_an_unexpected_error(self):
        """Real corrupt files, every command: a clear refusal (1), Ask me first (3), 64, or an unexpected error (2)."""
        commands = [c for c, _ in self.CRASHES if c[0] not in ("report",)]
        unique = []
        for c in commands:
            if c not in unique:
                unique.append(c)
        corruptions = {
            "LOGBOOK.md binary": lambda: self.log.write_bytes(b"\xff\xfe\x00garbage"),
            "logbook record is a folder": lambda: (self.root / ".umwayi" / "logbook.sha256").unlink()
            or (self.root / ".umwayi" / "logbook.sha256").mkdir(),
            ".umwayi is a file": lambda: shutil.rmtree(self.root / ".umwayi") or (self.root / ".umwayi").write_text("x"),
            "queue.md binary": lambda: (self.root / "queue.md").write_bytes(b"\x00\x81\xff"),
            "archive index is a folder": lambda: (self.root / "archive" / "INDEX.md").unlink()
            or (self.root / "archive" / "INDEX.md").mkdir(),
            "drafts is a file": lambda: shutil.rmtree(self.root / "drafts") or (self.root / "drafts").write_text("x"),
            "memory is a link loop": lambda: shutil.rmtree(self.root / "memory") or os.symlink("memory", self.root / "memory"),
        }
        seen = {}
        for name, corrupt in corruptions.items():
            self.tearDown_fresh()
            corrupt()
            for args in unique:
                with self.subTest(corruption=name, command=" ".join(args[:2])):
                    r = self.u(*args)
                    text = r.stdout + r.stderr
                    self.assertNotIn("Traceback", text)
                    self.assertIn(r.returncode, (0, 1, 2, 3, 64))
                    if "unexpected error" in r.stderr:
                        self.assertEqual(r.returncode, 2, text)
                    if r.returncode == 1:
                        self.assertTrue(r.stderr.startswith("umwayi: ") or r.stdout, text)
                        self.assertNotIn("unexpected error", text)
                    seen[r.returncode] = seen.get(r.returncode, 0) + 1
        self.assertTrue(set(seen) <= {0, 1, 2, 3, 64})

    def tearDown_fresh(self):
        for name in ("drafts", "archive", ".umwayi", "memory", "outbox"):
            p = self.root / name
            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.exists():
                shutil.rmtree(p)
        for name in ("LOGBOOK.md", "queue.md", "notes.md"):
            (self.root / name).unlink(missing_ok=True)
        (self.root / "notes.md").write_text("a b\nc d\n")
        (self.root / "memory").mkdir()
        (self.root / "memory" / "master.md").write_text("me\n")
        self.expect(["queue", "add", "--kind", "task", "One", "--date", D1], 0)
        self.expect(["steward", "--date", D1], 0)
        self.expect(["archive", "move", "notes.md", "--lines", "2-2", "--reason", "r", "--date", D1], 0)


# =========================================================== the code itself


NETWORK = {"socket", "ssl", "http", "urllib.request", "urllib.response", "urllib.error", "ftplib", "smtplib",
           "poplib", "imaplib", "telnetlib", "xmlrpc", "asyncio", "requests", "httpx", "aiohttp", "webbrowser",
           "socketserver", "wsgiref", "email.mime"}


def _modules():
    return sorted(PKG.rglob("*.py"))


# The budget governor's telemetry receiver (B.R2.1, approved Nov 9) is a standard library http.server on 127.0.0.1
# for one Claude Code run. It is the one allowed network import: only in umwayi/telemetry.py, only inside the function
# that starts a receiver, so importing any umwayi module still loads no network library (checked below).
ALLOWED_NETWORK = {("umwayi/telemetry.py", "http.server"), ("umwayi/telemetry.py", "http.server.BaseHTTPRequestHandler"),
                   ("umwayi/telemetry.py", "http.server.ThreadingHTTPServer"),
                   ("umwayi/telemetry.py", "socket")}  # S.2: the receiver's request deadline, in the same function


class CodeTests(SystemBase):
    def test_no_module_imports_a_network_library(self):
        for f in _modules():
            tree = ast.parse(f.read_text(encoding="utf-8"))
            top = {id(n) for n in tree.body}
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                for n in names:
                    with self.subTest(file=f.relative_to(REPO).as_posix(), imports=n):
                        if (f.relative_to(REPO).as_posix(), n) in ALLOWED_NETWORK:
                            self.assertNotIn(id(node), top, "the receiver's import must stay inside a function")
                            continue
                        self.assertFalse(any(n == b or n.startswith(b + ".") for b in NETWORK))
                        self.assertNotIn("importlib", n)
        src = (PKG / "telemetry.py").read_text(encoding="utf-8")
        self.assertIn('LOOPBACK = "127.0.0.1"', src)
        self.assertEqual(src.count("server_class((LOOPBACK, 0)"), 1)  # it binds loopback only, a free port
        self.assertNotIn("0.0.0.0", src)
        # and nothing pulls one in at run time: import every module in a fresh process
        mods = [".".join(f.relative_to(REPO).with_suffix("").parts) for f in _modules()]
        mods = [m[: -len(".__init__")] if m.endswith(".__init__") else m for m in mods]
        code = ("import sys\n" + "".join(f"import {m}\n" for m in mods if m != "umwayi.__main__")
                + f"print(sorted(m for m in sys.modules if any(m == b or m.startswith(b + '.') for b in {sorted(NETWORK)!r})))\n")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(REPO)), cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "[]")

    def test_no_helper_has_a_code_path_that_sets_an_approver(self):
        # 1. in the code: nothing that can run on its own mentions an approval, or imports publish
        runners = [PKG / "workflow.py", PKG / "jobs.py", PKG / "kill.py", PKG / "runlock.py", *sorted((PKG / "helpers").glob("*.py"))]
        for f in runners:
            src = f.read_text(encoding="utf-8")
            with self.subTest(file=f.relative_to(REPO).as_posix()):
                self.assertNotIn("approved", src.lower())
                for node in ast.walk(ast.parse(src)):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                        if isinstance(node, ast.ImportFrom):
                            mods += [f"{node.module}.{a.name}" for a in node.names]
                        self.assertFalse(any(m in ("umwayi.publish", "umwayi.cli", "umwayi.schedule") for m in mods), mods)
        # only the command line passes approved_by, and only from the owner's --approved-by: to publish-draft, and
        # since layer 11 (L11-Q4) to schedule install. Nothing that runs on its own imports schedule (above).
        cli = (PKG / "cli.py").read_text(encoding="utf-8")
        self.assertEqual(cli.count("approved_by"), 2)
        self.assertIn("publish.publish(Path(args.root), args.draft, args.date or _today(), args.approved_by)", cli)
        self.assertIn("schedule.install(root, args.name, args.date or _today(), args.approved_by, args.file)", cli)
        # 2. at run time: every helper, job and workflow, with rules that say Yes to everything, never calls publish
        (self.root / "rules.yaml").write_text("rules:\n  - id: all\n    title: t\n    text: t\n    verdict: yes\n"
                                              "    matchers:\n      type__exists: true\n")
        mark = Path(self._tmp.name) / "publish-called"
        for args in (["steward"], ["social", "draft", "articles/example.md"], ["run", "jobs.yaml", "--job", "open-queue"],
                     ["workflow", "run", "content-loop"]):
            with self.subTest(command=args[0]):
                self.u(*args, "--date", D1, fault="umwayi.publish:publish:record",
                       extra_env={"UMWAYI_FAULT_MARK": str(mark)})
                self.assertFalse(mark.exists(), "publish was called")
        self.assertFalse((self.root / "outbox").exists())
        # 3. the commands an AI helper could start have no --approved-by
        for args in (["steward"], ["social", "draft", "articles/example.md"], ["run", "jobs.yaml"],
                     ["workflow", "run", "content-loop"], ["workflow", "validate", "content-loop"], ["check", "{}"]):
            with self.subTest(option_on=args[0]):
                self.expect([*args, "--approved-by", "me"], 64)


if __name__ == "__main__":
    unittest.main()
