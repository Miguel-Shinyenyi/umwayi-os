"""Support for the goal scenarios of tests/test_whole_system.py (W9.10, W9.R21.4): a world in which the owner's day with
`umwayi goal` runs through real child processes only.

Everything is `python -m umwayi ...`: the owner's commands, and below them the supervisor's child `umwayi agent run`,
which starts a fake `kiro-cli` from the bin folder. The fake answers the version and login probes like the layer 10
fake, and for a real start it plays the script of its role (builder, tester, check or guide) from a JSON file the test
writes, with the program of tests/goal/fake_agent.py. All three roles are Kiro agents with a declared run of 10 UU, so
every run costs a known amount. HOME, TMPDIR and PATH are in a temporary folder; no real agent, network or account is
used. The three owner commands need a terminal: `tty` runs a command with a pseudo terminal on standard input and
output, the only way a child process can have one.

Two test-only hooks come through a sitecustomize in the child's PYTHONPATH: UMWAYI_TEST_TIME_OFFSET moves `time.time`
by some seconds (an approval deadline passes without a wait), and UMWAYI_TEST_STALL_SECONDS lowers the stall time of
the judge (a silent builder stalls in seconds).
"""

from __future__ import annotations

import json
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests.goal.fakeroot import GIT_ENV

REPO = Path(__file__).resolve().parents[2]
LAYER10_FAKE = REPO / "tests" / "agents" / "fake_agent.py"
GOAL_FAKE = REPO / "tests" / "goal" / "fake_agent.py"
GOAL_CODES = {0, 2, 3, 64}  # the only codes a goal command may give
SECRET = "S9-SECRET-never-in-a-record"
GOAL_TEXT = "Build the thing the owner asked for, in small safe steps."

SITE = r'''
import os
_off = os.environ.get("UMWAYI_TEST_TIME_OFFSET")
if _off:
    import time as _time
    _real = _time.time
    _time.time = lambda: _real() + float(_off)
_stall = os.environ.get("UMWAYI_TEST_STALL_SECONDS")
if _stall:
    try:
        import umwayi.goalwatch as _gw
        _gw.Policy.for_role = staticmethod(lambda role: _gw.Policy(stall_s=int(_stall), output_is_progress=role != "builder"))
    except ImportError:
        pass
'''

SHIM = r'''#!{python}
import io, json, os, runpy, sys
sys.path.insert(0, {repo!r})
args = sys.argv[1:]
if args in (["--version"], ["-v"], ["whoami"]):
    exec(compile(open({layer10!r}, encoding="utf-8").read(), "kiro-cli", "exec"), {{"__name__": "__main__"}})
    sys.exit(0)
prompt = sys.stdin.read()
role = ("guide" if "You are the guide. Split" in prompt else "check" if "You are the guide, checking" in prompt
        else "tester" if "You are the tester" in prompt else "builder")
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({{"started": True, "role": role, "pid": os.getpid(), "cwd": os.getcwd(), "argv": args}}) + "\n")
with open(os.environ["FAKE_GOAL_SCRIPTS"], encoding="utf-8") as f:
    scripts = json.load(f)
os.environ["FAKE_GOAL_SCRIPT"] = json.dumps(scripts.get(role, []))
sys.stdin = io.StringIO(prompt)
from tests.goal import fake_agent
sys.exit(fake_agent.main())
'''

AGENTS = """agents:
  - name: kiro-build
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
    timeout_minutes: 90
  - name: kiro-test
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
  - name: kiro-guide
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
"""
RULES = """rules:
  - id: w-goal
    title: goals may start helpers
    text: Allowed.
    verdict: yes
    matchers:
      type: goal_start
  - id: w-agent
    title: agents may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
  - id: w-budget
    title: spend within the limits
    text: The limits decide.
    verdict: yes
    matchers:
      type: budget_check
"""
UNITS = """version: 1
platforms:
  kiro:
    reading: runs
    run_micros:
      value: 100000
      date: 2026-11-13
      source: owner
limits:
  per_day: 100000
  per_agent_per_day: 100000
  per_platform_per_day: 100000
  per_run: 100
"""
GUIDANCE = """version: 1
guidance:
  - id: goal-sentence-present
    source_repo: hub
    source: "understanding-first.md#3"
    text: "A task states its goal in one sentence before any work starts."
    kind: enforce
    check: goal_sentence_present
    applies_to: task
    tier: 3
    source_hash: "2f0405e879b6615f34c5168161153363896e26eab43981dc6db1d96b0c1f6bc0"
"""
STATUS_PART = "date: 2026-11-13\npr: none\nwhat: Did the piece.\ntests: none\n"


