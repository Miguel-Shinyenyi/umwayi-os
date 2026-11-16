# Story guide (W52)

## Purpose

This guide is for anyone who writes an article or makes a video about umwayi-os. It gives the creed, the ritual, the symbol, the founding story and the laws, and ties each one to a file, a test or a command in this repo. Every claim ends in "verify it yourself" with the command to run, so a reader never has to take the story on trust. If this repo cannot prove a claim, it does not belong in the story.

Run the commands from the root of a clone. The `check` commands use `--no-log` (a dry run), so they write nothing.

## Current state

### The creed

Unclear means no: nothing unclear is ever a Yes. With no matching rule, a broken or missing rules file, or action JSON that cannot be read, the answer is Ask me first, and the action does not go ahead without the owner. The creed is "unclear means no" because an unclear case is never a Yes.

Verify it yourself:

```
python -m umwayi check --rules rules.yaml --no-log '{"type": "something_new"}'
python -m umwayi check --rules rules.yaml --no-log 'not json'
python -m unittest tests.test_rules.FailClosedTests
```

The first two print `Ask me first` and exit 3. The tests cover a missing rules file, broken rules files, one bad rule that voids the whole file, an empty rule list and bad action JSON.

### The ritual: Yes, No, Ask me first

Before an AI helper, a job, a workflow, an adapter or an agent acts, it asks the rules one question and gets one of three answers: Yes (exit 0), No (exit 2) or Ask me first (exit 3). When several rules match, No beats Ask me first, and Ask me first beats Yes.

Verify it yourself:

```
python -m umwayi check --rules rules.yaml --no-log '{"type": "payment", "amount": 5}'
python -m umwayi check --rules rules.yaml --no-log '{"type": "tool_read", "platform": "claude-code", "tool": "Read"}'
python -m unittest tests.test_rules.DecisionTests
```

The first prints `No` (rule `no-money`, exit 2), the second `Yes` (rule `cc-read`, exit 0). The table of answers and exit codes is in [rules](rules.md) and [exit codes](exit-codes.md).

### The symbol: the shepherd and the logo

The owner's logo is [ui/assets/amwayi-logo-512.png](../ui/assets/amwayi-logo-512.png): a dark staff with a crook, on an amber square with round corners. It is the owner's own work, all rights his ([ui/assets/README.md](../ui/assets/README.md)); ask him before you use it. The site uses the same bytes for its icons (`site/app/icon.png` and `site/app/apple-icon.png`).

The shepherd is the centre of the web interface's scene: a hanging lantern on a shepherd's staff, held by a shepherd figure, with a dog beside, in the Kenyan highlands at dusk. The AI helpers are the sheepdog and the herd. The scene is specified in `.kiro/specs/umwayi-os/requirements.md` (layer 12) and `.kiro/specs/umwayi-os/design.md`.

Verify it yourself:

```
cmp ui/assets/amwayi-logo-512.png site/app/icon.png && echo same
grep -n "shepherd's staff" .kiro/specs/umwayi-os/requirements.md
grep -n "sheepdog and herd" .kiro/specs/umwayi-os/design.md
```

### The founding story: main went red at midnight

This is what the repo records, and nothing more. The goal tests used a fixed date, 2026-11-13. After UTC midnight on Nov 14 they broke on main. The code dates each logbook entry by its clock (the election clock), and the logbook refuses an entry dated before its last one, so tests that still wrote the fixed date failed. The fix, W34 (PR 106), made the test date follow the clock: today's UTC date. Only the tests changed, and no test changed its meaning.

The story: the logbook would not let the past be written after the present. It held its rule against umwayi's own tests, and the tests were changed, not the rule.

Verify it yourself:

```
cat docs-parts/status-log/W34.md
git show --stat b67cf10
python -m unittest tests.test_logbook.AppendTests.test_backwards_date_is_refused
```

Do not add a detail that is not in these records: no time of night beyond "after UTC midnight", no person, no reaction.

### The laws

Each law is a rule or a test in this repo. Each line ends with the command that checks it.

