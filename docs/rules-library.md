# A base rules library (W76, design note)

## Purpose

This note designs a library of ready rules files that an owner can pick from instead of writing rules from nothing. It is a design note only. `rules.yaml` and every default rule stay exactly as they are. The example files below are text in this page, not active rules: nothing reads them.

Each example is written in the existing `rules.yaml` format ([rules](rules.md)). Each comes with a one line plain description and what it does not cover. Each was checked on Nov 16 with the real reader, `umwayi rules validate --rules FILE` (W58a), and gave `ok`.

## Current state

- **One rules file per umwayi root,** `rules.yaml`. It ends with starter rules for the four adapters (`cc-`, `kiro-`, `stdio-`, `oc-`) and holds 50 rules at main `25b3a47`; `umwayi rules validate` gives `ok` for it.
- **The format:** `id`, `title`, `text`, an optional `cause`, `verdict` (`yes`, `no`, `ask`), `matchers`, and the optional `review_by` and `autonomy`.
  - The matchers are `equals` (a bare field name), `__contains`, `__exists`, `__startswith` and `__prefix` (W57).
  - An unknown field in a rule makes the whole file malformed.
- **Answers:** No beats Ask me first beats Yes, and no matching rule is Ask me first.
- **One example file exists already:** the builder rules for goal worktrees in `goal.rules.example.yaml` (W57), commented out. They are the library's builder set (below).
- **No library, no index and no version** for a set of rules exists today.
- **The rules change log** hashes the bytes of `rules.yaml` and logs the ids added and removed when it changes ([rules](rules.md)).

## The library

Every set is for Claude Code (`platform: claude-code`). Kiro and OpenCode use other tool types (`tool_execute_bash`, `tool_fs_write`, `tool_shell`, ...) and other field names (`input_command`, `input_path`), so each set needs its own Kiro and OpenCode copy (open question 3).

**One limit holds for every set: a set applies to the whole root, not to one agent.** The hook's action names the platform and the tool, not the agent of `agents.yaml` (`adapters/common/umwayi_gate.py`). So a read only set in a root makes every Claude Code helper of that root read only. To give two helpers different sets today, give them two roots (open question 2).

### Read only helper (`lib-readonly`, version 1)

- **What it does:** A Claude Code helper may read and search, and never writes or runs a shell command.
- **What it does not cover:** Reads of any file the owner's user can read, including secrets the starter `cc-no-secrets` does not name; web and MCP tools (they stay Ask me first unless `lib-no-network` is added).
- **SHA-256 of the block below:** `82ce7251644b3740c50e6ff416bceb1a581a6c6e7f8a77cdd4f7c1531e3e673f`

```yaml
rules:
  - id: lib-ro-read
    title: The helper may read and search
    text: Reading files and searching for files or text is allowed.
    verdict: yes
    matchers:
      platform: claude-code
      type: [tool_read, tool_glob, tool_grep]
  - id: lib-ro-no-write
    title: The helper never writes
    text: No file is written, edited or deleted by this helper.
    verdict: no
    matchers:
      platform: claude-code
      type: [tool_write, tool_edit, tool_multiedit, tool_notebookedit]
  - id: lib-ro-no-shell
    title: The helper runs no shell command
    text: A read only helper runs no shell command.
    verdict: no
    matchers:
      platform: claude-code
      type: [tool_bash, tool_powershell]
```

### Tester with no write (`lib-tester`, version 1)

