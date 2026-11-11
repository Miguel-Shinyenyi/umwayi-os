"""Shared by tests/autonomy/ (layer 13, slice 5: graded autonomy, requirements 13.R9 to 13.R12).

Every command under test runs as a real child process (`python -m umwayi ...`) in a temporary root, with HOME and
XDG_CONFIG_HOME in the temporary folder and the system date set by UMWAYI_TEST_TODAY (tests/courts_support.py).

The owner's record is written through the real code, not by hand: `seed` runs one child process that calls
`umwayi.autonomy.record` once per outcome (the function behind `umwayi autonomy record`), oldest first, because
hundreds of separate child processes would make the suite slow. A few tests use the command itself. The only
entries written by hand are the forged inputs, on purpose.
"""

import json
import subprocess
import sys

from tests.courts_support import CourtsCase, REPO  # noqa: F401  (REPO is used by the test modules)

TODAY = "2026-12-01"
SETTINGS = {
    "version": 1, "enabled": "true", "window_days": 90, "min_decisions": 30, "min_lower_bound": 850,
    "confidence_z": 258, "revert_weight": 3, "max_cost_uu": 10, "cooldown_days": 30, "max_moves_per_day": 5,
}
ACTION = {"type": "tool_bash", "command": "git commit -m 'a change'"}


def settings_text(**over) -> str:
    values = dict(SETTINGS, **over)
    return "".join(f"{k}: {v}\n" for k, v in values.items() if v is not None)


def opt_in_rule(rid="commit-ask", cls="git-commit", reversible="true", cost=2, review_by=None,
                matchers="      type: tool_bash\n      command__contains: git commit\n", title=None, text=None,
                cause=None, autonomy=None):
    lines = [f"  - id: {rid}", f"    title: {title or 'A commit asks the owner'}",
             f"    text: {text or 'The owner is asked before an AI helper commits.'}"]
    if cause:
        lines.append(f"    cause: {cause}")
    lines.append("    verdict: ask")
    if review_by:
        lines.append(f"    review_by: {review_by}")
    if autonomy is not None:
        lines.append(autonomy.rstrip("\n"))
    else:
        lines += ["    autonomy:", f"      class: {cls}", f"      reversible: {reversible}", f"      cost_uu: {cost}"]
    lines.append("    matchers:")
    return "\n".join(lines) + "\n" + matchers


def plain_rule(rid, verdict, matchers, review_by=None, title=None, text=None, cause=None):
    lines = [f"  - id: {rid}", f"    title: {title or 'Title of ' + rid}", f"    text: {text or 'Text of ' + rid}"]
    if cause:
        lines.append(f"    cause: {cause}")
    lines.append(f"    verdict: {verdict}")
    if review_by:
        lines.append(f"    review_by: {review_by}")
    lines.append("    matchers:")
    return "\n".join(lines) + "\n" + matchers


def rules_text(*rules) -> str:
    return "rules:\n" + "\n".join(rules)


SEED = r'''
import json, sys
from pathlib import Path
from umwayi import autonomy
root = Path(sys.argv[1])
for cls, outcome, date, ref in json.loads(sys.argv[2]):
    autonomy.record(root, cls, outcome, "Owner", ref, date)
'''


class AutonomyCase(CourtsCase):
    def setUp(self):
        super().setUp()
        self.write_rules(rules_text(opt_in_rule()))

    # ---------------------------------------------------------------- the root

    def u(self, *args, today=TODAY, **kw):
        return super().u(*args, today=today, **kw)

    def settings(self, text=None, **over):
        (self.root / "autonomy.yaml").write_text(settings_text(**over) if text is None else text, encoding="utf-8")

    def chain(self, date="2026-08-01"):
        """A logbook with the hash chain started (the owner runs `umwayi logbook seal --chain` once)."""
        if not self.log.exists():
            from umwayi import logbook
            logbook.append(self.root, logbook.Entry(date, "umwayi test", "the first entry", "nothing", "nothing"))
        r = self.u("logbook", "seal", "--chain", "--by", "Owner", "--date", date)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def seed(self, approved=0, edited=0, rejected=0, reverted=0, cls="git-commit", dates=None, refs=False):
        """Record outcomes through umwayi.autonomy.record, oldest first. `dates` maps an outcome to its date; the
        default spreads them from 2026-09-10 to 2026-11-20, inside the 90 day window that ends on TODAY."""
        rows = []
        days = ["2026-09-10", "2026-10-01", "2026-10-20", "2026-11-05", "2026-11-20"]
        n = 0
        for outcome, count in (("approved", approved), ("edited", edited), ("rejected", rejected),
                               ("reverted", reverted)):
            for i in range(count):
                day = (dates or {}).get(outcome) or days[(n * len(days)) // max(1, approved + edited + rejected
                                                                                   + reverted)]
                rows.append([cls, outcome, day, f"Q-{9000 + n:04d}" if refs else None])
                n += 1
        rows.sort(key=lambda r: r[2])
        if rows:
            r = subprocess.run([sys.executable, "-c", SEED, str(self.root), json.dumps(rows)], capture_output=True,
                               text=True, env=self.env(), cwd=str(self.tmp), timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def ready(self, approved=80, edited=2, rejected=0, reverted=0, **settings):
        """The worked example's root: chain started, the record seeded, autonomy.yaml on."""
        self.chain()
        self.seed(approved, edited, rejected, reverted)
        self.settings(**settings)

    # ---------------------------------------------------------------- reading

    def ask(self, action=None, *extra, **kw):
        r = self.u("check", json.dumps(action or ACTION), "--json", *extra, **kw)
        try:
            data = json.loads(r.stdout)
        except ValueError:
            data = None
        return r.returncode, data, r

    def last_check(self):
        return [b for b in self.entries() if b["source"] == "umwayi check"][-1]

    def gate_word(self):
        checked = self.last_check()["checked"]
        marker = "; autonomy: no move ("
        if marker not in checked:
            return None
        return checked.split(marker, 1)[1].rstrip(")")

    def assert_no_move(self, word, action=None, *extra, code=3, answer="Ask me first"):
        c, data, r = self.ask(action, *extra)
        self.assertEqual((c, data["answer"] if data else None), (code, answer), r.stdout + r.stderr)
        if word is None:
            self.assertNotIn("autonomy", self.last_check()["checked"])
            self.assertNotIn("autonomy", data)
        else:
            self.assertEqual(self.gate_word(), word, self.last_check()["checked"])
            self.assertEqual(data["autonomy"], {"moved": False, "gate": word})
        self.assertNotIn("autonomy moved it to Yes", self.last_check()["added"])
        return data
