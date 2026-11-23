# A dedicated umwayi signing key (E5, design note)

## Purpose

This note designs one signing key used only for umwayi-os. The owner approved the idea; this note is the design. It is a design note only: nothing here is built, and no code, rule, steering file, safety check, workflow or exit code changes with it.

It builds on the [provenance design](provenance-design.md) (W49), which already designs signing a task's record with the owner's SSH key through `ssh-keygen -Y sign -U`. This note replaces "the owner's SSH key" with a key kept for umwayi only, and adds two more things to sign.

## Current state

- umwayi signs nothing today.
  - The logbook has a hash chain and an outside anchor that the owner keeps (`umwayi logbook anchor`; [logbook](logbook.md)).
  - A goal approval holds each packet's SHA-256 (`umwayi/goalstate.py`).
- W49 (designed, not built) signs task records with the key held by the owner's `ssh-agent`, with `-U`, so no private key file is read.
- Since W64, no AI helper umwayi starts gets `SSH_AUTH_SOCK` or `SSH_AGENT_PID` (`agents.AGENT_SOCKET_ENV`). A helper can still look for an agent socket by its path; the W64 limits part says so.
- `cc-no-secrets` makes a Claude Code tool call No when its path names `id_rsa` or `id_ed25519` (`rules.yaml`). A dedicated key file under another name is not covered by that rule.

## The design

### What the key signs

