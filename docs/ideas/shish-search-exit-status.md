# Tell an empty search from an incomplete count in Shish

An operator is trying Sanctuary's `grepr` in a runbook that uses `grep`
to count rejected parcels. Each parcel has one line in its depot's log.
Before reporting zero rejections at shift handoff, the operator needs to
know that the search read both depots' logs. Shish, Sanctuary's local
shell, could put `grepr 1 (input error) | wc 0` below the count.

A GitPython user fixed a quoting error and still saw the same exception
whenever `git grep` found no matches. A Starship user asked to see
individual exit codes at the prompt even when the pipeline succeeded.
[GitPython user's report](https://github.com/gitpython-developers/GitPython/discussions/1164)
and [Starship prompt request](https://github.com/starship/starship/issues/193)

## Reproduce the two zero counts

In an empty directory with `shish`, `grepr`, system `grep` and `wc` on
your path, start a session with a prompt that shows each command's exit
code from left to right, followed by the shell's overall status.
[Shish invocation](../../packages/shish/README.md#invocation)

```sh
PS1='stages=(${PIPESTATUS[*]}) shell=$? > ' shish --bash
```

Enter these lines in that session. The west log arrives between searches.

```sh
printf 'ACCEPT parcel-01\n' > east.log
grepr '^REJECT ' east.log west.log | wc -l
printf 'ACCEPT parcel-02\n' > west.log
grep '^REJECT ' east.log west.log | wc -l
```

On macOS both pipelines printed `0` and left `stages=(1 0) shell=0` at
the prompt. Enabling `set -o pipefail` changed both overall statuses to
`1`. System `grep` uses `1` for a complete search with no matches.
`grepr` exits zero for that case and can return `1` after reading only
the available files.
[Search behavior](../../buildins/grepr/README.md#before-using-it)
and [reference fixtures](../../buildins/grepr/tests/cases.toml)

| Search and inputs | Count | Handoff |
| --- | --- | --- |
| `grepr`, west log missing | 0 | Request `west.log`, the file named on stderr. |
| System `grep`, both logs present | 0 | Report zero rejections across the two logs. |
| `grepr`, east has one rejection and west is missing | 1 | Report the east rejection and leave the total open. |

## Add the meaning beside the code

Starship 1.26.0 in Bash also showed `1,0` for both searches with its
numeric pipeline display enabled. A local test driver matched each
runbook command and its executable's checksum. It interpreted exit `1`
as **input error** for `grepr` and **no matches** for `grep`.
A wrapper named `grep` called `grepr`. Its checksum was unfamiliar, so
the driver kept the raw codes. A rule keyed to the name would have
described the missing log as an empty search.
[Starship status settings](https://starship.rs/config/#status)

For a first pilot, annotate these two searches piped directly to `wc -l`
in an interactive `shish --bash` session. Have Shish capture both exit
codes before the next command replaces them. Add a label when Brush,
Shish's shell engine, selected a build verified for that command. Render
the label in the prompt so a file receiving the count contains just the
command output.
[Shish execution flow](../../packages/shish/docs/architecture.md#execution-flow)

## Would this help at shift handoff?

Ask four operators who maintain shell runbooks to review two equivalent
sets of logs. Give them the proposed Shish labels for one set and Bash
with Starship's numeric display for the other. Alternate which tool each
operator tries first. Keep stderr and the runbook note available in both.
Include the three cases above and the wrapper named `grep`.

Record which totals each operator would send, which file they would
request and whether they consulted the note or reran a search. Build
the annotation if all four report the complete zero and withhold every
incomplete total, and at least three avoid a lookup or rerun they needed
with Starship. If the runbook note does as well, keep the note.