def plan_line(tasks=1, size=40):
    obj = {"tasks": [{"goal": f"Do the numbered piece of work number {i} now.", "context": [],
                      "checks": [f"Check number {i} of the piece can be answered pass or fail."], "size": size,
                      "files": [f"umwayi/piece{i}.py"]} for i in range(1, tasks + 1)]}
    return {"result": "UMWAYI-PLAN", "body": obj}


def builder_steps(goal, task, n, extra=(), files=None, status=STATUS_PART):
    files = files if files is not None else {f"umwayi/piece{n}.py": "x = 1\n"}
    steps = [{"write": p, "text": t} for p, t in files.items()]
    if status is not None:
        steps.append({"write": f"docs-parts/status-log/{goal}-{task}.md", "text": status})
    steps += list(extra)
    return steps + [{"git": ["add", "-A"]}, {"git": ["commit", "-q", "-m", "work"]}, {"exit": 0}]


def tester_steps(verdicts=("pass",)):
    checks = [{"n": i, "verdict": v, "evidence": f"Looked at check {i} closely."} for i, v in enumerate(verdicts, 1)]
    return [{"result": "UMWAYI-RESULT", "body": {"checks": checks}}]


def check_steps(verdict="accept"):
    return [{"result": "UMWAYI-CHECK", "body": {"verdict": verdict, "reason": "Looks right to me."}}]


