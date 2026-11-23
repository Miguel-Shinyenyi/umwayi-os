"""W78 step 8 (W41 C2): tool calls the platform reported and no hook checked.

Claude Code reports every tool call to umwayi's own receiver on 127.0.0.1 (`tool_result` and `tool_decision` events) with the
call's `tool_use_id`. The hook gives the same id to `umwayi check`, which keeps it in the Checked line of its entry. After a run,
every reported id with no check entry written during the run is a finding: the call ran without the hook, for example because
the platform's hooks were turned off by a setting umwayi does not read.

It detects after the fact. It does not stop the call, undo it or show what it did. Only an id and a tool name are kept; no input,
no result and no parameter, because OTEL_LOG_TOOL_DETAILS stays 0. Claude Code only: Kiro and OpenCode send umwayi nothing.
When no log report arrived, it says it cannot tell and never says that every call was checked.
"""
from __future__ import annotations

import re
from pathlib import Path

from umwayi import logbook
from umwayi.errors import UmwayiError

CHECK_SOURCE = "umwayi check"
_ID = re.compile(r"; tool use id: ([A-Za-z0-9_-]{1,64})(?:;|$)")
MAX_NAMED = 10
OK, FOUND, CANNOT_TELL = "ok", "found", "cannot_tell"


def mark(root) -> int | None:
    """How many entries the logbook holds now, or None when it cannot be read with its checks."""
    try:
        return len(logbook.read_checked(Path(root)))
    except UmwayiError:
        return None


def checked_ids(root, since: int | None) -> set | None:
    """The tool_use_ids named by the `umwayi check` entries written after `since`, or None when the logbook cannot be read."""
    if since is None:
        return None
    try:
        entries = logbook.read_checked(Path(root))
    except UmwayiError:
        return None
    found = set()
    for e in entries[since:]:
        if getattr(e, "source", None) == CHECK_SOURCE:
            m = _ID.search(getattr(e, "checked", "") or "")
            if m:
                found.add(m.group(1))
    return found


def review(root, since: int | None, report: dict | None) -> tuple:
    """(status, [(id, tool name), ...]): `found` with the calls (sorted by id) the platform reported and no entry names; `ok` when
    every reported call has an entry; `cannot_tell` when no log report arrived (no api_request event was counted), the report
    was invalid, or the logbook could not be read. An empty reported set with a report that arrived is `ok`: no call was made."""
    if report is None or report.get("invalid") or not report.get("requests") or report.get("tools_bad"):
        return CANNOT_TELL, []
    seen = checked_ids(root, since)
    if seen is None:
        return CANNOT_TELL, []
    missing = sorted((i, n) for i, n in report.get("tools", {}).items() if i not in seen)
    return (FOUND, missing) if missing else (OK, [])


def entry_lines(agent: str, missing: list) -> tuple:
    """(added, checked) of the one logbook entry of a finding. Ids and tool names only, at most MAX_NAMED of them."""
    shown = ", ".join(f"{i} ({n})" for i, n in missing[:MAX_NAMED])
    more = len(missing) - MAX_NAMED
    return (f"Unchecked tool calls during the run of agent {agent}: {len(missing)}",
            f"tool calls the platform reported with no check entry: {shown}" + (f", and {more} more" if more > 0 else ""))
