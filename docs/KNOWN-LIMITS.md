# Known limits

These are real limits of umwayi-os today. They are written down on purpose and are not fixed yet. Each one says what happens, why it matters and what would fix it later. Items 1 to 11 were checked on the hardening branch (Nov 8 2026) by running the commands, not only by reading the code. Items 12 to 20 come from building the layer 9 Claude Code adapter (item 16 is fixed in PR 12). Items 21 to 28 come from building the Kiro and generic adapters. Items 29 to 34 come from building layer 10 parts 1 and 2 (agents.yaml and the gate checks). Items 35 to 40 come from building part 3 (`umwayi agent run` for Claude Code). Items 41 to 45 come from building part 4 (`umwayi agent run` for Kiro). Items 46 to 51 come from building part 5 (`umwayi agent chat` on the terminal). Items 52 to 58 come from building part 6 (ACP chat for Kiro). Items 59 to 64 come from building part 7a (Claude Code over ACP: agents.yaml, `adapters/claude_acp/` and the gate checks). Items 65 to 68 come from building part 7b (the Claude Code ACP chat: the inline settings, the canary and the stop). Items 69 to 72 come from building part 7c-1 (subscription first: the login check, the credential names, `forceLoginMethod`). Items 73 to 80 come from building the Layer 5 crash safety addendum (the intent, recovery, flock and held-off signals); item 39 changed with it. Items 81 to 88 come from building part 7c-2 (`umwayi agent login` and Kiro subscription first). Items 89 to 92 come from building part 7c-3 (the watch during an ACP chat, the chat end to end, and the docs of 10.31); item 71 changed with it. Items 93 to 103 come from building layer 11 (scheduled runs through systemd user timers). Items 104 to 109 come from building the logbook hash chain (addendum, tasks C.1 to C.4); item 3 changed with it. Items 110 to 128 come from building the budget governor (tasks B.1 to B.10). Item 129 comes from the whole-system test (S.1); item 98 is true since then (a gap rule refusal now writes its entry). Items 130 to 137 come from the security scan (S.2, [SECURITY-SCAN.md](SECURITY-SCAN.md)); item 122 changed with it.

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

## Layer 13: elections (found while building L13.1)

### 160. `review_by` depends on the owner renewing honestly, and a rule with none never lapses

A Yes rule runs out only if it has a `review_by` date. A rule with no date, or a date the owner moves forward without looking, stays in force. `umwayi rules due` lists what needs a look, but nothing makes the owner run it, and a date more than 366 days ahead is only flagged as `far`, not refused (L13-Q10). The owner may put `review_by` in `rules.yaml` only after the version with elections is installed: older code calls it an unknown field and every check gives Ask me first.

### 161. A clock set far ahead lapses every dated rule, and the election clock never goes back

The date of a check is the latest of the system date, `--date` and the newest logbook date. A system clock set far ahead, or one entry with a far date, makes every dated Yes rule give Ask me first until the owner edits the dates; that is a safe error, not a Yes. A clock set back changes nothing, because the newest logbook date still counts. If the logbook cannot be read, only the system date and `--date` are used, and the entry of that check cannot be written either, so no Yes comes out.
