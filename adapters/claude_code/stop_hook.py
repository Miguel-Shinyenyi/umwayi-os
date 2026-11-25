#!/usr/bin/env python3
"""Claude Code Stop hook for umwayi-os (B-0012, item 3): a session does not end its turn while the queue is low and a free task is pending.

Claude Code runs this when it is about to stop, with the hook input as JSON on stdin. The script asks umwayi, as a separate process (an adapter
never imports umwayi), `umwayi kill status` and `umwayi pr queue next --check` (exit 3: the queue is low and a free task is pending), and answers:

  * nothing on stdout and exit 0: let the session stop;
  * exit 0 and one JSON object {"decision": "block", "reason": "..."} on stdout: do not stop, here is why (the documented way for a
    Stop hook to keep Claude working; https://code.claude.com/docs/en/hooks).

It blocks only when ALL of these hold: the kill switch is known to be off; pr-queue.md is well formed (or missing); fewer than keep_ready
branches are local; at least one pending task of queue.md is free (not marked [blocked: REASON]). It blocks at most --max-blocks times in a
row for one session (default 3, from 1 to 10): the count is kept in `.umwayi/stop-hook/SESSION_ID`, counts only, and is deleted when the
queue is no longer low. After the last block the session is let stop, so the hook can never trap it. Anything unexpected (bad input, a
broken pr-queue.md, an unreadable folder, a write that fails) lets the session stop: this hook only nudges, it is NOT a gate, which is why it
fails open where the PreToolUse hook fails closed. A SubagentStop is never blocked, and an event that is not Stop is ignored.

It never exits 1 (on Claude Code exit 1 is a non blocking error) and never exits 2 (which would block the stop without a reason). It is
cooperative: a helper that ignores its hooks is not stopped by it, and nothing makes a session install it. See adapters/claude_code/README.md.

    python3 adapters/claude_code/stop_hook.py --root /path/to/umwayi/root [--max-blocks 3]

--root is required and is never taken from the hook input.
"""

import sys

STATE_REL = (".umwayi", "stop-hook")
DEFAULT_MAX = 3


def _args(argv):
    root, mx, it = None, DEFAULT_MAX, iter(argv)
    for a in it:
        if a == "--root":
            root = next(it, None)
        elif a == "--max-blocks":
            try:
                mx = int(next(it, ""))
            except ValueError:
                return None, None
        else:
            return None, None
    if not root or not 1 <= mx <= 10:
        return None, None
    return root, mx


def _session(data) -> str:
    import re
    s = data.get("session_id") if isinstance(data, dict) else None
    return s if isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", s) else "unknown"


def _count(path) -> int:
    try:
        n = int(path.read_text(encoding="utf-8").strip())
        return n if 0 <= n <= 1000 else 0
    except (OSError, ValueError):
        return 0


def _umwayi(root, src, args, timeout=10):
    """(exit code, stdout) of `python -m umwayi --root ROOT ARGS`, a separate process (an adapter never imports umwayi). (None, "") on any problem."""
    import os
    import subprocess
    env = dict(os.environ)
    if src is not None:
        env["PYTHONPATH"] = os.pathsep.join([str(src)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), *args], capture_output=True, text=True, timeout=timeout,
                           env=env, cwd=str(root), shell=False, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return p.returncode, p.stdout[:20000]


def main(argv, stdin, stdout, stderr) -> int:
    import json
    from pathlib import Path

    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parents[2]))  # the folder that holds the adapters package
    try:
        from adapters.common import umwayi_gate as gate
        root, mx = _args(argv)
        if root is None or not Path(root).is_dir():
            stderr.write("usage: stop_hook.py --root ROOT [--max-blocks N]\n")
            return 0
        try:
            data = json.loads(stdin.read(65536) or "null")
        except ValueError:
            return 0
        if not isinstance(data, dict) or data.get("hook_event_name") != "Stop":
            return 0
        src = gate.find_umwayi_src(here.parent)
        code, out = _umwayi(root, src, ["kill", "status"])
        if code != 0 or out.strip() != "off":
            return 0  # the kill switch is on or unknown, or umwayi could not be run: let the session stop
        state = Path(root).joinpath(*STATE_REL)
        counter = state / _session(data)
        code, out = _umwayi(root, src, ["pr", "queue", "next", "--check"])
        if code != 3:  # 0: the queue is not low (or nothing free is pending); 64 or anything else: unreadable, so do not block
            try:
                if code == 0:
                    counter.unlink()
            except OSError:
                pass
            return 0
        n = _count(counter)
        if n >= mx:
            stderr.write(f"umwayi stop hook: blocked {n} times already, letting the session stop\n")
            return 0
        try:
            state.mkdir(parents=True, exist_ok=True)
            counter.write_text(str(n + 1), encoding="utf-8")
        except OSError:
            return 0  # cannot count: cannot promise to stop blocking, so do not block
        low = next((l for l in out.splitlines() if l.startswith("queue low")), "queue low")
        low = low.split(" Nothing is started")[0]  # the sentence about the command is not for the session
        stdout.write(json.dumps({"decision": "block", "reason": f"umwayi: {low} Do not end the turn: build the next task first, then end "
                                                               f"(block {n + 1} of {mx})."}) + "\n")
        return 0
    except Exception:  # anything unexpected lets the session stop; this hook only nudges
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr))