class GoalWorld:
    def __init__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="umwayi-w9-")))
        self.root, self.work, self.bin = self.base / "umwayi-os", self.base / "work", self.base / "bin"
        self.home, self.site, self.tmp = self.base / "home", self.base / "site", self.base / "tmp"
        self.fake_log = self.base / "fake-calls.jsonl"
        self.scripts = self.base / "scripts.json"
        self.seen: list = []  # (command words, exit code) of every goal command run
        self.procs: list = []
        self.build()

    # ---- building

    def build(self):
        for d in (self.root, self.work, self.bin, self.home, self.site, self.tmp):
            d.mkdir()
        (self.site / "sitecustomize.py").write_text(SITE, encoding="utf-8")
        shim = self.bin / "kiro-cli"
        shim.write_text(SHIM.format(python=sys.executable, repo=str(REPO), layer10=str(LAYER10_FAKE)), encoding="utf-8")
        shim.chmod(0o755)
        shutil.copy(REPO / "umwayi.json", self.root / "umwayi.json")
        (self.root / "memory").mkdir()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        (self.root / "agents.yaml").write_text(AGENTS.replace("{work}", str(self.work)), encoding="utf-8")
        (self.root / "units.yaml").write_text(UNITS, encoding="utf-8")
        (self.root / "guidance.yaml").write_text(GUIDANCE, encoding="utf-8")
        (self.root / "README.md").write_text("root\n", encoding="utf-8")
        for rel in ("docs/status-log.md", "docs/KNOWN-LIMITS.md"):
            (self.root / rel).parent.mkdir(exist_ok=True)
            (self.root / rel).write_text("shared\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(".umwayi/\nLOGBOOK.md\nLOGBOOK.record\nqueue.md\nmemory/\n", encoding="utf-8")
        hooks = self.home / ".kiro" / "hooks"
        hooks.mkdir(parents=True)
        command = f"{sys.executable} {REPO / 'adapters' / 'kiro' / 'hook.py'} --root {self.root}"
        (hooks / "umwayi.json").write_text(json.dumps({"version": "v1", "hooks": [{
            "name": "umwayi check before every tool", "trigger": "PreToolUse",
            "action": {"type": "command", "command": command}, "timeout": 60}]}), encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".gitignore", "README.md", "rules.yaml", "agents.yaml", "units.yaml", "guidance.yaml", "umwayi.json",
                 "docs")
        self.git("commit", "-q", "-m", "first")
        self.script()

    def git(self, *args, cwd=None):
        env = dict(os.environ, **GIT_ENV)
        p = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(cwd or self.root), *args],
                           capture_output=True, text=True, env=env, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
        return p.stdout.strip()

    def script(self, **roles):
        """What each role does the next time it is started: builder, tester, check, guide (lists of fake agent steps)."""
        self.scripts.write_text(json.dumps(roles), encoding="utf-8")

    # ---- running

    def env(self, extra=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT") and not k.startswith(("FAKE_", "UMWAYI_TEST_"))}
        env.update(PATH=os.pathsep.join([str(self.bin), env.get("PATH", "")]), HOME=str(self.home), TMPDIR=str(self.tmp),
                   PYTHONPATH=os.pathsep.join([str(self.site), str(REPO)]), FAKE_LOG=str(self.fake_log),
                   FAKE_GOAL_SCRIPTS=str(self.scripts), **GIT_ENV)
        env.update(extra or {})
        return env

    def argv(self, *args):
        return [sys.executable, "-m", "umwayi", "--root", str(self.root), *args]

    def note(self, args, code):
        if args and args[0] == "goal":
            self.seen.append((tuple(args[:2]), code))

    def u(self, *args, extra=None, timeout=300):
        """One umwayi command as a child process with no terminal."""
        r = subprocess.run(self.argv(*args), capture_output=True, text=True, env=self.env(extra), cwd=str(self.base),
                           stdin=subprocess.DEVNULL, timeout=timeout)
        self.note(args, r.returncode)
        return r

    def bg(self, *args, extra=None):
        """A command in the background (a `goal run` the test acts on while it works)."""
        p = subprocess.Popen(self.argv(*args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=self.env(extra), cwd=str(self.base), stdin=subprocess.DEVNULL, start_new_session=True)
        self.procs.append(p)
        return p

    def finish(self, p, timeout=300):
        out, err = p.communicate(timeout=timeout)
        self.note(("goal", "run"), p.returncode)
        return p.returncode, out, err

    def tty(self, *args, extra=None, timeout=300):
        """An owner command with a pseudo terminal on standard input and output. Returns (code, output)."""
        master, slave = pty.openpty()
        try:
            p = subprocess.Popen(self.argv(*args), stdin=slave, stdout=slave, stderr=subprocess.PIPE, text=True,
                                 env=self.env(extra), cwd=str(self.base), close_fds=True)
            os.close(slave)
            slave = None
            out = b""
            end = time.monotonic() + timeout
            while True:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    out += chunk
                elif p.poll() is not None:
                    break
                if time.monotonic() > end:
                    p.kill()
                    break
            err = p.communicate(timeout=30)[1]
            self.note(args, p.returncode)
            return p.returncode, out.decode("utf-8", "replace") + err
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)

    # ---- looking

    def goals(self):
        d = self.root / ".umwayi" / "goals"
        return sorted(p.name for p in d.iterdir() if p.name.startswith("G-")) if d.is_dir() else []

    def task(self, goal, task="T-01"):
        return json.loads((self.root / ".umwayi" / "goals" / goal / f"{task}.json").read_text(encoding="utf-8"))

    def state(self, goal, task="T-01"):
        t = self.task(goal, task)
        return t["state"], t["reason"]

    def starts(self):
        """The starts of the fake agent, one dict each (role, pid, cwd)."""
        if not self.fake_log.exists():
            return []
        out = []
        for line in self.fake_log.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("started") and d.get("role"):
                out.append(d)
        return out

    def logbook_text(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def alive(self):
        pids = [d["pid"] for d in self.starts()]
        alive = []
        for pid in pids:
            try:
                with open(f"/proc/{pid}/stat", encoding="ascii") as f:
                    if f.read().rsplit(")", 1)[1].split()[0] != "Z":
                        alive.append(pid)
            except (OSError, IndexError):
                pass
        return alive

    def snapshot(self):
        import hashlib
        out = {}
        for folder in (self.root, Path(str(self.root) + "-worktrees")):
            if not folder.exists():
                continue
            for p in sorted(folder.rglob("*")):
                if ".git" in p.parts:
                    continue
                if p.is_file() and not p.is_symlink():
                    out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
                else:
                    out[str(p)] = "dir"
        return out

    def wait_quiet(self, timeout=30):
        end = time.monotonic() + timeout
        while self.alive() and time.monotonic() < end:
            time.sleep(0.1)

    def cleanup(self):
        for p in self.procs:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    p.kill()
        for pid in self.alive():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)
