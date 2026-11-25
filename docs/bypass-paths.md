# The bypass paths: what is proven, and what is not (J2 and J3)

## Purpose

One table that every claim about stopping an agent must point at. A claim about confinement, a post, a video or a pull request story may
say that a path is blocked only for a path that this table lists as proven, and must say which. For every other path the honest word is
cooperative: the agent is expected to follow the rules, and nothing was shown to stop it. The two columns "Works today" and "Needs proof"
keep the distinction visible in plain words (J3). The design behind the paths is in [the bypass design note](bypass-resistance-design.md); the
test is `tests/test_bypass_paths.py`.

## Current state

Read from `tests/test_bypass_paths.py` and the CI log of the run that merged it (2026-11-24, Landlock ABI 8 on the CI Linux runner; a Mac or a
container without Landlock skips the kernel parts, and a skip is never a pass). The kernel parts exercise the command that the run path
builds (`confine.argv`), not a real goal run: no real enforced goal run has finished (W40).

| # | Path tried from inside a confined run | Layer that refused it | Test (in `tests/test_bypass_paths.py`) | Status | Works today | Needs proof |
|---|---|---|---|---|---|---|
| 1 | A direct network call that skips the broker | none: the TCP connect succeeded | `test_path_1_a_tcp_connect_is_not_blocked_by_the_run_path_as_built_and_is_blocked_only_with_no_tcp` | not blocked, a finding (limit 344) | the option `no_tcp` refuses every TCP connect in the wrapper | the run path does not pass it, and a helper that must reach its model over HTTPS could not use it; a call to a host on port 443 is not blocked by anything here |
| 2 | `git push` with a stored token | the read limit (path 4) for the stored token; GitHub for a push to main | `test_path_2_a_stored_credential_in_the_home_folder_cannot_be_read_and_the_push_is_not_tried` | the read is proven; the push is not tried | a planted credential file in the home folder cannot be read from the wrapper | a real push with a stored token, in a real run |
| 3 | A write outside the allowed folders | the kernel (Landlock, EACCES) | `test_path_3_a_write_outside_the_allowed_folders_is_refused_by_the_kernel` | proven in the wrapper | the write inside the work folder works and the write outside is refused; the same child without the confinement succeeds | the same in a real goal run |
| 4 | A read of a credential file | the kernel (Landlock, EACCES) | `test_path_4_a_read_of_a_credential_file_outside_the_listed_folders_is_refused` | proven in the wrapper | a file outside the listed folders is refused | what a real run lists to read |
| 5 | A second process that drops the confinement | the kernel (an inherited restriction) | `test_path_5_a_second_process_cannot_drop_the_confinement` | proven in the wrapper | a fresh interpreter started by the child is refused too | a process started before the run and kept outside it is out of scope |
| 6 | A shell command that never goes through a hook | the kernel (Landlock, EACCES) | `test_path_6_a_shell_command_that_never_goes_through_a_hook_is_refused_by_the_kernel` | proven in the wrapper | a shell write outside the folders is refused with no gate or hook involved | the same in a real goal run |

Every path also has a logbook line that names the layer, written by `test_every_path_leaves_one_logbook_line_that_names_the_layer_that_refused_or_says_none`
into a test logbook: five say `kernel (landlock)` and path 1 says `none`. A real run does not write these lines yet.

How to read a claim: the word blocked may be used for paths 3, 4, 5 and 6 in the confined wrapper, on a kernel with Landlock, and for the read
of path 2. It may not be used for path 1, for a push, or for a real run. Confinement is off by default (`confine: false`).

## Decisions log

- 2026-11-25 (J2 and J3, the table first, docs only): one table with a Status column (proven, not proven, not blocked), and the two plain columns
  Works today and Needs proof. The scan that makes the word enforced sit next to a link to this table (J2) and the wider scan (K2) are code
  and wait for their own pull requests (owner stops).

## Open questions

- **Q-b1.** Should the honesty scan accept the word enforced only next to a link to this table? Recommendation: yes, as the J2 rule says, in a
  later pull request that changes the scan (an owner stop).
- **Q-b2.** Should the table be generated from the test so a new path cannot be added to one and not the other? Recommendation: keep it by
  hand for now; `test_the_note_has_six_paths_and_this_file_has_a_test_for_each` already ties the note to the test, and a later check can tie this file to it.
