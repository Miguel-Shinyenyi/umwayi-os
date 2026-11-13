"""W9.6b goldens, taken on the code before `--workdir` existed.

What `agent run` and `agent check` do without the option, for both platforms: the output and exit code of a check
that passes, a check that fails (an old version, and for Kiro a missing hook file in the working folder), the
argument lists, the working folder of every program that is started, the logbook entries, the output and the exit
code of a clean run, a refused run, and the usage errors. The expected values are in `golden/agent_workdir_none.json`,
written once on the old code by `UMWAYI_WRITE_GOLDEN=1` and never changed by the W9.6b change. The change must keep
every byte of them.

What differs between machines is replaced before the comparison: the temporary folders, the Python path, the repo
path, the date and the random run id.
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

from tests.agents.support import REPO
from tests.budget.support import BudgetCase, today

GOLDEN = Path(__file__).with_name("golden") / "agent_workdir_none.json"
WRITE = os.environ.get("UMWAYI_WRITE_GOLDEN") == "1"
END = {"do": "exit", "code": 0}
PLATFORMS = (("claude", "reviewer"), ("kiro", "helper"))
_STORE: dict = {}


def _load() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}


class WorkdirGoldenCase(BudgetCase):
    def norm(self, text) -> str:
        if not isinstance(text, str):
            return text
        for real, name in ((str(self.work), "WORK"), (str(self.root), "ROOT"), (str(self.tmp), "TMP"),
                           (str(REPO), "REPO"), (sys.executable, "PYTHON")):
            text = text.replace(real, name)
        text = text.replace(today(), "DATE")
        text = re.sub(r"\b[0-9a-f]{16}\b", "RUNID", text)
        return re.sub(r"after \d+ s\b", "after N s", text)

    def snapshot(self, r) -> dict:
        calls = [{"argv": [self.norm(w) for w in c["argv"]], "cwd": self.norm(c["cwd"]),
                  "started": c["started"], "probe": c.get("probe"), "stdin": self.norm(c.get("stdin"))}
                 for c in self.calls() if "argv" in c]
        entries = [[e.source, self.norm(e.added), self.norm(e.checked), self.norm(e.not_done)]
                   for e in self.entries()]
        return {"code": r.returncode, "stdout": self.norm(r.stdout), "stderr": self.norm(r.stderr),
                "calls": calls, "entries": entries}

    def check_golden(self, key: str, snap: dict):
        if WRITE:
            _STORE[key] = snap
            return
        want = _load()
        self.assertIn(key, want, f"no golden for {key}")
        golden = want[key]
        self.assertEqual(len(snap["entries"]), len(golden["entries"]))
        # umwayi cuts a logbook line at 300 characters and adds "...", and the cut falls before the paths are replaced
        # by their names, so where it falls depends on the length of the repo and temporary paths of the machine. A
        # field cut this way is compared up to the shorter cut; every other field and byte is compared exactly.
        got = dict(snap, entries=[[self.same_cut(g, w) for g, w in zip(ge, we)] for ge, we in
                                  zip(snap["entries"], golden["entries"])])
        self.assertEqual(got, golden)

    def same_cut(self, got: str, want: str) -> str:
        if got != want and got.endswith("...") and want.endswith("..."):
            a, b = got[:-3], want[:-3]
            if a.startswith(b) or b.startswith(a):
                return want
        return got

    def agent(self, which) -> str:
        return dict(PLATFORMS)[which]

    def check_cmd(self, *args, extra=None):
        return self.umwayi("check", *args, extra=extra)

    def run_cmd(self, name, *args, steps=(END,), prompt="Do the task"):
        return self.umwayi("run", name, "--prompt", prompt, *args, extra=self.script(*steps))


class CheckGoldenTests(WorkdirGoldenCase):
    def ok(self, which):
        self.check_golden(f"check-ok-{which}", self.snapshot(self.check_cmd(self.agent(which))))

    def test_check_ok_claude(self):
        self.ok("claude")

    def test_check_ok_kiro(self):
        self.ok("kiro")

    def old(self, which):
        key = "FAKE_CLAUDE_VERSION" if which == "claude" else "FAKE_KIRO_VERSION"
        r = self.check_cmd(self.agent(which), extra={key: "0.0.1"})
        self.check_golden(f"check-old-version-{which}", self.snapshot(r))

    def test_check_old_version_claude(self):
        self.old("claude")

    def test_check_old_version_kiro(self):
        self.old("kiro")

    def test_check_kiro_without_a_hook_file_in_the_workdir(self):
        for p in (self.work / ".kiro" / "hooks").iterdir():
            p.unlink()
        self.check_golden("check-no-hook-file-kiro", self.snapshot(self.check_cmd("helper")))

    def test_check_unknown_name(self):
        self.check_golden("check-unknown-name", self.snapshot(self.check_cmd("nobody")))

    def test_check_kill_switch_on(self):
        self.kill_on()
        self.check_golden("check-kill-on-claude", self.snapshot(self.check_cmd("reviewer")))


class RunGoldenTests(WorkdirGoldenCase):
    def clean(self, which):
        self.check_golden(f"run-clean-{which}", self.snapshot(self.run_cmd(self.agent(which))))

    def test_run_clean_claude(self):
        self.clean("claude")

    def test_run_clean_kiro(self):
        self.clean("kiro")

    def test_run_from_stdin_word(self):
        r = self.umwayi("run", "reviewer", "-", extra=self.script(END))
        self.check_golden("run-stdin-word-claude", self.snapshot(r))

    def test_run_refused_by_the_gate_claude(self):
        r = self.umwayi("run", "reviewer", "--prompt", "Do the task",
                        extra=dict(self.script(END), FAKE_CLAUDE_VERSION="0.0.1"))
        self.check_golden("run-gate-refused-claude", self.snapshot(r))

    def test_run_refused_for_a_missing_hook_file_kiro(self):
        for p in (self.work / ".kiro" / "hooks").iterdir():
            p.unlink()
        self.check_golden("run-gate-refused-kiro", self.snapshot(self.run_cmd("helper")))

    def test_run_unknown_name(self):
        self.check_golden("run-unknown-name", self.snapshot(self.run_cmd("nobody")))

    def test_run_without_a_prompt(self):
        self.check_golden("run-no-prompt", self.snapshot(self.umwayi("run", "reviewer")))

    def test_run_word_after_the_name(self):
        self.check_golden("run-bad-word", self.snapshot(self.umwayi("run", "reviewer", "go")))

    def test_run_kill_switch_on(self):
        self.kill_on()
        self.check_golden("run-kill-on-kiro", self.snapshot(self.run_cmd("helper")))


def tearDownModule():
    if WRITE:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(_STORE, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
