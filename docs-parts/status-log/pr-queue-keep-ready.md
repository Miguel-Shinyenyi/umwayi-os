date: 2026-11-24
pr: 217
what: G7 design note, two additions, docs only. (1) The queue is never left empty while tasks are pending (owner, 2026-11-24): a `keep_ready` setting (recommended 2), a `queue low` line in `next` that names the next pending task whose inputs exist, `blocked: TASK needs ANSWER` for a task that waits on the owner so the next one is named, and a `ready branches: N of keep_ready` line in the session report. (2) `watch` reads the check runs of the exact head commit, as `tools/pr_green.py` does, and treats an empty list as "not yet", after a watcher of mine said all checks had finished when none had started. Nothing is built.
tests: the docs tests.
