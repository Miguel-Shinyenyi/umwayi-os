"""Support for the supervisor tests (W9.7): a root that is a real git repo, a test port to git, a spawn that starts the
fake agent as a real child process, and the scripts of a clean task.

Standard library only. The port to git here starts the system `git`; the supervisor itself starts none (it goes through
`env.git`). The spawn double replaces the one `Popen` of `umwayi/goalrun.py`: it receives the argument list the
supervisor built (and the tests read it), writes the ledger entries that `agent run` would write, and starts
`tests/goal/fake_agent.py` in the working folder the argument list names.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tests.goal import goalsupport
from tests.goal.fakeroot import GIT_ENV, REPO, needs_git
from umwayi import agents, budget, logbook, units
from umwayi import goalrun as gr
from umwayi import goalstate as gs
from umwayi.errors import UmwayiError

FAKE_AGENT = REPO / "tests" / "goal" / "fake_agent.py"
U = units.MICROS_PER_UU
STATUS_PART = "date: 2026-11-13\npr: none\nwhat: Did the piece.\ntests: none\n"
RULES = """rules:
  - id: goal-yes
    title: goals may start helpers
    text: Allowed.
    verdict: yes
    matchers:
      type: goal_start
  - id: agent-yes
    title: agents may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
"""
AGENTS = """agents:
  - name: claude-build
    platform: claude-code
    command: claude
    workdir: {work}
  - name: kiro-test
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
  - name: claude-guide
    platform: claude-code
    command: claude
    workdir: {work}
"""


def git(cwd, *args, check=True):
    env = dict(os.environ)
    env.update(GIT_ENV)
    p = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(cwd), *args], capture_output=True, text=True,
                       env=env, timeout=60)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


class GitPort:
    """The questions the supervisor asks of git, answered with real git commands. A stand-in for `umwayi.goalgit` in
    tests that are about the supervisor and not about the worktree half (that has its own tests in W9.6b)."""

    CAP = 8

    def worktree_path(self, root, goal, task):
        return os.path.realpath(root) + "-worktrees/" + f"{goal.lower()}-{task.lower()}"

    def base(self, root):
        return git(root, "rev-parse", "refs/heads/main")

    def has_origin_main(self, root):
        return git(root, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main", check=False) != ""

    def behind_origin(self, root):
        return int(git(root, "rev-list", "--count", "refs/heads/main..refs/remotes/origin/main"))

    def _registered(self, root):
        out = git(root, "worktree", "list", "--porcelain")
        paths, branches = [], []
        for line in out.splitlines():
            if line.startswith("worktree "):
                paths.append(line[9:])
            if line.startswith("branch "):
                branches.append(line[7:])
        return paths, branches

    def leftover(self, root, goal, task, other_tasks=()):
        path = self.worktree_path(root, goal, task)
        branch = f"umwayi/{goal.lower()}-{task.lower()}"
        paths, branches = self._registered(root)
        if os.path.lexists(path) or path in paths or f"refs/heads/{branch}" in branches:
            return "leftover"
        if git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False):
            return "leftover"
        wroot = Path(path).parent
        if wroot.is_dir():
            known = {os.path.realpath(p) for p in paths}
            if any(str(c) not in known for c in wroot.iterdir()):
                return "leftover"
        if len([p for p in paths if os.path.realpath(p) != os.path.realpath(root)]) >= self.CAP:
            return "cap"
        return None

    def worktree_add(self, root, branch, path, base):
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        self._run(root, "worktree", "add", "-b", branch, path, base)

    def worktree_add_detached(self, root, path, base):
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        self._run(root, "worktree", "add", "--detach", path, base)

    def worktree_remove(self, root, path):
        self._run(root, "worktree", "remove", path)

    def _run(self, cwd, *args):
        try:
            return git(cwd, *args)
        except RuntimeError:
            raise UmwayiError("git refused") from None

    def verify_worktree(self, root, path, base):
        if os.path.realpath(git(path, "rev-parse", "--show-toplevel")) != os.path.realpath(path):
            return "toplevel"
        if git(path, "rev-parse", "HEAD") != base or self.status(path):
            return "dirty"
        return None

    def status(self, path):
        out = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(path), "status", "--porcelain=v1", "-z",
                              "--untracked-files=all"], capture_output=True, env=dict(os.environ, **GIT_ENV)).stdout
        return [(e[:2], e[3:].decode("utf-8", "replace")) for e in out.split(b"\0") if e]

    def head(self, path):
        return git(path, "rev-parse", "HEAD")

    def count_ahead(self, path, base):
        return int(git(path, "rev-list", "--count", f"{base}..HEAD"))

    def changed(self, path, base):
        out = subprocess.run(["git", "-C", str(path), "diff", "--name-status", "-z", "--no-ext-diff", "--no-renames", base,
                              "HEAD"], capture_output=True, env=dict(os.environ, **GIT_ENV)).stdout.split(b"\0")
        return [(out[i].decode(), out[i + 1].decode("utf-8", "replace")) for i in range(0, len(out) - 1, 2)]

    def is_ancestor(self, root, tip):
        return subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", tip, "refs/heads/main"],
                              capture_output=True, env=dict(os.environ, **GIT_ENV)).returncode == 0

    def commit_exists(self, root, sha):
        return subprocess.run(["git", "-C", str(root), "cat-file", "-e", sha + "^{commit}"], capture_output=True,
                              env=dict(os.environ, **GIT_ENV)).returncode == 0


def builder_steps(goal="G-0001", task="T-01", n=1, files=None, status=STATUS_PART, extra=()):
    """What a good fake builder does: write the packet's files and its status part, commit, exit 0."""
    files = files if files is not None else {f"umwayi/piece{n}.py": "x = 1\n"}
    steps = [{"write": p, "text": t} for p, t in files.items()]
    if status is not None:
        steps.append({"write": f"docs-parts/status-log/{goal}-{task}.md", "text": status})
    steps += list(extra)
    return steps + [{"git": ["add", "-A"]}, {"git": ["commit", "-q", "-m", "work"]}, {"exit": 0}]


