"""Support for the whole-system test (tasks.md S.1.1): the world it runs in.

One temporary folder holds everything a day of use needs: the umwayi root, the agents' workdir, HOME, XDG_CONFIG_HOME
(where the systemd user units go), TMPDIR, a copy of the umwayi source with a fake installed ACP adapter, and the
fakes first on PATH: `claude` (also the fake telemetry sender), `kiro-cli`, `node` with the scripted ACP agent. Every
command is `python -m umwayi ...` (or a layer 9 hook script, or a rendered ExecStart= line) as a real child process.

The day's end state is kept in a snapshot. Each fault scenario restores that snapshot into the same folder first, so
it starts from the day's end state with every absolute path the day wrote (the agents' workdir, the Kiro hook file's
--root, the unit files, the logbook entries) still true (design.md, "Added while building", S-Q2).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from tests.adapters.support import SITECUSTOMIZE
from tests.agents.support import FAKE_SOURCE, SITE_EXTRA, alive, copy_src
from umwayi.agents import CLAUDE_ACP_ADAPTER, CLAUDE_ACP_PACKAGE, CLAUDE_ACP_PACKAGE_DIR, CLAUDE_ACP_VERSION
from umwayi.agents import CLAUDE_CREDENTIAL_ENV

REPO = Path(__file__).resolve().parents[1]
NODE_SOURCE = REPO / "tests" / "agents" / "fake_node.py"
SECRET = "S1-SECRET-never-printed"
STOP_WITHIN = 1.0 + 10.0 + 20.0  # the watcher's second, the stop grace, and room for a slow machine (seconds)

# The exit codes each command may give (S.R1.5).
NEVER_ONE = ("agent", "schedule", "budget")
CODES = {0, 1, 2, 3, 64}

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: {work}
    max_turns: 20
  - name: acp-reviewer
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: kiro
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
  - name: kiro-acp
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
"""
EXTRA_RULES = """
  # The whole-system test (S.1): the agents of agents.yaml may start and spend, and may read.
  - id: s1-agents
    title: the day's agents may start
    text: The agents of the whole-system test may start.
    verdict: yes
    matchers:
      type: agent_run
      agent: [reviewer, acp-reviewer, kiro, kiro-acp]
  - id: s1-budget
    title: the day's agents may spend within the limits
    text: The limits in units.yaml decide.
    verdict: yes
    matchers:
      type: budget_check
  - id: s1-read
    title: reading is fine
    text: Reading a file is allowed.
    verdict: yes
    matchers:
      type: [tool_read, tool_read_file, tool_lookup]
  - id: s1-no-rm
    title: never delete trees
    text: Never.
    verdict: no
    matchers:
      type: tool_bash
      command__contains: ["rm -rf"]
  - id: s1-permission-read
    title: an ACP read permission is fine
    text: Allowed once.
    verdict: yes
    matchers:
      type: acp_permission
      kind: read
"""
JOBS = """jobs:
  - name: open-queue
    command: queue-list
    status: open
    min_gap_days: 1
  - name: answered-queue
    command: queue-list
    status: answered
    min_gap_days: 1
  - name: closed-queue
    command: queue-list
    status: closed
    min_gap_days: 1
"""
SCHEDULE = """schedules:
  - name: answered-queue
    run: job
    job: answered-queue
    every: daily
    at: "08:00"
  - name: closed-queue
    run: job
    job: closed-queue
    every: weekly
    day: mon
    at: "09:00"
"""
NOTES = "# Notes\n\nline 3 stays\nold plan line 4\nold plan line 5\nline 6 stays\n"
OPTIONS = [{"optionId": "o-allow", "name": "Allow", "kind": "allow_once"},
           {"optionId": "o-reject", "name": "Reject", "kind": "reject_once"}]


def today() -> str:
    return date.today().isoformat()


def units_yaml(per_run: int | None = None, per_agent: int = 100000, worst: int | None = None) -> str:
    """Roomy day limits (the day starts each agent more than three times), Kiro runs declared at 40 UU."""
    lim = f"  per_day: 100000\n  per_agent_per_day: {per_agent}\n  per_platform_per_day: 100000\n"
    if per_run is not None:
        lim += f"  per_run: {per_run}\n"
    if worst is not None:
        lim += f"  unknown_worst_case: {worst}\n"
    return ("version: 1\nplatforms:\n  claude-code:\n    reading: usd_micros\n  kiro:\n    reading: runs\n"
            f"    run_micros:\n      value: 400000\n      date: {today()}\n      source: owner\nlimits:\n" + lim)


