"""Command line entry point: `umwayi`.

Exit codes:
  umwayi check:  0 Yes, 2 No, 3 Ask me first
  usage errors:  64 (never 0, 2 or 3)
  other errors:  1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from umwayi import __version__, rules, taskqueue
from umwayi.config import load_config
from umwayi.errors import UmwayiError
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
    qc = qsub.add_parser("close", help="close a row")
    qc.add_argument("id", help="row id, for example Q-0001")
    for sp in (qa, qn, qc):
        sp.add_argument("--date", type=_date_arg, help="date YYYY-MM-DD (default: today, from the system clock)")

    c = sub.add_parser(
        "check",
        help="check an action (JSON) against the rules: Yes (0), No (2), Ask me first (3)",
    )
    c.add_argument("action", nargs="?", help="action as JSON, or '-' to read it from standard input")
    c.add_argument("--rules", help="path to rules.yaml (default: <root>/rules.yaml)")
    c.add_argument("--json", action="store_true", help="print the answer as JSON")
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
    decision = rules.check(action_text, rules_path)
    if args.json:
        out.write(json.dumps(decision.to_dict(), indent=2) + "\n")
    else:
        out.write(decision.render())
    return decision.exit_code


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
            out.write(line + "\n")
        return 0
    when = args.date or _today()
    if cmd == "add":
        row = taskqueue.add(root, args.kind, args.title, args.recommendation, when)
        out.write(f"Added {row.id} ({row.kind}): {row.title}\n")
    elif cmd == "answer":
        row = taskqueue.answer(root, args.id, when)
        out.write(f"Answered {row.id} on {row.answered}\n")
    else:
        row = taskqueue.close(root, args.id, when)
        out.write(f"Closed {row.id}\n")
    return 0


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
        if args.command == "memory" and getattr(args, "memory_command", None) == "bundle":
            return _cmd_memory_bundle(args, out)
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_ERROR
    parser.print_usage(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
