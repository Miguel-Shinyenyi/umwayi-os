# The enforcement broker (W78 build step 5, design note)

## Purpose

This note designs the broker named in [enforced-default-design.md](enforced-default-design.md) (W78, "The broker (design)", Q6): a small separate process that lets a confined helper's hook get a rules answer and have it logged, while the guard files stay unwritable from inside the confinement. It answers who writes the guard files once helpers are confined. Built in part on 2026-11-23 (step 5a): `umwayi/broker.py` alone, with `check` and `answer_status`, the limits, the run table and the fixed argument list. Not built: the supervisor starting it, the hooks asking it, `log`, `broker_lost`, and any confinement. Until those exist it changes no default and protects nothing. The rest of this note is still the design.

Product first: umwayi-os runs by itself. Every rule below holds with no outside guide, no AI session reading the note and no Kiro web session. The outside guide only reviews.

Sources: [enforced-default-design.md](enforced-default-design.md), [enforcement.md](enforcement.md) (B2, C1), [network-credentials.md](network-credentials.md) (W69), [untrusted-content.md](untrusted-content.md) (W68), [threat-model.md](threat-model.md) (W67, "The supervisor"), `umwayi/agents.py` (W64: `AGENT_SOCKET_ENV`, `claude_env`, `child_env`, `opencode_env`), `umwayi/logbook.py`, `adapters/stdio/hook.py`, `tests/test_system.py`.

## Current state

Read at main `ae009a2`. Enforcement is cooperative today. There is no confinement and no broker.

- **The hook writes the logbook itself.** `adapters/stdio/hook.py` runs `umwayi check` as a separate process with `--root` taken from its own command line, never from the call (`--platform` likewise). That process appends to `LOGBOOK.md` through `logbook.append` (a lock on `.umwayi/logbook.lock`, the hash record `.umwayi/logbook.sha256`, the intent file `.umwayi/logbook.pending`; names in `umwayi/logbook.py` lines 72 to 74). With `--no-ask` an Ask me first also adds a queue row. Every error in the hook is a deny and it never exits 1.
- **Under B2 that breaks.** A confined hook cannot write those files, and if it could, the helper could too ([enforcement.md](enforcement.md), option B2: "needs a broker before it can protect the guard files"). The tamper check and the chain show an edit; they do not prevent one.
- **The environment is already cut.** W64 removes `SSH_AUTH_SOCK` and `SSH_AGENT_PID` from every helper's environment (`AGENT_SOCKET_ENV`, `umwayi/agents.py:198` to `200`). The scrubbed environment with `env_keep` and a run marker is W78 step 2 and is not built.
- **Product rule 5.** No module of the core package imports a network library except two named by file in `tests/test_system.py` (lines 411 to 430: `umwayi/telemetry.py` and `umwayi/serve.py` may import `socket`). A broker that uses a socket is a third exception ([network-credentials.md](network-credentials.md), open question 2, had the same issue for the proxy).

## Who writes what once helpers are confined

| file or folder | written by | never written by |
| --- | --- | --- |
| the worktree, the helper's own config and cache folders, one private temporary folder | the confined helper and its children | the broker |
| `LOGBOOK.md`, `.umwayi/logbook.sha256`, `.umwayi/logbook.lock`, `.umwayi/logbook.pending` | the broker for a request from a confined run; the owner's own commands at the owner's terminal; the supervisor | a confined process |
| `queue.md` rows for a refused call | the broker (it adds the row a hook adds today) | a confined process |
| the guard files: `rules.yaml`, `autonomy.yaml`, `agents.yaml`, `units.yaml`, `guidance.yaml`, `.umwayi/enforcement.yaml`, `.kiro/steering/umwayi`, the tools folder | the owner, by hand or with an owner command at the owner's terminal (`umwayi enforce set`, the rules change that logs first) | the broker and every confined process |
| goal state under `.umwayi/goals/` | the supervisor (`umwayi/goalrun.py`) | the broker and every confined process |

The answer to the question: **the broker never writes a guard file.** It has no request that could. The guard files are written by the owner's commands, which run outside any confinement at a terminal. The W78 note says the broker "holds the only write access to" the guard files. This note narrows it: the broker's code writes only the logbook family and queue rows. The operating system's write permission on the guard files is what a confined process lacks; the broker's own restraint is a fixed list in its code, tested.

## The broker

