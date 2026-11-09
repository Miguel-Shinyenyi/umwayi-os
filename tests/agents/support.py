"""Shared helpers for the layer 10 tests: a fresh root, fake claude and kiro-cli programs, real child processes.

The fakes are small Python scripts put first on PATH. They record every call (argv and
working folder) to a JSON lines file, answer the version flag, and record "started" for
anything else, so a test can prove that no agent was started.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.adapters.support import SITECUSTOMIZE
from umwayi.agents import CLAUDE_CREDENTIAL_ENV

REPO = Path(__file__).resolve().parents[2]
SECRET = "sk-live-AGENTS-TEST-SECRET"
CODES = {0, 2, 3, 64}  # the only exit codes umwayi agent may give

FAKE_SOURCE = Path(__file__).with_name("fake_agent.py")

# Test only: loaded by the sitecustomize in every child. Makes a "minute" of timeout_minutes
# last UMWAYI_TEST_MINUTE seconds, so a timeout test does not take a real minute.
SITE_EXTRA = r'''
if os.environ.get("UMWAYI_TEST_MINUTE"):
    try:
        import umwayi.agents as _agents
        _agents.SECONDS_PER_MINUTE = float(os.environ["UMWAYI_TEST_MINUTE"])
    except ImportError:
        pass
# Test only: a shorter wait for the first gate (the canary) than the 30 s of acp.GATE_WAIT,
# for tests where the canary never runs. Tests where it runs keep the real 30 s.
if os.environ.get("UMWAYI_TEST_GATE_WAIT"):
    try:
        import umwayi.acp as _acp
        _acp.GATE_WAIT = float(os.environ["UMWAYI_TEST_GATE_WAIT"])
    except ImportError:
        pass
# Test only: the logbook is edited by hand right after the gate checks, so the rules check
# was logged but the start entry cannot be.
if os.environ.get("UMWAYI_TEST_BREAK_LOGBOOK_AFTER_GATE"):
    try:
        import umwayi.agents as _agents2
        _real_gate = _agents2.gate_checks
        def _gate_then_break(*a, **k):
            g = _real_gate(*a, **k)
            with open(os.path.join(os.environ["UMWAYI_TEST_ROOT"], "LOGBOOK.md"), "a", encoding="utf-8") as f:
                f.write("edited by hand\n")
            return g
        _agents2.gate_checks = _gate_then_break
    except ImportError:
        pass
'''

RULES = """rules:
  - id: agent-yes
    title: reviewer may start
    text: The reviewer agent may start.
    verdict: yes
    matchers:
      type: agent_run
      agent: [reviewer, slow, stubborn, quick]
  - id: agent-no
    title: blocked may not start
    text: The blocked agent never starts.
    verdict: no
    matchers:
      type: agent_run
      agent: blocked
  - id: agent-ask
    title: asker needs the owner
    text: The owner decides.
    verdict: ask
    matchers:
      type: agent_run
      agent: asker
  - id: read-yes
    title: reading is fine
    text: Reading is allowed.
    verdict: yes
    matchers:
      type: tool_read
  - id: bash-ask
    title: shell needs the owner
    text: The owner confirms shell commands.
    verdict: ask
    matchers:
      type: tool_bash
  - id: bash-no-rm
    title: no rm -rf
    text: Never delete trees.
    verdict: no
    matchers:
      type: tool_bash
      command__contains: ["rm -rf"]