1. **No beats Ask me first, and Ask me first beats Yes.** `tests/test_rules.py`. Verify it yourself: `python -m unittest tests.test_rules.DecisionTests.test_precedence_no_beats_yes tests.test_rules.DecisionTests.test_precedence_ask_beats_yes`
2. **AI helpers never move money.** The rule `no-money` in `rules.yaml`. Verify it yourself: `python -m umwayi check --rules rules.yaml --no-log '{"type": "transfer"}'` (No, exit 2)
3. **A logbook failure never weakens a No.** If the logbook cannot be written, a No stays No and a Yes becomes Ask me first. `tests/test_check_log.py`. Verify it yourself: `python -m unittest tests.test_check_log.FailingLogbookTests`
4. **The kill switch denies every tool call, also when its state cannot be read.** `tests/adapters/test_claude_code.py`. Verify it yourself: `python -m unittest tests.adapters.test_claude_code.KillSwitchTests`
5. **A Yes rule runs out.** Past its `review_by` date it counts as Ask me first. `tests/test_elections.py`. Verify it yourself: `python -m unittest tests.test_elections.LapseTests`
6. **A rules change is logged before it is used.** `tests/test_rulelog.py`. Verify it yourself: `python -m unittest tests.test_rulelog.ChangeTests.test_a_weakened_no_is_logged_before_the_check_that_uses_it`
7. **An edit to the logbook is found.** An edited, deleted or reordered entry breaks the hash chain, and `verify` names it. `tests/test_logbook_chain.py`. Verify it yourself: `python -m unittest tests.test_logbook_chain.BrokenChainTests`
8. **Some actions are never moved to Yes by graded autonomy.** Money, publishing, sending and starting a goal are on the never list in `umwayi/rules.py`. Verify it yourself: `python -m unittest tests.autonomy.test_inputs`

### The imagined order, the unifier and legitimacy

These are the ideas from the owner's notes on Sapiens, and what in the repo stands behind each one.

- **The rules file is the imagined order.** `rules.yaml` is text the owner wrote: ids, titles, verdicts and matchers. On its own it binds nothing. The gate makes it hold: every check reads the file and answers from it, and an adapter acts on that answer. Verify it yourself: `python -m unittest tests.test_starter_rules`, which loads the repo `rules.yaml` with the real parser and runs a table of adapter actions through it.
- **One gate over three tools is the unifier.** Claude Code, Kiro and OpenCode each send every tool call through the same `umwayi check` command, as a separate process, and the same rules file answers for all three. Each starter rule names its platform, so a rule for one tool never answers for another. Verify it yourself: `grep -n "run_check" adapters/claude_code/hook.py adapters/kiro/hook.py adapters/stdio/hook.py` (the OpenCode plugin runs `adapters/stdio/hook.py`, see [adapters](adapters.md)), then `python -m unittest tests.test_starter_rules`.
- **Legitimacy comes from being checkable, not from authority.** Every check that is not a dry run writes one logbook entry, the entries are chained by hash, and anyone with the files can run the check. Nobody has to be trusted to say what happened. Verify it yourself: `python -m umwayi logbook verify` in an umwayi root (it prints `ok` or each problem with a line number), and `python -m unittest tests.test_logbook_chain`.

### What not to claim

The story must stay inside what the repo proves. These limits are written down in the repo, so say them too:

- Enforcement is cooperative. The adapters ask umwayi before each tool call; a process that never asks is not checked ([what it is and is not](what-it-is.md)).
- Matching is plain text, not a shell parser, so a command can be written to get past a rule ([rules](rules.md)).
- The hash chain shows an edit; it does not stop one. Every limit that is known and not fixed is in [KNOWN-LIMITS](KNOWN-LIMITS.md).
- It is early and experimental, not a security product and not a sandbox ([README](../README.md)).

Verify it yourself: `grep -n "cooperative" docs/what-it-is.md`

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-15 | The story guide ties each claim to a file, a test or a command, and the founding story repeats only what W34's status part and commit record | W52, the owner's notes on Sapiens. |

## Open questions

- The hub articles the owner mentioned are not in this repo, so this guide uses only the repo's own record. If an article records more of the founding story, it can be added here with a link once it is published.