- **One process per goal run, not the supervisor** (W78 Q6, decided). The supervisor (`umwayi/goalrun.py`) holds goal state and starts helpers. A flaw in the request parser must not sit in the process that owns goal state, and the broker must stay small enough to read in one sitting (a few hundred lines, standard library only). The supervisor starts it before the first helper and stops it after the last. It is not confined.
- **Started by umwayi only.** Its arguments are `--root`, a run table file descriptor or path made by the supervisor, and nothing else. The root never comes from a request.
- **The run table.** The supervisor writes one row per run it starts: run id (made by the supervisor), agent name, platform, task id, and the mode in force. A request from a run id that is not in the table, or whose run has ended, is refused.
- **Three requests, no more:**
  - `check`: the helper's hook asks what the rules say about one action. The broker runs the same rules check as `umwayi check` in its own process (never a shell), writes the logbook entry itself, adds the queue row for Ask me first when asked to, and answers with the verdict word (`yes`, `no`, `ask`) and the rule id. It returns no file content and no text from the rule.
  - `log`: one fixed entry shape (kind from a fixed list, names from fixed lists, never a value, never free text), for the facts a hook knows and the supervisor does not.
  - `answer_status`: read only. It tells whether a queue row of the run is `open`, `answered` or `none`. It never returns the answer text.
- **Limits on a request.** One JSON line of at most 4 KiB, read with a deadline of 10 seconds however slowly it arrives, at most 16 connections at once, at most 20 requests a second for a run. Over a limit the request is refused and counted. The 10 second deadline and the 16 connections are the limits the telemetry receiver got after its security scan (item 122 of `docs/KNOWN-LIMITS.md` and [SECURITY-SCAN.md](SECURITY-SCAN.md)), reused; the 4 KiB and the 20 a second are new.
- **The kill switch wins.** While the switch is on, or its state cannot be read, every `check` is No. Unknown is stop.
- **No answer is No.** If the broker cannot be reached, the hook denies (as `hook.py` does for every error). The supervisor sees the broker end, stops the running task with the new cause word `broker_lost` and does not start another.
- **A refusal is logged.** An unknown request type, a bad shape or an unknown run id writes one logbook entry with a fixed reason word and the run id if it is valid. It never copies the request.

## The channel

The W78 note says one inherited socket pair and no path on disk. Reading the hooks shows a gap.

- A hook is a new process that the platform starts for each tool call, in parallel with others. One inherited stream shared by all of them cannot tell their requests and answers apart.
- Whether a platform passes an extra open file descriptor from the helper to its hook process is not shown for Claude Code, Kiro or the OpenCode plugin. Nothing in this repo checks it.

So the build has two ways, and the first real check chooses:

1. **Inherited descriptor.** The broker and the helper share a descriptor made at start. Each hook uses it only if it inherited it. Cheap and no path. Works only if the three platforms pass the descriptor on.
2. **A listening Unix socket in a private run folder.** The folder is made by the supervisor, mode 0700, outside the worktree, with a name from a random token. The confinement profile allows the helper to connect to that one path and write nowhere in the folder. Each hook makes its own connection. The path is known to the helper (it must be), so it is not a secret. What protects the broker is the fixed request set and the run table, not the path.

**Recommendation: way 2 for the first build,** because it does not depend on an unchecked platform behaviour. It is a third exception to product rule 5 and needs the owner's approval (open question 2).

## Exit codes

Only 0, 2, 3 and 64, as everywhere. Never 1.

- **The broker process:** 0 it was asked to stop and closed cleanly; 2 it could not start or ended on an error; 3 it cannot decide (the logbook lock is held too long, the chain is broken, the run table cannot be read), so it answers every request No and exits; 64 bad arguments.
- **A request:** answered with the verdict word. `check` passes the rules answer (Yes, No, Ask me first). A refused request is No. A request it cannot decide is Ask me first only where the hook can ask; where the platform cannot ask (Kiro), it is No with a queue row, as `--no-ask` does today.
- **A start that cannot set the broker up:** exit 2, "not confined", reason `broker`, from the fixed list of the W78 note. It never falls back to `cooperative` by itself and never starts the helper first.
- **The hook:** unchanged (0 allow, 2 deny, 3 ask).

## A planted fault for every rule

Each rule gets a test with real child processes in a temporary root, standard library only, and a planted fault it must catch. The rule ids are new: W78.B1 to B12.

| rule | what it says | planted fault the test must catch |
| --- | --- | --- |
| W78.B1 | the broker is a separate process that the supervisor starts before the first helper and that is not confined | the broker run inside the supervisor; a helper started before the broker answers; a broker that is itself confined and cannot write |
| W78.B2 | only the three request types are served | an unknown type served; a fourth type added with no rule; a request that carries a path or a command accepted |
| W78.B3 | a request carries a run id from the table, and a run that has ended is refused | an unknown run id served; the id of a finished run served; the id taken from the request's own claim of a platform |
| W78.B4 | the answer holds a verdict word and a rule id and never file content or rule text | a reply with a file's text; a reply with the matched rule's `text` field; a reply that echoes the request |
| W78.B5 | `check` runs the rules in the broker and the broker writes the entry; the hook writes nothing | the entry written by the hook; an entry that holds the command (only the first word is allowed, W55b); a verdict taken from the request |
| W78.B6 | `log` entries have a fixed shape with fixed lists and no free text | free text in an entry; a value outside its list; a name with a newline |
| W78.B7 | limits: 4 KiB, a 10 second deadline, 16 connections, 20 requests a second | an oversize request served; a trickling client that holds a thread; a 17th connection served; a flood that starves the supervisor |
| W78.B8 | no answer is No; a lost broker stops the task with `broker_lost` | a hook that allows when the broker is down; a lost broker that leaves the task `running` |
| W78.B9 | the kill switch on, or unreadable, makes every `check` No | a Yes while the switch is on; a Yes when the switch file cannot be read |
| W78.B10 | the broker never writes a guard file or goal state | a code path that opens `rules.yaml`, `units.yaml` or a goal file for writing; the writer list in the code differing from the list in the test |
| W78.B11 | the logbook is appended through `logbook.append` with its lock and chain checks, and a broken chain makes every answer No | an entry appended with no lock; an entry written over a broken chain |
| W78.B12 | the broker starts with a fixed argument list and takes no root from a request | `--root` read from a request; an environment variable that changes the root |

