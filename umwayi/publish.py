"""Layer 6: draft only publish step.

`umwayi publish-draft DRAFT` copies one draft from drafts/ to outbox/ as a
plain text file for the owner to post by hand. It never pushes, never uses
the network, never runs git or any other program, and never overwrites.

It asks the rules first with the action type `publish_draft`:
  * No stops it (exit 2).
  * Ask me first stops it (exit 3) unless the owner adds --approved-by NAME.
  * Yes lets it go on.
Every attempt that reaches the rules writes one logbook entry.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from umwayi import logbook, rules
from umwayi.config import load_config
from umwayi.errors import UmwayiError, UsageError
from umwayi.memory import is_private

DRAFTS_DIR = "drafts"
OUTBOX_DIR = "outbox"
MAX_DRAFT_BYTES = 1_000_000
MAX_NAME = 100
_DRAFT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.(md|txt)$")
ACTION = {"type": "publish_draft"}


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


def _resolve_draft(root: Path, draft: str) -> tuple[Path, str]:
    if not isinstance(draft, str) or not draft.strip():
        raise UmwayiError("publish: a draft file must be given")
    root_abs = Path(os.path.abspath(root))
    p = Path(draft)
    if ".." in p.parts:
        raise UmwayiError("publish: the draft path must not contain '..'")
    full = Path(os.path.normpath(p if p.is_absolute() else root_abs / p))
    if full.parent != root_abs / DRAFTS_DIR:
        raise UmwayiError("publish: the draft must be a file directly inside the drafts folder")
    if not _DRAFT_NAME.match(full.name):
        raise UmwayiError("publish: the draft name must be letters, digits, '.', '_' or '-', ending in .md or .txt")
    if (root_abs / DRAFTS_DIR).is_symlink():
        raise UmwayiError("publish: the drafts folder must not be a symbolic link")
    if full.is_symlink():
        raise UmwayiError("publish: the draft must not be a symbolic link")
    if not full.exists():
        raise UmwayiError("publish: the draft was not found")
    if not full.is_file():
        raise UmwayiError("publish: the draft must be a regular file")
    return full, f"{DRAFTS_DIR}/{full.name}"


def _read_draft(path: Path) -> bytes:
    try:
        size = path.stat().st_size
        if size > MAX_DRAFT_BYTES:
            raise UmwayiError(f"publish: the draft is larger than {MAX_DRAFT_BYTES} bytes")
        data = path.read_bytes()
    except OSError:
        raise UmwayiError("publish: the draft cannot be read") from None
    if not data.strip():
        raise UmwayiError("publish: the draft is empty")
    if b"\x00" in data:
        raise UmwayiError("publish: the draft is not plain text")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise UmwayiError("publish: the draft is not valid UTF-8 text") from None
    return data


def _stop_entry(today: str, rel: str, decision, note: str) -> logbook.Entry:
    who = f"rule {decision.rule_id}" if decision.rule_id else "no rule"
    return logbook.Entry(
        date=today,
        source="umwayi publish-draft",
        added=f"publish of {rel} stopped before copying: {who} gave {decision.answer}",
        checked=f"the draft is a readable text file in drafts; the rules were asked with action type {ACTION['type']}",
        not_done=f"Nothing was copied, published or pushed. {note}",
    )


def publish(root: Path, draft: str, today: str, approved_by: str | None = None) -> Result:
    root = Path(root)
    if approved_by is not None:
        approved_by = approved_by.strip()
        if not approved_by or len(approved_by) > MAX_NAME or not approved_by.isprintable():
            raise UsageError(f"publish: --approved-by must be one short line of plain text (1 to {MAX_NAME} characters)")

    # --- refusals before the rules are asked: nothing is logged, exit 1
    config = load_config(root)  # private paths unknown means refuse
    path, rel = _resolve_draft(root, draft)
    if is_private(rel, config.private_paths):
        raise UmwayiError("publish: the draft is a private path from umwayi.json")
    data = _read_draft(path)
    outbox = root / OUTBOX_DIR
    if outbox.is_symlink() or (outbox.exists() and not outbox.is_dir()):
        raise UmwayiError("publish: outbox must be a normal folder")
    target_name = Path(rel).stem + ".txt"
    target = outbox / target_name
    target_rel = f"{OUTBOX_DIR}/{target_name}"
    if target.exists() or target.is_symlink():
        raise UmwayiError(f"publish: {target_rel} already exists, nothing was copied (it is never overwritten)")

    # --- the rules
    decision = rules.check_in_root(json.dumps(ACTION), root / "rules.yaml", root, today)
    stop = None
    if decision.answer == rules.NO:
        stop = (2, "A rule says No.")
    elif decision.answer == rules.ASK and approved_by is None:
        stop = (3, "The owner can approve it with --approved-by NAME.")
    if stop is not None:
        code, note = stop
        lines = [decision.answer, f"Rule: {decision.rule_id or '(none)'}", f"Reason: {decision.reason}"]
        try:
            logbook.append(root, _stop_entry(today, rel, decision, note))
        except UmwayiError as e:
            why = str(e).rstrip(". ")
            lines.append(f"The logbook could not be written ({why}). Nothing was logged.")
        lines.append(f"Nothing was copied. {note}")
        return Result(code, lines)

    # --- copy, then log; undo the copy if the log fails
    try:
        outbox.mkdir(exist_ok=True)
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    except FileExistsError:
        raise UmwayiError(f"publish: {target_rel} already exists, nothing was copied") from None
    except OSError:
        raise UmwayiError("publish: the outbox file could not be created") from None
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        _unlink(target)
        raise UmwayiError("publish: the outbox file could not be written, nothing was copied") from None

    how = f"approved by {approved_by} after rule {decision.rule_id} gave Ask me first" if decision.answer == rules.ASK \
        else f"rule {decision.rule_id} gave Yes"
    entry = logbook.Entry(
        date=today,
        source="umwayi publish-draft",
        added=f"copied {rel} to {target_rel} ({len(data)} bytes, SHA-256 {logbook.sha256_hex(data)}); {how}",
        checked="the draft is a readable text file directly in drafts, not private, not a symbolic link; "
        "the outbox file was new",
        not_done="Nothing was published, posted, sent or pushed. No git command and no network were used. "
        "The owner posts it by hand.",
    )
    try:
        logbook.append(root, entry)
    except Exception as e:
        why = str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"
        if not _unlink(target):
            raise UmwayiError(f"the logbook write failed AND {target_rel} could not be removed, delete it by hand") from None
        if not isinstance(e, UmwayiError):
            raise  # the copy was removed; an unexpected error exits 2
        return Result(3, [
            rules.ASK,
            "Rule: (none)",
            f"Reason: The logbook could not be written ({why}). Nothing was logged, so nothing was copied.",
        ])
    return Result(0, [
        f"Copied {rel} to {target_rel}",
        f"Approved by: {approved_by}" if approved_by else f"Rule: {decision.rule_id} gave Yes",
        "Post it by hand. Nothing was published, sent or pushed.",
    ])


def _unlink(path: Path) -> bool:
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False