def permission(kind="read", title=None):
    return {"permission": {"toolCall": {"toolCallId": "call-1", "title": title or f"{kind} {SECRET}", "kind": kind},
                           "options": OPTIONS}}


class World:
    """The folder a day runs in, and every way the test touches it."""

    def __init__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="umwayi-s1-")))
        self.snap = Path(os.path.realpath(tempfile.mkdtemp(prefix="umwayi-s1-snap-")))
        self.root, self.work, self.bin = self.base / "root", self.base / "work", self.base / "bin"
        self.home, self.xdg, self.tmpdir = self.base / "home", self.base / "xdg", self.base / "tmp"
        self.site, self.src = self.base / "site", self.base / "src"
        self.units = self.xdg / "systemd" / "user"
        self.fake_log = self.base / "fake-calls.jsonl"
        self.seen: list = []  # (command words, exit code) of every umwayi command run
        self.procs: list = []  # every Popen, so none is left behind

    # ------------------------------------------------------------ building the fresh root (S.R2.1)

    def build(self) -> None:
        for d in (self.root, self.work, self.bin, self.home, self.xdg, self.tmpdir, self.site):
            d.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE + SITE_EXTRA, encoding="utf-8")
        copy_src(self.src)
        pkg = self.src / CLAUDE_ACP_PACKAGE_DIR
        (pkg / "dist").mkdir(parents=True)
        (self.src / CLAUDE_ACP_ADAPTER).write_text("// fake adapter, never run by node in these tests\n",
                                                   encoding="utf-8")
        (pkg / "package.json").write_text(json.dumps({"name": CLAUDE_ACP_PACKAGE, "version": CLAUDE_ACP_VERSION}),
                                          encoding="utf-8")
        for prog in ("claude", "kiro-cli", "claude-acp"):
            p = self.bin / prog
            p.write_text(f"#!{sys.executable}\n" + FAKE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
            p.chmod(0o755)
        node = self.bin / "node"
        node.write_text(f"#!{sys.executable}\n" + NODE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        node.chmod(0o755)
        self.node_answers()
        for name in ("umwayi.json",):
            shutil.copy(REPO / name, self.root / name)
        shutil.copytree(REPO / "workflows", self.root / "workflows")
        shutil.copytree(REPO / "articles", self.root / "articles")
        (self.root / "rules.yaml").write_text((REPO / "rules.yaml").read_text(encoding="utf-8").rstrip("\n") + "\n"
                                              + EXTRA_RULES, encoding="utf-8")
        (self.root / "agents.yaml").write_text(AGENTS.replace("{work}", str(self.work)), encoding="utf-8")
        (self.root / "units.yaml").write_text(units_yaml(), encoding="utf-8")
        (self.root / "jobs.yaml").write_text(JOBS, encoding="utf-8")
        (self.root / "schedule.yaml").write_text(SCHEDULE, encoding="utf-8")
        (self.root / "notes.md").write_text(NOTES, encoding="utf-8")
        mem = self.root / "memory"
        (mem / "projects").mkdir(parents=True)
        (mem / "journal").mkdir()
        (mem / "private").mkdir()
        (mem / "master.md").write_text("I am the owner. AI helpers draft only.\n", encoding="utf-8")
        (mem / "projects" / "umwayi.md").write_text("Project umwayi-os: the whole-system test.\n", encoding="utf-8")
        (mem / "private" / "bank.md").write_text(f"card {SECRET}\n", encoding="utf-8")
        hooks = self.work / ".kiro" / "hooks"
        hooks.mkdir(parents=True)
        command = f"{sys.executable} {self.src / 'adapters' / 'kiro' / 'hook.py'} --root {self.root}"
        (hooks / "umwayi.json").write_text(json.dumps({"version": "v1", "hooks": [{
            "name": "umwayi check before every tool", "trigger": "PreToolUse",
            "action": {"type": "command", "command": command}, "timeout": 60}]}), encoding="utf-8")

    def node_answers(self, acp: dict | None = None) -> None:
        """What the fake node answers; with acp, `node ADAPTER` becomes the scripted Claude flavour ACP agent."""
        cfg = {"fake_log": str(self.fake_log)}
        if acp is not None:
            cfg["acp"] = acp
        (self.bin / "node.json").write_text(json.dumps(cfg), encoding="utf-8")

    # ------------------------------------------------------------ the snapshot (S-Q2)

    def save(self) -> None:
        shutil.rmtree(self.snap)
        shutil.copytree(self.base, self.snap, symlinks=True)

    def restore(self) -> None:
        self.stop_all()
        for p in list(self.base.iterdir()):
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
        for p in self.snap.iterdir():
            dest = self.base / p.name
            if p.is_dir() and not p.is_symlink():
                shutil.copytree(p, dest, symlinks=True)
            else:
                shutil.copy2(p, dest, follow_symlinks=False)
        self.seen = []

    def cleanup(self) -> None:
        self.stop_all()
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.snap, ignore_errors=True)

    # ------------------------------------------------------------ running

    def env(self, extra: dict | None = None, fault: str | None = None, path: str | None = None) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT", "XDG_CONFIG_HOME", "TMPDIR") and k not in CLAUDE_CREDENTIAL_ENV
               and not k.startswith(("FAKE_", "OTEL_", "UMWAYI_"))}
        env["PATH"] = path if path is not None else os.pathsep.join([str(self.bin), env.get("PATH", "")])
        env["HOME"] = str(self.home)
        env["XDG_CONFIG_HOME"] = str(self.xdg)
        env["TMPDIR"] = str(self.tmpdir)
        env["FAKE_LOG"] = str(self.fake_log)
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(self.src)])
        env["UMWAYI_TEST_ROOT"] = str(self.root)
        if fault:
            env["UMWAYI_FAULT"] = fault
            env.setdefault("UMWAYI_FAULT_TEXT", SECRET)
        env.update(extra or {})
        return env

    def u(self, *args, input: str | None = None, extra=None, fault=None, path=None, timeout: float = 180):
        """`python -m umwayi --root ROOT ARGS` as a real child process; its exit code is checked and recorded."""
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args], input=input,
                           capture_output=True, text=True, env=self.env(extra, fault, path), cwd=str(self.base),
                           timeout=timeout)
        self.record(args, r.returncode)
        return r

    def start(self, *args, extra=None, fault=None):
        """`python -m umwayi ...` in the background, its stdin a pipe the test writes to."""
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=self.env(extra, fault), cwd=str(self.base))
        p.words = args
        self.procs.append(p)
        return p

    def finish(self, p, timeout: float = 120):
        """Wait for a background umwayi; return (code, stdout, stderr, the agent pids alive when it exited)."""
        p.wait(timeout=timeout)
        left = self.agent_pids_alive()
        for pid in left:
            _kill(pid)
        self.wait_quiet()
        if p.stdin is not None and not p.stdin.closed:
            try:
                p.stdin.close()
            except OSError:
                pass
        p.stdin = None
        out, err = p.communicate(timeout=30)
        self.record(p.words, p.returncode)
        return p.returncode, out, err, left

    def record(self, args, code: int) -> None:
        self.seen.append((tuple(args), code))

    def bad_codes(self) -> list:
        """Every exit code a command may not give (S.R1.5)."""
        bad = []
        for args, code in self.seen:
            if code not in CODES or (args and args[0] in NEVER_ONE and code == 1):
                bad.append((" ".join(args[:3]), code))
        return bad

    def hook(self, platform: str, payload, args=()):
        """A layer 9 hook script as the platform runs it: the payload on stdin, --root from the command line."""
        script = self.src / "adapters" / platform / "hook.py"
        return subprocess.run([sys.executable, str(script), "--root", str(self.root), *args],
                              input=json.dumps(payload), capture_output=True, text=True, env=self.env(),
                              cwd=str(self.work), timeout=60)

    def run_unit(self, name: str, extra: dict | None = None):
        """The rendered service, run the way systemd would: its ExecStart=, Environment= and WorkingDirectory=."""
        lines = self.unit_file(name, "service").read_text(encoding="utf-8").splitlines()
        value = {k: v for k, _, v in (x.partition("=") for x in lines if "=" in x and not x.startswith("#"))}
        var, _, val = value["Environment"].partition("=")
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), var: val,
               "XDG_CONFIG_HOME": str(self.xdg)}
        env.update(extra or {})
        r = subprocess.run(value["ExecStart"].split(" "), capture_output=True, text=True, timeout=300, env=env,
                           cwd=value["WorkingDirectory"])
        self.record(("run", "(scheduled)"), r.returncode)
        return r

    def unit_base(self, name: str) -> str:
        return f"umwayi-{hashlib.sha256(str(self.root).encode('utf-8')).hexdigest()[:8]}-{name}"

    def unit_file(self, name: str, kind: str) -> Path:
        return self.units / f"{self.unit_base(name)}.{kind}"

    # ------------------------------------------------------------ reading back

    def calls(self) -> list:
        if not self.fake_log.exists():
            return []
        data = self.fake_log.read_bytes()
        return [json.loads(line.decode("utf-8")) for line in data.split(b"\n")[:-1]]

    def node_calls(self) -> list:
        log = self.bin / "node-calls.jsonl"
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    def agent_pids_alive(self) -> list:
        pids = {c["pid"] for c in self.calls() if (c.get("started") or c.get("event") == "spawn") and c.get("pid")}
        pids |= {c["pid"] for c in self.node_calls() if c.get("started")}
        return sorted(pid for pid in pids if alive(pid))

    def wait_for(self, pred, what: str, proc=None, timeout: float = 60, since: float = 0.0) -> dict:
        """The first call of a fake that matches pred and was made at or after `since` (time.time()), so a call
        left in the log by an earlier step is never taken for the one being waited for."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for c in self.calls():
                if c.get("t", 0) >= since and pred(c):
                    return c
            if proc is not None and proc.poll() is not None:
                out, err = proc.communicate(timeout=30)
                raise AssertionError(f"umwayi exited ({proc.returncode}) before {what}\n{out}\n{err}")
            time.sleep(0.05)
        raise AssertionError(f"timed out waiting for {what}; calls: {self.calls()[-5:]}")

    def wait_quiet(self, timeout: float = 30) -> None:
        """No process that works on this root is left (a hook, an `umwayi check` it started), and no writer."""
        from tests.helpers import logbook_lock_held
        needle = str(self.root).encode()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            busy = False
            for name in os.listdir("/proc"):
                if not name.isdigit() or int(name) == os.getpid():
                    continue
                try:
                    with open(f"/proc/{name}/cmdline", "rb") as f:
                        cmd = f.read()
                except OSError:
                    continue
                if needle in cmd and alive(int(name)):
                    busy = True
                    break
            if not busy and not logbook_lock_held(self.root):
                return
            time.sleep(0.05)

    def entries(self) -> list:
        """The logbook entries, read under the logbook lock once no writer is left (as tests/agents/support.py)."""
        from umwayi import logbook
        self.wait_quiet()
        if not (self.root / logbook.LOGBOOK_NAME).exists():
            return []
        with logbook._lock(self.root):
            return logbook.read_checked(self.root)

    def raw_entries(self) -> list:
        """The parsed entries without the tamper check, for a test that broke the logbook on purpose."""
        from umwayi import logbook
        entries, _ = logbook.parse((self.root / "LOGBOOK.md").read_text(encoding="utf-8"))
        return [p.entry for p in entries]

    def log_text(self) -> str:
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    LOCKS = ("logbook.lock", "run.lock")  # a writer that takes a lock writes its pid there for messages (L-Q1)

    def tree(self) -> dict:
        """Every file under the root and the unit folder with a hash of its content (links as links). The two lock
        files are left out: they are kept on purpose and hold only who took them last, not any state."""
        out = {}
        for folder in (self.root, self.units):
            if not folder.exists():
                continue
            for p in sorted(folder.rglob("*")):
                if p.parent.name == ".umwayi" and p.name in self.LOCKS:
                    continue
                if p.is_symlink():
                    out[str(p)] = "link:" + os.readlink(p)
                elif p.is_file():
                    out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    # ------------------------------------------------------------ editing the logbook by hand

    def rewrite_logbook(self, text: str, rechain: bool = True) -> None:
        """Write LOGBOOK.md as given, recompute every Chain line if asked, and rewrite the whole-file record, so only
        the check under test can find the edit."""
        from umwayi import logbook
        lines = text.split("\n")
        if rechain:
            entries, problems = logbook.parse(text)
            assert not problems, problems
            first = next((p for p in entries if p.chain is not None), None)
            if first is not None:
                prev = hashlib.sha256(("\n".join(lines[:first.line - 2]) + "\n").encode("utf-8")).hexdigest()
                for p in entries:
                    if p.line < first.line:
                        continue
                    value = logbook.chain_value(prev, p.text)
                    lines[p.line - 1 + 6] = logbook.CHAIN_PREFIX + value
                    prev = value
        out = "\n".join(lines)
        (self.root / "LOGBOOK.md").write_text(out, encoding="utf-8")
        (self.root / ".umwayi" / "logbook.sha256").write_text(hashlib.sha256(out.encode("utf-8")).hexdigest() + "\n",
                                                              encoding="ascii")

    def stop_all(self) -> None:
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            try:
                p.communicate(timeout=30)
            except (ValueError, subprocess.TimeoutExpired):
                pass
        self.procs = []
        for pid in self.agent_pids_alive():
            _kill(pid)


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