"""

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
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE + SITE_EXTRA, encoding="utf-8")
        self.fake_log = self.tmp / "fake-calls.jsonl"
        self.src = REPO
        self.alive_at_exit = []

    # ------------------------------------------------------------ set up

    def fake(self, prog: str):
        p = self.bin / prog
        p.write_text(f"#!{sys.executable}\n" + FAKE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
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
        # The machine's own credential names (10.R12.6) are never inherited, so no test depends on whether the
        # machine running it sets ANTHROPIC_BASE_URL or a key, and no real credential reaches a fake. A test that
        # needs one plants it through `extra`.
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT") and k not in CLAUDE_CREDENTIAL_ENV
               and not k.startswith("FAKE_")}
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

    def start_umwayi(self, *args, extra: dict | None = None, fault: str | None = None, stdin=None):
        """umwayi agent ... in the background, for tests that act while the agent runs."""
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", *args],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env(extra, fault),
                             cwd=str(self.tmp), stdin=stdin if stdin is not None else subprocess.DEVNULL)
        self.addCleanup(self._reap, p)
        return p

    def _reap(self, p):
        if p.poll() is None:
            p.kill()
        p.communicate(timeout=30)
        for c in self.calls():  # never leave a fake (or its children) running after a test
            for pid in (c.get("pid"), c.get("pid") if c.get("event") == "spawn" else None):
                if pid and alive(pid):
                    os.kill(pid, signal.SIGKILL)

    def finish(self, p, timeout: float = 60):
        """Wait for umwayi to exit, note which agent processes are still alive at that moment, then read its output.

        communicate() alone would wait for every process holding the output pipe, including an agent
        umwayi failed to stop, so a leftover agent could finish on its own and look stopped.
        """
        p.wait(timeout=timeout)
        self.exited_at = time.monotonic()  # when umwayi exited; the quiet wait below is not part of the stop
        self.alive_at_exit = self.agent_pids_alive()
        for pid in self.alive_at_exit:
            os.kill(pid, signal.SIGKILL)
        self.wait_root_quiet()
        if p.stdin is not None and p.stdin.closed:
            p.stdin = None  # the test wrote the prompt and closed it already
        out, err = p.communicate(timeout=30)
        self.assertIn(p.returncode, CODES, f"exit {p.returncode} is not allowed\n{out}\n{err}")
        return p.returncode, out, err

    def wait_for(self, pred, timeout: float = 30, what: str = "an event", proc=None) -> dict:
        """Wait for a call of the fake that matches pred.

        With proc (the umwayi process the test started), stop waiting as soon as umwayi has exited, since
        no agent can start after that, and fail with umwayi's exit code and output, which say why it
        stopped (a refusal, a broken logbook). On a timeout the output is shown too.
        """
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            exited = proc is not None and proc.poll() is not None
            for c in self.calls():
                if pred(c):
                    return c
            if exited:
                self.fail(f"umwayi exited (code {proc.returncode}) before {what}; calls: {self.calls()}\n"
                          f"{self._proc_output(proc)}\n{self._lock_state()}")
            time.sleep(0.05)
        self.fail(f"timed out after {timeout:g} s waiting for {what}; calls: {self.calls()}"
                  + (f"\n{self._proc_output(proc)}" if proc is not None else "") + f"\n{self._lock_state()}")

    def _proc_output(self, p) -> str:
        """umwayi's output for a failure message. A process still running is killed first, so its pipes close."""
        if p.poll() is None:
            p.kill()
        try:
            out, err = p.communicate(timeout=10)
        except (subprocess.TimeoutExpired, ValueError):
            return "umwayi output: not readable (a child still holds its pipes)"
        return f"umwayi stdout:\n{out}\numwayi stderr:\n{err}"

    def _lock_holder(self):
        """(pid or None, alive) for .umwayi/logbook.lock, or None when there is no lock file."""
        lock = self.root / ".umwayi" / "logbook.lock"
        try:
            text = lock.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError):
            return (None, False)
        pid = int(text) if text.isdigit() else None
        return (pid, pid is not None and alive(pid))

    def _lock_state(self) -> str:
        holder = self._lock_holder()
        if holder is None:
            return "logbook lock: free"
        pid, running = holder
        return (f"logbook lock: held by PID {pid}, {'still running' if running else 'no longer running'}"
                if pid is not None else "logbook lock: present, no PID written yet")

    def agent_pids_alive(self) -> list:
        pids = [c["pid"] for c in self.calls() if c.get("started") or c.get("event") == "spawn"]
        return [pid for pid in pids if alive(pid)]

    def started(self) -> list:
        return [c for c in self.calls() if c.get("started")]

    def tools(self) -> list:
        return [c for c in self.calls() if c.get("event") == "tool"]

    def wait_root_quiet(self, timeout: float = 30) -> None:
        """Wait until no process that works on this root is left (a hook, an `umwayi check` it started).

        After umwayi exits, a hook started by an agent that was just killed can still be writing the
        logbook. Reading the logbook in the middle of that write sees a hash that does not match yet.
        """
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
            if not busy:
                holder = self._lock_holder()
                if holder is None:
                    return
                if holder[0] is not None and not holder[1]:
                    return  # the writer that holds the lock is gone, so it will never be freed: entries() says so
            time.sleep(0.05)

    def entries(self, timeout: float = 30) -> list:
        """The logbook entries, read only when no writer is in the middle of a write.

        Every umwayi writer appends to LOGBOOK.md and then records its hash, both under
        .umwayi/logbook.lock; a read between the two sees a hash that does not match yet. So the read
        waits for the processes on this root to finish, then takes the same lock itself. A lock whose
        writer is no longer running is never freed, and the logbook it left is not a timing problem:
        that fails at once and says so.
        """
        from umwayi import logbook
        from umwayi.errors import UmwayiError
        self.wait_root_quiet()
        if not (self.root / logbook.LOGBOOK_NAME).exists():
            return logbook.read_checked(self.root)  # no logbook: nothing to lock, and no .umwayi is created
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            holder = self._lock_holder()
            if holder is not None and holder[0] is not None and not holder[1]:
                self.fail(f"the logbook writer PID {holder[0]} was stopped while it held the logbook lock, so "
                          f"the lock is never freed and the logbook may not match its hash: "
                          f"{self._record_state()}")
            try:
                with logbook._lock(self.root):  # no umwayi writer is between its append and its hash record
                    return logbook.read_checked(self.root)
            except UmwayiError as e:
                last = e
                time.sleep(0.1)
        self.fail(f"the logbook could not be read within {timeout:g} s: {last}\n{self._lock_state()}; "
                  f"{self._record_state()}")

    def _record_state(self) -> str:
        from umwayi import logbook
        try:
            data = (self.root / logbook.LOGBOOK_NAME).read_bytes()
        except OSError:
            return "LOGBOOK.md is not readable"
        return f"LOGBOOK.md against its recorded hash: {logbook._record_state(self.root, data)}"

    def run_entries(self) -> list:
        return [e for e in self.entries() if e.source == "umwayi agent run"]

    def write_rules(self, text: str = RULES):
        (self.root / "rules.yaml").write_text(text, encoding="utf-8")

    def script(self, *steps) -> dict:
        return {"FAKE_SCRIPT": json.dumps(list(steps))}

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


def alive(pid: int) -> bool:
    """True if the process exists and is not a zombie."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError, IndexError):
        return False
