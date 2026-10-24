# Shish durability and recovery limits

Shish runs commands in a local shell process. It does not checkpoint commands,
restore interrupted processes, or retry work automatically. It runs with the
caller's privileges and provides no sandbox isolation.

## Shell state and persistence

| State | Current behavior |
| --- | --- |
| Variables, functions, aliases, options, and working directory | Held in shell memory; not restored after the shell exits or crashes. |
| Foreground and background jobs | No process restoration or durable job identity. The job table is shell state, not a recovery record. |
| Files | Written through ordinary filesystem operations. Their survival depends on the filesystem, storage, and program's write behavior; shish adds no transaction or durability guarantee. |
| Terminal output | Written to the terminal or redirected destination. Shish does not maintain a durable output store or replay buffer. |
| Command history | Plaintext command entries can be saved and loaded, but do not capture process state or prove whether a command completed. |

History loading does not execute saved entries. Explicit history writes and
appends are supported in Bash mode; automatic exit saving currently appends even
when `histappend` is unset. See [interactive history](../README.md#interactive-history)
for usage and the [overwrite limitation](compatibility-gaps.md#h68-exit-persistence-ignores-overwrite-mode).
History can contain command-line secrets and needs a private location.

## Interrupted commands

Reconnecting to a surviving process, restarting a command, and resuming from a
checkpoint are different operations. Shish does not provide a reconnect service
or checkpoint protocol. Running a command again starts a new execution with the
inputs and environment available at that time.

A command may change files or external systems before its exit status is lost.
For example, rerunning `printf x >> file` after an uncertain result may append
twice. Shell history and terminal output are not completion receipts. Inspect
the command's effects before deciding whether to rerun it.

## Boxie's boundary

Boxie currently runs Bash through operator-approved sandbox profiles; shish is
not included in those profiles. Boxie's lifecycle recovery does not give local
shish sessions additional guarantees.

Boxie separates its API from the supervisor that owns terminal processes.
An API restart can leave a process running, and clients can reconnect while the
execution survives and its deadlines permit. Terminal replay is bounded output
replay, not a saved screen, process memory, or replay of terminal input.
A supervisor restart can end terminals; lifecycle reconciliation handles resource
cleanup rather than restoring shell variables or command progress.

Boxie's writable `/workspace` and `/tmp` are ephemeral tmpfs mounts. Container
loss does not preserve those files. Temporal coordinates lifecycle work and
cleanup retries; it does not checkpoint the shell or make arbitrary command
side effects safe to repeat. No cross-host process recovery is promised.

See Boxie's [execution and recovery contract](../../boxie/docs/execution.md) for
resource limits and lifecycle behavior, and its
[terminal API](../../boxie/docs/consumer-api.md#connect-a-terminal) for reconnect
and replay semantics.
