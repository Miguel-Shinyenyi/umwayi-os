"""Whole-system test: the umwayi command run as real processes in a fresh folder.

Every call here is `python -m umwayi --root ROOT ...` in its own process (the same
main() as the `umwayi` script). Faults are made by editing files, or, for an
unexpected crash, by a sitecustomize.py that patches one function in the child
process only.
"""

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
        self.expect(["queue", "answer", "Q-0002", "--answer", "Seen, I publish by hand", "--date", D2], 0)
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
        results = [(p.wait(timeout=60), p.stdout.read(), p.stderr.read()) for p in procs]
        codes = sorted(c for c, _, _ in results)
        self.assertEqual(codes, [0, 3], results)
        self.assertEqual(self.drafts(), ["steward-0001.md"], results)
        busy = [out for c, out, _ in results if c == 3]
        self.assertIn("holds the run lock", busy[0])
        self.expect(["logbook", "verify"], 0, "ok: 4 entries")  # 3 steps and 1 refused run


if __name__ == "__main__":
    unittest.main()
