# Known limits

These are real limits of umwayi-os today. They are written down on purpose and are not fixed yet. Each one says what happens, why it matters and what would fix it later. Items 1 to 11 were checked on the hardening branch (Nov 8 2026) by running the commands, not only by reading the code. Items 12 to 20 come from building the layer 9 Claude Code adapter (item 16 is fixed in PR 12). Items 21 to 28 come from building the Kiro and generic adapters. Items 29 to 34 come from building layer 10 parts 1 and 2 (agents.yaml and the gate checks). Items 35 to 40 come from building part 3 (`umwayi agent run` for Claude Code). Items 41 to 45 come from building part 4 (`umwayi agent run` for Kiro). Items 46 to 51 come from building part 5 (`umwayi agent chat` on the terminal). Items 52 to 58 come from building part 6 (ACP chat for Kiro). Items 59 to 64 come from building part 7a (Claude Code over ACP: agents.yaml, `adapters/claude_acp/` and the gate checks). Items 65 to 68 come from building part 7b (the Claude Code ACP chat: the inline settings, the canary and the stop). Items 69 to 72 come from building part 7c-1 (subscription first: the login check, the credential names, `forceLoginMethod`). Items 73 to 80 come from building the Layer 5 crash safety addendum (the intent, recovery, flock and held-off signals); item 39 changed with it. Items 81 to 88 come from building part 7c-2 (`umwayi agent login` and Kiro subscription first). Items 89 to 92 come from building part 7c-3 (the watch during an ACP chat, the chat end to end, and the docs of 10.31); item 71 changed with it. Items 93 to 103 come from building layer 11 (scheduled runs through systemd user timers). Items 104 to 109 come from building the logbook hash chain (addendum, tasks C.1 to C.4); item 3 changed with it. Items 110 to 128 come from building the budget governor (tasks B.1 to B.10). Item 129 comes from the whole-system test (S.1); item 98 is true since then (a gap rule refusal now writes its entry). Items 130 to 137 come from the security scan (S.2, [SECURITY-SCAN.md](SECURITY-SCAN.md)); item 122 changed with it. Items 196 to 212 are the expected limits of the local backend (W6), written from the spec on Nov 12 before any code; nothing is built. Items 213 to 232 are the expected limits of goal orchestration (W9), written from the spec on Nov 12 before any code; nothing is built.

## Approval and the owner

### 1. `--approved-by` is self-declared

`umwayi publish-draft DRAFT --approved-by NAME` copies a draft to `outbox/` when the rules say Ask me first. Any name is accepted: `--approved-by "Not The Owner"` works. Nothing proves that the person typing it is the owner.

- What protects you today: the AI helpers, jobs and workflows have no code path that passes `--approved-by` (the system test checks the code and runs them with a spy on `publish`), and `publish-draft` only copies a file for you to post by hand. It never posts.
- What it does not protect against: any program that runs as you and calls `umwayi publish-draft --approved-by ...` itself.
- A later fix: an approval that something outside the repo signs, for example a key the AI helpers cannot read.

### 2. The kill switch is a file anyone with write access can remove

`umwayi kill on` creates `.umwayi/KILL`. Anyone, or any program, that can write the repo folder can delete it, and runs start again. `umwayi kill off` writes a logbook entry, but deleting the file by hand writes nothing.

- It stops runaway AI helpers, jobs and workflows. It is not a guard against a person or a program that has your file permissions.
- A later fix: a switch outside the repo folder, owned by another user, or checked against the logbook.

## The logbook

### 3. Editing both LOGBOOK.md and its hash record is not detected

The tamper check compares `LOGBOOK.md` with the SHA-256 in `.umwayi/logbook.sha256`. If someone edits the logbook and then writes the new SHA-256 into the record, `umwayi logbook verify` says ok. The record sits right next to the file it protects.

- Changed with the hash chain (PR 32): every entry after the chain starts carries a `- Chain:` line, so an edit, a deleted entry or a reordered pair in a chained entry is now found even when the record was rewritten too. A writer who rewrites the whole chain and the record together is still not found, unless the owner compares with an anchor kept elsewhere (`umwayi logbook verify --anchor`, item 104). Entries before the start of the chain are covered only as a whole (item 107).
- A later fix: sign the record or the chain.

### 4. Large logbooks are re-read on every append

Every append (every `umwayi check`, every queue change, every helper step) reads, parses and hashes the whole `LOGBOOK.md`. That is fine for thousands of entries. With many AI helper runs a day it will get slower over time, and it was not measured.

- A later fix: check only the end of the file against a stored length and hash, or start a new logbook file per month.

## Commands

### 5. `umwayi report` run directly does not check the kill switch

The kill switch stops AI helpers, jobs and workflows. `umwayi report` is an owner command, so when you run it yourself it writes a draft even while the switch is on. The `report` step inside `umwayi run` or `umwayi workflow run` is stopped, because those runners check the switch first.

- The same is true of the other owner commands (`queue`, `archive`, `check`, `publish-draft`). That is on purpose for the owner. It matters if a program, not you, runs `umwayi report`.

### 6. YAML syntax errors show only the first problem

`umwayi workflow validate NAME` reports every problem in a file that parses. A YAML syntax error (a tab, a flow mapping, an unclosed quote) stops the parser, so only that one problem is shown, with its line. Fix it and run validate again to see the rest. The same is true of `rules.yaml` and the jobs file.

### 7. Social drafts use the same text for every channel

`umwayi social draft` and the `social-draft` workflow step write one draft per channel in `social_channels`, but the text is the same in all of them: one fixed template, at most 280 characters. Nothing is tuned per channel (length, tone, links).

Inside a workflow there is a second difference: the social step is one rules check for all channels, so a rule that says No for one channel (matching `channel`) only works with `umwayi social draft`, not with the workflow step.

## Found while hardening, not fixed

### 8. A failed publish can leave an empty `outbox/` folder

If `publish-draft` copies a draft and then the logbook entry fails, the copy is removed, but the `outbox/` folder it created stays (empty). No file is left behind. Found by the system test.

### 9. The run lock needs `fcntl`, and owner commands do not take it

- The run lock (`.umwayi/run.lock`) uses `fcntl.flock`. Where `fcntl` does not exist (Windows), every AI helper, job and workflow answers Ask me first and nothing runs. That is the fail closed choice, but it means umwayi-os does not run its helpers on Windows today.
- `flock` may not work on some network file systems. Not tested.
- Owner commands (for example `umwayi queue add`) do not take the run lock, so you can change `queue.md` while Steward reads it. Each queue write is atomic and logged, but a proposal can be out of date by one change.

### 10. There is no `umwayi memory add` command

Memory is plain files that the owner writes in `memory/` (`master.md`, `projects/`, `journal/`). `umwayi memory bundle` reads them. The system test adds a memory file by hand.

### 11. What the tests do not cover

- The system test runs `python -m umwayi`, the same `main()` as the `umwayi` script, not the installed `umwayi` script itself.
- Unexpected crashes are made in the tests by patching one function in the child process. The corrupt state sweep found one real crash (a `memory` folder that is a link loop), which is fixed; there may be others.
- Tests run on Linux only, with Python 3.10 to 3.13. Windows and macOS are not tested.
- The two-process tests make the first run sleep while it holds the lock, so the two runs are sure to overlap. Races without that pause are not forced.

## Layer 9: the Claude Code adapter (found while building part 1, not fixed)

Facts about Claude Code below come from its hooks reference; the links are in `adapters/NOTES.md`.

### 12. Rules match plain text, not shell syntax

The adapter sends the whole Bash command as one string, and a rule like `command__contains: ["rm -rf"]` looks for that text, ignoring case. A command can be written to get past it: `rm -r -f`, a variable, a script that is written first and run later, another tool. The example rules in `adapters/claude_code/rules.example.yaml` are a first layer, not a sandbox. The Claude Code docs also call hook filtering best effort and point to Claude Code's own permission deny rules for hard limits; keep those too.

### 13. The adapter cannot block when it never gets to run

The adapter turns every error it can see into exit 2 (a block). Some failures happen before any of its code runs: Claude Code cannot start `python3`, the script path is wrong, the hook times out, or Python cannot compile `hook.py` (a bad edit, or a Python older than 3.10), which makes the interpreter exit 1. Claude Code treats all of these as a non blocking error and runs the tool, unless the handler sets `"onFailure": "block"`, which needs Claude Code v2.1.295 or later. The settings snippet in the README sets it. On older Claude Code versions these failures let the tool call run.

### 14. Yes skips Claude Code's permission prompt

umwayi's Yes becomes `allow`, and Claude Code then does not show its own permission prompt for that call. Claude Code still applies its own deny and ask permission rules. If you want Claude Code's prompt as well, do not give Yes rules for those tools.

### 15. An AI helper can try to turn off its own guard

The files that guard the adapter (`rules.yaml`, `LOGBOOK.md`, `.umwayi/`, the `.claude/settings` files) are ordinary files. The example rules deny Write and Edit calls to them and shell commands that name them, but that is text matching (item 12), so a script can still change them. Protecting them with Unix permissions (the AI helper runs as a user that cannot write them) is layer 11.

### 16. Fixed in PR 12: the kill switch now stops the adapters

Was: the adapter did not check the kill switch. Now every adapter runs `umwayi check --kill-switch`, which answers No while the switch is on or unknown, and the adapter also denies unless the answer says `"kill_switch": "off"` (owner decision 9.12). Tests in `tests/adapters/` for all three adapters.

### 17. Only some tool input is checked

The adapter sends the command, path, pattern, URL, query or subagent type, depending on the tool (`adapters/NOTES.md`). It does not send what a Write puts in a file, the text of an Edit, or a subagent's prompt, so rules cannot look at them.

### 18. Two processes per tool call, and a stricter answer when the logbook fails

- Every tool call starts the adapter and then `umwayi check`, two Python processes. On the build machine that took about 150 ms per call (median of 20). Not measured elsewhere.
- When the logbook cannot be written, `umwayi check` keeps a No as No and turns a Yes into Ask me first, but its answer then has `rules_ok` false, so the adapter denies all three. Stricter than `umwayi check` alone, and a broken logbook blocks every tool call until the owner seals it.

### 19. Claude Code cases the adapter does not see or decide

- Files you mention with `@` in a prompt are added without a tool call, so no PreToolUse hook sees them.
- In a non interactive `-p` run with nobody to answer, Claude Code turns an `ask` into a denial.
- The adapter only handles `PreToolUse`; configured on another event, it blocks.

### 20. Kiro: the docs were read only as Markdown copies, and they disagree

The Kiro hook pages render with JavaScript, so the notes come from the Markdown copies that `kiro.dev/llms.txt` lists. In those copies the Pre Tool Use JSON examples are empty. The pages disagree about other exit codes (one says any non zero code blocks a Pre Tool Use call, the others say only exit 2 does) and about the default timeout (60 seconds, or 30 seconds set with `timeout_ms`). The Kiro adapter therefore only exits 0 or 2. It was never run inside a real Kiro session.

## Layer 9 part 2: the Kiro and generic adapters (found while building, not fixed)

### 21. Kiro: the `tool_input` field names are not confirmed

The adapter sends every top level string field of `tool_input` as `input_<name>`. The example rules that look at `input_command` or `input_path` (`kiro-no-destroy`, `kiro-no-guard-shell`, `kiro-no-guard-edits`) match nothing if Kiro uses other names, and then only the type rules apply (shell and writes are Ask me first, so still denied). Check what your Kiro version sends before you rely on a field rule.

### 22. Kiro: a hook that cannot start or times out may let the call run

The Kiro docs say nothing about what happens when the hook command cannot start (no `python3`, a wrong path, a syntax error that makes Python exit 1) or hits its timeout, and they document no setting like Claude Code's `onFailure`. If Kiro lets the call run in those cases, umwayi cannot stop it. The adapter answers within about 15 seconds (10 for `umwayi check`, 5 for a queue item), under both documented timeouts.

### 23. Kiro: Ask me first is always a deny

Kiro has no ask, so an Ask me first denies the call and adds one queue item (`Kiro asks first: may it do TYPE?`). Answering that item does not allow the call, now or later: to allow calls like it, the owner adds a Yes rule. With the example rules, every shell command and every file write is denied until then. Kiro also only sees the reason on stderr; the agent may retry.

### 24. Kiro: the input must say `PreToolUse`, and the command runs in a shell

- The adapter blocks input whose `hook_event_name` is not exactly `PreToolUse` (the name in the one example shown). If a Kiro version sends another spelling, every tool call is blocked. Fail closed, but not confirmed.
- A Kiro command action is one command string run by a shell, so the paths in the snippet must not contain spaces or shell characters. Claude Code's exec form does not have this problem.

### 25. Queue items are matched by exact title

`queue add --if-not-open` skips a new item only while an open item of the same kind has exactly the same title. Once the owner answers or closes it, the next Ask me first for that type adds a new one. A title edited by hand in `queue.md` is not matched. The title has only the action type, so two different shell commands share one item.

### 26. The generic adapter trusts its caller to read the answer

The generic adapter only answers; it cannot stop anything itself. A caller that ignores the exit code, or treats exit 3 or a missing answer as allow, gets no protection. Callers must treat anything but exit 0 with `"decision": "allow"` as a deny. The platform name (`--platform`) is set by whoever writes the command line, so rules with `platform: NAME` are only as good as that setup.

### 27. Kiro and the generic adapter send more of the tool input

Because the field names are not known, `generic_action` sends every top level string field, which can include file contents. They reach `umwayi check` (not the logbook, which gets only the type). A tool input bigger than 64 KB as an action is denied. Rules cannot see nested fields, numbers or lists.

### 28. The owner's own `umwayi check` ignores the kill switch

By design, `umwayi check` without `--kill-switch` answers by the rules even while the switch is on, so the owner can still test rules. Only the adapters pass the flag. A platform set up to call `umwayi check` directly, not through an adapter, is not stopped by the kill switch.

## Layer 10 parts 1 and 2: agents.yaml and the gate checks (found while building, not fixed)

Doc facts and links for these items are in `adapters/NOTES-layer10.md`. No real `claude` or `kiro-cli` was run; every test uses fake programs.

### 29. The version check reads output whose format is not documented

`umwayi agent check` (and later every start) takes the first `N.N.N` in the output of `claude -v` or `kiro-cli --version` and refuses if there is none or it is too old (Claude Code 2.1.295 for `onFailure`, Kiro CLI 2.27.1 for hooks in V3 headless runs). Neither doc gives the output format. If a real version prints something else, every start is refused (fail closed) until `agents.parse_version` is fixed. If it prints another program's version number first (for example a runtime version), the check could pass on the wrong number.

### 30. A managed Claude Code policy can turn our hook off, and umwayi cannot see it

Managed settings (`allowManagedHooksOnly`, `strictPluginOnlyCustomization`) sit above `--settings` and can block every hook that is not managed. umwayi cannot read managed settings, so `check` can say "Gated" on a machine where Claude Code will not run the hook. The owner accepted this as a known limit for Dec 3 (design.md, layer 10, question 4). On a machine with managed Claude Code settings, check with `/hooks` in a Claude Code session that the umwayi hook is listed.

### 31. PATH decides which program is started

`command` is a word (`claude`, `kiro-cli`) found on `PATH` when umwayi runs. Whoever controls `PATH`, or a folder early on it, controls which program runs. `check` prints the full path it found (and every start will log it), but it does not check who owns that file or whether it is the real program. File permissions are layer 11.

### 32. The Kiro hook file check is a text match, not proof that Kiro loads the hook

umwayi only reads the hook files. It accepts a file in `WORKDIR/.kiro/hooks/` or `~/.kiro/hooks/` with a `PreToolUse` hook for every tool whose command is exactly the layer 9 command. It cannot tell whether a given Kiro version or mode really loads that file. That includes ACP sessions (not confirmed by the docs), a Kiro setting or agent configuration that turns hooks off (none is documented), and a field it does not know about, such as one that disables a hook. The match is exact on purpose: a command with anything before or after it is refused.

### 33. The hook self-test proves the hook starts, not that it decides correctly

The self-test runs the layer 9 hook with an event other than `PreToolUse` and expects exit 2. That shows Python and the hook script start and block. It does not check rules.yaml, the logbook, or that the hook allows and denies the right calls (the layer 9 tests do that), and it does not show that the platform will run the hook.

### 34. A passing check can be out of date by the time an agent starts

The files `check` looks at (the hook script, the Kiro hook file, the program on PATH) can change after it ran. `umwayi agent run` and `chat` (parts 3 to 5) will run every check again just before the start, but there is still a short window between that check and the platform reading its own hook files. An agent that can write those files can also change them while it runs (item 15).

## Layer 10 part 3: `umwayi agent run` for Claude Code (found while building, not fixed)

No real Claude Code was run. The tests use a fake `claude` that reads `--settings` and runs the real layer 9 hook the way the Claude Code hooks reference describes. Items 30 (a managed policy can turn the hook off unseen) and 31 (PATH decides the program) now apply to every run, not only to `check`.

### 35. The Claude Code prompt is visible in the process list

The Claude Code docs give no way to pass the `-p` prompt only on stdin (`adapters/NOTES-layer10.md`), so umwayi passes it as the last argument. While the agent runs, any user on the machine who can list processes (`ps`, `/proc/PID/cmdline`) can read it. Do not put a secret in a prompt. The logbook and umwayi's output never hold it.

### 36. An agent that leaves its process group, or a SIGKILL to umwayi, is not stopped

umwayi stops the agent by signalling its whole process group. A program the agent starts in a new session or process group (for example with `setsid`, or a daemon) is outside it and keeps running after the agent is stopped. If umwayi itself is killed with SIGKILL (which no program can catch), nothing stops the agent, and the run lock is released while the agent may still run. Such programs are not tool calls, so the hook does not see what they do. Running agents under a separate user or a sandbox is layer 11.

### 37. The kill switch takes up to a second, plus the stop

The kill switch is checked once a second while an agent runs, and stopping sends SIGTERM and waits up to 10 seconds before SIGKILL. A tool call already running when the switch goes on can finish in that time. Every new tool call is denied by the hook at once (decision 9.12), and the tests check that the next call after the switch is denied.

