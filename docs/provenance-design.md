# Provenance and verify (W49 and W50): design note

## Purpose

This page is the design of two tasks the owner named on Nov 15. W49 keeps a provenance record for each goal task: the hashes of every file the task produced, kept beside the work and never inside it, sealed in the hash-chained logbook and signed with the owner's SSH key. W50 is `umwayi verify PATH`, which says whether a file was made by umwayi and is unchanged, was made by umwayi and changed since, or has no record. With both, the owner can answer "did this come out of a checked umwayi task, as it is now?" with a command instead of memory.

## Current state

**Built (2026-11-23): the record, signing and verify.** `umwayi/provsign.py`, `umwayi provenance sign GOAL TASK` and `umwayi verify PATH [--key] [--anchor]` are built and tested with throwaway keys and a real `ssh-keygen` and `ssh-agent`; the owner has not signed a real record with their own key yet. The paragraph below describes the earlier state: **Built in part (2026-11-23): the record only.** `umwayi/provenance.py` makes, stores and seals the record of a task (W49.R1 to R3) when `umwayi.json` has `"provenance": {"record": true}` (off by default; a deviation from this note, which makes it always on, so no existing root changes). It needs the hash chain; without one the task is `needs owner` (config). Not built: signing, `umwayi provenance sign` and `umwayi verify`. They need the owner's key, and the tests of this note use throwaway keys, which this build does not make. Until they exist a record proves nothing of origin. The rest of this page describes the whole design. Before the build it said: **Nothing is built.** This page is a design note only: no code, test, rule, steering file, safety check or workflow changed. It is built only after the owner answers the open questions below. The facts about `ssh-keygen` and the Python AST were measured in the sandbox on Nov 16 (OpenSSH_9.9p1; Python 3.10.20 to 3.14.4) and are named where they are used.

### The record (W49)

One record per task, written by the supervisor (`umwayi/goalrun.py`) at the moment a task reaches `in review` (W9.R8.7), from the worktree whose tip the scope check saw. The files are the ones the existing `changed` list of `umwayi/goalgit.py` reports between the base and the tip (`diff --name-status`): every added or modified file gets a hash, and a deleted file is listed by path only. No new git argument list is needed. The files are read from the worktree with `O_NOFOLLOW`, after `status` is clean and `head` is the tip, and both are asked again after the read; a difference is the existing `needs owner` (`unclear`).

The record is one JSON file, written as canonical bytes: `json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` plus one newline.

```json
{"base":"SHA","fingerprint":"python-ast-v1","files":[
  {"ast_sha256":"HEX","bytes":812,"path":"umwayi/up.py","sha256":"HEX"},
  {"ast_sha256":null,"bytes":40,"path":"docs-parts/status-log/W44.md","sha256":"HEX"}],
 "goal":"G-0007","kind":"umwayi-provenance","made_at":"2026-11-16T10:02:11Z",
 "packet_sha256":"HEX","python":"3.11","removed":["old/name.py"],"task":"T-02","tip":"SHA","version":1}
```

- `path` is relative to the repository top, in POSIX form, and passes the same path check as a packet's files (`goalgit.check_path`).
- `sha256` is the SHA-256 of the file's bytes, as read. `bytes` is the length.
- `ast_sha256` is the structure fingerprint, only for a path ending `.py`: the SHA-256 of `ast.dump(ast.parse(raw_bytes), include_attributes=False)` in UTF-8. It is `null` for other files and for a `.py` file that does not parse. Parsing the bytes, not decoded text, keeps the encoding line and a byte order mark meaning what Python reads.
- Measured: comments, blank lines, spacing, extra parentheses, `'''` against `"""`, a byte order mark and a `# type: ignore` comment leave the fingerprint the same. A changed docstring changes it, because a docstring is code (`__doc__`).
- `python` is the minor version that made the fingerprint. The dump differs between versions for the same source (measured: 3.10 and 3.11 agree, 3.12 differs, 3.13 and 3.14 agree with each other and differ from both). A fingerprint is compared only under the same minor version.
- No file content, diff, prompt, packet text or helper output is in the record. The packet is held by its hash.
- Limits: at most 2,000 files per record and 64 MiB read per task; more is `needs owner` (`config`), never a partial record.

### Where it is stored

`.umwayi/provenance/G-0007/T-02.json`, and after signing `T-02.json.sig`, under the umwayi root: beside the work, never inside it. Nothing is written into the worktree, the branch, a commit, a produced file or the owner's working copy, so the produced content is byte for byte what the builder committed. The folders are 0700 and the files 0600, each written once through a temporary file and `O_EXCL`; an existing record or signature is never overwritten. `.umwayi/provenance/` is added to `.gitignore`, like `.umwayi/goals/`. The records stay on this machine (open question 5).

### What is sealed

