"""Command line entry point: `umwayi`.

Exit codes:
  umwayi check:  0 Yes, 2 No, 3 Ask me first
  usage errors:  64 (never 0, 2 or 3)
  other errors:  1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from umwayi import __version__, archive, jobs, logbook, publish, report, rules, taskqueue
from umwayi.config import load_config
from umwayi.errors import UmwayiError, UsageError
from umwayi.memory import load_bundle

EXIT_USAGE = 64
EXIT_ERROR = 1


def _today() -> str:
    """The system clock. Dates are never inferred from the queue itself."""
    return date.today().isoformat()


def _date_arg(value: str) -> str:
    if not taskqueue.is_valid_date(value):
        raise argparse.ArgumentTypeError("must be a real date in the form YYYY-MM-DD")
    return value


def _lines_arg(value: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)-(\d+)", value)
    if not m:
        raise argparse.ArgumentTypeError("must look like 10-20 (first and last line, counting from 1)")
    return int(m.group(1)), int(m.group(2))


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse would exit 2, which means "No"
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="umwayi", description="umwayi-os: an AI operating system for one person and their AI helpers.")
    p.add_argument("--version", action="version", version=f"umwayi {__version__}")
    p.add_argument("--root", default=".", help="folder that holds umwayi.json and rules.yaml (default: current folder)")
    sub = p.add_subparsers(dest="command", parser_class=_Parser)

    mem = sub.add_parser("memory", help="memory commands")
    msub = mem.add_subparsers(dest="memory_command", parser_class=_Parser)
    b = msub.add_parser("bundle", help="print the context bundle for an AI helper")
    b.add_argument("--format", choices=["text", "json"], default="text")

    q = sub.add_parser("queue", help="queue commands (queue.md)")
    qsub = q.add_subparsers(dest="queue_command", parser_class=_Parser)
    ql = qsub.add_parser("list", help="list rows of the queue")
    ql.add_argument("--status", choices=taskqueue.STATUSES, help="only rows with this status")
    ql.add_argument("--kind", choices=taskqueue.KINDS, help="only rows of this kind")
    qa = qsub.add_parser("add", help="add an open task or decision")
    qa.add_argument("--kind", required=True, choices=taskqueue.KINDS)
    qa.add_argument("title", help="short title, one line, no | character")
    qa.add_argument("--recommendation", default="", help="recommendation for the owner (optional)")
    qn = qsub.add_parser("answer", help="mark an open row as answered")
    qn.add_argument("id", help="row id, for example Q-0001")
    qn.add_argument("--answer", required=True, help="the answer text (one line, no | character, up to 500 characters)")
    qc = qsub.add_parser("close", help="close a row")
    qc.add_argument("id", help="row id, for example Q-0001")
    qm = qsub.add_parser("migrate", help="convert an old six column queue.md to the current layout (once)")
    for sp in (qa, qn, qc, qm):
        sp.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    ar = sub.add_parser("archive", help="archive commands")
    arsub = ar.add_subparsers(dest="archive_command", parser_class=_Parser)
    am = arsub.add_parser("move", help="move a block of text out of a file into the archive")
    am.add_argument("source", help="the file to cut the block from, relative to the root")
    am.add_argument("--reason", required=True, help="why the block is moved (one line, no | character)")
    am.add_argument("--lines", type=_lines_arg, help="first and last line to move, for example 10-20")
    am.add_argument("--start", help="a line that starts the block (the whole line must match, the line is included)")
    am.add_argument("--end", help="a line that ends the block (the whole line must match, the line is included)")
    am.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    arsub.add_parser("verify", help="recompute every SHA-256 fingerprint and compare with archive/INDEX.md")

    c = sub.add_parser(
        "check",
        help="check an action (JSON) against the rules: Yes (0), No (2), Ask me first (3)",
    )
    c.add_argument("action", nargs="?", help="action as JSON, or '-' to read it from standard input")
    c.add_argument("--rules", help="path to rules.yaml (default: <root>/rules.yaml)")
    c.add_argument("--json", action="store_true", help="print the answer as JSON")
    c.add_argument("--no-log", action="store_true", help="dry run: do not write the logbook entry")
    c.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD for the logbook entry (default: today)")

    rn = sub.add_parser("run", help="run one job from a jobs file (asks the rules first)")
    rn.add_argument("jobfile", help="the jobs file, for example jobs.yaml")
    rn.add_argument("--job", help="the job name (needed when the file has more than one job)")
    rn.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    rp = sub.add_parser("report", help="write a progress report draft from git history")
    rp.add_argument("--since", type=_date_arg, required=True, help="first day, YYYY-MM-DD")
    rp.add_argument("--date", type=_date_arg, help="today, YYYY-MM-DD (default: the system clock)")

    pd = sub.add_parser("publish-draft", help="copy a draft to outbox/ for the owner to post by hand")
    pd.add_argument("draft", help="a file directly inside drafts/")
    pd.add_argument("--approved-by", help="the owner's name, needed when the rules say Ask me first")
    pd.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    lg = sub.add_parser("logbook", help="logbook commands")
    lgsub = lg.add_subparsers(dest="logbook_command", parser_class=_Parser)
    lgsub.add_parser("verify", help="check the format and the hash record of LOGBOOK.md (changes nothing)")
    ls = lgsub.add_parser("seal", help="record the hash of LOGBOOK.md as it is now (explicit, never automatic)")
    ls.add_argument("--by", required=True, help="who seals it, one short line of plain text")
    ls.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")
    return p


def _cmd_check(args, out) -> int:
    root = Path(args.root)
    rules_path = Path(args.rules) if args.rules else root / "rules.yaml"
    action_text = args.action
    if action_text == "-":
        try:
            action_text = sys.stdin.read(rules.MAX_ACTION_BYTES + 1)
        except Exception:
            action_text = None
    decision, logged = rules.check_and_log(
        action_text, rules_path, root, args.date or _today(), log=not args.no_log
    )
    if args.json:
        data = decision.to_dict()
        data["logged"] = logged
        out.write(json.dumps(data, indent=2) + "\n")
    else:
        out.write(decision.render())
        if args.no_log:
            out.write("Nothing was logged (--no-log, dry run).\n")
    return decision.exit_code


def _cmd_run(args, out) -> int:
    r = jobs.run(Path(args.root), Path(args.jobfile), args.job, args.date or _today())
    out.write("\n".join(r.lines) + "\n")
    return r.code


def _cmd_report(args, out) -> int:
    rep, rel = report.make(Path(args.root), args.since, args.date or _today())
    out.write(f"Wrote {rel}: {len(rep.commits)} commits from {rep.since} to {rep.until}.\n")
    out.write("It is a draft. Nothing was published or pushed.\n")
    return 0


def _cmd_publish(args, out) -> int:
    r = publish.publish(Path(args.root), args.draft, args.date or _today(), args.approved_by)
    out.write("\n".join(r.lines) + "\n")
    return r.code


def _cmd_logbook(args, out) -> int:
    root = Path(args.root)
    if args.logbook_command == "seal":
        r = logbook.seal(root, args.date or _today(), args.by)
        out.write(f"Sealed LOGBOOK.md: {r.entries_before} earlier entries, hash recorded.\n")
        out.write(f"SHA-256: {r.sha256}\n")
        return 0
    report = logbook.verify(root)
    if not report.problems:
        out.write(f"ok: {report.entries} entries, the format is valid and the hash matches the record\n")
        return 0
    for p in report.problems:
        out.write(f"problem: {p.render()}\n")
    out.write(f"{len(report.problems)} problem(s) found\n")
    return 1


def _cmd_memory_bundle(args, out) -> int:
    config = load_config(Path(args.root))
    bundle = load_bundle(config)
    out.write(bundle.to_json() + "\n" if args.format == "json" else bundle.render())
    return 0


def _cmd_queue(args, out) -> int:
    root = Path(args.root)
    cmd = args.queue_command
    if cmd == "list":
        rows = taskqueue.list_rows(root, status=args.status, kind=args.kind)
        if not rows:
            out.write("No rows.\n")
            return 0
        for r in rows:
            line = f"{r.id}  {r.kind:<8}  {r.status:<8}  {r.answered or '-':<10}  {r.title}"
            if r.recommendation:
                line += f"  [recommendation: {r.recommendation}]"
            if r.answer:
                line += f"  [answer: {r.answer}]"
            out.write(line + "\n")
        return 0
    when = args.date or _today()
    if cmd == "add":
        row = taskqueue.add(root, args.kind, args.title, args.recommendation, when)
        out.write(f"Added {row.id} ({row.kind}): {row.title}\n")
    elif cmd == "answer":
        row = taskqueue.answer(root, args.id, args.answer, when)
        out.write(f"Answered {row.id} on {row.answered}\n")
    elif cmd == "close":
        row = taskqueue.close(root, args.id, when)
        out.write(f"Closed {row.id}\n")
    else:
        count = taskqueue.migrate(root, when)
        out.write(f"Migrated queue.md: {count} rows now have an answer column\n")
    return 0


def _cmd_archive(args, out) -> int:
    root = Path(args.root)
    if args.archive_command == "move":
        has_markers = args.start is not None or args.end is not None
        if (args.lines is None) == (not has_markers) or (has_markers and (args.start is None or args.end is None)):
            sys.stderr.write("umwayi archive move: error: give either --lines, or both --start and --end\n")
            return EXIT_USAGE
        r = archive.move(
            root, args.source, args.reason, args.date or _today(),
            lines=args.lines, start=args.start, end=args.end,
        )
        out.write(f"Moved lines {r.first_line}-{r.last_line} of {r.source} to {r.archive_path}\n")
        out.write(f"Id: {r.id}\n")
        out.write(f"Words: {r.words}\n")
        out.write(f"SHA-256: {r.sha256}\n")
        out.write(f"Pointer line left in {r.source}: {r.pointer}\n")
        out.write(f"To put it back later: umwayi archive restore {r.id} (this command is not built yet)\n")
        return 0
    results = archive.verify(root)
    counts = {s: 0 for s in (archive.OK, archive.CHANGED, archive.MISSING, archive.NOT_IN_INDEX)}
    for r in results:
        counts[r.status] += 1
        out.write(f"{r.id}  {r.status}  {r.path}\n")
    out.write(
        f"Checked {len(results)} archive files: {counts[archive.OK]} ok, {counts[archive.CHANGED]} changed, "
        f"{counts[archive.MISSING]} missing, {counts[archive.NOT_IN_INDEX]} not in the index\n"
    )
    return 0 if counts[archive.OK] == len(results) else 1


def main(argv: list[str] | None = None, out=None) -> int:
    out = out or sys.stdout
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_USAGE
    try:
        if args.command == "check":
            return _cmd_check(args, out)
        if args.command == "queue" and getattr(args, "queue_command", None):
            return _cmd_queue(args, out)
        if args.command == "run":
            return _cmd_run(args, out)
        if args.command == "report":
            return _cmd_report(args, out)
        if args.command == "publish-draft":
            return _cmd_publish(args, out)
        if args.command == "logbook" and getattr(args, "logbook_command", None):
            return _cmd_logbook(args, out)
        if args.command == "archive" and getattr(args, "archive_command", None):
            return _cmd_archive(args, out)
        if args.command == "memory" and getattr(args, "memory_command", None) == "bundle":
            return _cmd_memory_bundle(args, out)
    except UsageError as e:
        sys.stderr.write(f"umwayi: error: {e}\n")
        return EXIT_USAGE
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_ERROR
    parser.print_usage(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