### 38. Stopping an agent stops everything it left running

After the agent exits, or on any stop, umwayi signals its whole process group, so a server or watcher the agent started in the same group is stopped too, even after a normal exit. That is on purpose (nothing the agent started runs on after umwayi), but it may surprise.

### 39. A logbook that cannot be written stops the agent

Every second the run checks that the logbook could still take an entry (`logbook.check_writable`, under the logbook lock). A hand edit, a missing hash record, a broken format, or a logbook lock held by another writer for more than 3 seconds stops the agent with exit 2. Nothing can be logged about that stop; umwayi prints why. Since the crash safety addendum a writer that was killed can no longer leave the lock behind (it is a kernel lock), and an interrupted write in one of the two states its intent names is recovered by the check itself, with one entry, instead of stopping the agent. The check reads and hashes the whole logbook once a second, which grows with every tool call; it was not measured on a large logbook.

### 40. Exit 0 means the agent exited 0, not that the task was done

`umwayi agent run` exits 0 when the rules said Yes, the agent was gated, and Claude Code exited 0. The Claude Code docs say a failure inside the run (for example missing sign-in) is printed as the result on stdout; whether it also exits non-zero is not confirmed for every case. umwayi does not read the agent's output, so it cannot tell a finished task from a polite refusal.

## Layer 10 part 4: `umwayi agent run` for Kiro (found while building, not fixed)

No real kiro-cli was run. The tests use a fake `kiro-cli` that reads the instruction from stdin, runs the hook command from the hook file it finds, and denies tools not in `--trust-tools`, the way the Kiro docs describe (`adapters/NOTES.md`, `adapters/NOTES-layer10.md`). Items 21 to 24 (the Kiro hook) and 29 to 39 apply to Kiro runs too.

### 41. What Kiro does on SIGTERM is not documented

umwayi stops Kiro the same way as Claude Code: SIGTERM to its process group, SIGKILL after 10 seconds. The Kiro docs do not say whether `kiro-cli` stops cleanly on SIGTERM, what it does with a session or a tool call in progress, or which exit code it gives. If it ignores SIGTERM, it is stopped by SIGKILL, with no chance to clean up.

### 42. What Kiro does when the hook is missing or cannot start is not documented

Before every start umwayi checks, read only, that the hook file is there and matches exactly; if not, the run is refused (exit 2). After the start it does not watch the file. The Kiro docs do not say what Kiro does if the hook file is removed or changed while it runs, if the hook command cannot start, or if it times out (item 22): it may run the tool unchecked. An agent that can write `.kiro/hooks` can therefore change its own gate during a run (item 15); the example rules deny writes to `.kiro/hooks`, but they match text (item 12).

### 43. Kiro's own tool approval is a second lock, and its order is not documented

In a headless run, a tool not in `--trust-tools` is denied by Kiro (no one can approve it). A tool runs only if the rules say Yes through the hook and it is in `trust_tools`. The docs do not say whether Kiro runs the Pre Tool Use hook before or after its trust check, so for an untrusted tool the hook may or may not have run (and logged a check). The fake runs the hook first.

### 44. `--prompt TEXT` puts the prompt in umwayi's own process arguments

For Kiro the prompt goes on stdin, so it is never in Kiro's arguments, and a test checks both Kiro's and umwayi's arguments while it runs. But a prompt given with `--prompt TEXT` is in umwayi's own command line, which other users on the machine can read while it runs. Give a sensitive prompt with `--prompt-file PATH` or `-` (stdin). For Claude Code the prompt is an argument anyway (item 35).

### 45. Kiro exit codes other than 0 are all exit 2

umwayi reads only Kiro's exit code: 0 is exit 0, and 1, 3 (an MCP server did not start), 4 (the agent was not found) and anything else are exit 2, with the code in the end entry. The Kiro docs warn that with exit 4 the default agent may already have made tool calls; those went through the hook and are in the logbook, but `agent run` reports only the failure.

## Layer 10 part 5: `umwayi agent chat` on the terminal (found while building, not fixed)

Written Nov 8 2026.

### 46. No real Claude Code or Kiro chat was run

The tests use fake `claude` and `kiro-cli` programs that read lines and echo them, on a real pseudo terminal with a small job control "shell" in front, as a terminal and a shell would run umwayi. A real interactive Claude Code or Kiro screen was never started under umwayi. Not confirmed: that either one runs well with the terminal handed over this way, what each does on SIGTERM while its screen is up, and whether Claude Code holds back hooks given with `--settings` until the folder is trusted, and if any tool can run before that (`adapters/NOTES-layer10.md`).

### 47. In a chat on the terminal, the hook is the only gate

umwayi never reads the terminal: it does not see what the owner types, what the agent prints, or the tool calls. Every tool call is checked only by the layer 9 hook inside the platform. When the platform asks the owner itself (Claude Code's permission prompt after an Ask me first, Kiro's prompt for an untrusted tool), the owner's answer there is not checked or logged by umwayi. Anything that does not go through a tool call (for example a file mentioned with `@` in Claude Code) is not checked at all. The ACP chat (part 6) adds a second gate for Kiro.

### 48. Finding what the agent started relies on /proc, once a second

A chat agent shares umwayi's process group, so umwayi cannot stop it by group. Instead it reads `/proc` once a second and remembers every descendant of the agent. A process that is started and orphaned (its parent exits) between two passes, less than a second apart, is never seen and is not stopped. Neither is one that changes to another user. Without `/proc` (not Linux) only the agent itself is stopped. Run under a separate user or a sandbox to be sure (layer 11).

### 49. The agent can signal umwayi

Because the agent is in umwayi's process group, it can send a signal to the whole group, umwayi included (for example `kill 0`). A SIGTERM or SIGHUP that reaches umwayi stops the chat with exit 2 (fail closed). A SIGKILL to umwayi leaves the agent running, as in item 36.

### 50. Only the terminal mode is put back

After a chat, umwayi puts back the terminal mode (`termios`) it saw before the start. Other screen state a full screen program may leave behind, such as the alternate screen, colours or a hidden cursor, is not reset. Run `reset` if the terminal looks wrong.

### 51. The queue summary is for information only

Before a chat, umwayi prints how many items are open in the queue and the first five titles. If the queue cannot be read, it says so and the chat still starts: the summary is not a check. The titles are text from `queue.md`, printed as they are after replacing characters that are not printable.

## Layer 10 part 6: ACP chat for Kiro (found while building, not fixed)

Written Nov 8 2026. Doc facts and links: `adapters/NOTES-layer10.md`.

### 52. No real `kiro-cli acp` was run

Every test talks to a scripted fake ACP agent behind `kiro-cli acp`. Not confirmed against a real Kiro CLI V3 server: the shape of its `initialize` and `session/new` answers, the error it gives when the owner is signed out (umwayi takes code -32000, or "auth" in the message, as a sign in error), the permission requests it sends, whether it exits by itself when its stdin closes (if it does not, every ACP chat ends with exit 2 after `:quit`, because umwayi stops it), and what it does on SIGTERM.

### 53. The hook may not run in an ACP session: the permission answer may be the only gate

The gate check requires the layer 9 Kiro hook file before an ACP chat starts, but the Kiro docs do not confirm that a Pre Tool Use command hook runs inside a `kiro-cli acp` session (the ACP overview only says hooks apply "when available"). If it does not, the first gate is not active there, and the only check umwayi makes is its answer to `session/request_permission`. And ACP permission requests are advisory: the agent decides which tool calls it asks about, so a tool call it runs without asking is then not checked at all. Until a real run shows the hook entries in the logbook during an ACP chat, treat ACP chat as less gated than `agent run` and cli chat.

### 54. `content` or `prompt` in session/prompt

The ACP spec puts the owner's message in `prompt`; the Kiro ACP page's example (for the legacy CLI v2 server) puts it in `content`. umwayi sends `prompt`. If a real Kiro server expects `content`, the first prompt fails: the agent answers with an error and the chat ends with exit 2 (fail closed), or it ignores the message.

### 55. Claude Code over ACP: built, but not run for real

Claude Code has no ACP mode in its own command line; it needs the third party adapter `@agentclientprotocol/claude-agent-acp`, a Node package. The owner approved part 7 on Nov 8 (tasks.md 10.22). Part 7a (PR 20) accepts a Claude Code agent with `transport: acp` and runs its gate checks in `umwayi agent check`; part 7b (PR 21) runs the chat itself (the session, the inline settings and the canary). Only fakes were run; items 59 to 68.

### 56. Ctrl-C gives the owner back after 10 seconds, even if the agent goes on

If the agent does not answer `session/cancel` within 10 seconds, umwayi gives the owner the prompt back and ignores the late answer, but the agent may still be working on the cancelled turn. A new prompt then overlaps with it. Each tool call is still checked (by the hook, if it runs, item 53) and each permission request by the rules.

### 57. What safe_text does not catch

Agent text has control characters, bidirectional controls, zero-width characters and tag characters made visible. Look-alike letters from other scripts, very long lines and Markdown are shown as they are. A tool call's title is written by the agent: it describes the call, it is not proof of what the call does, and the rules never see it.

### 58. One chat, one turn at a time

umwayi sends one prompt at a time and holds the owner's next lines until the turn ends. It does not use `session/load`, `session/list`, modes, models or Kiro's extension methods, and it advertises no capabilities, so Kiro features that need them are not available in an ACP chat. Kiro's own interactive approvals (for tools it does not trust) arrive as permission requests and are answered by the rules and the owner as above.

## Layer 10 part 7a: Claude Code over ACP, the package and the gate checks (found while building, not fixed)

Written Nov 8 2026. Doc and source facts: `adapters/NOTES-layer10.md` ("Claude Code over ACP"); the package: `adapters/claude_acp/README.md`.

### 59. No real Node, adapter or Claude Code was run

Every test uses a fake `node` (a Python script first on PATH) and a fake installed `package.json` and `dist/index.js`. Not confirmed by a run: that `npm ci --ignore-scripts` installs everything and the bundled Claude CLI works without install scripts; that the real `--version` prints exactly `0.101.0`; that `--cli --version` prints `2.1.318 (Claude Code)` or something with that number first; that `--cli auth status` exits 0 when signed in and not 0 when signed out, within 15 seconds; and that all of them work with only the allow-listed environment. The owner's first real run (tasks.md 10.31) records these. A different format refuses the chat (exit 2): it fails closed, not open.

### 60. The supply chain is 115 packages

The lockfile pins 115 npm packages with `sha512` integrity hashes, all from registry.npmjs.org, none with an install script, among them a native Claude Code binary (one of 8 optional platform packages of the Claude Agent SDK). The review in PR 20 checked this metadata, not the code: umwayi trusts what the adapter and the SDK do inside the session, the way it trusts Claude Code itself. `npm ci` checks the hashes when the owner installs; umwayi checks only the adapter's own `package.json` name and version and its `--version`, not the files of the other 114 packages. A package changed in `node_modules` after the install is not noticed. The security scan (Nov 14 to 16) must cover the npm dependencies.

### 61. The sign-in check proves a login exists, not that it works

`auth status` exiting 0 says the bundled Claude CLI finds a login. It does not prove that the token is still valid, that the account may use the model, or that the network works; those fail later, inside the chat. umwayi never reads the output, so it cannot say which account is signed in.

### 62. Which `node` runs is the first on PATH

`node` is looked up on umwayi's PATH, like `claude` and `kiro-cli` are. Any `node` first on PATH that prints `v22` or later is used; umwayi does not check where it came from. The adapter path is fixed inside the umwayi-os checkout and may not be a link, but whoever can write to `adapters/claude_acp/node_modules/` can change what runs.

### 63. The allow list passes the owner's proxy and certificate settings

`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` (and their lowercase forms), `NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE` and `SSL_CERT_DIR` are passed when set, so a chat works behind the owner's proxy. A proxy or certificate set in the owner's environment can therefore see or redirect the adapter's traffic, as it can for any other program the owner runs. Everything not on the list is dropped, among them `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_EXECUTABLE`, `NODE_OPTIONS` and `NODE_PATH`.

### 64. `max_turns` is not used by an ACP chat, and `agent check` shows only the chat's checks

A Claude Code agent with `transport: acp` keeps `max_turns` for `umwayi agent run`, which stays `claude -p` and runs the checks of transport cli; an ACP chat has no turn limit of its own (only `timeout_minutes`). `umwayi agent check NAME` for such an agent shows the checks of the ACP chat only.

## Layer 10 part 7b: the Claude Code ACP chat (found while building, not fixed)

Written Nov 9 2026. Doc and source facts: `adapters/NOTES-layer10.md` ("Claude Code over ACP").

### 65. Not confirmed: that SessionStart runs at session/new in a real adapter session

The chat goes on only after the SessionStart canary has run in the session, and umwayi waits for it after `session/new`, before any prompt. The fake runs SessionStart hooks at `session/new`, as the tests assume; neither the adapter nor the Claude Agent SDK docs say when SessionStart runs in an SDK session. If a real session runs it only with the first prompt, every Claude Code ACP chat is refused with exit 2 after 30 seconds (fail closed, approved answers 1 and 9). The real Node, the real adapter and the real Claude Code were never run; the owner's first real run (tasks.md 10.31) settles this.

### 66. The canary proves that hooks from the inline settings run, not that every tool call is checked

The canary file shows that a command hook from the same inline settings as the PreToolUse hook ran in this session. It does not prove that the PreToolUse hook runs before every tool call, or that the adapter asks permission for every call it makes; in `acceptEdits` or other modes many calls are never asked about, which is why umwayi sets mode `default` right after the canary. The owner's own settings (user, project and local, approved answer 7) still apply, and a hook or mode there can make the session more permissive between turns: umwayi sets the mode once and does not watch it.

### 67. The token folder is in TMPDIR, and its file is only looked at

The folder is made with `tempfile.mkdtemp` (mode 0700, refused if it is inside the root or the workdir) in umwayi's TMPDIR, and removed on every way out umwayi controls. If umwayi is killed with SIGKILL, the empty folder (and the empty token file) stays in TMPDIR. The token is not a secret: any program that runs as the owner during the chat could create the file, and the chat would then go on without the hook having run. Only `os.path.exists` is used; the file is never read.

### 68. Tracking descendants once a second

Background commands are found in `/proc` once a second while the chat runs, and once more just before the chat ends. A command started and orphaned between two looks (its parent exits within the same second) can be missed, and is then not stopped (the same limit as item 48 for the terminal chat). Linux only.

## Layer 10 part 7c-1: subscription first for Claude Code (found while building, not fixed)

Written Nov 9 2026. Doc and source facts: `adapters/NOTES-layer10.md` ("Login and billing for Claude Code").

### 69. Most of the fields the login check reads are not documented

Claude Code documents `authMethod` and the exit code of `claude auth status`; `loggedIn`, `apiKeySource`, `apiProvider` and `subscriptionType` come from the pinned adapter's source. A Claude Code release that renames or drops one makes every Claude Code start refuse with "could not be confirmed" (exit 2): it fails closed, but `agent run` uses the owner's own `claude`, which is not pinned. The real field names (never the values) are to be recorded at the owner's first real run (10.31). The tests use fakes only.

### 70. The check may not see everything the session would use

The login check runs in the agent's folder with the agent's own environment, so it should see the same user and project settings. Not documented: whether `auth status` applies a settings file's `env` key, and whether it runs an `apiKeyHelper` (a shell command from a settings file, possibly the project's) to report it. If it does run it, a repository's command runs at the check, before the hook gate; the agent would have run it at its start anyway. If it does not see a credential, the check passes and the session pays by that credential; `forceLoginMethod: "claudeai"` is only a second line and is not confirmed to block it.

### 71. A window between the check and the start, and no watch during a run

The login is checked a moment before the agent starts. A login or logout in another terminal in that moment, or during a run or a terminal chat, is not seen. Since part 7c-3 the ACP chat has a watch (10.R12.8), with its own limits (items 91 and 92); `agent run` and the terminal chat have none.

### 72. Usage beyond the plan is not visible

The check proves which credential pays, not how much. A plan's extra usage, if the owner turned it on in the Claude account, is billed without umwayi knowing. Spend limits stay with the budget governor (H-078).

## Layer 5 addendum: logbook crash safety (found while building, not fixed)

Written Nov 10 2026. Spec: requirements.md and design.md, Layer 5, "Logbook crash safety"; tasks L5.1 to L5.5.

### 73. The intent sits next to the record

`.umwayi/logbook.pending` is in the same folder as `.umwayi/logbook.sha256`. Whoever can write both can forge an "interrupted write" and have the next umwayi write finish it. That is no new weakness: the same person can already rewrite the record (item 3). The hash chain and its outside anchor are the answer.

### 74. Durability depends on the disk

Every step is fsynced before the next one starts (the intent, the append, the record, and the folder after each change). Whether a power cut keeps them depends on the file system and the disk honouring fsync. The tests check that the calls happen and in which order; they cannot prove what a disk keeps.

### 75. A torn tail needs the owner

A power cut during the append can leave the start of an entry at the end of LOGBOOK.md. It is refused and never repaired automatically; the owner runs `umwayi logbook recover --torn-tail --by NAME`. If that command is itself stopped after the cut and before its entry, the next write finds the state before the interrupted write and logs an ordinary recovery entry, which does not say that bytes were cut.

### 76. The lock is a kernel lock on a local file

`flock` excludes processes on one machine. On a network share it may not. Where `fcntl` is missing (Windows) the logbook cannot be written at all, as the run lock cannot be taken there. Deleting `.umwayi/logbook.lock` by hand while a write runs lets a second writer lock a new file and write at the same time; no message asks for that any more. An older umwayi (which used a lock file that existed only while it wrote) and this one running at the same time on one root do not exclude each other.

### 77. Signals wait for the write

SIGTERM, SIGHUP, SIGINT and SIGQUIT that arrive during a write are delivered once it is done: milliseconds (two fsyncs, two atomic writes and one hash of the file), longer on a stalled disk. Two of the same signal during one write are delivered once. A logbook write from any thread but the main one is refused, because only the main thread can hold the handlers off; no such write exists today.

### 78. A SIGKILL between a change and its entry

