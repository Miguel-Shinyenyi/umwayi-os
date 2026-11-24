"""G2a: a rehearsal of `umwayi provenance sign` and `umwayi verify` with a THROWAWAY key, so the owner sees the prompts before the real signing.

`prepare` makes, in a new temporary folder: a scratch umwayi root with a hash chain, one fake goal task whose record was made from a
scratch worktree, a throwaway ed25519 key (no passphrase), an `ssh-agent` of its own that holds only that key, and an `umwayi.json` that
names the throwaway public key. It prints the commands to type. The owner's own key, `~/.ssh` and the owner's agent are never touched:
the agent is a new one on its own socket, and the commands carry its `SSH_AUTH_SOCK`. `cleanup` ends that agent and removes the folder.
The real signing (the owner's key, a real goal record, `provenance.public_key` set by the owner) stays the owner's act.

    python -m tools.provenance_rehearsal prepare
    python -m tools.provenance_rehearsal cleanup FOLDER

Exit codes: 0 done, 2 a tool is missing or a step failed, 64 usage.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from umwayi import logbook, provenance, provsign  # noqa: E402

GOAL, TASK, DATE = "G-0001", "T-01", "2026-01-01"


def prepare(base: Path | None = None) -> dict:
    """Make the scratch root, key and agent. Returns the folder, the pieces and the commands. Raises provsign.SignError when ssh-keygen is missing."""
    keygen = provsign.find_ssh_keygen()
    agent, add = shutil.which("ssh-agent"), shutil.which("ssh-add")
    if not (agent and add):
        raise provsign.SignError("no_agent")
    base = Path(base) if base else Path(tempfile.mkdtemp(prefix="umwr", dir="/tmp" if os.path.isdir("/tmp") else None))
    root, wt, keys = base / "root", base / "wt", base / "keys"
    for d in (root, wt / "umwayi"):
        d.mkdir(parents=True, exist_ok=True)
    keys.mkdir(mode=0o700, exist_ok=True)
    sock = keys / "agent.sock"
    out = subprocess.run([agent, "-a", str(sock)], capture_output=True, text=True, check=True).stdout
    pid = int(next(l for l in out.splitlines() if "SSH_AGENT_PID" in l).split("=")[1].split(";")[0])
    key = keys / "throwaway"
    subprocess.run([keygen, "-q", "-t", "ed25519", "-N", "", "-C", "umwayi-rehearsal-throwaway", "-f", str(key)], check=True)
    subprocess.run([add, "-q", str(key)], check=True, env={"SSH_AUTH_SOCK": str(sock), "PATH": os.environ.get("PATH", "")})
    (root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": [],
                                                  "provenance": {"record": True, "public_key": str(key) + ".pub"}}), encoding="utf-8")
    logbook.append(root, logbook.Entry(DATE, "rehearsal", "A scratch root for the rehearsal", "nothing real", "nothing"))
    logbook.seal(root, DATE, "rehearsal", start_chain=True)
    (wt / "umwayi" / "hello.py").write_bytes(b"print('hello')\n")
    provenance.make(root, GOAL, TASK, "b" * 40, "t" * 40, "p" * 64, [("A", "umwayi/hello.py")], str(wt), DATE)
    (root / "umwayi").mkdir(exist_ok=True)
    shutil.copy2(wt / "umwayi" / "hello.py", root / "umwayi" / "hello.py")
    env = f"SSH_AUTH_SOCK={sock}"
    py = f"cd {REPO} && {env} python3 -m umwayi --root {root}"
    return {"folder": str(base), "root": str(root), "agent_pid": pid, "sock": str(sock), "public_key": str(key) + ".pub",
            "commands": [f"{py} provenance sign {GOAL} {TASK}", f"{py} verify umwayi/hello.py",
                         f"echo 'x = 1' >> {root}/umwayi/hello.py   # a change, then verify again: expect exit 3",
                         f"python3 -m tools.provenance_rehearsal cleanup {base}"]}


def cleanup(folder: str) -> None:
    """End the throwaway agent (read from the folder) and remove the folder. Only a folder this tool made, by its name."""
    base = Path(folder)
    if not base.name.startswith("umwr") and not (base / "keys" / "throwaway").exists():
        raise ValueError("not a rehearsal folder")
    sock = base / "keys" / "agent.sock"
    try:
        pids = subprocess.run(["pgrep", "-f", f"ssh-agent -a {sock}"], capture_output=True, text=True, check=False).stdout.split()
        for p in pids:
            os.kill(int(p), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    shutil.rmtree(base, ignore_errors=True)


def main(argv) -> int:
    if argv == ["prepare"]:
        try:
            got = prepare()
        except (provsign.SignError, subprocess.CalledProcessError) as e:
            print(f"rehearsal: could not prepare ({type(e).__name__}); is ssh-keygen, ssh-agent and ssh-add installed?", file=sys.stderr)
            return 2
        print("A rehearsal with a THROWAWAY key. Your own key and agent are not used.\nType, one at a time:\n")
        for c in got["commands"]:
            print("  " + c)
        return 0
    if len(argv) == 2 and argv[0] == "cleanup":
        try:
            cleanup(argv[1])
        except ValueError:
            print("rehearsal: that folder was not made by this tool", file=sys.stderr)
            return 2
        return 0
    print("usage: python -m tools.provenance_rehearsal prepare | cleanup FOLDER", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
