# Known limits

These are real limits of umwayi-os today. They are written down on purpose and are not fixed yet. Each one says what happens, why it matters and what would fix it later. Items 1 to 11 were checked on the hardening branch (Nov 8 2026) by running the commands, not only by reading the code. Items 12 to 20 come from building the layer 9 Claude Code adapter (item 16 is fixed in PR 12). Items 21 to 28 come from building the Kiro and generic adapters. Items 29 to 34 come from building layer 10 parts 1 and 2 (agents.yaml and the gate checks). Items 35 to 40 come from building part 3 (`umwayi agent run` for Claude Code). Items 41 to 45 come from building part 4 (`umwayi agent run` for Kiro). Items 46 to 51 come from building part 5 (`umwayi agent chat` on the terminal). Items 52 to 58 come from building part 6 (ACP chat for Kiro).

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

- A later fix: keep the hash outside the repo, chain each entry to the one before it, or sign the record.

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

### 39. A logbook that cannot be written stops the agent, including a stale lock

Every second the run checks that the logbook could still take an entry (`logbook.check_writable`, under the logbook lock). A hand edit, a missing hash record, a broken format, or a `.umwayi/logbook.lock` left by a crashed command for more than 3 seconds stops the agent with exit 2. Nothing can be logged about that stop; umwayi prints why. The check reads and hashes the whole logbook once a second, which grows with every tool call; it was not measured on a large logbook.

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

### 55. Claude Code over ACP is not built

Claude Code has no ACP mode in its own command line; it would need Zed's third party adapter (`claude-agent-acp`), a Node package. The owner decided to decide this later (tasks.md 10.0, answer 9). A Claude Code agent with `transport: acp` is a validation error.

### 56. Ctrl-C gives the owner back after 10 seconds, even if the agent goes on

If the agent does not answer `session/cancel` within 10 seconds, umwayi gives the owner the prompt back and ignores the late answer, but the agent may still be working on the cancelled turn. A new prompt then overlaps with it. Each tool call is still checked (by the hook, if it runs, item 53) and each permission request by the rules.

### 57. What safe_text does not catch

Agent text has control characters, bidirectional controls, zero-width characters and tag characters made visible. Look-alike letters from other scripts, very long lines and Markdown are shown as they are. A tool call's title is written by the agent: it describes the call, it is not proof of what the call does, and the rules never see it.

### 58. One chat, one turn at a time

umwayi sends one prompt at a time and holds the owner's next lines until the turn ends. It does not use `session/load`, `session/list`, modes, models or Kiro's extension methods, and it advertises no capabilities, so Kiro features that need them are not available in an ACP chat. Kiro's own interactive approvals (for tools it does not trust) arrive as permission requests and are answered by the rules and the owner as above.
