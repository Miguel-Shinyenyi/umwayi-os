"""Build the rules.yaml of a goal root from the repo's own rules.yaml (the owner's option c of 2026-11-26).

    python -m tools.goal_rules --worktrees /abs/path/ROOT-worktrees --guide NAME --builder NAME --tester NAME [--out FILE]

The repo's `rules.yaml` is pinned by tests and asks the owner for every Claude Code write and shell command (`cc-ask-write`, `cc-ask-shell`).
A goal run is built so that the builder writes in its own worktree, so the goal root needs different rules. This tool makes them from the
repo file, without changing it: it drops those two Ask rules and appends (1) the builder rules of `goal.rules.example.yaml` for the worktree
folder (a write, five commands, the No rules for chains and `git diff --output`), (2) `python3 -B -m unittest` and the read only `git log`,
`git show` and `git ls-files`, in the same folder and under the same No rules, and (3) Yes rules for the three named agents only: `agent_run`,
`goal_start` with the roles, and `budget_check`. Every No rule of the repo file stays, and No beats Yes. Nothing is read from the network and no
token is touched. The text goes to standard output, or to `--out` (refused if the file exists). The output is parsed with the real rules parser
before it is printed; a text that does not parse is not printed (exit 2). Exit codes: 0 done, 2 the result is not well formed, 64 usage.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLACEHOLDER = "/path/to/umwayi-root-worktrees"
DROP = ("cc-ask-write", "cc-ask-shell")
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")


class Usage(ValueError):
    """A bad argument: the message names the argument and never echoes its value."""


def drop_rule(text: str, rid: str) -> str:
    """The rules text without the rule `rid`; exactly one such rule must exist."""
    text, n = re.subn(rf"\n  - id: {re.escape(rid)}\n(?:    .*\n|\n)*?(?=  - id: |  #|\Z)", "\n", text)
    if n != 1:
        raise Usage(f"the repo rules.yaml has no single rule {rid}")
    return text


def example_builder_rules(example_text: str, worktrees: str) -> str:
    """The commented builder rules of the example file, uncommented, with the placeholder replaced (the rules, no `rules:` line)."""
    lines = example_text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("# Builder rules (W57)"))
    start = next(i for i in range(start, len(lines)) if lines[i] == "# rules:")
    out = [ln[2:] if ln.startswith("# ") else ln[1:] for ln in lines[start + 1:]]
    return "\n".join(out).replace(PLACEHOLDER, worktrees).rstrip("\n") + "\n"


def extra_rules(worktrees: str, guide: str, builder: str, tester: str) -> str:
    names = ", ".join((guide, builder, tester))
    return f"""
  - id: builder-unittest-nobytecode
    title: A builder may run the tests with python3 -B
    text: python3 -B -m unittest, with or without arguments, is allowed in the goal worktrees.
    cause: A builder wrote python3 -B -m unittest and the plain rule did not match it (Project A, 2026-11-26).
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_bash
      cwd__prefix: {worktrees}
      command__startswith: ["python3 -B -m unittest "]

  - id: builder-unittest-nobytecode-bare
    title: python3 -B -m unittest with nothing after it
    text: python3 -B -m unittest written alone is allowed in the goal worktrees.
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_bash
      cwd__prefix: {worktrees}
      command: ["python3 -B -m unittest"]

  - id: builder-git-read
    title: A goal helper may read the history in a goal worktree
    text: git log, git show and git ls-files, with arguments, are allowed in the goal worktrees (read only).
    cause: The guide's check ran a git command and had no rule, so it could not look (Project A, 2026-11-26).
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_bash
      cwd__prefix: {worktrees}
      command__startswith: ["git log ", "git show ", "git ls-files "]

  - id: builder-git-read-bare
    title: git log, git show and git ls-files with nothing after them
    text: The three read only git commands of builder-git-read, written alone, are allowed in the goal worktrees.
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_bash
      cwd__prefix: {worktrees}
      command: ["git log", "git show", "git ls-files"]

  - id: goal-agents-run
    title: The named goal agents may start
    text: The guide, the builder and the tester named for this goal root may start ({names}).
    cause: A goal root runs its own three agents.
    verdict: yes
    matchers:
      type: [agent_run]
      agent: [{names}]

  - id: goal-agents-start
    title: The named goal agents may work on goals
    text: The three named agents may take the roles guide, builder, tester and check.
    cause: A goal root runs its own three agents.
    verdict: yes
    matchers:
      type: goal_start
      agent: [{names}]
      role: [guide, builder, tester, check]

  - id: goal-budget-check
    title: Budget checks of goal runs are allowed
    text: The budget reservation of a goal run is allowed in this root.
    cause: Every goal run reserves its budget first.
    verdict: yes
    matchers:
      type: [budget_check]
"""


def build(rules_text: str, example_text: str, worktrees: str, guide: str, builder: str, tester: str) -> str:
    if not _PATH.match(worktrees) or "/./" in worktrees or "/../" in worktrees or "//" in worktrees or worktrees.endswith("/"):
        raise Usage("--worktrees must be a clean absolute path without a trailing slash")
    for flag, name in (("--guide", guide), ("--builder", builder), ("--tester", tester)):
        if not _NAME.match(name):
            raise Usage(f"{flag} must be an agent name (lower case letters, digits, dashes)")
    if len({guide, builder, tester}) != 3:
        raise Usage("the guide, the builder and the tester must be three different agents")
    text = rules_text
    for rid in DROP:
        text = drop_rule(text, rid)
    text = text.rstrip("\n") + "\n"
    builder_block = example_builder_rules(example_text, worktrees)
    header = ("\n  # --- Goal root rules built by tools/goal_rules.py from the repo rules.yaml: cc-ask-write and cc-ask-shell are dropped,\n"
              "  # --- the builder rules for the goal worktrees and the named agents are added. Every No rule of the repo file stays.\n")
    return text + header + builder_block + extra_rules(worktrees, guide, builder, tester)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.goal_rules")
    p.add_argument("--worktrees", required=True)
    p.add_argument("--guide", required=True)
    p.add_argument("--builder", required=True)
    p.add_argument("--tester", required=True)
    p.add_argument("--out")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 64
    try:
        text = build((REPO / "rules.yaml").read_text(encoding="utf-8"), (REPO / "goal.rules.example.yaml").read_text(encoding="utf-8"),
                     args.worktrees, args.guide, args.builder, args.tester)
        sys.path.insert(0, str(REPO))
        from umwayi.rules import parse_rules
        parse_rules(text)
    except Usage as e:
        print(f"goal_rules: {e}", file=sys.stderr)
        return 64
    except Exception:  # the real parser's refusal: the text is not printed
        print("goal_rules: the built rules text does not parse; nothing was written", file=sys.stderr)
        return 2
    if args.out:
        out = Path(args.out)
        if out.exists():
            print("goal_rules: --out exists; nothing was written", file=sys.stderr)
            return 64
        out.write_text(text, encoding="utf-8")
        print(f"goal_rules: wrote {len(text.splitlines())} lines")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
