section: Enforced by default (W78), found while building broker_lost (step 5a3)
title: a lost broker is found when the run ends, not while it runs
number: 336

These are facts of the code of this change.

- The run is told its broker is gone only by the hook's answers: every call after the loss is refused. The supervisor learns of it when the run ends and stops the task then, not at the moment of the loss.
- A broker that ended and was started again is not a case: a broker is started once per run.
- Only a `claude -p` run is covered. The task id is still `none` in the run table.
