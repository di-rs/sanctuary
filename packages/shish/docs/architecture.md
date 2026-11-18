# Shish architecture

Shish is the shell application inside Sanctuary. It runs with the caller's
privileges; sandbox isolation and recovery belong to Boxie.
[Durability](durability.md) explains recovery limits and the proposed Boxie integration.

## Execution flow

The CLI selects command-string, script, stdin, or interactive execution. A private
syntax module handles `-n` without executing commands. The runtime adapter uses
Brush for parsing, expansion, command lookup, shell state, execution, and terminal
editing. Keeping that boundary in one package avoids a second evaluator or an API
that no other component needs yet.

Stdin is read without consuming data intended for `read` or external programs.
Interactive input uses a terminal editor. All execution paths preserve command
statuses and delegate shell exit handling to the runtime.

Explicit `--bash` selects Bash behavior for both syntax inspection and execution.
Sanctuary status builtins are available in either mode.

## History and builtins

A history adapter bounds display counts to available entries to prevent overflow.
History reads and writes resolve paths from the shell directory. Imports enforce
a size limit and never execute entries. Unknown history options are rejected
before file operations.
Appending saves only unsaved entries, so repeated appends do not duplicate them.

The `true` and `false` builtins call Sanctuary's utility libraries and return
status without terminating the shell. Their standalone CLIs own logging and
process termination.

## Dependencies and origin

Dependencies are recorded in the workspace lockfile. Shish carries a
[patch to Brush core 0.5.0](../vendor/brush-core/src/history.rs) at the single
file writer shared by explicit history commands, editor sync, and interactive
exit. Remove the local copy when a published release creates history files with
owner-only permissions.

Known limitations live in [known gaps](compatibility-gaps.md). Test evidence
lives in the [compatibility reference](compatibility.md). See the
[README](../README.md) for invocation, startup behavior, and compatibility.

The initial shell was imported from
[di-rs/shish](https://github.com/di-rs/shish/tree/46c41468d4105a238c439aa68b4ff0e3248a964e).
Its original evaluator and lookup of executables in repository build directories
have been replaced.