Two new entries of source `umwayi provenance`, in fixed shapes, each read back only when every line matches:

```text
- Source: umwayi provenance
- Added: record G-0007 T-02 written (sha256 HEX); files 7; with a fingerprint 4; removed 1; python 3.11
- Checked: the hash chain was intact before this entry; the task reached in review at tip SHA; the record was read back and its hash matched
- Not done: No produced file was changed, moved or written. The record is not signed yet. No path or content is in this entry.

- Source: umwayi provenance
- Added: record G-0007 T-02 signed (record sha256 HEX; signature sha256 HEX; key SHA256:FP)
- Checked: the hash chain was intact before this entry; the record hash matched the written entry; the signature verified with the configured public key and namespace umwayi-provenance
- Not done: No produced file was read or changed. The private key was not read by umwayi. No path or content is in this entry.
```

The written entry comes before the `in review` entry of the task. A record that cannot be written or logged stops the task as every failed record write does (W9.R13, `stopped`, reason `log`). Both entries need the hash chain: without a chain (`umwayi logbook seal --chain` not run yet) no record is written and the task goes to `needs owner` (`config`).

### How signing works

Signing is the owner's act, in a new owner command, `umwayi provenance sign G-0007 T-02`, never in the unattended supervisor (open question 2 has the reason). It needs a terminal on standard input and output, like `goal approve`.

1. The kill switch on or unreadable is Ask me first (3), nothing signed.
2. The task is `in review` or `merged`; the record parses, its hash matches the written entry, and no signature exists yet.
3. The public key is the file named in `umwayi.json` (`"provenance": {"public_key": "PATH"}`). It must be a regular file with one line of a public key of an allowed type, and no `PRIVATE KEY` text. umwayi computes its fingerprint itself (SHA-256 of the key blob, base64), with no process.
4. It prints the goal, the task, the tip, the file count, the record hash and the key fingerprint, and asks the owner to type `yes`.
5. It runs `ssh-keygen -Y sign -U -f PUBKEY -n umwayi-provenance` with the record bytes on standard input and the signature on standard output. No shell, a fixed argument list, a 60 second timeout (a hardware key waits for a touch), and an environment of `SSH_AUTH_SOCK`, `PATH` and `LANG=C` only.
6. It checks the output is one armoured `SSH SIGNATURE` block, verifies it at once as `verify` does, writes `T-02.json.sig` and appends the signed entry.

`-U` matters. Measured: without it, `ssh-keygen -Y sign -f KEY.pub` reads the private key file that lies beside the `.pub` file. With `-U` it uses only the key held by `ssh-agent` and fails when the agent does not have it ("Couldn't find key in agent") or there is no agent ("Couldn't get agent socket"). So no process started by umwayi reads a private key file. Signing from standard input to standard output was measured too: no temporary file holds the record, and the prompt that `ssh-keygen` gives when a `.sig` file exists never appears.

**Fail closed.** Each of these is exit 2 with one fixed line, nothing signed, no signature file and no logbook entry: no `provenance.public_key` in `umwayi.json`; a key file that is missing, a link, not one public key line or not an allowed type; `ssh-keygen` not found; no agent socket; the key not in the agent; `ssh-keygen` exiting non-zero or timing out (an old version without `-U` for `-Y sign` fails here); output that is not one signature; a signature that does not verify at once. A record that is not signed is never reported as made by umwayi: `verify` treats it as no record and says why.

### The three answers of verify (W50)

`umwayi verify PATH [--key PUBKEY] [--anchor COUNT:HEX]`. PATH is a regular file inside the umwayi root (no link); anything else is 64. `--key` checks with another copy of the public key; without it, the configured one is used. `--anchor` also checks the logbook against an anchor kept elsewhere, as `logbook verify --anchor` does.

A **trusted record** is one where all of these hold: the logbook verifies and has a chain (with `--anchor`, the anchor matches too); the record file is a regular file of the strict format above; its SHA-256 is in a written entry and in a later signed entry; the signature file's SHA-256 is in the signed entry; `ssh-keygen -Y verify -f ALLOWED -I umwayi-owner -n umwayi-provenance -s SIG` gives a good signature with the record bytes on standard input; and the key's fingerprint is the one in the signed entry. `ALLOWED` is one line, `umwayi-owner namespaces="umwayi-provenance" TYPE BLOB`, written by umwayi from the public key to a 0600 file made by `mkstemp` in `.umwayi/provenance/` and removed after the call.

verify finds every record that names PATH, newest first by the order of their signed entries, and answers:

| answer | when | exit |
| --- | --- | --- |
| made by umwayi and unchanged | the newest trusted record naming PATH has its `sha256`; or, for a `.py` file under the same Python minor version, its `ast_sha256` (the line then says "same structure; comments or formatting changed") | 0 |
| made by umwayi and changed since | a trusted record names PATH and neither hash matches (the line names the goal and task, and an older trusted record whose hash does match, if one does) | 3 |
| no record | no record names PATH, or the only ones that do are not signed | 2 |

