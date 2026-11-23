section: Provenance (W49, W50), found while building signing and verify
title: a signature proves that the key in the agent signed, and nothing about the code
number: 342

These are facts of the code of this change. Tested with throwaway keys; the owner's own key has not signed a real record.

- A signature proves only that a key held by an `ssh-agent` signed these record bytes. Anyone who can use that agent can sign. umwayi removes `SSH_AUTH_SOCK` from the environment of every helper it starts, but a helper that finds the socket by other means can ask the agent.
- `verify` trusts the logbook of this machine. Someone who can write the root can rewrite the chain, the records and the signatures together; only an anchor kept elsewhere (`--anchor`) catches that. Without `--anchor` the chain is only checked for itself.
- "Unchanged" does not show a file was never changed: a file changed and changed back looks unchanged. A structure match hides changed comments, and comments can matter (`# type: ignore`, `# noqa`, a shebang).
- A `.py` structure hash is compared only under the same Python minor version; under another one the bytes are compared.
- Only files a goal task produced have a record, and only when `provenance.record` is on in `umwayi.json`. The records are on this machine and not in git.
- It needs `ssh-keygen` at `/usr/bin`, `/usr/local/bin` or `/opt/homebrew/bin` (a regular file not writable by others). Old versions without `-Y sign -U` fail and the signing is refused.
- A hardware key waits for a touch (60 seconds). A key with a passphrase is the agent's business: umwayi never sees it.
