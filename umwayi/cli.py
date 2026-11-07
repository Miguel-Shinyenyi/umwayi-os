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
from pathlib import Path

from umwayi import __version__, rules
from umwayi.config import load_config
from umwayi.errors import UmwayiError
from umwayi.memory import load_bundle

EXIT_USAGE = 64
EXIT_ERROR = 1


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
        if args.command == "memory" and getattr(args, "memory_command", None) == "bundle":
            return _cmd_memory_bundle(args, out)
    except UmwayiError as e:
        sys.stderr.write(f"umwayi: {e}\n")
        return EXIT_ERROR
    parser.print_usage(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