def tester_steps(verdicts=("pass",), nonce=None):
    checks = [{"n": i, "verdict": v, "evidence": f"Looked at check {i} closely."} for i, v in enumerate(verdicts, 1)]
    return [{"result": "UMWAYI-RESULT", "body": {"checks": checks}}]


def check_steps(verdict="accept"):
    return [{"result": "UMWAYI-CHECK", "body": {"verdict": verdict, "reason": "Looks right to me."}}]


class ChildDouble:
    """The spawn of a test: one script per start, in order. Records each argument list. Writes the ledger entries of
    the run (a reservation and a settle of `spend` UU) before the process starts, as `agent run` would."""

    def __init__(self, case, scripts):
        self.case = case
        self.scripts = list(scripts)
        self.calls = []  # (argv, cwd)
        self.procs = []

    def spawn(self, argv, cwd, environ):
        self.calls.append((list(argv), str(cwd)))
        spec = self.scripts.pop(0) if self.scripts else {"steps": []}
        if isinstance(spec, list):
            spec = {"steps": spec}
        agent = argv[5]
        run = secrets.token_hex(8)
        if spec.get("ledger", True):
            platform = agents.find(agents.load(self.case.root), agent).platform
            when = self.case.env.when()
            reserved = int(argv[argv.index("--cap-uu") + 1])
            logbook.append(self.case.root, budget.entry(when, budget.reserve_text(run, agent, platform, reserved * U),
                                                        "test double", "nothing"))
            if spec.get("spend", 1) is not None:  # a run that was reserved and never settled counts its whole cap
                spend = spec.get("spend", 1) * U
                reading = units.Reading("measured", spend, "test")
                logbook.append(self.case.root, budget.entry(
                    when, budget.settle_text(run, agent, platform, reserved * U, reading, None), "test double", "nothing"))
        steps = list(spec["steps"])
        if spec.get("exit") is not None and not any("exit" in s for s in steps):
            steps.append({"exit": spec["exit"]})
        workdir = argv[argv.index("--workdir") + 1] if "--workdir" in argv else str(cwd)
        env = dict(os.environ, FAKE_GOAL_SCRIPT=json.dumps(steps), PYTHONPATH=str(REPO))
        proc = subprocess.Popen([sys.executable, str(FAKE_AGENT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, cwd=workdir, env=env, start_new_session=True)
        self.procs.append(proc)
        return proc

    def started(self):
        return len(self.calls)


class RunCase(goalsupport.GoalCase):
    """A goal root that is a git repo with a local `main`, rules that allow `goal_start`, three agents and the supervisor's
    environment with a fake clock. `self.run_task(...)` runs one task through the supervisor."""

    def setUp(self):
        super().setUp()
        needs_git()
        self.work = self.root.parent / "work"
        self.work.mkdir()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        (self.root / "agents.yaml").write_text(AGENTS.replace("{work}", str(self.work)), encoding="utf-8")
        (self.root / "README.md").write_text("root\n", encoding="utf-8")
        for rel in ("docs/status-log.md", "docs/KNOWN-LIMITS.md"):
            (self.root / rel).parent.mkdir(exist_ok=True)
            (self.root / rel).write_text("shared\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(".umwayi/\nLOGBOOK.md\nLOGBOOK.record\nqueue.md\nmemory/\n", encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", ".gitignore", "README.md", "rules.yaml", "agents.yaml", "docs")
        git(self.root, "commit", "-q", "-m", "first")
        self.port = GitPort()
        self.out = []
        self.addCleanup(self.reap)
        self.children = None
        self.env = None
        self.ticks = 0
        self.hooks = []

    def reap(self):
        for p in (self.children.procs if self.children else []):
            if p.poll() is None:
                p.kill()
                p.wait()
        worktrees = Path(str(self.root) + "-worktrees")
        if worktrees.exists():
            shutil.rmtree(worktrees, ignore_errors=True)

    def sleep(self, seconds):
        """The watch's sleep: fake time moves by `seconds`, real time by a few milliseconds. A test can run a function at
        the Nth call with `self.at_tick(N, fn)`."""
        self.ticks += 1
        for n, fn in list(self.hooks):
            if self.ticks == n:
                fn()
        self.clock.advance(seconds)
        time.sleep(0.003)

    def at_tick(self, n, fn):
        self.hooks.append((n, fn))

    def make_env(self, scripts=(), gate=None, **kw):
        self.children = ChildDouble(self, scripts)
        args = dict(root=self.root, git=self.port, clock=self.clock, mono=self.clock, sleep=self.sleep,
                    spawn=self.children.spawn, gate=gate or (lambda root, name, workdir=None: agents.Result(0, [])),
                    out=self.out.append, busy_wait=1.0)
        args.update(kw)
        self.env = gr.Env(**args)
        return self.env

    def run_task(self, goal, task, scripts=(), **kw):
        self.make_env(scripts, **kw)
        return gr.run_task(self.env, goal, task)

    def task_state(self, goal="G-0001", task="T-01"):
        return gs.read_task(self.root, goal, task)["state"], gs.read_task(self.root, goal, task)["reason"]

    def good_scripts(self):
        return [{"steps": builder_steps(), "spend": 10}, {"steps": tester_steps(), "spend": 4},
                {"steps": check_steps(), "spend": 3}]

    def logbook_kinds(self):
        return [e.added for e in logbook.read_checked_chain(self.root)[0] if e.source == gs.SOURCE]