The queue, the archive and the AI helpers change their files and then write their logbook entry. A SIGKILL between the two leaves the change without an entry. That is as before the addendum and not fixed here; the addendum makes the logbook write itself safe, not the work around it.

### 79. Leftover temporary files

`fsutil.atomic_write` removes its temporary file on every error, but not when the process is SIGKILLed: a `.umwayi-*.tmp` file can stay in `.umwayi/`. It is harmless and not cleaned up.

### 80. An interrupted seal that never wrote leaves no entry

If `umwayi logbook seal` is stopped before it appends, the next write drops its intent without an entry, because the logbook was not sealed and still cannot take one: the owner seals again. An interrupted seal that did write its entry is finished and logged like any write.

## Layer 10 part 7c-2: `umwayi agent login` and Kiro subscription first (found while building, not fixed)

Written Nov 10 2026. Doc facts: `adapters/NOTES-layer10.md` ("Signing in from umwayi", "Kiro: login and billing"). The tests use fakes only; the owner's real check is folded into 10.31.

### 81. `--claudeai` is not in the Claude Code CLI reference

The sign-in runs the pinned adapter's `--cli auth login --claudeai`. The flag is in the adapter's bundled Claude Code, not in the public CLI reference. If a release drops it, the sign-in fails and the login check afterwards refuses with exit 2: fail closed, but the owner then signs in by hand (`claude`, then `/login`).

### 82. The sign-in's own exit code is not documented

umwayi only logs it ("the login exited with code N"); the login check afterwards decides. A sign-in that exits 0 without signing in is refused by that check; one that signs in and exits non-zero passes it.

### 83. How the browser is opened is not documented

The sign-in gets the terminal, `BROWSER`, `DISPLAY`, the XDG desktop names, the D-Bus address and the SSH markers, which is what `xdg-open` and the remote fallback read. The older `KDE_FULL_SESSION`, `KDE_SESSION_VERSION`, `GNOME_DESKTOP_SESSION_ID` and `MATE_DESKTOP_SESSION_ID` are left out. On a desktop that needs one of them the browser may not open; the sign-in then shows the URL and code to copy by hand.

### 84. What the sign-in prints stays on the screen

umwayi never reads the sign-in's output, but the owner's terminal shows it, and its scrollback keeps the URL and code until the terminal is closed or cleared. The code is short-lived and is not a credential afterwards.

### 85. Kiro: the exit code of `whoami` when signed out is not documented

umwayi refuses a Kiro start when `kiro-cli whoami` does not exit 0. If a Kiro release exits 0 while signed out, the check proves nothing and the start fails later at Kiro's own sign-in error (exit 2, still fail closed). The owner checks it on the real machine (10.31).

### 86. Kiro: headless runs without `KIRO_API_KEY` are not confirmed

The Kiro docs conflict on whether `kiro-cli chat --no-interactive` needs `KIRO_API_KEY`. umwayi never passes it. If headless runs need it, every Kiro `agent run` fails with exit 2 (fail closed) and only the chats work. The owner checks one real run (10.31).

### 87. Kiro: the plan and the credits cannot be read

Every Kiro login pays from the subscription's credits, so there is no separate pay-as-you-go path to block. But how many credits are left, and which plan, is only visible inside a Kiro session. umwayi does not read it and sets no limit; spend stays with the budget governor.

### 88. Kiro gets the rest of umwayi's environment

`kiro_env` removes only `KIRO_API_KEY` and passes the rest of the environment (for example AWS variables) to Kiro.

## Layer 10 part 7c-3: the watch during an ACP chat and the chat end to end (found while building, not fixed)

Written Nov 10 2026. Items 59, 60 and 65 (nothing real was run, the supply chain, when SessionStart runs) still hold until the owner's first real run, whose steps are in `adapters/NOTES-layer10.md` ("The owner's first real run (10.31)").

### 89. A permission answer never sees the command

In a Claude Code ACP chat the rules answer a permission request from its `kind` (`read`, `execute`, `switch_mode`, `think` and others) and the tool name. The command, the path or the plan (`rawInput`) and the title are never in the action, so a rule can tell `Bash` from `Read` but not `ls` from `rm -rf`. The layer 9 hook, which runs first for every tool call, does see the command.

### 90. The adapter changes fast

The adapter publishes several preview builds a day. umwayi pins 0.101.0 and refuses anything else, so a new release cannot change the gate unnoticed; but staying on the pin means fixes arrive only when the owner updates it in a pull request that also updates NOTES, `package.json`, the lockfile and the constant. A release may change the session options, the permission shape or the `_auth/status_update` push; each update needs that review.

### 91. The billing watch limits the damage, it does not prevent it

The adapter pushes `_auth/status_update` only when what it reports changed: after `initialize`, at `session/new`, and at the start of each prompt, as an asynchronous probe. Nothing waits for it, so the push can arrive in the middle of a turn that the new payer is already paying for. umwayi then stops the chat (exit 2), but what was used until then is paid as the push says.

### 92. The watch trusts the adapter's push

umwayi reads only `params.authStatus.kind`. A push with no readable kind is ignored, because the adapter sends "cannot tell" as silence. If a release stops sending the push, renames the kind, or cannot see a payer change, nothing stops the chat; the login check before the start is then the only check. Not yet confirmed with a real adapter (10.31).

## Layer 11: scheduled runs (found while building, not fixed)

Written Nov 10 2026. Facts: `adapters/NOTES-layer11.md`. No systemd ran in the tests; the owner's real check (11.6) is not done yet.

### 93. Timers run only while the owner is logged in

The systemd user manager starts at the first login and stops after the last session ends, unless lingering is on. umwayi never runs `loginctl enable-linger`; `schedule install` says so. A run missed while logged out happens at the next login (`Persistent=true`), where the layer 6 gap rule still applies.

### 94. Anyone who can write the unit folder can change what runs

`~/.config/systemd/user` belongs to the owner. Any program running as the owner can edit a unit umwayi wrote, add a drop-in (`UNIT.service.d/`) or add a unit of its own. `umwayi schedule check` finds a changed file, a drop-in next to it and left over `umwayi-` units in that folder only. It does not see a unit of the same name earlier in the user load path, a drop-in in another folder of the load path, or units that are not named `umwayi-`. `systemd-analyze --user cat-config UNIT` shows what systemd really loads.

### 95. A scheduled run that finds the run lock held is skipped

A long chat, an agent run, a helper or another job holds the run lock. A timer that fires then gets Ask me first (exit 3) and one logbook entry, and is not retried until its next time.

### 96. A run stopped at the start limit writes no entry

After `TimeoutStartSec=30min` systemd stops the run's control group (SIGTERM, SIGKILL after 15 s). The logbook stays whole (crash safety), but the run writes no entry about that stop; only the user journal has it.

### 97. umwayi's output goes to the user journal

A scheduled run prints what it would print on a terminal (queue titles, draft names, the reason of a stop). systemd keeps it in the user journal, which the owner and administrators can read (`journalctl --user -u UNIT`).

### 98. A refusal of `umwayi run` shows as a failed unit

`umwayi run` keeps layer 6's exit code 1 for a refusal (the gap rule, for example), as L11-Q9 decided. systemd marks the unit failed for 1, 2 and 3 alike; the logbook says which.

### 99. Local time, and daylight saving changes

The calendar is the owner's local time, with no time zone in the timer. What a systemd calendar timer does with a time that is skipped or repeated by a daylight saving change is not documented on the pages read. cron (printed only) skips a missing time and runs a repeated time twice.

### 100. An install stopped by SIGKILL can leave one file

Install writes the service, then the timer. A SIGKILL between the two (or a power cut) leaves the service alone. `schedule check` reports it as partly installed, and running `schedule install` again keeps the identical file and writes the missing one.

### 101. The unit folder must be a real folder

A dotfiles setup that makes `~/.config/systemd/user` a link is refused (exit 2), so that umwayi never writes through a link it did not choose.

### 102. check and remove compare with what this Python would write

The unit file holds the absolute path of the Python that ran `schedule install`. `schedule check` and `schedule remove` render again with the Python running them. Run with another interpreter (or after the root or the umwayi checkout moved), they report the files as changed and remove refuses; the owner removes them by hand or installs again from the new place.

### 103. `--approved-by` is self-declared

As for `publish-draft` (item 1): any name is accepted when the rules say Ask me first. Nothing proves the person typing it is the owner. An AI helper that can run shell commands as the owner can pass it; the layer 9 hook sees that command first (`tool_bash`).

## Layer 5 addendum: logbook hash chain (found while building, not fixed)

Written Nov 7 2026 (PR 32), built early; the plan said Nov 16. No real Claude Code or Kiro ran in the tests; the agent tests used fakes.

### 104. Without an outside anchor the whole chain can be rewritten

The chain is kept in `LOGBOOK.md` itself. Someone who can write the file can compute a new chain for every entry and write the new whole-file hash into the record; `umwayi logbook verify` then says ok. Only a copy of the anchor kept somewhere else finds it.

- What the owner does: run `umwayi logbook anchor` weekly and before each submission, and paste the `COUNT:HEX` line into the hub repository's sync log and on the Kiro Notion page. umwayi never writes there. Then `umwayi logbook verify --anchor COUNT:HEX` compares.
- A later fix: sign the anchor, or publish it automatically to a place the writer cannot change.

### 105. A broken chain cannot be sealed by umwayi

`umwayi logbook seal` refuses a logbook whose chain is broken, and `seal --chain` refuses once a chain exists. This is on purpose: sealing over a broken chain or starting a new one would hide the edit. The only way back is to restore `LOGBOOK.md` from a copy you trust (for example git). Until then every umwayi write, every job, workflow and helper start is refused (fail closed).

- A later fix: a recorded, owner-approved restart of the chain that keeps the old values in the logbook.

### 106. The chain alone does not find a truncated tail

Cutting the newest entries off the end leaves a chain that is still valid up to the new end. The whole-file hash record finds it, and `verify --anchor` finds it ("shorter" than the anchor). If the record was rewritten too and no anchor is compared, it is not found.

- A later fix: as for item 104, an anchor kept elsewhere and compared on a schedule.

### 107. An edit before the start shows only at the genesis

The first chained entry (the seal entry) takes as its previous value the SHA-256 of everything before it. An edit in any older entry breaks that first link, and `verify` names the seal entry, not the old entry that was edited.

- A later fix: none planned; compare with git to find the line.

### 108. Nothing starts the chain on its own, and the start must be a seal

A logbook that was never sealed after this change has no chain until the owner runs `umwayi logbook seal` (an unchained logbook, sealed, always starts the chain) or `umwayi logbook seal --chain --by NAME` (a logbook that is already sealed and intact). The first entry with a `- Chain:` line must be a seal entry (source `umwayi logbook seal`); any other start is reported as "an entry before the start of the chain has a Chain line".

- A later fix: none planned (C-Q1: the owner starts it once).

### 109. Every append walks the whole chain

As asked (C-Q2), every append, recovery and torn-tail cut recomputes the chain from its start, under the lock. This adds to item 4: the cost grows with the logbook and was not measured.

- A later fix: keep the newest value with the hash record and check only the new end.

## Budget governor (found while building, not fixed)

Written Nov 2026 (PR 33). No real Claude Code, Kiro or paid account ran in the tests: the fake `claude` is the fake telemetry sender. The owner's capture of one real export (B.10) is not done.

### 110. A forged report is accepted (B-Q5)

The run secret is in the agent's environment, so any program the agent starts can send its own report to the receiver. A report only adds to the total, but a small forged report can turn a run that would be unknown (100 UU) into a cheap measured one. A large forged report stops the run (it passes the cap).

- A later fix: accept only reports whose resource says `service.name` is Claude Code, or compare the reported model and requests with what the adapter saw.

### 111. UU is an estimate, not a bill

The measured reading is Claude Code's own `cost_usd_micros`, which its docs call an estimate. On a subscription nothing is billed per token at all. UU says what the same use would cost at list price; it is not what the owner pays, and extra usage beyond a plan is not seen (item 72).

### 112. The parser follows the docs, not a real export

The OTLP JSON nesting (`resourceLogs`, `logRecords`, attribute value shapes such as `intValue`) comes from the OpenTelemetry and Claude Code docs. If a real Claude Code export differs, for example a count sent as a string or a token count as a double, every report is invalid and every Claude Code run is stopped with exit 2. Run the owner's capture (tasks.md B.10) before relying on the governor.

- A later fix: adjust the parser to the captured shape, with a test of that shape.

### 113. Managed settings can send telemetry elsewhere

A managed settings file can pin the OTLP destination and remove the variables umwayi sets. Then no report reaches umwayi and every run is unknown at the worst case. `budget status` shows the unknown share.

### 114. Budget entries are chained only once the chain is started

The ledger entries are chained like every other entry, but only after the owner started the hash chain (`umwayi logbook seal --chain`, item 108). Before that, only the whole-file hash protects them. umwayi does not refuse an agent start on an unchained logbook.

- A later fix: refuse agent starts until the chain is started.

### 115. `logbook verify` does not check the budget shapes

A `umwayi budget` entry that is not one of the fixed shapes is found by the governor (every start and `budget status` exit 2), not by `umwayi logbook verify`, which still says ok when the chain and the hash match. A consistent edit of a settle (micros, UU and released changed together) is found only by the chain and an outside anchor (items 3 and 104).

### 116. The cap is checked on reports, once a second

Claude Code exports every 5 seconds, and umwayi checks the total once a second. A run can pass the cap by what it spends in those seconds before it is stopped. The overrun is settled as measured.

### 117. Kiro has no mid-run cap

Kiro sends umwayi nothing. A Kiro run reserves and settles what `units.yaml` declares, but nothing stops it in the middle for its cost; only its timeout does.

### 118. The last report has to arrive before the agent is gone

After the agent is stopped, the receiver waits up to 6 seconds, but only while a report is still being received. An export Claude Code did not send before it exited cannot arrive later. A report sent by an orphaned process after the stop is lost. A short run whose only export came too late is unknown, never zero.

### 119. A day is the logbook date of the reservation

A run that passes midnight counts on the day it was reserved. There is no week or month limit.

### 120. `status` cannot tell a lost reservation from a running one

Both have no settle yet, so `status` names them the same way. `settle-lost` refuses while any umwayi run holds the run lock, so it never settles a run that is still going.

### 121. `settle-lost` settles at the worst case

A reservation lost to a SIGKILL is settled as unknown at `unknown_worst_case`, never at what the run really spent: the reports of that run were in the killed process.

### 122. The receiver does not limit how often it is asked

A local program can send many requests without the run header. Each is answered 401 and counted, and never read, but nothing slows it down.

### 123. Limits carry no date or source

Rates in `units.yaml` have a value, a date and a source; limits are plain numbers in UU (design.md). A change to a limit is dated by its change entry in the logbook.

### 124. Every start reads the whole logbook for the ledger

The ledger is read from the logbook on every start (B-Q1), and three more entries are written per run. This adds to items 4 and 109; it was not measured.

### 125. One module has network code

`umwayi/telemetry.py` imports `http.server`, only inside the function that starts a receiver, and binds 127.0.0.1 only. The network guards in `tests/test_system.py` and `tests/test_automation.py` allow exactly that import; every other module still has none.

### 126. The telemetry names are added at the start, not in the ACP allow list

The names of B.R2.2 are added to the environment of the agent itself (run, cli chat, ACP chat), not to `CHILD_ENV_SET`, so the gate check programs (`node --version`, the login check) run with no telemetry at all.

### 127. The placeholders are a guess

Until calibrated, the limits are the placeholders of B.R1.7. Without `units.yaml`, every run is unknown at 100 UU, so one agent can start three times a day (`per_agent_per_day` 300) and all agents five times (`per_day` 500).

### 128. Kiro credits are the owner's own count

The `credits` reading multiplies `credits_per_run`, a number the owner declares, by the credit rate. umwayi reads no credit count from Kiro.

## Whole-system test (found while building S.1, not fixed)

Written Nov 10 2026 (PR 36). The test uses fakes only; the owner's real runs (10.21, 10.31, 11.6, B.10) are not part of it.

### 129. A job checks the kill switch at its start only

`umwayi run` (and so a scheduled run of a job) checks the kill switch before it reads the jobs file, and not again. A job that has started finishes even if the kill switch is turned on meanwhile; agents are checked every second (layer 10), jobs are not. A job takes a moment (`queue-list`, `check`, `report`), so the whole-system test checks the switch at a scheduled job's start, not in its middle.

- A later fix: none planned while jobs stay this short.

## Security scan (found while building S.2, not fixed)

Written Nov 10 2026 (PR 37). The results, the tools and what the scan cannot prove: [SECURITY-SCAN.md](SECURITY-SCAN.md). Item 122 changed with it: the receiver now handles at most 16 requests at once and cuts each at 10 s, though it still does not slow down a client that keeps trying.

### 130. The advisory scan is true on its date only

OSV-Scanner and `npm audit` found no known vulnerability in the adapter's 112 packages on 2026-11-10. A new advisory can appear for any of them on any day, and nothing in umwayi checks again on its own.

- A later fix: run the commands in SECURITY-SCAN.md before each submission, or add a scan job to CI after Dec 3 (S-Q13).

### 131. `npm audit` tells the registry the package list, and may skip peer packages

`npm audit --package-lock-only` sends the list of the adapter's packages to the npm registry (accepted in S-Q4). It counts 102 of the 115 as peer dependencies, and its documentation says it does not check peer dependencies. OSV-Scanner, offline, read all 112, so the result rests on it.

### 132. The Claude Agent SDK is not open source and not scanned inside

Its 9 packages are under Anthropic's terms ("all rights reserved"), which the owner reads (S-Q11). Their prebuilt platform programs are not scanned by anything here; only their published files' signatures are checked.

### 133. Python 3.10 is end of life

Python 3.10 gets no security fixes since 2026-10-01, but `pyproject.toml` still says `requires-python = ">=3.10"` and CI tests it. Nothing was changed by the scan: keeping or dropping 3.10 is the owner's decision (open in SECURITY-SCAN.md).

### 134. A local flood of the receiver can make the agent's reports wait or be lost

