# Known compatibility gaps

These limitations are reproduced in shish. Each entry records the affected
behavior, expected and observed results, workaround, and regression test.
The [compatibility reference](compatibility.md#reading-the-evidence) defines
coverage labels and records the audit environments. Ignored acceptance tests
assert the intended behavior and are not passing support claims.

- [POSIX gaps](#confirmed-posix-gaps)
- [Input and command lookup gaps](#input-and-command-lookup-gaps)
- [Interactive gaps](#interactive-compatibility-gaps)

## Confirmed POSIX gaps

All P01–P04 reproducers use the [audit environment](compatibility.md#reading-the-evidence). Unless noted,
stdout is shown with `\n` for a newline and stderr is empty. The expected status
is 0. The owner identifies the component responsible for the behavior.

### P01: non-whitespace IFS fields

Reference: POSIX §2.6.5. Reproducer:

```sh
shish -c 'IFS=:; v=":a::b:"; set -- $v; printf "<%s>\n" "$@"'
```

Expected `<>\n<a>\n<>\n<b>\n`; observed `<a>\n<b>\n`, status 0. Empty fields
are lost, corrupting delimiter-based records. Owner: Brush expansion. Workaround:
keep values quoted and use an explicit data parser when delimiters matter.
Acceptance test: `posix_ifs_preserves_empty_fields` in [audit.rs](../tests/audit.rs),
currently ignored because it fails.

### P02: assignments before special builtins

Reference: POSIX §2.9.1 and §2.15. Reproducer:

```sh
shish -c 'unset v; v=kept :; printf "<%s>\n" "$v"'
```

Expected `<kept>\n`; observed `<>\n`, status 0. Subsequent commands lose assigned
shell state. Owner: Brush evaluation. Workaround: `v=kept; :` when that separate
assignment has the intended semantics. Acceptance test:
`posix_special_builtin_assignment_persists` in [audit.rs](../tests/audit.rs),
currently ignored.

### P03: asynchronous process parameter

Reference: POSIX §2.5.2 and §2.9.3. Reproducer:

```sh
shish -c '/bin/sleep 0.01 & printf "<%s>\n" "${!:+set}"; wait'
```

Expected `<set>\n`; observed `<>\n`, status 0. PID-based wait, cancellation, and
ownership scripts cannot identify the launched process through `$!`. Owner:
Brush job tracking; jobs currently use internal asynchronous tasks without a
reliable process ID. Workaround: `wait` without a PID when waiting for all jobs is
acceptable. Acceptance test:
`posix_background_process_parameter_is_set` in [audit.rs](../tests/audit.rs),
currently ignored.

### P04: signal traps

Reference: POSIX §2.12 and `trap`. Reproducer:

```sh
shish -c 'trap "printf caught" TERM; kill -TERM $$; printf done'
```

Expected `caughtdone`, status 0; observed no output and termination by SIGTERM
(signal 15, conventionally status 143 when observed by a parent shell). Owner:
Brush signal/trap dispatch; handler registration does not establish TERM delivery.
EXIT handling works separately. Workaround: delegate signal-sensitive scripts to
a shell with verified handling; do not depend on this trap for cleanup.
Acceptance test: `posix_term_trap_handles_signal` in [audit.rs](../tests/audit.rs),
currently ignored.

### P05: interactive startup files are skipped

Reference: the POSIX `sh` ENV startup requirements. In the snapshot above, launch
`ENV=/absolute/startup shish -i` with a file containing `export MARK=loaded`, then
inspect `$MARK`. POSIX interactive startup would source the file; shish leaves
MARK unset. Owner: intentional shish integration policy (`ProfileLoadBehavior`
and `RcLoadBehavior` are Skip), verified by the PTY test
`startup_policy_skips_interactive_env` in [audit.rs](../tests/audit.rs).
Impact: users must source configuration explicitly. Workaround: `. /absolute/startup`.

### P06: command descriptions omit functions

Reference: POSIX `command`, `-v` description behavior. Reproduced during task 06
with the same shish/Brush versions, platform, and default mode as the initial audit:

```sh
shish -c 'f() { :; }; command -v f'
```

Expected `f\n`, status 0; observed empty output, status 1, empty stderr. Scripts
that use `command -v` to detect a function incorrectly conclude it is absent.
Owner: Brush's `command` builtin lookup only considers builtins and executables.
Workaround: use `type` for inspection where its descriptive format is acceptable.
Acceptance test: `posix_command_v_reports_functions` in [audit.rs](../tests/audit.rs),
currently ignored.

## Input and command lookup gaps

Evidence was collected on macOS 27.0.1 (arm64) in the default sh/POSIX mode.
Other platforms are unverified.
The reference is `/bin/sh` (Bash 3.2.57 in sh mode); it passes both fixtures.
The ignored tests in [the CLI suite](../tests/cli.rs) assert the desired behavior;
they are not passing support claims.

### Large multiline stdin: partial support

The stdin adapter clones and reparses the entire pending command after every
line. A multiline quoted assignment containing 20,000 `payload` lines, followed
by `printf done`, exceeds the five-second acceptance budget before producing
output. The same input should finish with status 0, stdout `done`, and empty
stderr. Small multiline commands work; generated loops, here-documents, and
quoted strings can incur quadratic input-processing cost. This is an integration
performance gap, not a POSIX timing violation.

Run the bounded reproducer from the repository root:

```sh
cargo test -p shish --test cli large_multiline_stdin_completes_within_budget -- --ignored --exact
```

As a workaround, save generated code in a script and invoke `shish script.sh`.
Script operands use Brush's script API and avoid the adapter's prefix loop.
The shell preserves stdin for `read` and external programs instead of consuming
the entire stream before execution.

### Directory entries in PATH: partial support

With `PATH=first:second:third`, put a directory named `probe` in `first`, a
non-executable file named `probe` in `second`, and an executable `probe` that
prints `found` in `third`. Expected behavior is status 0, stdout `found`, and empty
stderr. Current execution returns 126 with a permission-denied diagnostic and
no stdout because lookup selects the first directory.

This conflicts with the executable search described in POSIX.1-2024,
[Shell Command Language, Command Search and Execution](https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html#tag_19_09_01_04).
Brush's normal cached lookup checks executable permissions without excluding
directories; its separate path-search helper excludes them. No shish lookup
replacement is introduced. Use an explicit executable path or remove the
conflicting directory entry from PATH as a workaround.

```sh
cargo test -p shish --test cli path_lookup_skips_directories_and_nonexecutable_files -- --ignored --exact
```

The separate checkout-relative `target/debug` lookup vulnerability is removed by
the runtime replacement and covered by an active CLI regression.

## Interactive compatibility gaps

These are product/Readline behaviors, separate from the POSIX scope. They use the
recorded Darwin 27 arm64 audit environment, with `-i`; Bash mode is stated when
required. Terminal output combines stdout/stderr. Acceptance tests assert the intended behavior and
are ignored because they currently fail.

### C25: Enter after an empty command-completion menu

Reference:
[Readline completion commands](https://www.gnu.org/software/bash/manual/html_node/Commands-For-Completion.html).
In an isolated PATH, type `shish_missing_completion`, Tab, then Enter. Expected:
the unchanged command executes, reports command-not-found, and returns status 127.
Observed: the input remains visible without execution; the first Enter dismisses
the empty menu. The acceptance test times out waiting for the diagnostic.

Owner: Brush/Reedline integration. Brush activates a completion menu even with no
candidates. Unmatched text preservation and Ctrl-C cancellation are verified.
Impact: an extra interaction is needed to submit the command. Workaround: cancel
with Ctrl-C and type the full command without Tab.

Tests: `task_25_unmatched_input_can_be_cancelled` and the ignored
`task_25_enter_executes_after_no_completion` in [audit.rs](../tests/audit.rs).

### C28: command completion does not insert the common prefix

Reference:
[Readline completion commands](https://www.gnu.org/software/bash/manual/html_node/Commands-For-Completion.html).
Put executable files `shish_pick_one` and `shish_pick_two` on an isolated PATH.
In default interactive mode, type `shish_p` and Tab. Expected input:
`shish_pick_`. Observed input: `shish_p`, with both candidates displayed below it.

Owner: Brush's Reedline configuration leaves partial completions disabled and
exposes no setting to enable them. Impact: users must type the shared suffix
themselves. Workaround: cancel and type the complete command, or use the candidate
menu. Task 27 verifies candidate display separately.

Ignored acceptance: `task_28_command_common_prefix` in [audit.rs](../tests/audit.rs).

### C32: Enter after unmatched filename completion

Reference: Readline completion behavior linked under C25.
In an empty directory, start default `shish -i`, type
`/bin/echo shish_missing_filename`, Tab, then Enter. Expected: the unchanged
argument is printed, followed by a new prompt. Observed: the input remains visible
without execution; the acceptance test times out waiting for the output.

Owner: the same Brush/Reedline empty-menu handling as C25. Impact: filename
completion adds an extra submission step. Workaround: cancel with Ctrl-C and
retype the full command without Tab. Ignored acceptance:
`task_32_missing_file_completion` in [audit.rs](../tests/audit.rs).

### C34: filename completion does not insert the common prefix

Reference: Readline completion behavior linked under C28.
Create files `shared_one` and `shared_two`. In default `shish -i`, type
`/bin/cat sha` and Tab. Expected input: `/bin/cat shared_`. Observed input:
`/bin/cat sha`, with both filenames listed.

Owner: Brush's disabled Reedline partial-completion setting (C28). Impact: the
shared filename suffix must be entered manually. Workaround: cancel and type the
full filename without Tab. Ignored acceptance: `task_34_file_common_prefix` in
[audit.rs](../tests/audit.rs).

### C40: Enter after an empty programmable-completion result

Reference:
[Bash programmable completion](https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion.html).
In `shish --bash -i`, register
`_pick() { COMPREPLY=(); }; pick() { printf '<%s>\n' "$1"; }; complete -F _pick pick`.
Type `pick untouched`, Tab, then Enter. Expected: `<untouched>` and a new prompt.
Observed: the unchanged input remains visible without execution.

Owner: Brush/Reedline empty-menu handling (C25); the empty result itself is
preserved. Impact: a completer returning no candidates impedes command submission.
Workaround: cancel and retype the command without Tab. Ignored acceptance:
`task_40_empty_programmed_completion` in [audit.rs](../tests/audit.rs).

### C44: programmable completion does not insert the longest common prefix

Reference: Bash/Readline completion references above.
In `shish --bash -i`, run `complete -W 'prefix_one prefix_two' pick`, then type
`pick pre` and Tab. Expected input: `pick prefix_`. Observed input:
`pick pre`, with both programmed candidates listed.

Owner: Brush's disabled Reedline partial-completion setting (C28). Impact: users
must enter the shared suffix themselves. Workaround: cancel and type the full
argument without Tab. Ignored acceptance: `task_44_programmed_common_prefix` in
[audit.rs](../tests/audit.rs).

### J54: job numbers collide after selective reaping

Reference: POSIX §2.11 job-control job IDs must identify jobs unambiguously.
Reproduced with the recorded default interactive sh mode on Darwin:
launch two workers blocked on separate release files, release and `wait %1`,
then launch a third worker while job 2 is still running.

Expected two distinct active job IDs. Observed two entries numbered `[2]`,
one for the surviving worker and one for the new worker. A subsequent jobspec can
select the wrong job. Owner: Brush's job manager assigns `jobs.len() + 1` rather
than an unused ID. Reusing 1 after the entire table is empty works separately.
Workaround: avoid launching additional jobs while a partially reaped table still
contains active jobs; use an external supervisor for reliable job identity.

Acceptance: `task_54_job_number_recycling` in [audit.rs](../tests/audit.rs)
is ignored after reproducing the collision.

### H68: exit persistence ignores overwrite mode

Reference: [Bash history facilities](https://www.gnu.org/software/bash/manual/html_node/Bash-History-Facilities.html),
`histappend` unset means overwrite. In the recorded Darwin/Brush environment with
`--bash -i`, start with `obsolete\n` in HISTFILE, then run:

```sh
shopt -u histappend; history -c; history -s replacement; exit 0
```

Expected `replacement\n`; observed `obsolete\nreplacement\n`. Fresh-file saving
works, but cleared entries remain on disk. Owner: Brush core's exit-history save
always appends dirty entries; the interactive loop invokes it internally regardless
of the option. Workaround: explicitly run `history -w && unset HISTFILE` before exit
when replacement is required. This also disables the later automatic save.

Acceptance: `task_68_exit_history_overwrite` in [audit.rs](../tests/audit.rs),
ignored after reproducing the failure; fresh-file saving has a passing test.