Fail closed: when the logbook does not verify, a record file cannot be read or parsed, or a record naming PATH is signed but not trusted (a signature or a hash that does not match, a key that differs, `ssh-keygen` missing or failing), verify answers none of the three. It prints one fixed refusal line and exits 2. It never falls back to an older record when a newer one is not trusted. Exit codes: 0, 2, 3 and 64, never 1. 64 is usage (a bad option, a bad anchor, a PATH that is not a regular file inside the root, a bad `--key` or `umwayi.json`). An unexpected error is 2.

### What it logs

`verify` writes nothing: no logbook entry, no file other than its temporary allowed-signers file, no lock. It prints one answer or refusal line and, below it, the goal, the task, the tip, the date of the signed entry and the key fingerprint. It never prints file content, the record's other paths or a key. The kill switch does not stop it, because it changes nothing (as `umwayi view snapshot`). The supervisor writes one entry per record, and `provenance sign` one per signature, in the shapes above; no entry holds a path.

### What it never does

- No network: `ssh-keygen -Y sign` and `-Y verify` are local, and signing talks only to the agent's local socket.
- No install and no new dependency: the standard library and the system's `ssh-keygen`, found at a fixed absolute path (`/usr/bin/ssh-keygen`, then `/usr/local/bin/`, then `/opt/homebrew/bin/`), a regular file not writable by others. Not found is a refusal, never an install.
- No private key is read, opened, copied or printed by umwayi, and with `-U` none is read by `ssh-keygen` either. umwayi prints only the key fingerprint.
- No key is made, added to the agent or removed from it. No `ssh-add`, no `ssh` and no agent start.
- No produced file is changed, moved, renamed or touched, and nothing is written into a worktree, branch or commit.
- No push, fetch or pull. verify starts only `ssh-keygen`, and no AI helper.

### The spec lines it would add or change

New, in `requirements.md`:

- **W49.R1 The record.** One record per task at `in review`, of the format above, from the tip the scope check saw; every added or modified file with `sha256` and `bytes`, every `.py` file with `ast_sha256` and the Python minor version, deleted files by path.
- **W49.R2 Where.** `.umwayi/provenance/GOAL/TASK.json` and `.json.sig`, 0700 and 0600, written once, ignored by git; nothing written into the work.
- **W49.R3 Sealed.** The written and signed entries of source `umwayi provenance`, strict shapes, chain required, no path in an entry.
- **W49.R4 Signing.** `umwayi provenance sign GOAL TASK`: terminal, kill switch, typed `yes`, `ssh-keygen -Y sign -U -f PUBKEY -n umwayi-provenance` from standard input, verified at once; every failure is exit 2 and signs nothing. Exit codes 0, 2, 3, 64, never 1.
- **W49.R5 Never.** The list under "What it never does".
- **W50.R1 The answers.** The three answers and the trusted record, as above.
- **W50.R2 Exit codes.** 0 unchanged, 3 changed since, 2 no record or a refusal or an unexpected error, 64 usage, never 1.
- **W50.R3 Never.** Writes nothing, logs nothing, no network, no private key, not stopped by the kill switch.
- **W49.R6 and W50.R4 Tests.** The table below.

Changed:

- **W9.R8.7** gains: "and the provenance record of W49.R1 is written and its entry appended before the `in review` entry; a failed write is W9.R13."
- **W9.R19** gains `.umwayi/provenance/` in the files of the root.
- **docs:** `exit-codes.md` rows for `verify` and `provenance sign`; the two shapes in `logbook.md`; `.gitignore` gains `.umwayi/provenance/`. `umwayi/goalgit.py` keeps its 18 argument lists.

### The tests it would need

`tests/test_provenance.py` and `tests/test_verify.py`, with throwaway ed25519 keys and an agent made in the test (skipped with a reason when `ssh-keygen` or `ssh-agent` is missing; CI sets a variable that makes the skip a failure). Dates are today's UTC date, never a fixed day. One planted fault per rule:

