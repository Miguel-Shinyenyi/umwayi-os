"""W33: `umwayi feedback export`. A summary of the logbook that a tester can paste into a feedback issue.

    umwayi feedback export

It prints counts and dates and nothing else: the number of entries, the count of entries for each kind (the command that
wrote it, from a fixed list of names; any other source is counted as "other"), the count of the checks for each verdict
(Yes, No, Ask me first), the first and last date, whether the hash chain is intact, and the budget spent in UU.

It holds no path, no command text, no rule text, no file content and no text of any logbook entry. Every word it prints is
a fixed word of this file or a number or a date in the fixed form YYYY-MM-DD. It reads only: it writes no file and appends
no logbook entry. It uses the layer's own readers (logbook.verify for the tamper check and the chain, logbook.read_checked_chain
for the entries, budget.parse_ledger and budget.day_totals for the budget).

Fail closed: a logbook that does not pass its check (a hand edit, a broken chain, a format problem, an unreadable file) gives
exit 2 and no summary at all, and the message holds no text of the logbook.

Exit codes: 0 done, 2 the logbook failed its check or an unexpected error, 64 usage. Never 1 or 3.
Standard library only.

W29: `redact` below is the one filter of everything a feedback bundle holds (tokens and keys, a secret after a key word, a
password in an address, emails, home paths of macOS, Linux and Windows, the tester's own home folder, the root path and the
user name). It is pure: text in, text out. `umwayi feedback send` (umwayi/feedbacksend.py) uses it and is the only feedback
code that writes; this module stays read only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from umwayi import budget, logbook, units
from umwayi.errors import UmwayiError

# The kinds that are named. A source that is not one of these is counted as "other", so a source that holds text of the
# owner (a name, a path) can never reach the output.
KINDS = (
    "umwayi agent run", "umwayi archive move", "umwayi autonomy", "umwayi autonomy record", "umwayi budget", "umwayi check",
    "umwayi decision reopen", "umwayi goal", "umwayi kill", "umwayi logbook recover", "umwayi logbook seal", "umwayi petition",
    "umwayi publish-draft", "umwayi queue add", "umwayi queue answer", "umwayi queue close", "umwayi queue migrate",
    "umwayi report", "umwayi rules", "umwayi run", "umwayi schedule", "umwayi serve", "umwayi view snapshot",
    "umwayi feedback send",
)
OTHER = "other"
CHECK_KIND = "umwayi check"
VERDICTS = ("Yes", "No", "Ask me first")
UNREADABLE = "unreadable"
# "<who> gave <verdict>" at the start of the Added line of a check. <who> is a rule id, "No rule" or the word of what
# stopped the check; it is never printed.
_GAVE = re.compile(r"^[^;]{1,120}? gave (Yes|No|Ask me first)(?: and autonomy moved it to Yes)?;")

REFUSED = ("feedback: the logbook did not pass its check, so no summary was made. Nothing was changed. "
           "Run 'umwayi logbook verify' yourself, and read what it says before you share it.")
NO_LOGBOOK = ("feedback: there is no logbook in this folder yet, so there is nothing to summarise. Nothing was changed. "
              "Run umwayi in the folder you used, or use --root.")
HEADER = "umwayi feedback export: counts and dates only; no paths, commands, rules or file contents."


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


def kind_of(source: str) -> str:
    return source if source in KINDS else OTHER


def verdict_of(added: str) -> str:
    m = _GAVE.match(added)
    return m.group(1) if m else UNREADABLE


def _budget_uu(entries: list) -> int:
    led = budget.parse_ledger(entries)
    micros = 0
    for day in sorted({r.date for r in led.reserves.values()}):
        t = budget.day_totals(led, day)
        micros += t.used + t.reserved  # an open reservation counts in full
    return units.uu(micros)


def summary(entries: list, chain_length: int) -> list:
    """The lines of the summary, from entries that already passed the checked readers."""
    kinds = {}
    verdicts = {v: 0 for v in (*VERDICTS, UNREADABLE)}
    for e in entries:
        k = kind_of(e.source)
        kinds[k] = kinds.get(k, 0) + 1
        if e.source == CHECK_KIND:
            verdicts[verdict_of(e.added)] += 1
    lines = [HEADER, f"entries: {len(entries)}", "entries by kind:"]
    named = sorted(k for k in kinds if k != OTHER)
    lines += [f"  {k}: {kinds[k]}" for k in named]
    if OTHER in kinds:
        lines.append(f"  {OTHER}: {kinds[OTHER]}")
    if not kinds:
        lines.append("  none")
    lines.append(f"checks by verdict ({CHECK_KIND}):")
    lines += [f"  {v}: {n}" for v, n in verdicts.items()]
    dates = sorted(e.date for e in entries)
    lines.append(f"dates: first {dates[0]}, last {dates[-1]}" if dates else "dates: none")
    lines.append(f"chain: intact, {chain_length} entries in the chain" if chain_length else "chain: not started")
    lines.append(f"budget spent: {_budget_uu(entries)} UU (an open reservation counts in full)")
    return lines


def export(root) -> Result:
    root = Path(root)
    try:
        if not (root / "LOGBOOK.md").is_file():
            return Result(2, [NO_LOGBOOK])
        report = logbook.verify(root)
        if report.problems:
            return Result(2, [REFUSED])
        entries, chain_length = logbook.read_checked_chain(root)
        return Result(0, summary(entries, chain_length))
    except UmwayiError:
        return Result(2, [REFUSED])


# ------------------------------------------------------------------------------------------------ W29: the filter

HIDDEN_SECRET, HIDDEN_EMAIL, HIDDEN_PATH = "[hidden secret]", "[hidden email]", "[hidden path]"
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|PRIVATE KEY-----")
_TOKENS = re.compile(
    r"\b(?:sk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{12,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{16,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}"
    r"|umt1_[A-Za-z0-9_-]{20,}|npm_[A-Za-z0-9]{30,})")
_BEARER = re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}")
_KEYED = re.compile(r"(?i)\b((?:pass(?:word|wd)?|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|auth"
                    r"|authorization|credentials?)\s*[:=]\s*)(?!\[hidden)\S+")
_URL_PASSWORD = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
_HOME_PATH = re.compile(r"(?:(?<![\w/])/(?:Users|home)/[^\s/]+|(?<![\w/])/root(?=/|\b)|(?<![\w])~/"
                        r"|\b[A-Za-z]:\\Users\\[^\s\\]+)[^\s]*")
_LONG_WORD = re.compile(r"(?<![\w/.-])[A-Za-z0-9+/=_-]{32,}(?![\w/.-])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]")


def _real(path):
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError, ValueError):
        return path


def redact(text, home=None, root=None, user=None):
    """(the text with every secret, email and home path replaced, how many things were replaced). One line in, one line
    out: control characters become spaces. This is the one filter every line of a feedback bundle goes through."""
    t = _CONTROL.sub(" ", str(text))
    if _PRIVATE_KEY.search(t):
        return HIDDEN_SECRET, 1
    count = 0

    def sub(rx, repl, s):
        nonlocal count
        out, n = rx.subn(repl, s)
        count += n
        return out

    for literal in sorted({p for p in (root, home) if p and len(p) > 1 and p != "/"}, key=len, reverse=True):
        for form in {literal, _real(literal)}:
            if form and form in t:
                count += t.count(form)
                t = t.replace(form, HIDDEN_PATH)
    t = sub(_URL_PASSWORD, lambda m: m.group(1) + HIDDEN_SECRET + "@", t)
    t = sub(_EMAIL, HIDDEN_EMAIL, t)
    t = sub(_TOKENS, HIDDEN_SECRET, t)
    t = sub(_BEARER, lambda m: m.group(1) + " " + HIDDEN_SECRET, t)
    t = sub(_KEYED, lambda m: m.group(1) + HIDDEN_SECRET, t)
    t = sub(_HOME_PATH, HIDDEN_PATH, t)
    def long_word(m):
        nonlocal count
        w = m.group(0)
        if re.search(r"[A-Za-z]", w) and re.search(r"\d", w):
            count += 1
            return HIDDEN_SECRET
        return w

    t = _LONG_WORD.sub(long_word, t)
    if user and len(user) >= 3:
        t = sub(re.compile(rf"(?<![\w-]){re.escape(user)}(?![\w-])"), HIDDEN_PATH, t)
    return t, count
