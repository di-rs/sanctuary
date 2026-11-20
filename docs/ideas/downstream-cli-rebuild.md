# Check a CLI rebuild against a downstream script

A platform team is preparing a new build of jq. Its colleagues use jq to
extract order IDs from a supplier's export. The release reviewer needs to
know whether their script will still look up the right orders after the
update. Sanctuary could let the script owner supply a sample export and
expected IDs, then show the reviewer how the deployed and proposed
executables handle that sample on one machine.

## Why the script looks up the first order twice

A jq user reported getting the wrong digits from a plain `.id` lookup.
The jq 1.8 manual explains how a build option changes the handling of
numeric input. This example passes two invented order records to jq.
[Original jq issue](https://github.com/jqlang/jq/issues/369)
and [jq number handling](https://jqlang.org/manual/v1.8/#identity)

```sh
printf '%s\n' '{"id":9007199254740992}' '{"id":9007199254740993}' |
  jq -r .id
```

Two local macOS builds of jq 1.8.1 printed identical `--help` and
`--version` text. Both exited zero with empty stderr on all three inputs.
The script needs one line per order with the ID copied exactly.

| Input to each build | Default number handling | Built with `--disable-decnum` |
| --- | --- | --- |
| The two JSON numbers above | Both IDs in order | `9007199254740992` twice |
| The same IDs as JSON strings | Both IDs in order | Both IDs in order |
| Small JSON numbers `41` and `42` | `41`, then `42` | `41`, then `42` |

A team concerned only with this jq build option can use
`jq -en have_literal_numbers`. It exited 0 on the first build and 1 on
the second. [jq build features](https://jqlang.org/manual/v1.8/#have_literal_numbers)

## What the reviewer would get

Sanctuary's `cli-testing` checked both builds against the expected ID
lines in two runs. Today it accepts one candidate per comparison and
requires a `Cargo.toml` whose package name matches the suite's binary name.
A proposed standalone mode would read cases from the script owner's
repository and take paths to two trusted executables. Each case would
supply the arguments, stdin, expected stdout, stderr and exit status.
[Candidate comparison](../../tools/cli-testing/README.md#compare-a-built-candidate)
and [current suite requirements](../../tools/cli-testing/docs/testing.md#schema-1-reference)

The report would identify each executable by its SHA-256 digest and show
the first difference for each failed case. Here, the reviewer could hold the
rebuild and point to the changed digit on line two. If both builds produce
the same unexpected output, the reviewer could flag a pre-existing failure
for the script owner. A launch error would read **Could not run**. In the
local trial, the checker's JSON labeled both a wrong ID and a file
without execute permission `failed`.

## Decide whether to adopt the report

For changes to flags, Sanctuary's optional playground catalog compares a
pull request's declared interface with its merge base. Usage can flag a
removed option between two CLI specifications. Both jq builds accepted
the same command.
[Playground catalog comparison](../../tools/cli-playground/docs/previews.md#build-and-comparison-contract)
and [Usage spec comparison](https://usage.jdx.dev/cli/diff)

Scrut already runs shell examples written in Markdown. On the same three
cases, Scrut 0.5.1 passed the default jq build and showed the exact line
that changed on the second build. [Scrut's executable examples](https://facebookincubator.github.io/scrut/)

Ask two teams that distribute CLIs to bring a past break reported by a
script owner. Give two reviewers on each team the same deployed binary and
two rebuilds. One rebuild introduces the break. The other preserves the
script's output. Include a stale expectation that fails on all three.
One reviewer uses Scrut and can reuse the deployed result. The other uses
the proposed report. Count time to prepare the cases and to decide which
rebuild to hold. Try a CI integration if both teams identify the new and
pre-existing failures correctly, spend less total time with Sanctuary and
keep a case for their next release.
