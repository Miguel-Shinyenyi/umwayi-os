"""Shared helpers for the layer 10 tests: a fresh root, fake claude and kiro-cli programs, real child processes.

The fakes are small Python scripts put first on PATH. They record every call (argv and
working folder) to a JSON lines file, answer the version flag, and record "started" for
anything else, so a test can prove that no agent was started.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.adapters.support import SITECUSTOMIZE

REPO = Path(__file__).resolve().parents[2]
SECRET = "sk-live-AGENTS-TEST-SECRET"
CODES = {0, 2, 3, 64}  # the only exit codes umwayi agent may give

FAKE = r'''#!{python}
import json, os, sys, time
prog = os.path.basename(sys.argv[0])
key = "KIRO" if prog == "kiro-cli" else "CLAUDE"
version_flag = "--version" if prog == "kiro-cli" else "-v"
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prog": prog, "argv": sys.argv[1:], "cwd": os.getcwd(),
                        "started": sys.argv[1:] != [version_flag]}}) + "\n")
if sys.argv[1:] == [version_flag]:
    if os.environ.get(f"FAKE_{{key}}_HANG"):
        time.sleep(60)
    sys.stdout.write(os.environ.get(f"FAKE_{{key}}_VERSION", "{default}") + "\n")
    sys.exit(int(os.environ.get(f"FAKE_{{key}}_EXIT", "0")))
sys.exit(0)
'''
DEFAULT_VERSIONS = {"claude": "2.1.300 (Claude Code)", "kiro-cli": "kiro-cli 2.40.0"}

CLAUDE_AGENT = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: {work}
    max_turns: 20
"""
KIRO_AGENT = """agents:
  - name: helper
    platform: kiro
    command: kiro-cli
    transport: {transport}
    workdir: {work}
    trust_tools: [read_file, grep_search]
"""


def copy_src(dest: Path) -> Path:
    """A copy of the umwayi package and the adapters, so a test can break a hook without touching the repo."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "umwayi", dest / "umwayi", ignore=ignore)
    shutil.copytree(REPO / "adapters", dest / "adapters", ignore=ignore)
    return dest


def tree_state(*folders: Path) -> dict:
    """Every path under the folders with a hash of its content, to prove nothing was written."""
    out = {}
    for folder in folders:
        for p in sorted(folder.rglob("*")):
            if p.is_symlink():
                out[str(p)] = "link:" + os.readlink(p)
            elif p.is_file():
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                out[str(p)] = "dir"
    return out


class AgentCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-agents-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.root = self.tmp / "root"
        self.work = self.tmp / "work"
        self.bin = self.tmp / "bin"
        self.home = self.tmp / "home"
        self.site = self.tmp / "site"
        for d in (self.root, self.work, self.bin, self.home, self.site):
            d.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.fake_log = self.tmp / "fake-calls.jsonl"
        self.src = REPO

    # ------------------------------------------------------------ set up

    def fake(self, prog: str):
        p = self.bin / prog
        p.write_text(FAKE.format(python=sys.executable, default=DEFAULT_VERSIONS[prog]), encoding="utf-8")
        p.chmod(0o755)
        return p

    def write_agents(self, text: str, name: str = "agents.yaml") -> Path:
        p = self.root / name
        p.write_text(text.replace("{work}", str(self.work)).replace("{root}", str(self.root)), encoding="utf-8")
        return p

    def kiro_hook_file(self, command: str | None = None, folder: Path | None = None, name: str = "umwayi.json",
                       hook: dict | None = None, data=None) -> Path:
        folder = folder or (self.work / ".kiro" / "hooks")
        folder.mkdir(parents=True, exist_ok=True)
        if data is None:
            if hook is None:
                hook = {"name": "umwayi check before every tool", "trigger": "PreToolUse",
                        "action": {"type": "command", "command": command or self.kiro_command()}, "timeout": 60}
            data = {"version": "v1", "hooks": [hook]}
        p = folder / name
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p

    def kiro_command(self, python: str = "python3", root: Path | None = None) -> str:
        return f"{python} {self.src / 'adapters' / 'kiro' / 'hook.py'} --root {root or self.root}"

    # ------------------------------------------------------------ run

    def env(self, extra: dict | None = None, fault: str | None = None) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT") and not k.startswith("FAKE_")}
        env["PATH"] = os.pathsep.join([str(self.bin), env.get("PATH", "")])
        env["HOME"] = str(self.home)
        env["FAKE_LOG"] = str(self.fake_log)
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(self.src)])
        if fault:
            env["UMWAYI_FAULT"] = fault
        env.update(extra or {})
        return env

    def umwayi(self, *args, extra: dict | None = None, fault: str | None = None, root: Path | None = None,
               timeout: float = 60):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root or self.root), "agent", *args],
                           capture_output=True, text=True, env=self.env(extra, fault), cwd=str(self.tmp),
                           timeout=timeout)
        self.assertIn(r.returncode, CODES, f"exit {r.returncode} is not allowed\n{r.stdout}\n{r.stderr}")
        self.assertNotEqual(r.returncode, 1)
        return r

    def calls(self) -> list:
        if not self.fake_log.exists():
            return []
        return [json.loads(line) for line in self.fake_log.read_text(encoding="utf-8").splitlines()]

    def assert_nothing_started(self):
        started = [c for c in self.calls() if c["started"]]
        self.assertEqual(started, [], "an agent program was started with more than its version flag")

    def lines(self, r) -> list:
        return r.stdout.splitlines()

    def argv_line(self, r, mode: str) -> list:
        for line in self.lines(r):
            if line.startswith(f"{mode} would start: "):
                text = line[len(f"{mode} would start: "):]
                return json.loads(text.split(" with the prompt on stdin")[0])
        self.fail(f"no '{mode} would start' line in:\n{r.stdout}")