At most 16 requests are handled at once; one more is answered 503 at once, and every request is cut at 10 s (S-Q6, S-Q7). A process of the same user that keeps 16 slow connections open can make the agent's own reports wait, and a report refused that way is not counted. The OTLP exporters retry a 503, but if the agent's last report is lost the run reads lower, or unknown at the worst case. It is the same-user boundary (item 135).

### 135. Nothing here protects against a process of the same user

umwayi, its agents and the owner's other programs run as one user. Such a process can read the agent's environment (the run secret), write the logbook and its record, change unit files, plant links in the root, or flood the receiver. The hash chain, the anchor, the kill switch and the checks in this list make some of it visible or harder; none of it is prevented (S-Q10). A sandbox could change that and is deferred (L11-Q13).

### 136. Hard links are refused only where umwayi writes in place

umwayi writes in place only to `LOGBOOK.md` (an append) and the logbook lock (its holder's pid); both now refuse a second name. Every other file it writes is replaced through a new file (`queue.md`, the hash record, the intent, the archive) or created new with `O_EXCL` (drafts, the outbox, `KILL`, unit files, the capture file), so a hard link there is replaced, never written through.

### 137. Some reads follow a link, and a check before a read can race

`rules.yaml` (and `--rules PATH`) and `umwayi.json` may be links to a regular file elsewhere, for a dotfiles setup; they must be regular files of at most 1 MB and 64 KB. Other files umwayi reads are refused when they are links, but the check comes before the open, so a link swapped in between can make umwayi read another file's text. Nothing is written that way; the writes are atomic or `O_NOFOLLOW` (item 136).


## Layer 12: the snapshot (found while building UI.2, not fixed)

### 138. The snapshot is only as fresh and as true as the last run

`umwayi view snapshot` writes counts at the moment it runs; the page shows the snapshot's date and does not poll. The logbook counts in it leave out the command's own entry, so the file says one entry fewer than the logbook has after the run. Anyone who can write the file can forge it: the page checks its shape, not its truth (the logbook chain and `umwayi logbook verify` are the check). It also does not say whether the logbook was intact later than the run.

### 139. A reader that fails shows as null, and a check before the write can race

A layer reader that raises (even for a bug) gives null for its part and the command still exits 0, as 12.R4.3 says; only an error in the command itself exits 2. A missing `queue.md` is null, not 0, because only `schedule.yaml` is allowed to be absent. The `--out` target is checked (regular, one name, an earlier snapshot) and then replaced through a new file: another process of the same user that swaps the file in between would have its file replaced, never written through (see 135). `used_uu` counts a reservation without a settle in full, so a lost run raises it until `umwayi budget settle-lost`.

## Layer 12: the public site (found while building UI.6, not fixed)

### 140. The public site's policy lets inline scripts run

Next.js writes three small inline scripts into every page (its start-up and the page data), and a policy of `script-src 'self'` stops the page from starting, so `site/next.config.mjs` sends `script-src 'self' 'unsafe-inline'`. A script from another host is still refused, and so are a remote style, font, image or connection, but a script injected into the page itself would not be refused by the policy. The site takes no input, keeps nothing and has no cookie, so there is nothing today to inject; a nonce would close this and would make every page render on each visit instead of being sent as a static file. The choice is left open in the pull request for the owner.

### 141. The site's host sees which files a browser asks for, and the browser pass is one browser

The device hints are read in the browser and never sent, but the host that serves `site/` logs which files are requested, so its logs can tell whether the scene script was fetched (Standard) or not (List). That is a property of serving files, not tracking, and nothing else about the device is in a request. The pass that showed this ran in one browser (Chrome for Testing 158 with software drawing); Firefox, Safari, a real GPU and a screen reader are not checked, and a browser that offers no Network Information API gets Standard by the rule of 12.R16.6.

## Layer 12: reading the snapshot (found while building UI.3)

### 142. A snapshot is true only as far as the last command and the owner's hands

The page checks the shape of the file, not that it is true. A file edited by hand with a correct shape (a queue of 3 where there are 30) loads and is drawn. The date shows how old it is; nothing makes the page refresh it. The reader is also stricter than JSON: it accepts only the command's own text, so a file re-saved by a program that writes `2.0` for 2 or reorders nothing but changes a number's form is refused with the one message, and the message does not say why.

### 143. Unknown has one look for four stations, and two are fixed by the spec

A queue, logbook, schedule or budget that is null shows an unlit lantern on a post beside the feature, no count and "unknown" in the panel. Rules draws unknown as 12 lanterns of Ask me first and the kill switch as on (12.R3.9), so a rules file that really has 12 Ask me first rules looks the same as one that could not be read; the panel and the strip say which. The look was seen in software drawing at one size only.

### 144. The public site now reads a file a visitor opens

12.R17.6 and rule 10 said the site never reads a snapshot; the owner's task for UI.3 changed that. The file is read with `FileReader` in the browser and the page makes no request with it, but the site's host cannot prove that to a visitor: only the source and the request log of the browser pass do. A visitor who opens someone else's real snapshot sees counts of that root, and nothing in the file is text from a file of theirs (12.R4.2).

### 145. A quiet station stays at its default place

The design proposed that a quiet station drifts out past its default place. The acceptance test says a quiet snapshot gives the defaults, so a quiet need is 0.4 and a station only comes nearer. One constant (`QUIET`) changes it. Open question in the pull request.

## Layer 12: the owner checks panel (found while building UI.4)

### 146. The panel's steps are a copy of the NOTES files, and the B.10 steps are new

Every step, code block, command and "what to record" cell in `ui/src/data/checks.js` is found word for word in its NOTES file by `tests/test_checks.py`, so a change in one place and not the other fails the suite. The test cannot tell whether a step is right. The NOTES had no steps for the B.10 capture, so UI.4 added five to `adapters/NOTES-layer10.md` from tasks.md B.10 and `umwayi/telemetry.py`; they were not run. A tick means the owner says they did the step. The page runs nothing and never shows a check as passed.

### 147. The value warning is a hint with misses and false alarms

It fires on an email address, `://`, a run of 24 or more letters and digits, a hex string of 16 or more digits (or a UUID), and, for a step marked as an exit code, anything but a number up to 255. It misses a secret that is short, split by dashes or underscores into pieces under 24, or written in words, and it flags a plain 16 digit number. It never blocks a tick or the export. A typed result is on screen and in the export text until the owner closes the page.

### 148. The notes exist only in the page, and Download is a data address

Nothing is stored (12.R2.2): a reload, a crash or closing the tab loses every tick and result, and the panel says so. Download saves the text through a link whose address holds the text, so it needs no Blob and makes no request. It saved the file in the one browser tried (headless Chromium, under the live view's policy `default-src 'none'` and under the site's); other browsers may refuse a very large data address, and then Copy is the way.

## Layer 12: access and polish (found while building UI.5, first slice)

### 149. The contrast check reads the CSS colours, not the pixels

`ui/test/contrast.test.mjs` works out the ratio of the ink and muted text on the page, the solid panel, the glass over the page and the dark wells of the code blocks and fields, in normal and in Calm mode (the lowest is 6.0 to 1 in Calm mode, against a floor of 4.5), and of the focus ring and the field border (3 to 1). It does not check the glass panel and the name pills over the sky, which the owner cut on Nov 11, so text over a bright part of the picture is not measured, and the picture's own colours are not in it. A colour written in the CSS that is not one of the variables fails the test, but a new ground that is not in the list is not found.

### 150. The keyboard and screen reader pass is read from the code, and the phone layout from one browser

The names, landmarks, heading order, Tab order, live regions and target sizes are tested on the built HTML and on a fake document (`ui/test/access.test.mjs`), and the owner checks panel was measured at 390 by 844 in headless Chromium (no sideways scroll, no control under 24 pixels). No screen reader was run: how NVDA, VoiceOver or TalkBack read the hidden file input, the live regions, the picture's text alternative and a panel that opens by script is not known (step 1.12 of the interface check asks the owner). The station panel on a phone is a sheet at the bottom of the first screen (the picture area), not of the whole window. The frame rate check and the by-hand pass of the finished scene wait for UI.7.

## Layer 12: the High tier of the public site (found while building UI.7)

### 151. High is checked only in software drawing, and its frame rate is unknown

Every browser run of High was in headless Chromium with SwiftShader, which draws on the processor: High drew there, and the fallback, the switch and the wildlife worked, but a drag in High timed out and a frame took seconds. That says nothing about a real GPU. The automatic rule offers High only on a fast network, 8 or more cores, 8 GB or more where the browser says, a large screen, no reduced motion and a hardware renderer, so a visitor with a weak GPU and strong numbers can still be given High. Their way back is the switch, which keeps Standard in the address. Slow frames step the detail down inside High as in Standard (a lower pixel ratio, then no bloom, and less grass), but nothing steps down from High to Standard by itself (UI.8 in tasks.md, not built, KNOWN-LIMITS 156).

### 152. High is about 4.7 MB of photographs, and the 15 s limit is one number for every network

The five photographs are 4.72 MB (JPEG does not compress further) and the High code 10 KB compressed, on top of Standard. The rule offers High only on a reported 4g network of 10 Mbit/s or more, but that is the browser's estimate. A visitor who chose High on a slow network waits up to 15 s for it and then gets Standard with the words saying why; the files that arrived late are not used, and the next visit downloads them again unless the browser cached them. The limit is not tuned to the network.

### 153. The antelope is drawn three times life size, and is clear of trees only for the default view

The antelope stands on a crest about 130 m from the default camera, where a real impala would be a speck of about 7 pixels (a back about 7 pixels high at 1440 by 750). The owner asked for it to show, so the model (a real impala) is drawn `ANTELOPE_SCALE` = 3 times larger: a back about 21 pixels high and a body about 34 pixels long in the default view, a shoulder height of about 2.5 m against 0.85 m for the animal. Nothing near it gives a size to compare with, so it reads as an antelope, but it is not the size of one. Its keep out reach, its sight line and its speed (1 m a second, 8 pixels a second at that distance) are all in the drawn size. The High forest leaves out every young tree that would stand between the default overview camera and the antelope's path (`blocksAntelope`), and every tree in the line of each station's view (`inStationView`). A camera that the visitor drags elsewhere can see the antelope behind a tree, or close up, where it is plainly too large, or not at all. The birds fly under the top bar of the default view at 1440 by 750 only; at other sizes they may be behind it.

### 154. The photographs are of other places, and High still looks made in parts

The grass, soil and rock photographs are CC0 from Poly Haven and are not of Laikipia; the shaders tint them towards the Standard palette. Up close the ground and the rocks read as real surfaces, but the shepherd, the animals and the trees are still shapes made from code: the shuka is a lathe with folds, the coats are smooth shells, the tree crowns are lumps, and the far forest is the Standard forest. The screenshots in the pull request show where.

### 155. A High that fails after it is on is not caught

The fallback covers a High that cannot load its code, cannot load a photograph, throws while it is built, or is too slow. A failure after High is on (a shader that does not compile on a given GPU, a lost context) shows as whatever the browser does with it: three.js logs the shader error and the object is not drawn. A lost context goes through the Standard path (List, with the words). No test or browser run here had a shader fail to compile.

### 156. High does not step down to Standard by itself (not built)

A device that is offered High, or whose visitor chooses it, and draws it slowly keeps High. The detail ladder lowers the pixel ratio, then the bloom and the multisampling, and thins the grass, after slow frames, but nothing takes High off when that is not enough, so a weak GPU with strong numbers can stay at a few frames a second. The visitor's way back is the switch. The owner asked for the automatic step down on PR 58 as a follow-up, not part of that pull request: it is the task UI.8 in tasks.md and is **not built**. Until it is, the sandbox runs of High in software drawing (1 to 3 frames a second) are what a slow device would show.

## Layer 13: elections (found while building L13.1)

### 160. `review_by` depends on the owner renewing honestly, and a rule with none never lapses

A Yes rule runs out only if it has a `review_by` date. A rule with no date, or a date the owner moves forward without looking, stays in force. `umwayi rules due` lists what needs a look, but nothing makes the owner run it, and a date more than 366 days ahead is only flagged as `far`, not refused (L13-Q10). The owner may put `review_by` in `rules.yaml` only after the version with elections is installed: older code calls it an unknown field and every check gives Ask me first.

### 161. A clock set far ahead lapses every dated rule, and the election clock never goes back

The date of a check is the latest of the system date, `--date` and the newest logbook date. A system clock set far ahead, or one entry with a far date, makes every dated Yes rule give Ask me first until the owner edits the dates; that is a safe error, not a Yes. A clock set back changes nothing, because the newest logbook date still counts. If the logbook cannot be read, only the system date and `--date` are used, and the entry of that check cannot be written either, so no Yes comes out.

## Layer 13: reversal (found while building L13.2, written in L13.4)

### 162. A reopen links a hash, so it needs the hash chain, and an older entry cannot be linked

`umwayi decision reopen` names the old entry by its `Chain` value. A logbook whose chain has not started cannot be reopened (the owner starts it once with `umwayi logbook seal --chain`), and a decision closed before the chain started has no hash to link, so it is refused. A decision that was answered or closed by hand in `queue.md`, with no closing entry in the logbook, is refused too, and so is a `queue.md` row that was deleted by hand after a reopen: the row is not made again. Only the newest closing entry of a decision can be linked. The link proves which entry the owner meant; it does not prove the entry was wise, and a process of the same user that can write a well formed chained entry can write a reopen that nobody asked for (item 135 again).

### 163. The revisit condition is the owner's words, and nothing watches for it

`--revisit-if` keeps one line of text in the logbook entry of the answer, up to 200 characters, or `none`. umwayi shows it again when the decision is reopened and does nothing else with it: it does not check that the condition came true, and it does not remind the owner. An answer from before layer 13 shows `not recorded before layer 13`. A condition in another shape than the fixed one, for example text a person added to an entry, is not read. The text is the owner's, so a vague condition stays vague.

## Layer 10 part 8: OpenCode over ACP, and Muse Spark Open (the OpenCode chat is built and tested with a fake; Muse Spark Open is not built)

Items 180 to 187 were written from the spec (10.R13, PR 44) and were made true to what is built in task 10.51 (Nov 13): each was read against `umwayi/agents.py`, `umwayi/acp.py` and `adapters/opencode/plugin/index.js`. Items 188 and 189 are still the spec's, because Muse Spark Open is not built (10.55 makes them true). Items 190 and 191 come from the real install of 10.42. The tests use a fake `opencode` (10.47), so none of this was seen in a real chat: the owner's check is in `adapters/NOTES-layer10.md`, "The owner's real check of the OpenCode chat (10.51)". Later items for the same chat: 242, 243, 248, 250 and 251. Facts with links: `adapters/NOTES-layer10.md`, "OpenCode V2: the facts checked for the adapter spec".

### 180. umwayi's inline config is the weakest place for a policy, and V2 does not document it

umwayi passes its strict config in `OPENCODE_CONFIG_CONTENT` (`opencode_inline_config()`, the one `OPENCODE_` name the child gets). The V2 source reads that variable and 2.2.7 applied it in 10.42, but no V2 docs page names it, so a release could drop it. In the source, policies from earlier-loaded documents win, and the inline content loads late. So a `provider.use` or `integration.use` statement with `allow` in the global file, a project file, a connected Console workspace or a managed file outranks umwayi's `deny`.

- What protects you: the plugin is named only in the inline config, so if OpenCode ignores it, no canary is written and the chat is refused (exit 2, after at most 30 seconds, nothing of yours sent). Gate check 4 (`managed config`) refuses when a managed config exists, and gate check 5 (`other config`) when a project, home or suspect global config exists. The plugin also raises every `allow` of a permission to `ask`, so the second gate does not rest on the inline `ask` rule alone.
- What it does not protect against: a Console workspace (182), and a config written after the start (181). Whether the inline policies hold in a real chat is the owner's check; the tests see only the bytes of the config and a fake that applies it as the tests say.

### 181. Other config is found by name and by text, and only at the start

Gate check 5 looks for `opencode.json`, `opencode.jsonc` and `.opencode` by name from the workdir up to `/` (the path as given and the real path), for `.opencode` in the home folder, and for `plugins`, `plugin`, `agents` and `agent` entries in the global OpenCode folder (`$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode`). It searches the global `opencode.json(c)` as quoted text for ten fixed keys (`permissions`, `permission`, `policies`, `plugins`, `plugin`, `agents`, `agent`, `experimental`, `enabled_providers`, `disabled_providers`) and refuses a file over 1 MiB unread. It does not run OpenCode's merge, and it reads names, sizes and those words only: a refusal shows a path and a key, never file text. It runs at `agent check` and before every chat, not during one.

- `{file:PATH}` substitution in the global file can pull in keys from a file umwayi never reads.
- A remote `.well-known` config from a connected integration is not seen.
- OpenCode reloads a changed config during a chat. An AI helper that writes `.opencode/opencode.json` in the workdir could add a plugin or a policy after the check. The starter rules (`oc-no-guard-edits`, `oc-no-guard-shell`) say No to edits and shell commands that name `opencode.json`, `.opencode`, `rules.yaml`, `LOGBOOK.md` and `.umwayi`, but they match plain text, and a shell command can be written to get past a text match. They are only in force if the owner's `rules.yaml` has them (the repo `rules.yaml` does).

### 182. A connected Console workspace or a saved account is invisible

Saved accounts live in OpenCode's database, which umwayi does not read. A connected Console workspace delivers policies that rank right below managed ones, so it can allow what umwayi denies. A ChatGPT sign-in and a saved OpenAI API-key account are both `openai`. umwayi allows only the connected-account form `openai#*`, but whether an API-key account also takes that form was not confirmed.

### 183. The permission request does not say what OpenCode's rules matched

An OpenCode `toolCall` carries the tool's `name`, `kind`, `title` and `rawInput`, not the permission's action and resources. umwayi answers by `kind` and `tool` only, as for Kiro and Claude Code. A tool name is sent to the rules only if it is a letter followed by up to 39 letters, digits, `_` or `-`; any other name (one with `:` or `.`, or over 40 characters) is left out, so its rules see only `kind`. An MCP name such as `mcp__github__create_issue` passes that test and is sent. When OpenCode has no tool for a request, `name` is absent and the answer is Ask me first at most (248).

### 184. The first gate is JavaScript inside OpenCode

The plugin is umwayi's only JavaScript in a gate. It runs in the `opencode` binary's own runtime, Bun 1.4.4 on 2.2.7, where `node:child_process` `spawnSync` and `node:fs` worked (10.42 and the smoke test of 10.45); the tests run it under `node`, not Bun, so a difference between the two is not caught by them. It starts one Python process per tool call, so every call waits for `umwayi check` (it gives up and stops the call after 10 s). It works only while OpenCode keeps calling `execute.before` for every tool and lets a throw stop the call. The spec's reading of the source (not seen on a real install) is that built-in plugins cannot be turned off and that the order of the `evaluate` hooks is not documented, so a later hook could lower umwayi's `ask` back to `allow`; the first gate still runs, and no test can show the order.

### 185. One tool call can write two logbook entries and ask twice

The plugin's check writes one `umwayi check` entry. The permission request that follows writes another (10.49 counts one entry per check). With rules that say Yes in the first gate but have no `acp_permission` rule for OpenCode, the owner is still asked at the permission request: no matching rule is Ask me first. The starter rules cover the common cases. The logbook keeps no action JSON, so an entry does not say which of the two gates wrote it.

### 186. The canary token and the inline config are in OpenCode's environment

`OPENCODE_CONFIG_CONTENT` holds the hook command, the canary path and the token, and it is in the environment of the `opencode` process. Whether a shell command OpenCode runs inherits it was not tested on a real install; assume it does. An AI helper that can read it could write the canary file itself (the plugin creates it with `O_EXCL`, and umwayi accepts a regular file holding exactly the token). The canary is checked before the first prompt, before the model has run any tool, so this matters only if OpenCode ran a tool before then. The same was accepted for the Claude Code canary (7b). The folder is removed when the chat ends, and a new folder and token are made for every start.

### 187. OpenCode changes fast, and the version is read as text

There were 46 stable 2.x releases between Sep 11 and Nov 10 2026, and several facts the design uses are from the source, not the docs. The version check takes the first `N.N.N` in the first 4096 bytes of `opencode --version` (on 2.2.7 the whole output is `opencode v2.2.7`; a 1.x or older than 2.2.3 is refused) and compares it with 2.2.3. Only 2.2.7 was run (10.42); 2.2.3 to 2.2.6 are allowed but were not seen, and no version is capped from above. A newer release may rename a hook or change the config order. The canary and the gate checks fail closed when that happens, but they cannot catch a change that keeps the names and loosens the behaviour. The real `--version` output is still to be recorded in the owner's check.

### 188. Muse Spark Open: the local server is trusted as it is

umwayi checks that `base_url` is a loopback or private address, not what is behind it. It does not check that the served model really is Muse Spark Open. Plain `http` to a private address sends prompts and code across the owner's network unencrypted (MS7). The licence was read only through summaries; the owner reads `LICENSE.md` before the notice is added (MS4).

### 189. Muse Spark Open: free means local only, on large hardware

No free hosted route was confirmed on Nov 9 and none was looked for again on Nov 11. The local route needs about 300 GB of memory or more. The V2 field names for tool calls and settings on a custom provider are not confirmed, so the route stays refused until a real install confirms them (10.52).

### 190. Code Mode runs JavaScript whose inner tools ask no permission

OpenCode's `execute` tool (Code Mode) runs JavaScript that can call `fetch` and OpenCode's own tools, such as `worktree_create`, `worktree_remove` and `session_move` (seen on 2.2.7 in 10.42). `execute` itself asks no permission, and neither do the inner tools.

- The first gate sees `execute` and each inner tool under its own name (`opencode_worktree_list`). With the starter rules (Ask me first), the plugin throws and they do not run.
- A rule that says Yes to `tool_execute` lets the model run any JavaScript that the inner tools and `fetch` allow. A `fetch` then asks as the `execute` tool call: the owner sees the code, not the URL, and the rules see only `kind: other`.
- No setting to turn Code Mode off was found (OC15).

### 191. OpenCode downloads ripgrep from the network on its own

On its first use in a fresh home folder, OpenCode 2.2.7 fetched `ripgrep` from the network and saved it as `bin/rg` under its cache folder (`~/.cache/opencode/bin/rg`), seen in 10.42. This is network access by OpenCode itself, and it is outside umwayi's control.

- umwayi cannot stop it or see it. It happens inside the `opencode` process, before or apart from any tool call, so neither the plugin nor a permission request is involved, and nothing about it reaches the logbook.
- The policies in umwayi's inline config cover providers and integrations (`provider.use`, `integration.use`). They do not cover this download.
- What would fix it later: a cache folder with `rg` already in place, inside a private `HOME` that umwayi gives OpenCode, so there is nothing to fetch; or a network sandbox around OpenCode, after Dec 3.

## Layer 13: courts and the rules change log (found while building L13.3)

### 192. Petition limits stop a flood, not a patient helper

A helper name is a label the helper gives itself, so the per helper limits are bounded only by the totals (10 open, 10 a day). A refused petition writes nothing, so a flood leaves no trace in the logbook. The day of the daily limits is the date of the entry: a helper that passes a later `--date` gets a new day, and the logbook dates then move forward for every command. The reason is untrusted text in `queue.md` that an owner, or an AI helper that reads the queue, can still take as an order.

### 193. The rules change log shows a weakening and does not hold it

A rule weakened by an edit (`no-money` from no to yes) is used at the next check, after its entry is written. The entry makes it visible and dated; it does not stop it (L13-Q11). A process of the same user can also write a well formed `umwayi rules` entry with the new hash before the check, so the change is not listed (item 135 again).

### 194. Only ids, verdicts and review dates are listed

A change of a rule's matchers, title, text or cause shows as `no rule changed` with a new SHA-256. A No rule whose matchers were narrowed to match nothing is a weakening that the entry does not name (L13-Q20). Compare the file with an older copy (for example git) to see what changed.

### 195. A dry run neither logs a rules change nor falls back

`umwayi check --no-log` writes nothing, so changed rules are not logged by it and its answer comes from the new rules as they are (L13-Q19). A dry run approves nothing in umwayi, but a script that treats its Yes as a permission would use rules that are not logged yet.

## Layer 13: graded autonomy (found while building L13.5)

### 166. A process of the same user can write well formed, chained score inputs

The record is chained and read line by line in fixed shapes, so a hand edit, a deleted entry, a forged line or an unchained entry makes the whole record invalid and nothing moves. A process that runs as the owner can still call the same append umwayi uses and add well formed `umwayi autonomy record` entries, chained and recorded like the owner's own. Graded autonomy would then move on a record the owner did not write. This is item 135 again: nothing here protects against a process of the same user. The anchor of the chain (`umwayi logbook anchor`, kept outside the machine) shows that entries were added, not who added them.

### 167. The score is a statistic of the past, and a class that is too wide mixes histories

The score counts what the owner did with earlier proposals of one class. It cannot see that today's action differs from the last eighty, that the context changed, or that one rule's matchers catch more than the owner meant. A class is only as narrow as the matchers of the rules that name it; `umwayi autonomy status` shows the counts, so a class that grew is visible, not prevented.

### 168. Reversibility and cost are the owner's declaration

`reversible` and `cost_uu` are written by the owner in the rule. umwayi does not check that an action of the class can really be undone or what it really costs. A rule that says `reversible: true` for something that cannot be undone lets the score move it. The never list keeps money, publishing, an install, a spending approval and the start or permission of an agent out, by action type only.

### 169. Careless approving builds a high score

The owner's record is the input. Approving without a look counts as approved as proposed, and the score rises. The bound is cautious (a lower bound, z 2.58 suggested, a revert weighs 3 and starts a cooldown), and nothing here checks whether the owner's record is wise.

### 170. The moves of one day are capped, but a wrong move is still a wrong move

`max_moves_per_day` caps the moves of one class on one logbook day, and a `rejected` or `reverted` outcome stops the class for the cooldown. A move that was wrong has still happened: turning graded autonomy off takes effect at the next check and undoes nothing. The owner records `reverted`, which holds the class for the cooldown and lowers its score. A move is also made only in a check that logs; a script that reads the answer of a dry run never sees a move.

## Local backend (W6): `umwayi serve` (built Nov 12 in W6.1 to W6.6; the page client W6.9 and the chat and intake routes are not built)

These are the limits of [serve.md](serve.md). Items 196 to 212 were written before any code (W6.0 pull request) and are confirmed or corrected by the build (W6.1 to W6.6, Nov 12); items 233 to 236 are new from the build. Items about the chat (206, 207, 209, 211) and the page (197) describe parts that are not built yet. Numbers are never reused.

### 196. Whoever has the token is the owner, as far as the backend can tell

The token is checked, not the person. A process of the same user that learns it (from the terminal scrollback where it was shown once, the clipboard, a shell history, a screen capture) can send any request the table allows. In a chat that is at most a reject of an Ask me first (item 211); the page cannot approve one. The raw token is never on disk and never in a child's environment, and the example rules keep an AI helper from `umwayi serve` and from the token file, but those rules match text (item 12). The same kind of limit as items 1 and 15.

### 197. A script that runs inside the page can use the token

The page holds the token in memory, so any script that runs in the page can send requests with it. What stands in the way is that the page sets all text as text, loads no script from outside, has a Content-Security-Policy, and is tested for it. That is a list of checks, not a proof, and a flaw in the page's own code or in a package it bundles would defeat it.

### 198. The port is open to every user of the machine

127.0.0.1 is shared. Another user of a multi-user machine can connect, send requests and try tokens (5 failures a minute, then 429, and a 256 bit token). They cannot do anything without the token, but they can use up request slots (item 199). A Unix socket with file permissions would stop that and a browser cannot use one.

### 199. Any local process can crowd out the owner

The server handles 16 requests at once and answers the 17th with 503 without reading it. A process that holds 16 connections open for the 10 second deadline, over and over, keeps the owner's page waiting. Nothing identifies the caller on loopback, so nothing can tell it apart.

### 200. A request changes the real files, exactly as the command line does

The queue, the kill switch and (later) a chat are real. A wrong click in the page is a wrong command. The rules check adds Ask me first by default, but a Yes rule written for `serve_request` by type alone says Yes to every route of its class. The page shows the route and the words, and the owner writes the rules.

### 201. Each request adds logbook entries, and each append reads the whole logbook

A read adds two entries (the rules check and the request), a write up to three. Item 4 applies: every append reads and hashes the whole file. Requests with no valid token, and requests over the rate, are counted in one summary entry a minute, so a flood cannot add an entry each, but a long session of authenticated use grows the file. **Measured at the build (Nov 12, the in-process tests, one machine):** a read costs about 10 ms while the logbook is under 600 entries (180 KB) and about 28 ms between 600 and 1200 entries (360 KB), because each of its two appends reads and hashes the whole file; one request pair adds about 600 bytes. A thousand requests a day would add 0.6 MB a day. The owner approved logging every request on Nov 12 and asked for this volume to be looked at again after the build (W6-Q10); the numbers are for that look.

### 202. No TLS on loopback

The token and the responses travel as plain HTTP on 127.0.0.1. A user who can read loopback traffic (root, or a process with packet capture rights) sees them, and could replay the token until it expires or is rotated. Such a user can usually do more than that already. A certificate for 127.0.0.1 needs a local certificate authority, which W6 does not build.

### 203. A tunnel that rewrites `Host` can carry reads

The gate refuses any `Host` that is not `127.0.0.1:PORT`, which stops a tunnel or reverse proxy that passes the public name through. A tunnel that rewrites `Host` to the local address, and a client that has the token, can send `GET` requests, which need no `Origin`; a `POST` or `DELETE` from a remote page carries the page's own origin and is refused. The docs say never to carry the port out. Nothing in umwayi can detect a tunnel.

### 204. The page and its fingerprint sit in the same folder

`GET /` serves the built page only if its SHA-256 matches `ui/dist/build.json`. Someone who can write one can write the other. This is item 3 again (a record next to the file it protects), and the owner's build is the only source of both.

### 205. Browser behaviour comes from documentation

How a browser sets `Origin` and the fetch metadata headers for `http://127.0.0.1`, what it does with a private network request from a public page, and how it treats `frame-ancestors` were read, not tried. The server relies on the token, the exact `Host` and the exact `Origin` on `POST` and `DELETE`, and checks the other headers only when present. The by-hand pass (W6.10) uses one headless Chromium; Firefox, Safari, a real phone browser and an extension that rewrites headers are not tested ([NOTES-w6.md](../adapters/NOTES-w6.md)).

### 206. A web chat holds the run lock

One run at a time for the root, so while a chat started from the page is open (up to its 10 minute idle stop), a scheduled job, `umwayi run` or a command line chat gets the lock's answer (Ask me first, exit 3).

### 207. Only ACP chats work over the web

An agent with `transport: cli` needs the owner's terminal and is refused. The limits of items 52 and 53 apply to Kiro (the hook may not run in an ACP session, and permission requests are advisory), and OpenCode waits for task 10.48.

### 208. "Clear" in the intake step is a checklist, not understanding

The first intake slice asks fixed questions and has a pure function judge that each has an answer of reasonable length. A long, vague answer passes. The owner's commit, which shows the exact title and recommendation first, is the real check.

### 209. A server killed with SIGKILL leaves a reservation open

Ctrl-C and SIGTERM stop each chat and settle its budget before the process exits. SIGKILL cannot be caught, so a live chat's reservation stays open until the owner runs `umwayi budget settle-lost`, as for a command line run (item 36).

### 210. Dates use the system date

A token's expiry and the logbook date come from the system date (taken with the newest logbook date, so a clock set back does not revive an expired token or make an old one valid). A clock set far forward expires the token early, which is the safe direction. The rate windows use a monotonic clock.

### 211. The page can only reject an Ask me first of a chat; approvals are at the terminal

By the owner's answer of Nov 12 (W6-Q12), a request from the page can answer an Ask me first of a chat with `reject_once` and nothing else. A holder of the token can therefore stop an AI helper's tool call and cannot allow one, and a stolen token cannot approve. The approval is made at the terminal where `umwayi serve` runs (W6-Q28, answered Nov 12: at the console of `umwayi serve`, with the prompt `Allow once? [y/N]`; with no terminal attached the request is rejected); a process of the same user that can type into that terminal, or an AI helper that can read it, is the same limit as items 1 and 15. A holder of the token can also deny every Ask me first, which makes a chat unusable until a Yes rule exists (a nuisance, not a way in). Allowing from the page waits until the page's threat model has been tested by hand and the owner approves.

### 212. Login for a deployed interface is not built (W7)

By the owner's answer of Nov 12 (W6-Q22), W7 version 1 is login plus the public site with sample data, and does not control a local backend. A relay, or any way for a deployed page to reach a local backend, is decided after Dec 3 and nothing of it is built. Any of them would be a second door with its own limits, an outbound network import in the core, and a third party in the path of the owner's data. The spec only fixes what they may not do: open the local backend to the internet, or relax a check of W6.

## Goal orchestration (W9): `umwayi goal` (known from the spec, Nov 12; nothing is built)

### 213. The owner commands trust a terminal

`goal approve`, `answer` and `merged` refuse unless standard input and output are terminals, and the example rules of the three adapters deny an AI helper from running them. A process of the same user that opens a pseudo terminal, or an AI helper whose command the rules text match misses (item 12), can still run them. This is the same limit as items 1 and 15: nothing proves the person typing is the owner.

### 214. The tester is an AI helper, and a pass is a claim

The tester says pass, fail or unclear for each acceptance check, with a line of evidence. umwayi checks that every check has an answer and that the answer carries the nonce of the run, and cannot check that the tester looked. A tester on the same platform and model as the builder can share its blind spots, and a tester can be talked into printing a pass by text in the repo. The owner's review before the merge is the real check.

### 215. The files a task may touch are checked after the run

During a run the gate is `rules.yaml`, as for every run, and it knows nothing of the packet. The scope check compares the branch with its base afterwards. A builder that changes a file outside its packet is found and failed, but it did change it, on its own branch in its own worktree. Damage outside the checkout is for the rules to stop. A rules overlay per task is W9.16.

### 216. Error recognition is a list of line markers

On a `cli` run umwayi sees only the lines the AI helper prints. An error is a line that starts with one of nine markers, and two identical signatures in a row stop the run. A builder that varies its error text, or prints none, escapes that rule and is caught only by 30 minutes without a change of the work tree.

### 217. Progress is a changed work tree, and a tree can be changed for nothing

A builder that rewrites a file back and forth counts as making progress, until the agent's own `timeout_minutes`, the budget cap or the owner stops it. Output alone is not progress, so a silent builder that is working only by thinking, for more than 30 minutes, is stopped too.

### 218. Cost is attributed by a window of the ledger

The supervisor records the run ids in the budget ledger before a run and after it, and counts the runs of that agent that appeared in between. A run of the same agent that another process started in the same window (a scheduled job) is counted in the task. That over-counts, so the cap is smaller, never larger.

### 219. A deadline is enforced when a command next runs

There is no daemon. A deadline that passed while no `umwayi goal` command ran is already No (an answer after it is refused), but the denial is written to the logbook when the next command runs, with the deadline's own time. Between the two, the queue row is still open.

### 220. A merge is seen only on the local `main`

umwayi never fetches or pulls. A merge on the remote is not seen until the owner updates the local `main`. The `stale` check of a start has the same limit: it compares `main` with the remote-tracking ref `origin/main`, which is as old as the owner's last fetch. A squash or rebase merge leaves the branch tip off `main`, so it is not seen either, and the owner declares it with `goal merged G T --commit SHA` (checked only to be on `main`).

### 221. `git` is trusted

umwayi starts `git` by a fixed argument list with the hooks path, the file monitor, the global config and external diff turned off. A filter driver or other program named in the repository's own config can still run. Its three writes are `git worktree add` (with a new branch, or detached for the plan) and `git worktree remove`, without force. They change the repository's metadata (a branch and a worktree entry) and never the owner's working copy.

### 222. The shared docs are stale until rebuilt, and the status paragraph stays by hand

After a task merges, `docs/status-log.md` and `docs/KNOWN-LIMITS.md` do not change until `umwayi goal docs build` runs (the last step of a goal). In between, `docs check` and `status` say so. The hand-written head of the status log (the "Status" paragraphs) is not generated and is edited by the owner, so it can still conflict. Two rebuilds started at once conflict, and the second is redone.

### 223. A model word is checked for shape, not for being honored

umwayi checks `^[A-Za-z0-9._:/-]{1,64}$` and the five effort words, and passes them to the platform's own flag. Whether the platform accepts the model, and whether a level is supported by that model, is the platform's answer, and an unsupported value shows as a failed builder (adapters/NOTES-w9.md). The UU of an unknown model is the worst case of the governor (items 111 and 121).

### 224. The event log is not tamper evident

Each line has a CRC to find a torn or garbled line. A process of the same user can rewrite a log with a matching CRC. The logbook (chained once the owner starts the chain) is the record of every state; if the event log and the logbook disagree, the logbook wins.

### 225. One goal, one task, and the owner is the wait

One goal runs per root and one task at a time, and the next task waits for the owner's merge. A goal of five tasks needs five runs and five merges. This is the cost of "the owner merges". Working ahead needs the overlap rule of W9.12 (`--ahead N`); the worktree per task is already core.

### 226. OpenCode is not a builder yet

An OpenCode agent is refused by `agent run` today, and its chat is task 10.48. Until a non-interactive ACP run exists (W9.13), a goal uses Claude Code and Kiro. An effort for an OpenCode agent is refused until a flag is confirmed on a real install.

### 227. The plan's quality and the AI helpers' reading are not judged

The checks on a packet are character rules: lengths, one line, files that exist. They cannot tell a good split from a bad one, or a vague acceptance check from a sharp one; the owner reads the plan before approving it. Text in the repo that the guide, builder or tester reads can steer it (prompt injection). The nonce only stops a forged result line left in the repo; it does not stop a helper that is persuaded, and a Claude Code run shows its prompt, nonce included, in the process list to the same user (item 35).

### 228. A killed supervisor leaves a child

SIGKILL or a power loss while `goal run` works leaves the task `running` with no supervisor; the next command marks it `stopped` (`supervisor`). The child `agent run` is in its own session and ends by itself at its timeout, or by the kill switch, and until then it holds the run lock, so the next start gets `busy`. The task's worktree stays (item 230). Its reservation is settled by `umwayi budget settle-lost` if it was killed too (item 36).

### 229. Each worktree is a full checkout and uses disk

Each task's worktree holds every tracked file of its base, and the plan's does too until the plan is decided, so each live worktree costs the size of the tracked tree plus whatever the helper builds in it. A start is refused as `leftover` at eight worktrees in the root, and `status` lists the disk used by each leftover (counted only for listed worktrees, up to 10 000 files). umwayi does not check the free space of the disk, so a large repository or a build that fills a worktree can still fill it.

### 230. Leftover worktrees stay until removed

A failed, stopped, needs-owner or in-review task keeps its worktree, and a crash can leave one. umwayi removes a worktree only after the owner's merged (and an unused one it made itself), never with force, so a worktree that git refuses to remove stays. The next start for that task, and any start once eight exist, is refused as `leftover` until the owner removes the worktrees with `git worktree remove`. umwayi never deletes a branch, so the branches stay too.

### 231. Untracked and ignored files are not in a worktree

`node_modules`, build folders, caches, `.env`, local config and any file the owner did not commit are neither copied nor linked into a worktree. A helper that needs them has to make them, which costs time and disk and may need the network (a package install is the helper's own act under the rules). A gate check that needs an untracked file, for example a Kiro hook file that was never committed, fails and the task is `needs owner` with the reason `config`.

### 232. Worktrees share the repository's metadata

A linked worktree shares objects, refs and config with the root repository. A helper that can run git write commands in its worktree can change refs or config of the shared repository (a branch, a tag, a hook path; umwayi turns the hooks path off only for its own git calls). The gate (`rules.yaml`, which should say Ask me first for git writes) is what stops that. The scope check looks only at the files of the task branch, not at other refs.

## Local backend (W6), items from the build (233 to 236)

### 233. Requests run one at a time, on the main thread

A logbook write holds the termination signals off and can only run in the main thread (`logbook._held_off`), so the handler threads of `umwayi serve` do the reading and the gate and hand every request that may write to the main thread, which runs them one after another. A read waits behind a write, and a slow command (an agent check starts programs) delays the next request for as long as it runs. A write that has not started within 5 seconds is answered `busy`. Relaxing the rule in the logbook would change crash safety code and is not done here.

### 234. A locked-out caller with a token of the right shape is still compared

After 5 failed token checks in a minute, failures are answered 429 (`rate`) for the next minute. A token of the wrong shape is refused without a comparison, but one of the right shape is compared with the stored digest, because a valid token must never be slowed by someone else's failures (W6.R5.2, W6.R16.1). The comparison is a constant-time compare of two SHA-256 digests, and a guess still has 256 bits to find.

### 235. With a broken logbook the page can read only the status

A request is rules-checked and the check is logged before the route runs, so when the logbook cannot be written (a hand edit, a failed tamper check) every request but `GET /v1/status` and the page is answered `logbook` (exit-equivalent 2) and the server goes into the degraded state. The page cannot show the owner what is wrong with the logbook; `umwayi logbook verify` at the terminal says. `snapshot` and `logbook.verify` therefore cannot give `refused` (1) on a broken logbook, which the table of the design had.

### 236. The reader strips the whitespace around a header value

The server's own reader takes the bytes on the wire and cuts spaces and tabs from both ends of a header value, as HTTP says. The pure gate sees the cut value, so `Host: 127.0.0.1:PORT ` with a trailing space is accepted. Everything else the gate refuses is refused as it arrived: a fold, a bare line feed, a space before the colon, a duplicate.

## Layer 12: the phone layout (found while building W1)

### 237. The phone layout is checked in one emulated browser, not on a device

The overlap, sideways and touch size checks (`ui/test/phone.test.mjs`, `site/test/phone.test.mjs`) run in headless Chromium 158 with the phone sizes 375 by 667, 390 by 844, 412 by 915 and 360 by 640 and the same four on their side, with touch and a mobile viewport emulated and the pixel ratio at 1. No real phone, real touch, real GPU, Safari (iOS) or Firefox (Android) was used. Fonts are those of the machine, and they matter: on GitHub's runner one Chrome version (157) put the name of the selected feature a few pixels over the station panel at 640 by 360 where Chrome 156 and the headless shell used here (158) did not, so the page now moves that name out of the panel's way and a test forces the case, but another font could find another near miss. a phone with wider system fonts or a larger text size setting can wrap a button label onto more lines, which the layout allows (the bar is in the page and grows) but no test measured. A layout that fits in the emulation can still differ on a device with a notch, a rounded corner or a browser bar that changes the height while scrolling (the first screen uses `100svh`, the smallest height).

### 238. The phone tests need a Chromium and skip without one

`ui/tools/browser.mjs` finds Google Chrome, Chromium or a Playwright headless shell on PATH or in `~/.cache/ms-playwright`, or the file named by `UMWAYI_BROWSER`. With none, the four phone tests report as skipped and print the steps for the check by hand, so a machine without a browser sees a green run that did not look at the layout. `UMWAYI_REQUIRE_BROWSER=1` makes a missing browser a failure. The CI workflow was not changed (it is outside `ui/` and `site/`); the runner image normally has Chrome, and whether the tests ran there is read from the "skipped" count of the Node step. The tests add about 50 seconds to `ui/` and 60 to `site/` (the site is also built and served on 127.0.0.1).

### 239. On a phone the top bar scrolls away with the page, and the Standard first screen is shorter

Below 700 pixels wide, on a touch screen and in a window under 520 pixels high the top bar is part of the page instead of floating over it, so it can never cover the title. The cost is that the View switch, Owner checks and Calm mode are not on screen once the visitor has scrolled down; there is no sticky bar. On an upright phone the bar is two rows (116 pixels), so the picture is shorter than before (at 360 by 640 about 440 pixels instead of 470) and the strip below shows a heading instead of its first row. The camera still picks its narrow framing (picture taller than wide; the hero has a minimum height of 120 per cent of the width for that reason). Wide screens with a mouse keep the floating bar: the screenshots at 1440 by 900 and 1024 by 768 are the same bytes as on main.

### 240. The tick box is drawn by the page on touch screens

To give the owner checks a 44 pixel target without making the box big, `appearance: none` and a drawn 24 pixel box are used below 700 pixels and on touch screens (a ticked box is filled, with an inner ring). It was seen in one browser; a browser that ignores `appearance` on a checkbox shows its own box inside a 44 pixel area. The tick box itself is the target, with negative margins to keep the text column wide, so on a 360 pixel screen it overlaps the padding of its neighbours, which holds nothing to touch.

### 241. Two phone rules use `:has()`, and a short window gets the side card

While a station panel is open the "sample" tag is hidden with `:has()` (Chrome 105, Safari 15.4, Firefox 121 and later); in an older browser the tag stays visible behind the panel's glass. In a window under 520 pixels high, which includes every phone on its side, the station panel is a card at the right (at most 360 pixels, 48 per cent of the width) and the title and promise are narrowed to what is left, so on a 667 pixel wide screen the promise wraps to about five lines. The side card scrolls inside itself; nothing was done for a window that is both narrow and short beyond the same rules.

## OpenCode chat start (part 8), items from the build (242 and 243)

### 242. An error that mentions "auth" is shown as a sign-in request

In an OpenCode chat, an error answer to `initialize`, `session/new` or `session/prompt` whose code is -32000 or whose message contains the letters "auth" in any case ends the chat with "Run opencode auth login first, then try again." The same text test is used for the Kiro chat. An error that merely contains a word such as "author" or "authority" gets this line too, and the real cause is only in what OpenCode wrote to its own stderr. Nothing is sent after the error and the chat ends with exit 2, so the cost is a wrong hint, not a wrong action. Not seen on a real OpenCode: only the fake answers `auth_required` (10.47).

### 243. The model must be reported as exactly the agent's model

The chat start compares the `currentValue` of the `model` config option in the `session/new` answer with the agent's `model`, as text, with no case folding or trimming. 10.42 saw OpenCode 2.2.7 replace a model it could not find with one from its own catalogue and report that, which is what the check is for. If a later version reports the same model under another spelling (an alias, a variant suffix), the chat is refused with exit 2 before the first prompt: safe, but the owner has to write the model as OpenCode reports it. Only the fake and the one 10.42 observation stand behind the format `provider/model`; the owner's own run (10.51) is the first test against a real chat.

## CI path filters and shards (W20), items 244 to 246

### 244. What the path filter and the test map cannot see

The decider skips tests only from a map that a scanner builds by reading test code (`tests/test_ci_map.py` keeps it true). The scanner sees a path built from the repository root in the test code, an import of `adapters`, a walk of the whole repository, and the Node equivalents. It does not see a path that a child process reads from its working directory, or one built from data. If a test reads `docs/`, `ui/` or `site/` that way, a change there can skip that test on the pull request. Every route outside `ui/`, `site/`, `docs/`, `README.md`, `PROJECT.md` and `.kiro/` runs the whole Python suite, which limits the gap to those six areas. Inside `umwayi/`, `tests/` and `adapters/` the filter selects nothing: a change there runs the whole Python suite, so `tools/affected_tests.py` also gives you the whole suite for such a change. `affected_tests.py` also depends on an up to date `origin/main`.

### 245. Skipped jobs run on main, not on the pull request

When the plan leaves out a Python version (3.11 and 3.12 for a change that only touches `ui/`, `site/`, `docs/`, `README.md`, `PROJECT.md` or `.kiro/`), a Python test file, or the Node job, that part does not run on the pull request. The `result` check passes and its summary lists the part as NOT RUN. The part runs when the pull request is merged, because a push to main always runs everything on 3.10 to 3.13. A break that only the skipped part would find is therefore found after the merge, not before. Merging is still guarded by `result`, but `result` can only vouch for what was planned.

### 246. The required check names changed

Before W20 the required checks were `tests / test (3.10) (pull_request)` to `tests / test (3.13) (pull_request)`. They no longer exist. The new checks are `tests / plan (pull_request)`, `tests / test (V, shard K/3) (pull_request)` for each planned version V and shard K, `tests / node (pull_request)` (only when planned) and `tests / result (pull_request)`, and the same names with `(push)` on main. The owner changes the branch rule by hand to require `tests / result (pull_request)` only. Until then a branch rule that names the old checks waits for checks that never come. Requiring the shard checks by name would not work either, because a skipped part creates no check. A test file added without an entry in `tools/ci_shards.json` fails `result`.


## Shared docs builder (W9.9), found while building

### 247. Two branches that each run the build give the same number twice

`umwayi goal docs build` writes the number of a new limit into its part file and never changes it later. If two branches each run the build with a new limits part, both parts get the same next number, and the second merge puts two parts with one number in `main`. The build then refuses (exit 2, "a number that another part also has") and writes nothing, so no entry is lost or renumbered silently; a part that was deleted after it had a number is refused the same way, as a gap.

- What protects you today: the design lets one place run the build, the last step of a goal on its own branch (W9-Q10), and a task never runs it. Nothing stops the owner or a task from running it early.
- What it does not protect against: the collision itself. The fix is by hand: delete the `number:` line of the part that merged last and run the build again.
- A later fix: give numbers only on `main` (a step after the merge), or keep a reservation file per number.

## OpenCode chat end to end (part 8, 10.49)

### 248. A request with no `name` is capped after the check, so its entry can say Yes

In an OpenCode chat, a permission request with no `name` (OpenCode had no tool for it) never gets Yes: when the rules answer Yes, umwayi asks the owner instead, as for Ask me first. The cap is applied after the check, so the `umwayi check` entry of that request still names the Yes rule, and the logbook does not say that the owner was asked. A No stays No. A request whose `name` is present is not capped, even when it is not a plain word (a name with `:` or over 40 characters): the rules then see only its kind. An MCP name such as `mcp__x__y` is a plain word and is sent to the rules as `tool`. Only the fake sends a request with no `name`; a real OpenCode was seen to do so only in the source (10.42).

## Page client (W6.9), found while building

### 249. A bad answer or a failed request stops the page until it is reloaded

The page client fails closed. If an answer from `umwayi serve` has the wrong shape or status, or a request fails, the client forgets the token, the panel shows one message and disables its controls, and nothing more is sent until the page is loaded again and the token is pasted again. A server that is stopped and started again therefore needs a reload.

- What protects you today: nothing can be sent after a doubtful answer, and the token is not kept.
- What it does not do: tell a short network fault from tampering, and it has no timeout (no timer in the page, W6.R14.6), so a server that never answers leaves the panel waiting. Stop everything is never held back by a request on its way.
- Not tried in a browser here: the panel was tested against a fake document and the client against the real server from Node. A password manager may still offer to save the token field. The by-hand pass is W6.10.

## OpenCode planted faults and mutation checks (part 8, 10.50)

### 250. The fault runs are manual, and four guards have a twin that hides them

`tests/agents/opencode_mutants.py` plants 153 faults in a copy of the source and reports which tests notice. It is a helper that a person runs (`python -m tests.agents.opencode_mutants`, about 10 minutes with 6 jobs on 8 cores), not part of the test suite or of GitHub CI. The suite checks only that the fault table is still true (`tests/agents/test_opencode_mutants.py`: every edit still matches the source, every mutated file compiles, every named test exists). A later change that loosens the gate in a way the table does not list is not found by it.

- **Four survivors.** Each is a guard whose twin refuses the same case, so removing one alone changes nothing a test can see. B3b: the "is a link" refusal for `index.js` or `hook.py` (the "not a regular file" check refuses a link too, only the wording differs). B3e: `lstat` becoming `stat` in the same check (the real-path check refuses a link whose target has another path). B5l and B5m: the size limit on a global config file is checked from the file's size before the read and again on the text after it (the second only matters if the file grows between the two). Removing both guards of each pair is caught (faults B3x and B5lm), so each pair is tested as a whole. They stay as defence in depth.
- **Not reachable as root.** A plugin folder that can be entered but not listed cannot be made by a test running as root, so that check (fault B3h) is tested by making the listing itself fail, not with a real folder mode.
- **One catch depends on timing.** The test for the last look at the agent's descendants before a clean exit (fault S2) needs the whole chat to end within the one-second watcher interval. On a machine that is much slower the fault could survive that test; the code itself passes either way.
- **Only the fake.** All of this runs against the fake `opencode` and the plugin under `node`. What the real OpenCode does is the owner's check, task 10.51.

## OpenCode docs and the real check (part 8, 10.51)

### 251. OpenCode runs with the owner's own HOME, and its stderr reaches the terminal

umwayi gives an OpenCode chat the allow-listed environment (`opencode_env()`), and `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` are on that list, so they are passed through exactly as they are in the shell that started umwayi. umwayi does not make a home folder of its own for OpenCode. The design said it would discard OpenCode's stderr; the code does not: `opencode acp` has its stdin and stdout as the ACP pipes and its stderr is umwayi's, so OpenCode's own error text appears on the owner's terminal.

- **OpenCode writes into the owner's real folders.** It keeps its database, logs and repositories under `~/.local/share/opencode/`, an empty config folder at `~/.config/opencode/`, and the downloaded `ripgrep` at `~/.cache/opencode/bin/rg` (seen in 10.42, in a throwaway home; see 191). In a real chat these are the owner's real folders. Nothing in the gate depends on them being empty, except gate check 5, which refuses a global config folder that holds a plugin or agent entry or a listed key (181).
- **A saved account in that database counts.** An account the owner connected earlier (182) is in the same database. umwayi neither reads it nor hides it.
- **What would change it.** A private `HOME` for OpenCode, with its cache and data inside it, would also give 191 a fix (an `rg` already in place). That is a change to `umwayi/agents.py` and a decision for the owner; nothing here does it.
- **stderr.** What OpenCode prints to stderr is not logged and not filtered, and it is not checked for control characters the way agent text on stdout is. Nothing of it is sent anywhere by umwayi.
- **To check.** What OpenCode wrote in the folders above on the owner's first real run is a line in the owner's check (`adapters/NOTES-layer10.md`).

## Whole-system scenarios and the mutation pass (W6.10), found while building

### 252. The checks of the backend are not a browser test, and the mutation pass is run by hand

The scenarios of `tests/serve/test_scenarios.py` start a real `umwayi serve` and speak the page client's requests, but the client is Python's `http.client` or the real `ui/src/api/client.js` run by Node, not a browser. Node's `fetch` sends no `Origin` and no fetch metadata, so the test driver adds the ones a browser adds to a same-origin request. What a real browser does with the `Host`, `Origin` and `Sec-Fetch-*` headers, the Content-Security-Policy, a password manager or a second page on another port is therefore still read from documentation (item 205), and the by-hand pass (`docs/serve.md`, "The by-hand browser pass") is the owner's and has not been run.

- What protects you today: 96 planted faults in `servegate.py`, `serve.py`, `servetoken.py` and `client.js` (`tests/serve/faults.py`), each applied to a throwaway copy of the tree and tried against only the tests named for it; 93 were caught, and the 3 that were not are shown equivalent in the catalogue. `test_mutation.py` runs the tool on a tree of its own and four real faults in CI.
- What it does not do: the full pass takes about 25 minutes and is not in CI, so a later change to the four files can weaken a test without anything failing until someone runs `python -m tests.serve.mutation`. A planted fault is a text edit that someone thought of; it is not a proof that no other fault exists, and an edit that no longer matches the source is reported as not found and fails `test_mutation.py`, not silently skipped. The faults of W6.R16.10 about a chat (`a chat message logged with its text`, and the kill switch for chats) wait for the chat routes (W4); the kill switch fault is tried on the write routes meanwhile.
- Platform: the loopback scenario reads `/proc/net/tcp` and is skipped where that file is missing; the scenarios that make a logbook that cannot be written use a folder in its place, which works as any user; the Node scenarios are skipped without Node.

## Board status (W16), found while building

### 253. The board status shows the time of the last commit, not of the last push, and it may run out of unauthenticated requests

`tools/board_status.py` reads only the public GitHub API with no token. That keeps it simple and safe, and it has two limits.

- The time is the committer date of the head commit, because the public pull request data has no push time. A commit made long ago and pushed just now (a branch built locally over a long time, for example) can show as a stall when it is not, and a push of nothing new cannot be seen. The stall line is a prompt to look, not proof.
- Without a token GitHub allows 60 requests an hour per address. One run uses 1 request plus 4 or 5 for each open pull request, so ten open pull requests cost about 50 and a few runs in an hour hit the limit. The script then prints the reset time and exits 2; it never shows an old or guessed state.
- Only GitHub check suites count for CI. An old style commit status from another service is not read, and a head commit with no check suite yet shows `ci none`, which is not green.

- What protects you today: every failure prints one line and exits 2, so the guide cannot mistake a failure for a clean board.
- What it does not protect against: a long wait between a commit and its push, a busy board in one hour, a service that reports only as a commit status.
- A later fix: an optional token read from the environment (a decision for the owner, because the script reads no secret today), and the push time from the repository events.

## Concerns record (W19)

### 254. The concerns checker proves the form of the record, not that it is true

`umwayi concerns check` shows that a concerns record is complete and well formed. It cannot tell whether a row is true.

- What protects you today: the record must have exactly one row for each of the 111 numbers, each with one of three answers, a reason that is not empty, a real date, and, for Applies, a regular file that exists inside the repo (no `..`, no absolute path, no link that leads out). Any failure exits 2.
- What it does not protect against: a reason that is wrong or careless, an Applies row that points at a file that has nothing to do with the concept, a file that exists but is empty, a concept marked Not applicable that does apply, and a record that was true once and is now out of date (the date is checked for its form only, not its age). The reason is checked for being present, not for being one sentence.
- A later fix: none planned. A judgment about whether an answer is true stays with the owner. The record is checked only when the owner runs the command; nothing runs it on a schedule.

## Model routing and task log (W19)

### 255. The routing checker proves the form of the table and the log, not that they are true or current

`umwayi routing check` shows that a model routing table or a task log is well formed. It cannot tell whether a row is true.

- What protects you today: every routing row has a known platform, task types from a fixed list, a source that is an https page of the vendor of that platform, real dates, and a `review_by` date that is after the source date, at most 45 days after it and not yet past. Every log row has an allowed outcome and review result, a credits value that is `unknown` or a plain number, and a real date that is not in the future. Any failure exits 2.
- What it does not protect against: a strength that is wrong or out of date (the vendor page is not fetched), a source address that is a real page of the vendor but the wrong one, a model name that does not exist, a task type that does not fit the model, a model or credits value in the log that is wrong, and a review result that does not match what really happened. The model cell of the log is not checked against the table. The starter log says `unknown` for the model and the credits of PRs 66 to 79, because history does not hold them.
- The check can start failing without any change to the file: a row whose `review_by` has passed fails until its page is read again. That is intended.
- The 30 day wait and the 45 day limit are the builder's proposal, not an owner decision. Other OpenCode models are not listed, because the OpenCode page states no strength for them.
- A later fix: none planned. Choosing a model, and judging whether a row is true, stay with the owner. The command runs only when the owner runs it.

## Guidance (W19), found while building

### 256. The guidance check proves a field is there, not that it is true, and only some rules are loaded yet

`umwayi goal guard` runs the enforce rules of `guidance.yaml` against a task record. It is a shape check and a first step, with these limits.

- A field passes if it is a string with something other than white space in it (or, for acceptance checks, a list of such strings). "x" passes. A zero width character passes. The code never judges whether the goal is one good sentence, whether the consequences are real or whether an undo step would work.
- `open_prs` is filled by whoever calls the check. umwayi makes no network call here (steering rule 5), so it does not look at GitHub: a caller that sends an empty list for a task with two open pull requests passes.
- `source_hash` covers the one numbered line of the source file, not the lines that continue it. A change to the continuation of a rule is not seen. A source that is moved to another number or section stops the loader, which is the intended Ask me first.
- A hub entry is only as good as the last `verify`. The loader reads no hub file, so a normal load, `goal guard` and `list` without `--hub` trust the stored hub hash and say nothing about the real file; `list` shows such an entry as unverified. The hash is of the whole hub file, so it says that the file changed, not which rule, and a changed hub file makes every entry of that file mismatch together. The hashes were taken from a local hub clone at hub commit 658a799 that may be behind the real hub, so the first `verify` may report a mismatch, which is correct. Nothing checks that the rule number exists in the hub file or says what the entry's text says; the text is our own words.
- `guidance.yaml` holds nine entries: four enforce, four advise and one owner. The brief asked for six advise and three owner examples, the owner named four and one, and no rule was invented. The acceptance checks entry is tier 3 as the owner assigned it, while the tier list puts agent-practices in tier 5.
- `resolve` ranks two entries by tier and kind only. It does not read `overrides`, and it cannot decide two enforce rules of one tier: that is always Ask me first. The tier of an entry is the owner's word in the file; the code checks that it is a number from 1 to 6, not that the tier suits the rule.
- The goal flow of W9.8 does not exist yet. Nothing calls `guard` by itself; today it is a command the owner or a script runs, and the later `goal start` and `goal run` are to call the same function.

- What protects you today: a missing, malformed or changed guidance file stops everything (exit 64 or 3), and a task record that cannot be read is Ask me first.
- What it does not protect against: a task record whose fields are filled with meaningless text, and a caller that hides an open pull request.
- A later fix: add the two missing enforce entries and the advise and owner examples once their source file is in the repo, and call `guard` from `goal start` and `goal run` when W9.8 is built.

## History backfill (W19), found while building

### 257. The backfill records have no model field, the task kind is a weak guess, and one run reads only about 19 pull requests an hour

`tools/backfill_history.py` writes derived records from public GitHub data with no token. That keeps it safe and it has limits.

- The output has no model field because GitHub does not record which model built a pull request. A routing table that needs it must get it from somewhere else, and the records must not be read as saying anything about models.
- The task kind is guessed only from the title prefix (W9, W16, L13, UI, CI, docs). A title with no such prefix, or a wrong prefix, gives `unknown` or a wrong kind. It is a weak guess, not evidence of what the work was.
- Without a token GitHub allows 60 requests an hour per address. Each pull request costs 3 requests plus the list pages, so one run reads about 19 pull requests an hour. The run then stops cleanly: it writes what it finished with `complete` false in the header, prints one line and exits 2. `--after NUMBER` carries on in the next hour.
- Check counts use the check runs of the head commit only, and a check that was re run is counted once, by its latest result. A page of 100 reviews or check runs may hide more, and then the value is `unknown`. Checks of an old commit that GitHub has dropped count as zero.
- Label names are kept only if they look like plain tags; any other becomes `unknown`.

- What protects you today: the allow list of fields, the tests that plant private text in a title, body, comment and file name and search the whole output, and exit 2 on any failure.
- What it does not protect against: private text placed in a label name that looks like a plain tag, a wrong task kind, a pull request changed on GitHub between two runs.
- A later fix: an optional token read from the environment (a decision for the owner), and a cache so a run can carry on without repeating requests.

## Stall checks (W19 part 5), found while building

### 258. The stall checker judges a file nobody writes yet, and a finding is only as good as the events in it

`umwayi stalls check` reads a JSON list of builder events and reports four kinds of finding. It trusts the file.

- Nothing produces the events file yet. The W9 event log is not built, so today the owner or a script writes the file by hand. The shape in `docs/stalls.md` is the builder's choice, approved by the owner, and may change when the log is built.
- It cannot tell whether the events are true. A file that leaves out an event can hide a stall, a loop or an unanswered approval. A file with an invented push can reset the stall timer.
- The error signature is given to it. It does not compute one, so it cannot tell whether two different errors were given different signatures by mistake.
- A stall is measured against the system clock when the command runs. A wrong clock gives wrong ages. A time in the file that is in the future gives exit 2, not an age.
- A builder is checked for a stall and a loop only while its last state, started or stopped event says it runs. A builder with no such event counts as running.
- The limits (30 minutes, two errors, 1,000,000 bytes, 20,000 events) are starting values from the W9 spec and the builder, not measured ones.
- It reports and exits. It does not stop a builder, answer an approval or tell anyone. Any finding gives exit 3, so a script that treats 3 as Ask me first sends it to the owner.
- A later fix: none planned until the W9 supervisor and event log exist.

## Command map (W2), found while building

### 259. The command map shows names and the first sentence of each help line, and it is only as true as the last run of the script

`ui/dist/cli-map.html` shows the umwayi command line as a mind map. It is a reading aid, with these limits.

- It lists groups, commands and the first sentence of each help line, and nothing else. It shows no flags, no arguments, no exit codes beyond what a first sentence says, and no example. A command that `umwayi --help` hides is not listed either.
- The first sentence is cut at the first semicolon or full stop outside brackets. Some cut lines still carry words the owner may find hard, such as "layer 13", "W19.1", "SHA-256", "ACP" and "transport cli". The wording is the help text in `umwayi/cli.py`, which this task did not change.
- A command with no help line is listed as "no help line yet". No command is in that state today, so that branch is covered by a test with a made up command and was never seen on the real page.
- The data file `ui/src/data/cli-map.json` is written by `python ui/tools/cli_map.py`. If a command is added and nobody runs the script, the page is old, but `tests/test_cli_map.py` fails until the file and the page are rebuilt. The test is only as good as the run: if the test is not run, nothing warns.
- The page is built by `node build.mjs`, which only the owner runs. The built page is checked against `ui/dist/build.json` without npm, so a page edited by hand is found.
- The phone test `ui/test/climap-phone.test.mjs` needs a Chromium and skips without one. In the build sandbox the repo's own driver could not start the browser, so the repo's phone audit function was run in a Playwright browser at 375 by 667, 360 by 640, 390 by 844, 412 by 915 and the two small ones on their side, with every group closed and then open, and it found nothing. The skipped test itself was not run, and nobody has looked at the page on a real phone.
- The groups open and close with the browser's own details element. In a browser that does not support it, the groups show as plain text and every command stays readable.

## Concerns record (W19 part 6), found while building

### 260. The draft concerns record is the builder's reading of the repo, and the checker passes it whether or not it is true

`docs/concerns-record.md` is a first draft of the 111 rows, written by the builder for the owner to review. It passes `umwayi concerns check`, which checks form only (see item 254).

- Every answer and reason is the builder's judgement from a search of the repo. Nobody has run the code paths named in the Applies rows to confirm them, and an Applies row names one file, not every file that matters.
- A Not applicable answer says why the concept does not fit a stdlib Python command line tool with a small web page. If the tool grows (a database, a deployed service, more than one user), those rows must be looked at again.
- Some rows are Deferred because the builder could not tell, not because the owner decided. The owner has not read any of them.
- The record is not run by any job or schedule, so it can go out of date unnoticed.
- A later fix: the owner reviews the draft, and the record is re-read whenever a layer is added.

## Guidance (W19)

### 261. The steering entries are advice, the coverage test checks that a rule has an entry and not that the entry is right

W19 part 3a gave every numbered rule of the builder workflow and steering rules 1 to 13 a guidance entry. Only builder rule 1 is enforced. The other 22 are advise entries.

- What protects you today: each entry is tied to its rule by a hash of the rule line, so an edited, moved or removed rule stops the loader (Ask me first, exit 3). A test lists the numbered rules of both files and fails when one has no entry and is not on a reasoned exclusion list, so a new rule cannot be added unseen.
- What it does not protect against: an entry whose one sentence says something different from its rule (the wording is ours and nobody checks it by machine), an advise line that an AI helper ignores, a rule added in a form the test does not read (a numbered line outside the builder file, the section "Safety rules" and the indented rules of the Layer 13 section of the product file), and a hash that is updated by hand without reading the change. Tiers are as the owner decided: builder 4, safety 1, rules 5 and 10 tier 2. Nothing checks that a tier is the right one.
- The loader now accepts spaces before a rule number. A section that holds both a flush and an indented rule of one number is refused as ambiguous.
- Fields `worktree` and `model` of the task record are written down but no check reads them.
- A later fix: new enforce checks (only the owner decides them), and the call from `goal start` and `goal run` (W9.8).

## Frontier practices tracker (W10), found while building

### 262. The frontier practices table is the builder's reading, and the test checks form and evidence existence, not truth

`docs/frontier-practices.md` marks each of the ten practices Covered, Partly covered, Not covered or Not applicable. The builder wrote every state from a search of the repo, and the owner has not read it.

- `tests/test_frontier_practices.py` checks that the table has ten rows, none missing or twice, that each state is one of the four, that each evidence file exists and that each guidance id is in `guidance.yaml`. A wrong state passes. A file that exists is not proof that the practice is met.
- The ten titles are taken from the ten pages linked from the kiro.dev page, in its order, on 2026-11-13. The page can change and nothing re-reads it.
- The Covered rows (4 and 8) rest on files the builder read, not on a run of the code paths. The gap sentences are the builder's judgement.
- No job or schedule runs the test beyond the normal test run, so the table can go out of date unnoticed.
- A later fix: the owner reviews the table, and it is re-read when a layer is added or the W9 goal flow is built.

## Goal orchestration (W9), found while building W9.6

### 263. A cap on one run is a stop that comes late and a count; for Kiro it is only a number in the ledger

`agent run --cap-uu N` reserves N UU and, for Claude Code, stops the run when its own report passes N. That is as strong as the report, and for Kiro there is none.

- The watch reads the report once a second, so a run can spend more than N before it is stopped. The settle counts what was measured, which is above N, and the run ends with exit 3. The caps the supervisor hands out can add up to more than the goal budget by that overshoot.
- A Claude Code run that sends no report settles at `unknown_worst_case`, which can be above a small N. The ledger counts more than the cap (the safe side), and a goal budget can be used up by runs that did nothing.
- Kiro sends umwayi no cost (KNOWN-LIMITS 117), so nothing can stop a Kiro run at N. The only protection is the refusal at the start: a declared or worst-case reading above N is exit 3 with nothing reserved. A run that is let in can still spend more than `run_micros` says, and nothing notices.
- That refusal is `Ask me first` with one entry and no queue item, so the owner has no row to answer: the owner raises the cap, changes `units.yaml`, or does not run it. Whether it should add a queue item, as the `budget_check` ask does, is open for W9.7.
- `--model` and `--effort` are passed as written. umwayi checks their shape only; a model or level the platform refuses ends the run with the platform's own non-zero exit, after the reservation was made and settled (KNOWN-LIMITS 223).

## Goal orchestration (W9), found while building W9.1 to W9.5

### 264. Four readings in the pure core that are choices, not facts

The pure core of W9 (`goalpacket`, `goallog`, `goalwatch`, `goalstate`, `goalbudget`) makes four choices where the spec left room. 1. `goalwatch.signature` masks a hex word as `H` only when it holds both a letter and a digit, and does it before digits become `#` (W9.R10.4 lists digits first, which would spoil a hash). 2. `goalpacket.parse_result_line` refuses two different tagged lines (`doubled`), so a forged line cannot win by being first or last. 3. `goalpacket.roles_ok` requires the tester and the guide each to differ from the builder, as W9.R2.2 is written, and does not require the guide to differ from the tester. 4. `goalstate.start_goal` writes `goal.json` first and the `started` entry second.

- What protects you today: the same error with another number, hash or path still gives one signature, so a loop is seen; a forged result line never counts as the answer; the builder is never the tester or the guide; a goal folder with no entry is never used as a goal and its id is never reused.
- What it does not protect against: a hash of only letters or only digits is not masked, so two such errors that differ only there are two errors and make no loop; a tester that quotes the example line of its prompt makes its answer `doubled`, which costs the owner a look (the nonce still does not stop a tester that is talked into a good line, KNOWN-LIMITS 214 and 227); a guide and a tester that are one agent check each other's view of one result; a crash between the two writes of `start_goal` leaves a goal folder that the owner deletes by hand.

## Progress page (W8 slice), found while building

### 265. The progress page counts boxes and copies the first sentence of rows, and it is only as new as the last build

`ui/dist/progress.html` (built, not committed) shows work done and open per group, the latest ten status log rows, the highest known limit number and the date it was built. It is a reading aid, with these limits.

- A task is a line that starts with a checkbox in `.kiro/specs/umwayi-os/tasks.md`, counted under the nearest heading that starts with two hash marks. A task written in another form, such as a table row or plain text, is not counted. The Status table at the top of that file has no checkboxes, so it has no group on the page. Sub-headings with three hash marks count inside their group.
- The group name is the heading cut at its first bracket, so the words in brackets (dates, PR numbers) are not on the page.
- The latest ten rows are the first ten rows of the pull request table in `docs/status-log.md`, in file order. The file is newest first, but one row has an older date above a newer one, so file order and date order can differ. The page does not sort.
- Each row shows only its first sentence (cut at 240 characters), not the tests column.
- The highest limit number is the largest number in a heading of `docs/KNOWN-LIMITS.md`. A gap in the numbers is not shown.
- Since W22 the page is built by `node build.mjs` and is not committed: `ui/dist/progress.html` is in `.gitignore`, and `ui/dist/build.json` holds no hash of the page or of what it shows. A pull request that adds a status row, ticks a box or adds a limit therefore changes no committed ui file and cannot fail CI as stale. The page exists only after a build (`npm ci --ignore-scripts` then `node build.mjs` in `ui/`); a checkout that has not been built has no page. Nothing in this repository builds or publishes it at deploy time yet: there is no deploy workflow, so whoever deploys must run the build step.
- The two readers (one in `ui/src/data/progress.js`, one in `tests/test_progress_page.py`) are separate code that has to agree. `tests/test_progress_page.py` runs the JavaScript one with node (no npm) on the real sources and compares the string with its own; when node is missing that test is skipped and says so. A matching string shows the two readers agree, not that the page text is right. The node test `ui/test/progress.test.mjs` runs the build and checks the page it wrote.
- The date is the day of the build and is not checked against anything. Because the page is not committed, a rebuild of unchanged sources changes no committed file.
- The page was not looked at in a real phone or browser, and no phone audit was run on it.

## Goal orchestration (W9), found while building W9.6b

### 266. A worktree is proven by its place, name and repo, git is given 20 seconds, and an undone start leaves a branch

`agent run --workdir` and `agent check --workdir` take only a path that `umwayi/goalgit.py` would make, and the module makes, checks and removes the worktrees of a goal. These are the limits of that proof and of the lifecycle.

- "Made by umwayi" is proven by place, not by a record. The path is the exact `<root>-worktrees/g-0007-t-02`, a real folder, in a root of mode 0700, whose toplevel is itself and whose common dir is the root repo's. A worktree that the owner made by hand with `git worktree add` under that exact name passes too. The check also looks at the folder at one moment: a folder swapped between the check and the start is not seen.
- The folder is only the working folder. A helper's tools can still read and write anywhere its rules allow, and the `.git` metadata is shared with the root repo (KNOWN-LIMITS 232). `--workdir` does not confine a helper to its worktree.
- Every git command has 20 seconds and 1 MB. A `worktree add` of a very large repo can run past that. The command is then stopped, the start is `config`, and a half-made folder, registration or branch may be left. The next start of that task finds it as a leftover and stops; the owner removes it by hand. Whether the three writes should get a longer limit is open for W9.7.
- When a new worktree does not check out right, umwayi removes the worktree without force but never deletes a branch. The task's branch at BASE stays, and the next start of that task is a `leftover` until the owner deletes the branch with git.
- A task file of any goal that cannot be read stops every start (`leftover`, kind `task-file`), because umwayi cannot show that the path and branch are free. A folder or file that someone put in the worktree root, and a worktree that git lists there, count toward the cap of eight; so does a registration whose folder was deleted, until `git worktree prune` is run by the owner (umwayi never runs prune).
- The worktree root must be exactly mode 0700 and owned by the user who runs umwayi. One made with a looser or narrower mode is refused as `config`; umwayi never changes the mode of an existing folder. A path must be spelled with the real path of the root: the same folder reached through a link is refused.
- This task builds the git list, the path and cleanup functions and the two options. The entries, events, queue rows and exit 3 that a refusal becomes, the child process, and the list of left over worktrees with their disk use in `status` and `report` belong to W9.7 and W9.8 and are not built yet. A start that is refused here is an error (`Refused`) that the supervisor must turn into `needs owner`.
- Tested with the system `git` of a Linux machine only. Windows paths, a case-insensitive file system, a root on a network drive and a git older than 2.17 were not tried.

## Merging main (W21), found while building

### 267. merge_main repairs generated files only, and some of its guarantees are narrower than they sound

`python -m tools.merge_main` clears a conflict only in a file of `tools/generated_files.json`. These are its limits.

- Any other conflict is exit 3 and the merge is aborted. This includes prose in `docs/testing.md` outside the generated table block, and a conflict in `tools/generated_files.json` itself.
- Taking main's version of a generated file drops that branch's own version of it. This is right only because nobody edits those files by hand; a hand edit of `docs/status-log.md` is lost.
- `ci_shards assign-missing` puts a new file on the lightest shard and counts it as the average. It never rebalances, so repeated merges can leave the shards less even than `balance`. `tests/test_ci_shards.py` pins the file as a fixed point of `balance`, so after a merge that assigned a file, `balance` must be run again for that test to pass. This was not changed because it would change what an existing test means.
- `ci_map update` keeps an entry that is still true, even one that lists more than the scan found, and rewrites one that is false. It reads only what the scanner sees (see the W20 limits).
- A verify that passes shows a file is current, not that its content is right. `ui/dist/build.json` is checked only by the hashes in it (`tests/test_ui_package.py`). The progress page is built and not committed since W22, so `merge_main` does not list it.
- A listed regenerate may write other files only if the entry names them under `writes`; the check finds a stray file after the commands and verify, not while they run.
- The ui files need node and npm. `npm ci` reads the npm registry or its cache, so the rule of no network except `git fetch` holds for `merge_main` itself and not for that command. If node or npm is missing the run is exit 3, never skipped, and a branch that needs the ui files cannot be repaired on such a machine.
- `merge_main` makes a merge commit even when the branch only had to catch up (no fast forward), so the branch history shows it.
- Commits need a git user name and email; without them the commit fails, the tree is put back to the last commit and the run is exit 2.
- It was tested with git 2.50 on Linux against a bare folder as origin. Other git versions, Windows paths and a real GitHub origin were not tried.
- The two parallel limits parts of one merge are numbered by the builder in the order of its own sort (date, then part name), not in the order the pull requests landed.

## Progress page at build time (W22), found while building

### 268. The progress page is built and not committed, and nothing here publishes it yet

Since W22 `ui/dist/progress.html` is not in git. These are the limits of that.

- This repository has no deploy workflow, so no job builds or publishes the page. The build step is `node build.mjs` in `ui/` (after `npm ci --ignore-scripts`). Until a deploy step runs it, there is no page to look at except one a person built by hand.
- A checkout that has not been built has no `ui/dist/progress.html`. `tests/test_progress_page.py` skips its check of the built page then, and says so; the page rules are still checked on a sample page made from `ui/src/progress.html`, and the node job checks the page its own build wrote.
- Nothing can now tell that a published copy of the page is old. The hashes that did this were removed from `ui/dist/build.json` on purpose, because they were what failed CI on every pull request that added a status row. A deploy that builds on every run has no old copy; a deploy that reuses one does.
- The page still shows only the first ten rows, the group counts and the highest limit number, and its date is the day of the build. Limit 265 lists the rest.
- `ui/test/progress.test.mjs` runs `node build.mjs`, which rewrites `ui/dist/index.html`, `cli-map.html` and `build.json` with the same bytes when nothing changed. A node test run therefore touches those files' timestamps, and a ui source change that was not built shows as a changed file after the test run.
- The test that a pull request adding a status row does not fail CI works on the committed files at HEAD in a temporary copy, with the Python tests of `ui/` only. It does not run the node job or the whole CI.

## Goal orchestration (W9), found while building W9.7

### 269. The supervisor took the reading that fails closed where the spec was open, and some of it waits for the commands

`umwayi/goalrun.py` is built and no command calls it yet. These are the choices it made and what it leaves to W9.8.

- A task stopped by the kill switch gives exit 2, not 3. W9.R3.2 says a stopped task is 2, the switch is 3, and a command with both gives 2. A `run` that finds the switch on before it starts anything gives 3.
- A goal marked stopped by the kill switch or by its budget stays stopped. `goalstate` has no entry that lifts a goal's stop, so "after kill off the owner runs goal run again" holds for the goals the switch did not mark, not for the ones it did. W9.R16.2 reads as if it could be lifted.
- The planning run's spend is counted at the owner's plan budget, because nothing records what it really spent: the goal file has no field for it and the `planned` entry has no UU. It can count more than was spent (the safe side). A task's spend is written to its task file only when its state changes, so a crash between two runs of one task keeps the ledger right and the file behind.
- The plan line, the verdict line and the guide's check line have a bound of their own (32 KB, 8 KB and 4 KB) when the child's output is read. The stream bound of 4096 bytes in W9.R12.5 would cut a plan, and W9.R5.2 allows 32 KB on one line. At most four different tagged lines are kept for a run, so a flood of forged lines cannot grow memory.
- The supervisor tells a timeout or a stop at the cap from another failure by the fixed sentences of `agent run` in the child's output. A helper can print the same words. That only changes the reason word of a task that already failed (`timeout` or `budget` in place of `builder`).
- `goal_start` joins `NEVER_AUTONOMY` in W9.8. Until then the supervisor treats a decision that graded autonomy produced as Ask me first, and no command calls it.
- The queue row of a task that needs the owner for the reason `ask` is the text of `goalstate`, which does not say that a Yes rule for `goal_start` is what allows the start (W9.R7.3 asks for it). A cap refusal by `agent run` (exit 3, the open point of KNOWN-LIMITS 263) now gets that row from the supervisor.
- The entry of a stall or a loop names only the reason word. The seconds without progress, the signature and the count of errors that W9.R10.5 puts in it have no place in the fixed entry shapes; the event log holds the signature.
- A task that the owner answers `yes` after its builder ran goes back to `queued` with its worktree and branch still there, so the next start is `leftover` until the owner removes them with `git worktree remove`. W9.R9.6 and W9.R8.12 together say this and neither says what the owner should expect.
- A planning run that is refused before it has a plan (a rule, the lock, `stale`, a config problem) leaves the goal in `plan` with no packets and one queue row, and there is no way to run it again: the owner starts a new goal.
- The guard that names the modules allowed to start a program (`tests/test_automation.py`, the subprocess list) was widened by the owner's decision of Nov 13 2026 (option A) to add `umwayi/goalrun.py`, for its one child `umwayi agent run`. The list is now `agents.py`, `goalgit.py`, `goalrun.py` and `report.py`. What keeps that start narrow is `tests/goal/test_goalrun.py`: one `Popen`, `shell=False`, the fixed prefix `[sys.executable, "-m", "umwayi", "agent", "run"]`, and no git word that writes. A later change to `goalrun.py` could start another program and that list would not catch it; only those guards would.

## CI (W24)

### 270. A pull request is tested on Python 3.10 and 3.13 only, so 3.11 and 3.12 run only after the merge

Since W24 a pull request runs the Python suite on 3.10 and 3.13 only, and a push to main runs it on 3.10, 3.11, 3.12 and 3.13. This cuts the wait on a pull request, and it moves two of the four versions to after the merge.

- A change that fails only on 3.11 or only on 3.12 can pass `tests / result` on its pull request, be merged, and fail on main. The merge is then already done, and the fix is a new pull request. The oldest and the newest version catch most such faults, because a behaviour that changed between 3.10 and 3.13 usually shows at one of the two ends, but a fault inside the range is not caught before the merge.
- The main run is the only record for 3.11 and 3.12. Someone has to look at it after a merge. A red main for a version that no pull request ran is the expected way this limit shows itself.
- A full local run before a merge still covers every version that is installed (`python tools/affected_tests.py --run --python python3.11 --python python3.12`). Nothing makes a session do it.
- The versions are chosen in `tools/ci_plan.py`, not in the workflow, and `tools/ci_shards.py verify` refuses a plan whose versions do not match its event. A third kind of event (a manual run) runs all four.
- The required check is still only `tests / result (pull_request)`. A branch rule that required a name of a 3.11 or 3.12 job on a pull request would wait for ever, because those jobs are no longer created there.

## Steering and guidance (W23), found while building

### 271. The guidance hash covers only the first line of a steering rule

`guidance.yaml` pins a steering rule by the SHA-256 of one line. These are the limits of that.

- The hash is of the first line of the rule only. A sentence added on a later line of the same rule (as W23 did to rule 9) changes no hash, so the loader does not stop and no test fails if the sentence and the guidance entry drift apart. Keeping them together depends on the rule 9 sentence being followed.
- Rule 9 itself cannot be enforced by a check: nothing finds a steering edit that has no matching guidance edit when the edited line is not the pinned one.
- `docs/kiro-issues-log.md` is written by hand from pull requests and CI logs. Nothing checks it against them.

## Goal orchestration (W9), found while building W9.8

### 272. The goal commands call the guard without a task record, and an AI helper is not yet denied the owner commands by the example rules

`umwayi/goal.py` is built. These are the choices it made where the spec was open, and what waits for the owner.

- `start`, `approve` and `run` call the guard of W19.1 before anything else, as the design says, but without a task record. A packet has no `consequences`, `undo` or `open_prs`, so a record built from it would fail every start. The guard therefore checks only that `guidance.yaml` loads and that its sources match; the four enforce checks do not run on a goal yet.
- W9.R2.6 asks the example rules of the adapters to deny an AI helper every `umwayi goal` command except `status` and `stop`. Adding those words changes rules whose hashes `tests/test_starter_rules.py` pins, and a new rule changes the pinned list of ids, so it waits for the owner. Until then the only guards of `approve`, `answer` and `merged` are the terminal check and the goal lock; a helper that has a terminal is not stopped (KNOWN-LIMITS 213).
- `approve --plan-hours N` is accepted and kept in the goal file, but the plan's deadline was set when the plan was made, so it changes nothing. `--wait-hours` sets the deadline of a later `needs owner`.
- `goal stop` does not take the goal lock. It records the stop and marks the queued tasks; a running `run` reads the goal file every second and stops its child with the reason `owner`. A run that holds the lock and has no child at that moment sees the stop at its next start step.
- The report shows the tester's verdict words and the guide's word but not their reasons or evidence, because the supervisor keeps no text of a helper. W9.R20.3 allows that text, cut and cleaned; nothing records it to show.
- `status` shows the spend of the goal as the planning budget plus what each task spent, because the planning run's real spend is not recorded (the W9.7 entry).

## Tester feedback (W26), found while building

### 273. The feedback path asks the tester to remove secrets by hand, and there is no safe export yet

The tester feedback path is an issue template and a page. These are its limits.

- The only protection against a secret in a report is the warning, the checkbox and the tester reading what they paste. Nothing scans an issue. A tester who ticks the box without reading can still post a secret, and a public issue cannot be unsent.
- The logbook summary export (counts per entry kind, counts per verdict, the date range, the chain status, the budget spent in UU, and no path, command text or rule text) does not exist. `docs/feedback.md` says Not yet available. `umwayi view snapshot` is not a substitute: it has no per kind or per verdict count and no date range, and it writes a logbook entry.
- The template cannot make GitHub require the answers: a tester can delete any question, and a blank issue stays allowed on purpose. `tests/test_feedback.py` checks the template file, not what a tester sends.
- The template has no label, so a report is not found by label. The template was not opened on GitHub in this task, so how GitHub shows it was not seen.

## Tester quickstart (W25)

### 274. The quickstart is checked against the command line, not against a real agent, and a tester copies three files by hand

`docs/quickstart.md` is for a stranger who installs umwayi-os from the public repo. `tests/test_quickstart.py` keeps every quoted command real, and the page was run command by command on a fresh clone. That proves less than it sounds.

- The test proves that each quoted command line parses against the real command line, not that it works or that the output in the page is the output you get. The outputs were checked by hand on one day, on Linux, and the page can go stale when a message changes.
- The agent section was run with a stand-in program for Claude Code, not a real one, so what a real `agent check`, `agent run` and cost report print was not seen (KNOWN-LIMITS 117 and the owner's real runs 10.21 and 10.31 are still open). The page says so.
- There is no `umwayi init`. A tester copies `rules.yaml`, `umwayi.json` and `jobs.yaml` into a scratch folder by hand, and a worktree for `--workdir` is made by hand with `git worktree add` under the exact name `ROOT-worktrees/g-NNNN-t-NN`. A wrong mode or name gives exit 64 with one fixed sentence and no hint which part was wrong.
- The page tells a tester that the logbook export is not available yet. When the exporter is built, nothing fails until someone reads the page; the open questions of the page say so. The goal section shows only `goal status` and a refused `goal start`: `approve` and `run` were not run for the page, because they need real agents and a terminal.
- Only Linux was tried. macOS, Windows and a Python older than 3.10 were not.

## Progress page artifact (W27), found while building

### 275. The progress page workflow was never run here, and its artifact is not a public page

`.github/workflows/progress-page.yml` keeps the progress page as a workflow artifact on a push to main. These are its limits.

- A workflow cannot run in this environment. `tests/test_progress_workflow.py` reads the file as text and pins what it must and must not contain. Whether the first run on main builds the page, uploads it and shows it in the Artifacts list was not seen.
- The artifact is not a public page. A person with read access to the repository downloads a zip from the Actions tab. It has no stable address, and it expires after 30 days. Publishing is the owner's decision and is not built.
- The workflow runs the build on every push to main, even a push that changes nothing the page shows. It also runs `npm ci`, which reads the npm registry or its cache.
- The build writes `ui/dist/index.html`, `cli-map.html` and `build.json` too, but only `progress.html` is uploaded. If the build wrote a different `progress.html` path, the step would fail (`if-no-files-found: error`) and no page would be kept.
- The page shows the sources as they are on main at that push, with the build date. A run that is cancelled or fails leaves the last artifact of an earlier run as the newest, so an old page can look current.