| rule | planted fault | expected |
| --- | --- | --- |
| W49.R1 files | a task that adds, modifies and deletes a file | all three listed; hashes equal `hashlib` of the tip's bytes |
| W49.R1 fingerprint | the same `.py` reformatted, with comments; then a changed docstring | same `ast_sha256`; then a different one |
| W49.R1 version | a record made under another Python minor version | verify compares bytes only and says so |
| W49.R1 read race | the worktree's head moved between the reads | `needs owner` (`unclear`), no record |
| W49.R2 never inside | snapshot of the worktree, branch and root before and after | byte for byte the same |
| W49.R2 written once | a record and a `.sig` already there | refused, the old bytes kept |
| W49.R3 shapes | every entry built and matched; one hand-edited entry | refused by the parser |
| W49.R3 no chain | a logbook without a chain | no record, `needs owner` (`config`) |
| W49.R3 no path | a sentinel in a produced file's path and content | in no entry |
| W49.R4 no key | no `public_key`; a missing file; a link; a private key in its place | exit 2, no `.sig`, no entry |
| W49.R4 no tool | `ssh-keygen` missing at every fixed path | exit 2, nothing signed |
| W49.R4 agent | no socket; an agent without the key | exit 2, nothing signed |
| W49.R4 `-U` | a private key beside the `.pub` and an empty agent | exit 2 (the file beside it is not used) |
| W49.R4 terminal | not a terminal; a typed `no`; the kill switch on | exit 2, 2, 3; nothing signed |
| W49.R5 never | a source check of every argument list and every `open` | only `ssh-keygen -Y sign` and `-Y verify`; no `ssh-add`, no network module |
| W50.R1 unchanged | a signed record, the file as made | 0 |
| W50.R1 changed | one byte appended | 3 |
| W50.R1 structure | a comment added to a `.py` file | 0, with the structure line |
| W50.R1 no record | a file no task made; a record never signed | 2, 2 |
| W50.R1 older match | a file changed by a later task, then put back | 3, naming the older record |
| fail closed | a flipped signature byte; a changed record byte; another key; a broken chain; a torn record file; a wrong anchor | each 2 with its refusal line, never 0 |
| W50.R2 usage | a link; a folder; a path outside the root; a bad anchor | 64 |
| W50.R3 writes nothing | the whole root hashed before and after a verify | the same, no entry, the temporary file gone |

### What it does NOT prove

- It does not prove the code is correct, safe, tested well or free of copied work. It proves only that these bytes came out of a umwayi task that passed its checks, and that the owner's key signed the record of it.
- It does not prove who wrote the bytes. An AI helper wrote them; umwayi recorded them.
- A signature proves only that the key in the agent signed. Anyone who can use that agent can sign. Today every AI helper that umwayi starts gets the owner's `SSH_AUTH_SOCK`, because `claude_env` and `kiro_env` in `umwayi/agents.py` remove only credential names. A builder could therefore ask the agent to sign its own text. The signed entry is still needed, but a process that can write the root can write that too (open question 7).
- The logbook is local. Someone who can write the root can rewrite the whole chain, records and signatures included. Only an anchor kept elsewhere (`--anchor`) catches that.
- "Unchanged" does not prove the file was never changed: a file changed and changed back looks unchanged. A structure match hides changed comments, and comments can matter (`# type: ignore`, `# noqa`, a shebang line).
- Times come from the local clock.
- "No record" does not prove a person wrote the file, and a record on this machine says nothing on another one: the records are not in git, so a clone has none.
- It covers only files a goal task produced. Files the owner or a session writes outside a goal are never recorded, and that includes every pull request of this repository so far.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only; nothing built until the open questions are answered | The owner's task W49 and W50 (Nov 15): "design note only, no code". |

## Open questions

1. **The key (the owner's choice).** A new ed25519 key used only for umwayi provenance, with a passphrase, held in the agent only while signing; or the key the owner signs git commits with; or a hardware key (`sk-ssh-ed25519`). Recommendation: a new dedicated key, and the hardware type if the owner has one, so a signature needs a touch. Allowed types would be ed25519 and sk-ed25519 only.
2. **Who signs.** In the owner command at a terminal (this design), or by the supervisor at `in review`. Recommendation: the owner command. The supervisor runs unattended next to AI helpers that hold the agent socket (see "What it does NOT prove"), and a signature should be the owner's act.
3. **The exit code of "changed since".** 3, Ask me first: the owner should look (this design), or 2. Recommendation: 3, so a script can tell "never umwayi's" (2) from "umwayi's, but edited" (3).
4. **A structure-only match.** 0 with its own line (this design, following the owner's words that reformatting and comments do not change it), or 3. Recommendation: 0 with the line, since that is the purpose of the fingerprint.
5. **Where records live.** Only in `.umwayi/provenance/` on this machine (this design), or also exported to the hub repository. Recommendation: local for version 1, and an export command later as its own task.
6. **Finding `ssh-keygen`.** The fixed absolute paths (this design) or `PATH`. Recommendation: fixed paths, so a planted program earlier on `PATH` is never run with the record.
7. **The agent socket in AI helper children.** Remove `SSH_AUTH_SOCK` from the environment of every AI helper umwayi starts. Recommendation: yes, as its own small task before W49 is built. It changes the environment of the gated runs, so it needs the owner's word, and it is not done here.
8. **When to build.** Recommendation: after Dec 3, W49 first (about 8 hours), then W50 (about 6 hours), each in its own pull request; the hours are an estimate.
