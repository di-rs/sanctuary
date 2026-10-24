# Shish compatibility

Shish defaults to sh/POSIX settings but does not claim full conformance.
This reference covers shell language and shell builtins against
[POSIX.1-2024](https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html).
It does not claim operating-system-wide or complete utility conformance.

- [Evidence and environments](#reading-the-evidence)
- [POSIX coverage](#posix-scope-audit)
- [POSIX gaps](compatibility-gaps.md#confirmed-posix-gaps)
- [Input and command lookup gaps](compatibility-gaps.md#input-and-command-lookup-gaps)
- [Interactive gaps](compatibility-gaps.md#interactive-compatibility-gaps)
- [Feature coverage](#feature-coverage)

## Reading the evidence

- **Verified** means the linked cases passed in the recorded environment; it does
  not mean every variation of that feature works.
- **Partial** means tested cases work but a reproduced gap remains in the area.
- **Missing** means the specified behavior was attempted and did not work.
- **Unverified** means no adequate shish evidence has been recorded. An upstream
  claim, parser acceptance, or absence of a reported failure is not verification.

The initial audit ran on 2026-10-22 on Darwin 27.0.0 arm64 in default sh/POSIX
mode. For dependency versions, consult [Cargo.lock](../../../Cargo.lock) at the
audited revision. Commands used `-c` unless otherwise stated.
PTY cases use `-i`, a 120-column terminal, and an isolated temporary home. Linux,
gVisor, other locales, and other architectures remain unverified by this local run.
The Rust tests and doctests also passed on Ubuntu 24.04 and macOS 15 in
[run 39836059386](https://github.com/di-rs/sanctuary/actions/runs/39836059386).
This extends only the tested cases to those runners; it does not verify gVisor.

Independent reference checks used macOS `/bin/bash` 3.2.57(1)-release with
`--noprofile --norc --posix`, `LC_ALL=C`, `PATH=/usr/bin:/bin`, and a temporary HOME.
Bash is a comparison implementation, not the standard; its differences and
unspecified behavior do not automatically become requirements. New 2024-only
requirements need specification-derived expectations or another suitable reference.
Expected bytes are written from the specification/reference, never regenerated
from shish. Explicit `--bash` uses the same dependency versions; mode-selection,
parse-only, registry, and conflict tests are in [audit.rs](../tests/audit.rs).
This does not verify the entire Bash feature set. External utility output depends
on the image's tools: Brush's default
sh registry does not include `echo` or `printf`, so those names currently use PATH.

See [audit tests](../tests/audit.rs), [invocation tests](../tests/runtime.rs), and
[utility tests](../tests/builtins.rs). The
[test guide](testing.md) explains reproducibility and the terminal driver.

The feature table records 76 cases: 68 verified, five partial, and three missing.
The audit suite has 13 ignored acceptance cases: five POSIX cases and eight
interactive cases. P05 is a separately tested startup policy. Two additional
ignored CLI cases cover [multiline input and PATH lookup](compatibility-gaps.md#input-and-command-lookup-gaps).

## POSIX scope audit

Sections below refer to the shell language in POSIX.1-2024; named utilities also
have their own utility reference pages. Each broad area retains untested edges.

| Area | Reference | Initial evidence and remaining scope |
| --- | --- | --- |
| Quoting | §2.2 | Verified cases include unterminated quotes and the quote/escape boundaries in tasks 13–18; full locale and nesting combinations remain unverified. |
| Parameters and expansion | §2.5–2.6 | Quoted `$@`, command-substitution newline removal, arithmetic, and dollar-single-quotes manually matched reference. P03 affects `$!`; full parameter operator matrix unverified. |
| Field splitting | §2.6.5 | Partial; P01 reproduces loss of empty non-whitespace IFS fields. |
| Pathname expansion | §2.6.6 | Unverified: glob sorting, locale, dotfiles, and unmatched patterns need separate cases. |
| Lookup and statuses | §2.8, §2.9.1 | Verified missing command 127, nonexecutable 126, parse error 2, and ordinary status propagation. Function/builtin/PATH precedence and caching need broader coverage. |
| Pipelines | §2.9.2 | Tasks 55–57 verify two/multiple commands, builtins, output, and final status. Negation and pipefail matrix unverified. |
| Redirections and here-documents | §2.7 | Verified failure has no output/file effect; quoted/unquoted here-doc delimiters. Descriptor ordering manually matched. Descriptor closing, tab stripping, noclobber, and mixed redirections unverified. |
| Assignments and special builtins | §2.9.1, §2.15 | Partial; P02 affects assignment persistence. Readonly assignment failure aborts execution, with implementation-specific nonzero status. Full special-builtin error/lookup matrix unverified. |
| Control flow | §2.9.3–2.9.4 | Verified for/case/continue sample. Nested loops, break levels, until/while, and error propagation unverified. |
| Functions | §2.9.5 | Verified argument scope in one function case; recursion, return, traps, and lookup interactions unverified. |
| Subshells/environment | §2.13 | Verified variable isolation in parentheses. File descriptors, traps, and background environment edges unverified. |
| Traps/signals | §2.12, `trap` | Partial: EXIT handler/status verified; P04 reproduces missing TERM handling. Other signal traps remain unverified. |
| Asynchronous jobs | §2.9.3, §2.11, `jobs`, `wait` | Tasks 46–53 verify interactive launch, output, listing, and reaping. P03 breaks PID tracking and J54 reproduces duplicate active IDs. Wait error/status and advanced jobspec options need broader coverage. |
| Terminal ownership | §2.11 | Verified foreground Ctrl-C returns control and status 130 in a PTY. Stop/continue, fg/bg, and terminal resize remain unverified. |
| Invocation/startup | `sh` | Verified -c/script/-s/-n arguments and EOF. P05 records intentionally skipped ENV startup. Login/interactive option combinations need more coverage. |
| Builtin requirements | §2.15 and individual utilities | true/false status/argument contract verified. Complete required-builtin option, error, and environment matrices remain unverified. |

These are bounded checks, not a conformance suite. Upstream's
[compatibility reference](https://github.com/reubeno/brush/blob/main/docs/reference/compatibility.md)
provides audit candidates, not confirmed shish defects. `select`, `wait -n`,
`disown`, advanced key bindings, and other Bash-specific gaps need reproduction
in explicit Bash mode and stay outside the POSIX gap count.

## Feature coverage

The numbers match the `task_NN` tests in [audit.rs](../tests/audit.rs).
Verified rows cover only the named cases. `complete`, `history`, and `declare`
require Bash mode; completion UI and prompt appearance are product behavior.

| Task | Area and behavior | Mode/reference | Status and evidence |
| --- | --- | --- | --- |
| 01 | Basics: prompt | sh; invocation/§2.9.1 | Verified: home/directory prompt, PS1, no noninteractive prompt; [task_01](../tests/audit.rs) |
| 02 | Basics: invalid commands | sh; invocation/§2.9.1 | Verified: status 127, diagnostic, and continued stdin execution; [task_02](../tests/audit.rs) |
| 03 | Basics: REPL | sh; invocation/§2.9.1 | Verified: multiline interactive loop and persistent variables; [task_03](../tests/audit.rs) |
| 04 | Basics: exit | sh; invocation/§2.9.1 | Verified: exit stops later commands and inherits the last status; [task_04](../tests/audit.rs) |
| 05 | Basics: echo | sh; invocation/§2.9.1 | Verified: ordinary echo in sh/PATH and Bash builtin modes; option extensions excluded; [task_05](../tests/audit.rs) |
| 06 | Basics: type | sh; invocation/§2.9.1 | Verified: builtin/external type and function type via -t extension; missing type diagnostic. P06 tracks command -v separately; [task_06](../tests/audit.rs) |
| 07 | Basics: executable lookup | sh; invocation/§2.9.1 | Verified: custom PATH, executable permission, and missing lookup; [task_07](../tests/audit.rs) |
| 08 | Basics: program execution | sh; invocation/§2.9.1 | Verified: argv boundaries, stdout/stderr, and external status; [task_08](../tests/audit.rs) |
| 09 | Navigation: pwd | sh; pwd/cd | Verified: initial and changed working directories; [task_09](../tests/audit.rs) |
| 10 | Navigation: absolute cd | sh; pwd/cd | Verified: absolute cd updates shell cwd while host test cwd is unchanged; [task_10](../tests/audit.rs) |
| 11 | Navigation: relative cd | sh; pwd/cd | Verified: relative paths and parent traversal; [task_11](../tests/audit.rs) |
| 12 | Navigation: home-directory cd | sh; pwd/cd | Verified: cd without operands and tilde expansion; [task_12](../tests/audit.rs) |
| 13 | Quoting: single quotes | sh; §2.2 | Verified: single quotes retain whitespace, empty words, metacharacters, and joined quote segments; [task_13](../tests/audit.rs) |
| 14 | Quoting: double quotes | sh; §2.2 | Verified: double quotes preserve whitespace and empty expansions without globbing; [task_14](../tests/audit.rs) |
| 15 | Quoting: unquoted backslashes | sh; §2.2 | Verified: escaped spaces and metacharacters, plus backslash-newline joining; [task_15](../tests/audit.rs) |
| 16 | Quoting: backslashes in single quotes | sh; §2.2 | Verified: backslashes remain literal inside single quotes; [task_16](../tests/audit.rs) |
| 17 | Quoting: backslashes in double quotes | sh; §2.2 | Verified: double-quote escape rules preserve unknown escapes and remove continued newlines; [task_17](../tests/audit.rs) |
| 18 | Quoting: quoted executables | sh; §2.2 | Verified: executable paths containing spaces retain argument boundaries; [task_18](../tests/audit.rs) |
| 19 | Redirection: stdout | sh; §2.7 | Verified: exact file contents, unaffected output stream, and success status; [task_19](../tests/audit.rs) |
| 20 | Redirection: stderr | sh; §2.7 | Verified: exact file contents, unaffected output stream, and success status; [task_20](../tests/audit.rs) |
| 21 | Redirection: append stdout | sh; §2.7 | Verified: exact file contents, unaffected output stream, and success status; [task_21](../tests/audit.rs) |
| 22 | Redirection: append stderr | sh; §2.7 | Verified: exact file contents, unaffected output stream, and success status; [task_22](../tests/audit.rs) |
| 23 | Command completion: builtins | interactive; product UI | Verified: bounded PTY Tab interaction with isolated PATH; [task_23](../tests/audit.rs) |
| 24 | Command completion: arguments | interactive; product UI | Verified: bounded PTY Tab interaction with isolated PATH; [task_24](../tests/audit.rs) |
| 25 | Command completion: no matches | interactive; product UI | Partial: unmatched input is preserved and cancellation works; Enter handling remains missing (C25); [task_25](../tests/audit.rs) |
| 26 | Command completion: executables | interactive; product UI | Verified: custom PATH executable is completed and executed; [task_26](../tests/audit.rs) |
| 27 | Command completion: multiple matches | interactive; product UI | Verified: completion menu lists both executable candidates and can be cancelled; [task_27](../tests/audit.rs) |
| 28 | Command completion: partial matches | interactive; product UI | Missing: multiple candidates are listed but the common prefix is not inserted (C28); [task_28](../tests/audit.rs) |
| 29 | Filename completion: files | interactive; product UI | Verified: a completed filename containing a space opens the intended file; [task_29](../tests/audit.rs) |
| 30 | Filename completion: nested files | interactive; product UI | Verified: directory continuation and a nested file are completed and opened; [task_30](../tests/audit.rs) |
| 31 | Filename completion: directories | interactive; product UI | Verified: completion appends a directory separator and cd enters the result; [task_31](../tests/audit.rs) |
| 32 | Filename completion: no matches | interactive; product UI | Partial: unmatched filename is preserved; first Enter is consumed by the empty menu (C32); [task_32](../tests/audit.rs) |
| 33 | Filename completion: multiple matches | interactive; product UI | Verified: both filename candidates appear in the completion menu; [task_33](../tests/audit.rs) |
| 34 | Filename completion: partial matches | interactive; product UI | Missing: filename candidates are displayed without insertion of their common prefix (C34); [task_34](../tests/audit.rs) |
| 35 | Filename completion: multiple arguments | interactive; product UI | Verified: completing the next argument preserves an already completed filename; [task_35](../tests/audit.rs) |
| 36 | Programmable completion: registration | bash; Bash §8.6–8.7 | Verified: Bash-mode specification state, exact output/diagnostic, and status; diagnostic wording is Brush-specific; [task_36](../tests/audit.rs) |
| 37 | Programmable completion: missing specifications | bash; Bash §8.6–8.7 | Verified: Bash-mode specification state, exact output/diagnostic, and status; diagnostic wording is Brush-specific; [task_37](../tests/audit.rs) |
| 38 | Programmable completion: display specifications | bash; Bash §8.6–8.7 | Verified: Bash-mode specification state, exact output/diagnostic, and status; diagnostic wording is Brush-specific; [task_38](../tests/audit.rs) |
| 39 | Programmable completion: single candidate | bash; Bash §8.6–8.7 | Verified: COMPREPLY supplies one candidate that is completed and passed to the command; [task_39](../tests/audit.rs) |
| 40 | Programmable completion: no candidates | bash; Bash §8.6–8.7 | Partial: empty COMPREPLY leaves input unchanged; Enter handling remains missing (C40); [task_40](../tests/audit.rs) |
| 41 | Programmable completion: command-line arguments | bash; Bash §8.6–8.7 | Verified: completer receives command name, current word, and previous word in Bash mode; [task_41](../tests/audit.rs) |
| 42 | Programmable completion: environment variables | bash; Bash §8.6–8.7 | Verified: external completer receives COMP_LINE, COMP_POINT, and exported environment; [task_42](../tests/audit.rs) |
| 43 | Programmable completion: multiple candidates | bash; Bash §8.6–8.7 | Verified: registered word-list candidates appear in the terminal menu; [task_43](../tests/audit.rs) |
| 44 | Programmable completion: longest common prefix | bash; Bash §8.6–8.7 | Missing: programmed candidates are listed without inserting their longest common prefix (C44); [task_44](../tests/audit.rs) |
| 45 | Programmable completion: unregistration | bash; Bash §8.6–8.7 | Verified: Bash-mode specification state, exact output/diagnostic, and status; diagnostic wording is Brush-specific; [task_45](../tests/audit.rs) |
| 46 | Background jobs: jobs | interactive sh; §2.11/jobs/wait | Verified: empty job table, builtin lookup, status and streams; [task_46](../tests/audit.rs) |
| 47 | Background jobs: launch | interactive sh; §2.11/jobs/wait | Verified: prompt returns while a background worker awaits release; [task_47](../tests/audit.rs) |
| 48 | Background jobs: output | interactive sh; §2.11/jobs/wait | Verified: background stdout and stderr reach the terminal; [task_48](../tests/audit.rs) |
| 49 | Background jobs: list one | interactive sh; §2.11/jobs/wait | Verified: one active job lists its number, state, and command; [task_49](../tests/audit.rs) |
| 50 | Background jobs: list multiple | interactive sh; §2.11/jobs/wait | Verified: two active jobs have distinct IDs and current/previous annotations; [task_50](../tests/audit.rs) |
| 51 | Background jobs: reap one | interactive sh; §2.11/jobs/wait | Verified: wait %1 completes the worker and removes it before the next command; [task_51](../tests/audit.rs) |
| 52 | Background jobs: reap multiple | interactive sh; §2.11/jobs/wait | Verified: bare wait completes both workers and clears the job table; [task_52](../tests/audit.rs) |
| 53 | Background jobs: reap before prompt | interactive sh; §2.11/jobs/wait | Verified: completion notice and job removal before the next command; [task_53](../tests/audit.rs) |
| 54 | Background jobs: recycle job numbers | interactive sh; §2.11/jobs/wait | Partial: empty-table recycling works; J54 reproduces duplicate live IDs; [task_54](../tests/audit.rs) |
| 55 | Pipelines: two commands | sh; §2.9.2 | Verified: pipeline output, final status, and bounded fixture execution; [task_55](../tests/audit.rs) |
| 56 | Pipelines: builtins | sh; §2.9.2 | Verified: pipeline output, final status, and bounded fixture execution; [task_56](../tests/audit.rs) |
| 57 | Pipelines: multiple commands | sh; §2.9.2 | Verified: pipeline output, final status, and bounded fixture execution; [task_57](../tests/audit.rs) |
| 58 | History: builtin | bash; Bash §9 | Verified in Bash mode: history remains available without PATH commands; [task_58](../tests/audit.rs) |
| 59 | History: listing | bash; Bash §9 | Verified in Bash mode: numbered history listing preserves command order; [task_59](../tests/audit.rs) |
| 60 | History: entry limits | bash; Bash §9 | Verified in Bash mode: history 0, 1, and oversized counts preserve status and numbering; [task_60](../tests/audit.rs) |
| 61 | History: up-arrow | bash; Bash §9 | Verified in Bash mode: up-arrow recalls the preceding command; [task_61](../tests/audit.rs) |
| 62 | History: down-arrow | bash; Bash §9 | Verified in Bash mode: down-arrow advances from older to newer history and returns to an empty line; [task_62](../tests/audit.rs) |
| 63 | History: recalled execution | bash; Bash §9 | Verified in Bash mode: recalling and submitting repeats the command's filesystem effect; [task_63](../tests/audit.rs) |
| 64 | History persistence: read file | bash; Bash §9 | Verified in Bash mode: explicit and default history files load without executing entries; [task_64](../tests/audit.rs) |
| 65 | History persistence: write file | bash; Bash §9 | Verified in Bash mode: history -w replaces explicit/default files after cd; [task_65](../tests/audit.rs) |
| 66 | History persistence: append file | bash; Bash §9 | Verified in Bash mode: history -a preserves existing contents and appends each new entry once; [task_66](../tests/audit.rs) |
| 67 | History persistence: startup read | bash; Bash §9 | Verified in Bash mode: HISTFILE loads before the first command without executing entries; [task_67](../tests/audit.rs) |
| 68 | History persistence: exit write | bash; Bash §9 | Partial: fresh-file exit persistence verified; H68 reproduces ignored overwrite mode; [task_68](../tests/audit.rs) |
| 69 | History persistence: exit append | bash; Bash §9 | Verified in Bash mode: exit appends unsaved entries without duplicating an earlier history -a; [task_69](../tests/audit.rs) |
| 70 | Parameters: declare | bash declare; sh §2.5–2.6 | Verified: declare creates a shell variable (bash mode); [task_70](../tests/audit.rs) |
| 71 | Parameters: missing-variable diagnostics | bash declare; sh §2.5–2.6 | Verified: missing variable diagnostics (bash mode); [task_71](../tests/audit.rs) |
| 72 | Parameters: storage | sh; §2.5–2.6 | Verified: shell variable storage and export (sh mode); [task_72](../tests/audit.rs) |
| 73 | Parameters: name validation | bash declare; sh §2.5–2.6 | Verified: invalid declaration names are rejected (bash mode); [task_73](../tests/audit.rs) |
| 74 | Parameters: expansion | sh; §2.5–2.6 | Verified: quoted and unquoted variable expansion (sh mode); [task_74](../tests/audit.rs) |
| 75 | Parameters: braced expansion | sh; §2.5–2.6 | Verified: braced parameter boundaries and defaults (sh mode); [task_75](../tests/audit.rs) |
| 76 | Parameters: empty expansion | sh; §2.5–2.6 | Verified: empty quoted and unquoted parameters (sh mode); [task_76](../tests/audit.rs) |

Bash-extension references: [completion](https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion.html),
[completion builtins](https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion-Builtins.html),
[history](https://www.gnu.org/software/bash/manual/html_node/Bash-History-Facilities.html),
and [Bash builtins](https://www.gnu.org/software/bash/manual/html_node/Bash-Builtins.html).