A whole system scenario in `GoalWholeSystemTests` runs one task in `enforced` mode where the fake helper's hook asks the broker, the helper tries to write `rules.yaml` directly and the broker is then killed. It expects the direct write refused by the confinement, one logged answer, and the next call denied with the task stopped as `broker_lost`.

## Spec lines it would add or change

- `requirements.md`: W78.B1 to B12 after W78.R16.
- `docs/enforced-default-design.md`: the sentence "holds the only write access to ... the guard files" narrowed as in this note, and the channel paragraph pointed here.
- W9.R6.2: the cause word `broker_lost`.
- The fixed reason list of "not confined": `broker` is already there.
- `tests/test_system.py`: the file list that may import `socket` gains `umwayi/broker.py`, (approved by the owner on 2026-11-22, open question 2).
- `docs/exit-codes.md`, `docs/security.md`, `docs/enforcement.md`: the broker and a link here. A limits part and a status part when it is built.

## What it does not prove

- **Not that a confined process cannot reach the logbook some other way.** That is the confinement's job (Landlock, Seatbelt), built in steps 6 and 7. The broker only gives the confined side a way to ask.
- **Not that the platforms pass what the channel needs.** Way 1 depends on a descriptor reaching the hook. Way 2 depends on the profile letting the hook connect. Neither is checked on Claude Code, Kiro or OpenCode.
- **Not that the rules are right.** The broker serves the owner's rules as they are. A wrong Yes is still a wrong Yes.
- **Not the owner's commands.** `umwayi enforce set`, `queue answer`, `goal approve` and the rules change stay at the owner's terminal. A helper that fakes a pseudo-terminal is open question 1 of the W78 note and is not closed here.
- **Not a broker that is hard to crash.** It fails closed: a crash stops the task. It does not recover.
- **Not Kiro web, or a session the owner opens outside umwayi.** Those have no run id in the table.
- **Not macOS.** Seatbelt is deprecated and CI has no macOS. Nothing about the broker on a Mac is shown until the owner's check.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-22 | Design note only. The broker never writes a guard file; the owner's commands do. The channel is two ways, with way 2 recommended. | Round 4, task 4 of the owner's message. The W78 note's "only write access to the guard files" and "one inherited socket pair" were written before the hooks were read for this. |
| 2026-11-22 | The owner approved open question 2: a third exception to product rule 5, `socket` in `umwayi/broker.py` only, named by file in `tests/test_system.py`. The other open questions are not yet decided. | The owner accepted the recommendation in the chat of the same day. |

## Open questions

Each has a recommendation. The owner decides.

1. **The channel.** Inherited descriptor (way 1) or a listening Unix socket in a private run folder (way 2)? **Recommendation:** way 2 first, because it needs no unchecked platform behaviour. Check way 1 in the real check of step 6 and switch only if it works on all three platforms.
2. **A third exception to product rule 5.** Decided 2026-11-22: approved. The broker may import `socket`, by file name in `tests/test_system.py`, inside `umwayi/broker.py` only, with the same guard test as the telemetry receiver. Nothing is built yet: the exception is used when the broker is built. (The note had asked: the broker imports `socket`; the alternative, pipes of its own for each hook, has no way to separate parallel hooks.)
3. **Does `log` exist at all?** The W78 note lists it. **Recommendation:** keep `check` and `answer_status` for the first build and add `log` when a fact is found that only the hook knows. Fewer requests means less to attack.
4. **Who stops a broker whose supervisor died?** **Recommendation:** the broker exits (code 2) when its parent ends, and the next `goal run` starts a new one. The repair of a lost supervisor at the start of `supervise` (`umwayi/goalrun.py`) already marks the task.
5. **Should the broker run for a plain `agent run` and a chat, not only a goal run?** **Recommendation:** yes in `enforced` mode, since any confined helper needs a hook answer; one broker per run, started by `umwayi agent run` and `agent chat` as the supervisor does for a goal.
6. **Queue rows from the broker.** **Recommendation:** keep adding the row in the broker, in the same shape as `--no-ask` today, so the owner sees one list. Rows come only from the fixed `check` path, never from request text.
