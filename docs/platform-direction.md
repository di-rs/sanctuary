# Sanctuary platform direction

Sanctuary is being built as a platform for executing durable shell sandboxes.
Its runtime, shell, and consumer services have distinct responsibilities, so new
applications can use the platform without inheriting the CLI playground's product
model.

## Platform responsibilities

Boxie is the platform runtime. It owns sandbox execution and isolation. Shish
is a shell application in this repository. It embeds Brush for local shell
execution.

Separate applications and services will manage consumer accounts, consumer API
tokens, and environment setup. Their names, interfaces, and deployment boundaries
are not settled. Runtime enforcement will still need to honor the consumer and
execution policies established through those services.

CLI playground is an internal tool and Sanctuary's first consumer. Its job is to
let people try repository commands in a browser. As the platform develops, it
will use the same consumer boundary as other applications rather than determine
Sanctuary's runtime or account model.

## Where the implementation stands

Today, Boxie exposes a private consumer API and runs bounded Bash sandboxes.
Temporal workers in its supervisor coordinate provisioning and cleanup; they do
not make shell processes or terminal sessions resumable after a supervisor restart.
The playground connects directly to that API, uploads preview binaries, and owns
its own preview and browser-session metadata.

The [current architecture](architecture.md) describes these implemented boundaries.
The target platform does not change today's operating requirements or imply that
the planned management services are available.

## Compatibility and product priorities

The platform's goal is isolated shell workloads with explicit, tested recovery
guarantees. Four contracts contribute to that goal:

| Contract | Responsibility |
| --- | --- |
| Shell compatibility | Predictable arguments, quoting, expansion, pipelines, redirection, and exit statuses |
| Sandbox isolation | Enforced filesystem, network, process, resource, and ownership boundaries |
| Execution durability | Defined outcomes after disconnects, crashes, cancellation, and retries |
| Interactive experience | Prompts, completion, history, and job controls |

POSIX is a compatibility reference for the shell. Full conformance is not a
prerequisite for platform delivery. Prioritize correct common shell operations and
clear recovery semantics. Interactive features and compatibility edge cases are
not all platform release gates.

Shish embeds Brush and tracks the behavior verified through shish itself. Parser and runtime integration stay inside the shish package
until another component needs a shared API. Selecting a library or enabling its
POSIX mode does not establish conformance.

Shish's [compatibility reference](../packages/shish/docs/compatibility.md) records
the detailed compatibility inventory.
Record verified, partial, missing, and unverified behavior against the tested
library version, shell mode, and platform. For a gap, retain the applicable
standard section, a reproducer, expected and observed results, its cause and user
impact, any workaround, and test links. Track Bash extensions
separately. Upstream-reported limitations require reproduction before they become
confirmed shish defects.

Shell compatibility alone makes no operating-system-wide or complete utility-conformance
claim.

## Shell recovery limits

Shish runs locally; Boxie's approved sandbox profiles run Bash. Boxie's Temporal
workers coordinate sandbox lifecycle operations, not durable shell commands.
Restarting the supervisor ends terminal processes. Reconnecting to a surviving
process does not restore a lost process or its shell state.

Shell history and syntax trees do not provide execution checkpoints. A command
can change files or external systems before its result is lost; rerunning it can
repeat those effects. See Boxie's [execution and recovery contract](../packages/boxie/docs/execution.md)
for its current guarantees.

The [shish durability plan](../packages/shish/docs/durability.md) covers the
unimplemented Boxie integration and explicit durable jobs, including persistence,
retry policy, cancellation, and staged acceptance criteria.
