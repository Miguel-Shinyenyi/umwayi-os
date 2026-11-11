"""Shared by tests/test_rulelog.py and tests/test_petition.py (layer 13, slice 3: Courts and the rules change log).

Every command under test runs as a real child process (`python -m umwayi ...`) in a temporary root, with HOME and
XDG_CONFIG_HOME in the temporary folder. A sitecustomize file sets the system date of the child
(UMWAYI_TEST_TODAY) and can plant a fault in one function (UMWAYI_FAULT=module:name:effect).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EM_DASH = "\u2014"
TODAY = "2026-11-17"
LOCKS = (".umwayi/logbook.lock", ".umwayi/petition.lock", ".umwayi/reopen.lock", ".umwayi/run.lock")

SITECUSTOMIZE = r'''
import os
t = os.environ.get("UMWAYI_TEST_TODAY")
if t:
    import umwayi.cli as _c
    import umwayi.rules as _r
    _c._today = lambda: t
    _r.system_today = lambda: t
fault = os.environ.get("UMWAYI_FAULT")
if fault:
    import importlib, time
    module, name, effect = fault.split(":")
    mod = importlib.import_module(module)
    real = getattr(mod, name)
    def patched(*a, **k):
        if effect == "crash":
            raise RuntimeError(os.environ.get("UMWAYI_FAULT_TEXT", "injected"))
        if effect == "error":
            from umwayi.errors import UmwayiError
            raise UmwayiError("planted: this write fails")
        if effect == "pause":
            time.sleep(float(os.environ.get("UMWAYI_FAULT_PAUSE", "1")))
        return real(*a, **k)
    setattr(mod, name, patched)
'''

RULES_SOURCE = "umwayi rules"
RULES_CHECKED_HEAD = ("rules.yaml was read and parsed before this entry; this entry is written before the new rules "
                      "are first used; state: ")
RULES_NOT_DONE = "Only rule ids, verdicts, dates and counts are logged, not rule text. No action was checked by this entry."


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rule(rid, verdict="yes", type_="read", review_by=None, title=None, text=None, cause=None):
    lines = [f"  - id: {rid}", f"    title: {title or 'Title of ' + rid}", f"    text: {text or 'Text of ' + rid}"]
    if cause:
        lines.append(f"    cause: {cause}")
    lines.append(f"    verdict: {verdict}")
    if review_by:
        lines.append(f"    review_by: {review_by}")
    lines += ["    matchers:", f"      type: {type_}"]
    return "\n".join(lines) + "\n"


def rules_file(*rules) -> str:
    return "rules:\n" + "\n".join(rules)


def blocks(text: str) -> list:
    """Every entry of a logbook text, read here by the format rule: a dict per entry, oldest first."""
    lines = text.split("\n")
    out = []
    for h, line in enumerate(lines):
        if not line.startswith("## ") or h + 5 >= len(lines):
            continue
        b = {"date": line[3:]}
        for i, (label, key) in enumerate((("Source", "source"), ("Added", "added"), ("Checked", "checked"),
                                          ("Not done", "not_done"))):
            b[key] = lines[h + 2 + i][len(f"- {label}: "):]
        nxt = lines[h + 6] if h + 6 < len(lines) else ""
        b["chain"] = nxt[len("- Chain: "):] if nxt.startswith("- Chain: ") else None
        out.append(b)
    return out


def snapshot(root: Path) -> dict:
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            full = Path(dp) / f
            rel = full.relative_to(root).as_posix()
            if rel not in LOCKS and "__pycache__" not in rel:
                out[rel] = full.read_bytes()
    return out


class CourtsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-courts-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(os.path.realpath(self._tmp.name))
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.site = self.tmp / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"
        self.q = self.root / "queue.md"
        self.rules_path = self.root / "rules.yaml"
        self.rec = self.root / ".umwayi" / "logbook.sha256"

    def env(self, fault=None, extra=None, today=TODAY):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT", "UMWAYI_FAULT_PAUSE", "UMWAYI_TEST_TODAY", "HOME",
                            "XDG_CONFIG_HOME")}
        env["HOME"] = str(self.home)
        env["XDG_CONFIG_HOME"] = str(self.home / ".config")
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(REPO)])
        if today:
            env["UMWAYI_TEST_TODAY"] = today
        if fault:
            env["UMWAYI_FAULT"] = fault
        env.update(extra or {})
        return env

    def u(self, *args, fault=None, extra=None, today=TODAY, stdin=None):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args], capture_output=True,
                              text=True, timeout=120, env=self.env(fault, extra, today), cwd=str(self.tmp), input=stdin)

    def popen(self, *args, fault=None, extra=None, today=TODAY):
        return subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=self.env(fault, extra, today), cwd=str(self.tmp))

    def write_rules(self, text: str):
        self.rules_path.write_text(text, encoding="utf-8")

    def repo_rules(self):
        shutil.copy(REPO / "rules.yaml", self.rules_path)

    def check(self, action, *extra, **kw):
        if not isinstance(action, str):
            action = json.dumps(action)
        return self.u("check", action, *extra, **kw)

    def check_json(self, action, *extra, **kw):
        r = self.check(action, "--json", *extra, **kw)
        return r.returncode, json.loads(r.stdout)

    def logtext(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def entries(self) -> list:
        return blocks(self.logtext())

    def sources(self) -> list:
        return [b["source"] for b in self.entries()]

    def rule_entries(self) -> list:
        return [b for b in self.entries() if b["source"] == RULES_SOURCE]

    def rerecord(self):
        self.rec.write_text(sha(self.log.read_bytes()) + "\n", encoding="ascii")

    def rows(self) -> list:
        if not self.q.exists():
            return []
        return [l for l in self.q.read_text(encoding="utf-8").splitlines() if l.startswith("| Q-")]

    def assert_clean_output(self, r, *secrets):
        text = r.stdout + r.stderr
        self.assertNotIn("Traceback", text)
        self.assertNotIn(EM_DASH, text)
        for s in secrets:
            self.assertNotIn(s, text)


_REGEX_CACHE = {}


def fullmatch(pattern: str, value: str):
    rx = _REGEX_CACHE.setdefault(pattern, re.compile(pattern))
    return rx.fullmatch(value)