| what | when | namespace | signed bytes |
| --- | --- | --- | --- |
| the logbook head | when the owner runs `umwayi logbook anchor --sign` | `umwayi-logbook` | the anchor line `COUNT:HEX` |
| a goal packet approval | at `umwayi goal approve`, when signing is on | `umwayi-approval` | one canonical line: the goal id, every kept task id with its packet SHA-256, the budgets and the roles |
| a release tag | when the owner tags a release with `git tag -s` | `git` (git's own namespace for SSH signatures) | git's tag object |
| a W49 task record | at `umwayi provenance sign` | `umwayi-provenance` | the record bytes (as W49) |

A namespace is part of each signature. A signature made for one use can never be accepted for another: an approval signature does not verify as a logbook head.

### Where the private key lives

- **On the owner's machine only.** It is a file the owner makes, for example `~/.ssh/umwayi_signing_ed25519`, with a passphrase. It can also be a hardware key (`-t ed25519-sk`).
- **Never in the repo.** The W62 secret scan (designed, not built) would refuse a private key header in any tracked file. Nothing refuses it today.
- **Never passed to a helper:**
  - umwayi signs only in owner commands that need a terminal. The supervisor and helpers never sign.
  - umwayi passes the key to `ssh-keygen` only through the agent (`-U`), as W49 does, so no process umwayi starts reads the file.
  - The agent socket is already removed from every helper environment (W64).
- **In the scrub lists.** The key's file name joins the secret path names of the starter rules (`cc-no-secrets`, `kiro-no-secrets`, `stdio-no-secrets`, `oc-no-secrets`), as `id_ed25519` is. That is a rules change and is listed here, not made (open question 2).
- **Loaded only while signing.** The owner adds it to the agent for a short time and asks to confirm each use: `ssh-add -t 300 -c ~/.ssh/umwayi_signing_ed25519`. A helper that finds the agent socket by its path then cannot use the key without the owner seeing a confirmation.

### How a verifier checks

- **The public key is in the repo**, in an allowed signers file, `.github/umwayi_signers`, with one line per key and its dates. For example: `umwayi-owner namespaces="umwayi-logbook,umwayi-approval,umwayi-provenance,git",valid-after="20261116" ssh-ed25519 AAAA...`. The options are joined by commas with no space. Measured with OpenSSH 9.9p1 on Nov 16: a space between them makes the line an invalid key.
- **Anyone can verify** with `ssh-keygen -Y verify -f .github/umwayi_signers -I umwayi-owner -n NAMESPACE -s FILE.sig < DATA`. A release tag is checked with `git tag -v TAG`, with `gpg.ssh.allowedSignersFile` set to that file.
- **What to publish (G2b).** Publish the PUBLIC key, the `.pub` file that `provenance.public_key` of `umwayi.json` names, in `.github/umwayi_signers` (one line) or beside the repository, never the private key. A third party then checks a file with `umwayi verify PATH --key THAT.pub`, which accepts a copy of the key and not the one in the owner's `umwayi.json`.
- **The date of a signature.** An SSH signature holds no trusted time. Measured with OpenSSH 9.9p1 on Nov 16: `valid-before` and `valid-after` are compared with the time of the verify, not the time of the signing, unless `-O verify-time=YYYYMMDD` is given. umwayi's verify passes the date of the logbook entry that holds the signature, which the hash chain and the outside anchor protect.
- **umwayi's own verify** (W50 for records, and the same for the anchor and approvals):
  - The signature must be good.
  - The namespace must be the expected one.
  - The key must be in the file and inside its dates, checked at the date of the entry (`-O verify-time`).
  - The signed bytes must be exactly the ones umwayi rebuilds.

  Anything else is a refusal, never a pass.
- **The signers file is protected.** A change to it needs a commit signed by a key already in it, as the W63 design's owner flag does (branch `w63-merge-ready-design`).

### Rotation

1. The owner makes the new key on their machine.
2. The owner adds the new key's line to `.github/umwayi_signers` with `valid-after` set to today, and sets `valid-before` on the old line to the same day.
3. That commit is signed with the old key. One logbook entry, `Signing key rotated: old SHA256:FP to new SHA256:FP`, is signed with the new key.
4. The old signatures stay valid when they are verified at the date of their own logbook entry (`-O verify-time`). A signature by the old key in an entry dated after the change fails. A bare `ssh-keygen -Y verify` without `verify-time` fails every old signature once `valid-before` has passed, so a verifier outside umwayi must pass the entry's date too.

### Loss or compromise

- **Lost, not leaked** (the file is gone, the passphrase forgotten):
  - The owner sets `valid-before` on the old line to the last day it was used, and adds a new key as in rotation.
  - The commit cannot be signed by the lost key, so it is signed by the new key and marked in the logbook as `Signing key lost: SHA256:FP`.
  - This one change is accepted only with the owner present at a terminal, as an owner command.
- **Leaked or suspected:** the same, with `valid-before` set to the last date the owner trusts.
  - Every signature after that date is treated as no signature.
  - Signatures before it are trusted only if the logbook anchor kept elsewhere matches.
- **No escrow.** umwayi keeps no copy of any key. A lost key is gone.

### When the key is missing: fail closed

- **Signing on, key missing.** Signing is on when `umwayi.json` has `"signing": {"public_key": PATH}`. If the agent does not hold the key at that moment:
  - `goal approve` refuses (exit 2) and nothing is approved;
  - `logbook anchor --sign` prints the anchor unsigned and says it is not signed (exit 2);
  - `provenance sign` refuses (exit 2, as W49).

  The fixed line says which: no agent socket, the key not in the agent, or a signature that did not verify at once.
- **Signing off** (no `signing` in `umwayi.json`): everything works as today, unsigned. Every verify says `not signed`, never `signed`.
- **A verifier with no public key, or a signers file it cannot read,** refuses (exit 2). It never treats an unsigned item as signed.

### Key generation is the owner's step

- umwayi never generates, imports, copies, adds to the agent or removes a key.
- The owner runs `ssh-keygen -t ed25519 -f ~/.ssh/umwayi_signing_ed25519 -C umwayi-signing` (or `-t ed25519-sk` for a hardware key), chooses a passphrase, and adds the public line to `.github/umwayi_signers` in a commit of their own.
- `umwayi agent check`-style output can say "signing: on, key SHA256:FP" or "signing: off". It never prints the key.

## Exit codes

Only 0, 2, 3 and 64:

- Signing and verify commands: 0 signed or verified; 2 refused (no key, a bad signature, a missing signers file); 64 usage or a bad `umwayi.json`.
- 3 when the kill switch is on or unknown, as for every owner command that writes.
- Never 1.

## What it never does

- No network: `ssh-keygen -Y sign` and `-Y verify` are local.
- It never reads a private key file, never prints a key, and never signs from an unattended run, a helper or the supervisor.
- No install: the system's `ssh-keygen`, at a fixed path (W49).
- It never accepts an unsigned item as signed, or a signature from another namespace.

## What it does not prove

- **A signature shows the owner's key was used, not that the owner read what was signed.** The approval prompt shows the counts and hashes, not every line of every packet.
- **A key on the owner's machine is only as safe as that machine.** A helper running as the owner's user could use a loaded key while it is in the agent. Confirmation per use (`ssh-add -c`) or a hardware key narrows this, and does not remove it.
- **Signing does not stop an edit.** It shows one, as the chain does.

## The tests it would need

| rule | test | planted fault |
| --- | --- | --- |
| one namespace per use | `test_an_approval_signature_does_not_verify_as_a_logbook_head` | use one namespace for all |
| signing only in owner commands | `test_the_supervisor_and_helpers_never_call_ssh_keygen_sign` (an import and call scan) | sign at `in review` |
| no key file read | `test_sign_uses_dash_U_and_no_private_path` | drop `-U` |
| missing key fails closed | `test_approve_refuses_when_signing_is_on_and_the_key_is_not_in_the_agent` | approve unsigned |
| signing off is said | `test_verify_says_not_signed_when_signing_is_off` | print `signed` |
| dates of a key | `test_a_signature_in_an_entry_after_valid_before_is_refused_and_one_before_passes` | verify at today's date instead of the entry's |
| signers file protected | `test_a_signers_change_needs_a_signature_by_a_listed_key` | accept an unsigned change |
| no key in the repo | `test_no_private_key_header_in_tracked_files` | plant one in a copy |
| exit codes | rows in `tests/test_exit_codes.py` | a refusal exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. A dedicated SSH signing key for umwayi on the owner's machine, used through the agent with `-U`, one namespace per use (logbook head, approval, release tag, W49 record), public key in `.github/umwayi_signers`, fail closed when the key is missing, generation the owner's step | E5, the owner's approval of a dedicated key. |

## Open questions

1. **A hardware key or a file with a passphrase?** Recommendation: a hardware key (`ed25519-sk`) if the owner has one, because each use needs a touch. Otherwise a file with a passphrase, loaded for five minutes with confirmation.
2. **The scrub lists.** Recommendation: add `umwayi_signing` to the secret path names of all four platforms' starter rules, in one owner-approved rules change with the pinned hashes updated in the same pull request.
3. **Sign every approval, or only when signing is on?** Recommendation: only when on, so umwayi keeps working for an owner who has not made a key. Once on, never fall back to unsigned.
4. **Where the signers file lives.** Recommendation: `.github/umwayi_signers`, protected as the W63 design protects `.github/`. One file for all namespaces, with the namespaces listed per key.
