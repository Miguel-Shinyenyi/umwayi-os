"""Shared helpers for the adapter tests: a fresh umwayi root, a fault injector, and real child processes."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRET = "sk-live-ADAPTER-TEST-SECRET"

# Loaded at start up in every child process when UMWAYI_FAULT is set: "module:function:effect".
SITECUSTOMIZE = r'''
import os
fault = os.environ.get("UMWAYI_FAULT")
if fault:
    import importlib, time
    module, name, effect = fault.split(":")
    try:
        mod = importlib.import_module(module)
    except ImportError:
        mod = None
    if mod is not None:
        real = getattr(mod, name)
        def patched(*a, **k):
            if effect == "crash":
                raise RuntimeError(os.environ.get("UMWAYI_FAULT_TEXT", "injected"))
            if effect == "interrupt":
                raise KeyboardInterrupt
            if effect == "hang":
                time.sleep(30)
            return real(*a, **k)
        setattr(mod, name, patched)
'''


class AdapterCase(unittest.TestCase):
    HOOK: Path = None
    RULES: Path = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-adapter-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "home"
        self.root.mkdir()
        shutil.copy(self.RULES, self.root / "rules.yaml")
        self.site = self.tmp / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"

    def raw(self, payload, args=None, fault=None, pythonpath=None, timeout=60):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "UMWAYI_FAULT")}
        env["PYTHONPATH"] = os.pathsep.join(pythonpath if pythonpath is not None else [str(self.site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = fault
            env["UMWAYI_FAULT_TEXT"] = SECRET
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = payload
        argv = args if args is not None else ["--root", str(self.root)]
        r = subprocess.run([sys.executable, str(self.HOOK), *argv], input=data, capture_output=True,
                           env=env, cwd=self.tmp, timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

    def umwayi(self, *args):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)

    def entries(self):
        if not self.log.exists():
            return []
        return [l for l in self.log.read_text(encoding="utf-8").splitlines() if l.startswith("- Source: ")]

    def added_lines(self):
        if not self.log.exists():
            return []
        return [l for l in self.log.read_text(encoding="utf-8").splitlines() if l.startswith("- Added: ")]

    def checked_lines(self):
        if not self.log.exists():
            return []
        return [l for l in self.log.read_text(encoding="utf-8").splitlines() if l.startswith("- Checked: ")]

    def queue_rows(self):
        q = self.root / "queue.md"
        if not q.exists():
            return []
        return [l for l in q.read_text(encoding="utf-8").splitlines() if l.startswith("| Q-")]

    def kill_on(self):
        r = self.umwayi("kill", "on")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def kill_off(self):
        r = self.umwayi("kill", "off")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def kill_unknown(self):
        d = self.root / ".umwayi"
        if d.exists():
            shutil.rmtree(d)
        d.write_text("not a folder")  # the kill switch state cannot be read