- **What it does:** A Claude Code tester writes nothing and may run only `python3 -m unittest`, one command, inside the goal worktrees.
- **What it does not cover:** What the tests themselves do once started (they run as the owner's user and can write or connect); test runners other than `unittest`; a worktree root other than the one written in place of `/path/to/umwayi-root-worktrees`.
- **SHA-256 of the block below:** `e805413ad07b73847471489004bcf4762121478604bc05eb2c07e39f41958c39`

```yaml
rules:
  - id: lib-test-no-write
    title: The tester writes nothing
    text: The tester never writes, edits or deletes a file.
    verdict: no
    matchers:
      platform: claude-code
      type: [tool_write, tool_edit, tool_multiedit, tool_notebookedit]
  - id: lib-test-no-chain
    title: One command at a time
    text: A tester shell command may not chain, pipe, run in the background, substitute or redirect.
    verdict: no
    matchers:
      platform: claude-code
      type: tool_bash
      command__contains: ["&", ";", "|", "`", "$(", ">"]
  - id: lib-test-unittest
    title: The tester may run the tests
    text: python3 -m unittest is allowed inside the goal worktrees.
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_bash
      cwd__prefix: /path/to/umwayi-root-worktrees
      command__startswith: ["python3 -m unittest "]
  - id: lib-test-unittest-bare
    title: The tests, with no arguments
    text: python3 -m unittest written alone is allowed inside the goal worktrees.
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_bash
      cwd__prefix: /path/to/umwayi-root-worktrees
      command: python3 -m unittest
```

### No network (`lib-no-network`, version 1)

- **What it does:** A Claude Code helper fetches no web page, searches nothing, calls no MCP tool and runs no shell command that names a network program.
- **What it does not cover:** Network use by a program that a command starts, or by code that names no listed word. Checked on Nov 16: `python3 -c "import urllib.request"` matches no rule of this set (it stays Ask me first only because no Yes rule matches it). Plain text matching, not a shell parser (KNOWN-LIMITS 12).
- **SHA-256 of the block below:** `67b40985286333bb5e5d5aeb2d92c0723719c0af1dccadc2115a040dc230e390`

```yaml
rules:
  - id: lib-net-no-web
    title: No web pages, searches or MCP tools
    text: The helper fetches no page, searches nothing and calls no MCP tool.
    verdict: no
    matchers:
      platform: claude-code
      type: [tool_webfetch, tool_websearch, tool_mcp]
  - id: lib-net-no-shell-net
    title: No network commands in the shell
    text: A shell command that names a network program or a download is refused.
    verdict: no
    matchers:
      platform: claude-code
      type: [tool_bash, tool_powershell]
      command__contains: ["curl", "wget", "ssh ", "scp ", "rsync", "nc ", "git push", "git fetch", "git pull", "git clone", "pip install", "npm install", "npx ", "gh "]
```

### No credentials (`lib-no-credentials`, version 1)

- **What it does:** A Claude Code helper reads no credential file and runs no shell command that names one or prints the environment.
- **What it does not cover:** Credentials already in the helper's environment (removed only for the names `claude_env` knows, and the SSH agent since W64); a credential file under a name not listed; a program that reads one without naming it.
- **SHA-256 of the block below:** `3197ef155f4d3489c6f7cc4a827597b63dd1eb1f3f033e4d53a6fb545cb4068f`

```yaml
rules:
  - id: lib-cred-no-paths
    title: No credential files
    text: Files and folders that usually hold keys or tokens are not read or changed.
    verdict: no
    matchers:
      platform: claude-code
      path__contains: [".aws/", ".ssh/", ".netrc", ".config/gh", ".npmrc", ".pypirc", ".docker/config.json", ".kube/config", ".git-credentials", ".gnupg"]
  - id: lib-cred-no-shell
    title: No credential reads in the shell
    text: A shell command that names a credential file or prints the environment is refused.
    verdict: no
    matchers:
      platform: claude-code
      type: [tool_bash, tool_powershell]
      command__contains: [".aws/", ".ssh/", ".netrc", ".config/gh", ".npmrc", ".pypirc", ".git-credentials", ".gnupg", "printenv", "security find", "secret-tool", "gh auth token"]
```

### Budget check for named agents (`lib-budget`, version 1)

- **What it does:** The budget check is Yes for two named agents; every other agent's start is Ask me first.
- **What it does not cover:** The size of a budget. Rules match words, not numbers: there is no less-than matcher, so a cap is set in `units.yaml` (`limits`: `per_run`, `per_day`, `per_agent_per_day`, `per_platform_per_day`), not in a rule. `budget_check` is on the never list, so graded autonomy never moves it.
- **SHA-256 of the block below:** `adb81a98fb5e60a67c7b7e70e28aa80533da4a13cb03993fad4ef703116ced76`

```yaml
rules:
  - id: lib-budget-named
    title: The budget check is fine for these agents
    text: These agents may reserve a budget without asking; every other agent asks.
    verdict: yes
    matchers:
      type: budget_check
      agent: [claude-build, kiro-test]
```

### Builder in a goal worktree (`lib-builder`, version 1)

- **What it does:** a Claude Code builder may write files and run five commands (`git status`, `git diff`, `git add`, `git commit`, `python3 -m unittest`) inside the goal worktrees, with no chain characters and no `--output`.
- **What it does not cover:** see `goal.rules.example.yaml` and [rules](rules.md), "Builder rules for goal worktrees". The set is the five commented rules of that file, unchanged; it is not repeated here, so there is one copy.
- **One step it needs:** take `cc-ask-write` and `cc-ask-shell` out of the root's `rules.yaml`, because Ask me first beats Yes. Without that the set does nothing.

## How an owner chooses and copies a set

1. Read the one line description and "does not cover" of each set in this page.
2. Copy the block of each set wanted, as it is, to the end of the root's `rules.yaml`. There is no include and no import: one file stays the one source.
3. Replace a placeholder such as `/path/to/umwayi-root-worktrees` with the real path.
4. Run `umwayi rules validate`. It must give `ok` (exit 0). A malformed file makes every check Ask me first until it is fixed.
5. Check a few actions with `umwayi check --no-log` against the file before any helper runs.
6. Every later check logs the change before it is used: the rules change log names the ids added, all `lib-...`.

Sets combine by the rules of the gate, not by order: a No from any set beats every Yes. So `lib-no-network` with `lib-tester` refuses a test command that contains `curl`, and `lib-readonly` with `lib-builder` refuses every builder shell command (`lib-ro-no-shell` is No).

## Versions and hashes

- **Ids carry the set:** every rule id starts with the set's prefix (`lib-ro-`, `lib-test-`, `lib-net-`, `lib-cred-`, `lib-budget-`, `builder-`), so the rules change log shows which set was added or removed.
- **A version per set:** this page gives each set a version and the SHA-256 of its exact block. A new version is a new block with a new hash, never an edit of the old one; the old version stays listed with its hash.
- **Checking a copy:** a later command (`umwayi rules library check`, not built) would find each `lib-` rule in `rules.yaml`, rebuild its set's block from the rules found, and compare the hash with the index. A copy that was edited by hand is reported as `changed`, not refused: the owner may edit a copy, and then it is the owner's rule.
- **What the hash does not show:** that a set is right for this root.

## How the gate treats an unknown rule

- **An unknown field** in any rule makes the whole file malformed. `umwayi rules validate` exits 64 and every check answers Ask me first. Checked on Nov 16: a rule with `colour: red` gave `rule 'x': unknown field(s)`, exit 64, and `umwayi check` answered Ask me first.
- **An unknown action** (no rule matches) is Ask me first.
- **An unknown matcher operator** (`command__endswith`) is not refused. It is read as an equals matcher on a field of that whole name, which no action has, so the rule never matches (W58a, W57). A set that relies on it does nothing. This is the one way a copied rule can fail silently (open question 4).

## What stays a No by default

None of the sets weakens a starter No. These stay No whatever set is copied, because No beats Yes:

- money (`no-money`, `no-money-amount`, `cc-no-money`, `oc-no-money`);
- publishing (`no-publish`);
- a push to main or a forced push (`no-push-main`, `cc-no-push-main`, `oc-no-push-main`);
- wiping folders or disks (`cc-no-destroy`, `kiro-no-destroy`, `oc-no-destroy`);
- the guard files and commands (`cc-no-guard-edits`, `cc-no-guard-shell`, and the Kiro and OpenCode copies);
- secret paths (`cc-no-secrets` and its copies).

A set adds Yes and No rules. It never removes a rule; only the owner does, by hand, as the builder set's step says.

## Tests it would need

| rule | test | planted fault |
| --- | --- | --- |
| every block is valid | `test_every_library_block_validates_ok` (extract each block from this page, run the real reader) | a block with an unknown field |
| the hash in the index | `test_each_block_matches_its_listed_sha256` | edit a block without its hash |
| the decisions of each set | `test_each_set_answers_its_table` (`umwayi check --no-log` on a fixed list of actions per set) | drop the chain rule of `lib-tester` |
| nothing is active | `test_no_library_block_is_read_by_umwayi` and `test_rules_yaml_is_unchanged` (its bytes pinned) | load the page's blocks at start |
| no starter No is weakened | `test_every_starter_no_still_answers_no_with_each_set_added` | a set with a Yes for `tool_bash` that names `rm -rf` |
| unknown operator | `test_no_library_rule_uses_an_unknown_operator` | `command__endswith` in a block |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. Five sets as text in this page plus the builder set of `goal.rules.example.yaml`, each validated with the real reader, versioned and hashed; copied by the owner into `rules.yaml`; no default rule changed | W76, the owner's task of Nov 16. |

## Open questions

1. **Where do the sets live once built: this page, or files such as `rules.library/readonly.yaml`?** Recommendation: files in the repo, outside the root, never read by the gate, with this page listing them and their hashes, and the test that extracts and validates them. A page alone is easy to copy wrongly.
2. **Per agent sets.** Today a set applies to every Claude Code helper of a root. Recommendation: let `agent run` put the agent's name in the hook's action (with the run marker of W41 option A), so a rule can match `agent:`. Until then, one root per role when the roles need different sets.
3. **Kiro and OpenCode copies.** Recommendation: write each set for the three platforms in one go, with the Kiro tool ids that the Kiro docs confirm (KNOWN-LIMITS 21), and say where a Kiro field is not confirmed.
4. **Refuse an unknown operator at load?** Recommendation: yes, as its own owner-approved change, because a copied rule that silently never matches is the worst failure a library can have. Until then, the library test refuses one in any block.
5. **Should `umwayi rules library check` exist?** Recommendation: yes, read only, exit 0 when every `lib-` rule matches its set, 3 when one changed, 64 for a bad file. Never 2 for a changed copy: an owner's edit is not an error.
