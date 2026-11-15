"""W28: `umwayi login [--agents PATH]`, the login wizard.

One line per agent in agents.yaml: ok, needs a sign-in, cannot be checked, or not offered (OpenCode). Then, only on a real
terminal (standard input and output both), it asks "Sign in agent NAME now? [y/N]" for each agent that needs a sign-in and
can have one, one at a time, and for each yes calls `agents.login_agent`, the same code as `umwayi agent login NAME`: the
kill switch, the rules (action agent_login), the run lock, the gate checks, the tool's own sign-in on the owner's terminal and
the login check again. The wizard adds no other way to start anything.

What it never does (10.R12.4, 10.R12.9, 10.R12.13, 10.R13.12, unchanged): it never offers or lists accounts, never passes a
word to a sign-in (no account, provider, email or key flag), never reads what a sign-in prints, never reads, stores or prints
a password, key or token, and never passes KIRO_API_KEY (the agent code removes it from every Kiro environment). It starts no
sign-in for a Claude Code agent with transport cli (there is no approved login for it) and none for OpenCode (its sign-in is
the owner's own `opencode auth login`). The report itself writes nothing: like `umwayi agent check`, it runs only the gate
checks up to and including the login check (version and login probes, no agent).

Exit codes: 0 every agent it checks is signed in at the end; 2 one is not (or cannot be checked, or its sign-in failed); 3 every
agent that is not signed in was held by the kill switch or by Ask me first, so the owner has to act first; 64 usage (a bad
agents file). 2 wins over 3. Never 1. An OpenCode agent is not checked and does not change the code.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from umwayi import agents, kill

OK, NEEDS, BROKEN, NOT_OFFERED = "ok", "needs a sign-in", "cannot be checked", "not offered"
OPENCODE_LINE = ("umwayi does not check or start an OpenCode sign-in. If your route needs one, run opencode auth login "
                 "yourself.")
CLI_LINE = "umwayi starts no sign-in for a Claude Code agent with transport cli."
NO_TERMINAL = ("Not a terminal, so no sign-in is offered. Run umwayi login on a terminal, or umwayi agent login NAME, to "
               "sign in.")
NO_AGENTS = "There are no agents in the agents file. Nothing was checked."


@dataclass
class Status:
    agent: agents.Agent
    kind: str
    detail: str

    def line(self) -> str:
        a = self.agent
        return f"{self.kind}: {a.name} ({a.platform}, {a.transport}): {self.detail}"

    @property
    def offered(self) -> bool:
        return self.kind == NEEDS and agents.can_login(self.agent)


def status_of(root: Path, agent: agents.Agent) -> Status:
    """What the login check says now. Starts no agent and writes nothing."""
    if agent.platform == "opencode":
        return Status(agent, NOT_OFFERED, OPENCODE_LINE)
    mode = agents.LOGIN if agents.can_login(agent) else None
    gate = agents.gate_checks(agent, root, mode=mode)
    login = next((c for c in gate.checks if c.name == "login"), None)
    for c in gate.checks:
        if c is login:
            break
        if c.ok is not True:
            return Status(agent, BROKEN, f"{c.name}: {c.detail}")
    if login is None or login.ok is None:
        return Status(agent, BROKEN, gate.reason() or "the login check did not run")
    if login.ok:
        return Status(agent, OK, login.detail)
    if mode is None:  # Claude Code with transport cli: the existing refusal reason, and nothing is started
        return Status(agent, NEEDS, f"{login.detail} {CLI_LINE}")
    return Status(agent, NEEDS, login.detail)


def _is_yes(text) -> bool:
    return isinstance(text, str) and text.strip().lower() in ("y", "yes")


def _terminal(stdin, stdout) -> bool:
    try:
        return bool(stdin.isatty() and stdout.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def run(root, clock, given: str | None = None, out=None, stdin=None, terminal=None) -> int:
    """The wizard. out: where umwayi's own lines go (standard output). stdin: where the answers come from. terminal: a
    function that says whether both are a real terminal (the command line asks the two files)."""
    root = Path(root)
    out = out or sys.stdout
    stdin = stdin or sys.stdin
    on_terminal = terminal() if terminal is not None else _terminal(stdin, out)
    listed = agents.load(root, given)  # a bad agents file is 64
    if not listed:
        out.write(NO_AGENTS + "\n")
        return 0
    statuses = [status_of(root, a) for a in listed]
    for s in statuses:
        out.write(s.line() + "\n")
    offered = [s for s in statuses if s.offered]
    held = set()  # agents that stay unsigned because the owner has to act first (kill switch, Ask me first)
    if offered:
        st = kill.state(root)
        if kill.stopped(st):
            out.write(f"The kill switch is {st}, so no sign-in is offered. {kill.reason(st)}\n")
            held = {s.agent.name for s in offered}
        elif not on_terminal:
            out.write(NO_TERMINAL + "\n")
        else:
            for s in offered:
                if kill.stopped(kill.state(root)):
                    out.write("The kill switch is on now, so no further sign-in is offered.\n")
                    held |= {o.agent.name for o in offered if o.kind == NEEDS}
                    break
                out.write(f"Sign in agent {s.agent.name} now? [y/N] ")
                out.flush()
                answer = stdin.readline()
                if not _is_yes(answer):
                    out.write(f"Agent {s.agent.name} was not signed in. Nothing was started.\n")
                    continue
                result = agents.login_agent(root, s.agent.name, clock, given)
                out.write("\n".join(result.lines) + "\n")
                if result.code == 0:
                    s.kind, s.detail = OK, "signed in now"
                elif result.code == 3:
                    held.add(s.agent.name)
    checked = [s for s in statuses if s.kind != NOT_OFFERED]
    not_ok = [s for s in checked if s.kind != OK]
    if not not_ok:
        return 0
    if all(s.agent.name in held for s in not_ok):
        return 3
    return 2
