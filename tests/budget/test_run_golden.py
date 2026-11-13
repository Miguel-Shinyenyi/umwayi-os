"""W9.6 goldens, taken on the code before `--cap-uu`, `--model` and `--effort` existed.

The argument lists, the logbook entries, the output and the exit codes of `agent run` without the three options, for
both platforms: a clean run, a stop by the kill switch before the start and in the middle of a run, a stop by the
per-run cap, and a refusal by the day cap. The expected values are in `golden/agent_run.json`, written once on the old
code by `UMWAYI_WRITE_GOLDEN=1` and never changed by the W9.6 change. The change must keep every byte of them.

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
from tests.budget.support import BudgetCase, api_request, send_logs, today
from umwayi import agents
from umwayi.agents import Agent

GOLDEN = Path(__file__).with_name("golden") / "agent_run.json"
WRITE = os.environ.get("UMWAYI_WRITE_GOLDEN") == "1"
END = {"do": "exit", "code": 0}
WAIT = {"do": "sleep", "s": 60}
PLATFORMS = (("claude", "reviewer"), ("kiro", "helper"))
_STORE: dict = {}


def _load() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}


class GoldenCase(BudgetCase):
    def norm(self, text: str) -> str:
        for real, name in ((str(self.tmp), "TMP"), (str(REPO), "REPO"), (sys.executable, "PYTHON")):
            text = text.replace(real, name)
        text = text.replace(today(), "DATE")
        text = re.sub(r"\b[0-9a-f]{16}\b", "RUNID", text)
        return re.sub(r"after \d+ s\b", "after N s", text)

    def snapshot(self, r) -> dict:
        calls = [c for c in self.calls() if c.get("started")]
        entries = [[e.source, self.norm(e.added), self.norm(e.checked), self.norm(e.not_done)] for e in self.entries()]
        return {"code": r[0] if isinstance(r, tuple) else r.returncode,
                "stdout": self.norm(r[1] if isinstance(r, tuple) else r.stdout),
                "argv": [[self.norm(w) for w in c["argv"]] for c in calls],
                "stdin": [self.norm(c["stdin"]) for c in calls],
                "entries": entries}

    def check(self, key: str, snap: dict):
        if WRITE:
            _STORE[key] = snap
            return
        want = _load()
        self.assertIn(key, want, f"no golden for {key}")
        self.assertEqual(snap, want[key])


class RunGoldenTests(GoldenCase):
    def agent(self, which):
        return dict(PLATFORMS)[which]

    def clean(self, which):
        steps = (send_logs(api_request(cost_micros=12345)), END) if which == "claude" else (END,)
        r = self.run_agent(self.agent(which), *steps)
        self.check(f"clean-{which}", self.snapshot(r))

    def test_clean_claude(self):
        self.clean("claude")

    def test_clean_kiro(self):
        self.clean("kiro")

    def before_start(self, which, prepare, key):
        prepare()
        r = self.run_agent(self.agent(which), END)
        self.check(f"{key}-{which}", self.snapshot(r))

    def test_kill_before_start_claude(self):
        self.before_start("claude", self.kill_on, "kill-before")

    def test_kill_before_start_kiro(self):
        self.before_start("kiro", self.kill_on, "kill-before")

    def kill_while_running(self, which):
        name = self.agent(which)
        p = self.start_run(name, WAIT)
        self.wait_for(lambda c: c.get("started"), what="the start", proc=p)
        self.kill_on()
        code, out, _ = self.finish(p)
        self.check(f"kill-during-{which}", self.snapshot((code, out)))

    def test_kill_during_claude(self):
        self.kill_while_running("claude")

    def test_kill_during_kiro(self):
        self.kill_while_running("kiro")

    def test_per_run_cap_stop_claude(self):
        self.limits(per_run=10)
        p = self.start_run("reviewer", send_logs(api_request(cost_micros=150000)), WAIT)
        code, out, _ = self.finish(p, timeout=60)
        self.check("cap-stop-claude", self.snapshot((code, out)))

    def test_per_run_cap_kiro(self):
        # Kiro reports no cost (KNOWN-LIMITS 117): nothing can stop the run mid way. It ends by itself and settles
        # at unknown_worst_case, which is above the 10 UU reservation. The golden keeps that as it is today.
        self.limits(per_run=10)
        r = self.run_agent("helper", END)
        self.check("cap-stop-kiro", self.snapshot(r))

    def day_cap(self, which):
        self.limits(per_day=50)
        r = self.run_agent(self.agent(which), END)
        self.check(f"day-cap-{which}", self.snapshot(r))

    def test_day_cap_claude(self):
        self.day_cap("claude")

    def test_day_cap_kiro(self):
        self.day_cap("kiro")


class ArgvGoldenTests(unittest.TestCase):
    """build_argv without options, for every shape of agent that `agent run` accepts."""

    def argvs(self) -> dict:
        root = Path("/golden/root")
        out = {}
        shapes = {
            "claude": Agent(name="a", platform="claude-code", command="claude", transport="cli",
                       workdir="/golden/work"),
            "claude-turns": Agent(name="a", platform="claude-code", command="claude", transport="cli",
                                  workdir="/golden/work", max_turns=20),
            "kiro": Agent(name="a", platform="kiro", command="kiro-cli", transport="cli", workdir="/golden/work"),
            "kiro-agent": Agent(name="a", platform="kiro", command="kiro-cli", transport="cli",
                                workdir="/golden/work", kiro_agent="coder", trust_tools=("read_file", "grep_search")),
        }
        for key, a in shapes.items():
            argv, stdin = agents.build_argv(a, agents.RUN, "/bin/prog", root, "/usr/bin/python3",
                                            prompt="Do the task", src=REPO)
            out[key] = {"argv": [w.replace(str(REPO), "REPO") for w in argv], "stdin": stdin}
        return out

    def test_argv_lists(self):
        got = self.argvs()
        if WRITE:
            _STORE["argv"] = got
            return
        self.assertEqual(got, _load()["argv"])


def tearDownModule():
    if WRITE:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(_STORE, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
