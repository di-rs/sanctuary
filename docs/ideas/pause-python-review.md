# Pause a private Python review between shifts

An analyst reviewing telescope detections flags the first candidate for a
second look. At the end of the shift, their flag and their place in the list
live in a Python interpreter. A proposed **Pause until tomorrow** action
in Boxie, Sanctuary's private sandbox runtime, would free their slot for
a colleague. On their next shift, **Resume** would reopen the interpreter
at the next candidate.

The researchers who built Elsa estimated costs with machines running 15%
of the time, based on the usage they observed. Their JupyterHub pause
button released the machine and later restored the user's running notebook
server. E2B preserves process memory across a pause, and its Embed team
has tested pause and resume on a single Linux host with hardware
virtualization (KVM). A lab can try that experience before investing in
a Boxie integration.
[Elsa study](https://arxiv.org/html/2101.05782),
[E2B sandbox persistence](https://docs.e2b.dev/sandbox/persistence) and
[E2B Embed host requirements](https://github.com/e2b-dev/runtime/blob/9d24b56b23dc12eeaa1807ec02ac92f18168316e/embed/compose/README.md#requirements)

## What has to survive the night?

Start `python3 -q` in an empty writable directory. This review has three
synthetic candidate IDs and one decision made at the prompt.

```python
from pathlib import Path

targets = Path("targets.txt")
targets.write_bytes(b"A-17\nB-04\nC-22\n")
source = targets.open(encoding="ascii")
flags = {next(source).strip(): "recheck"}
print(source.buffer.tell(), targets.stat().st_size)
```

CPython 3.12.16 printed `15 15`. After reading just one ID, the text
reader had fetched all 15 bytes from the underlying stream. Seeking to
that byte position in a new interpreter skipped both remaining candidates.
To try a runtime that supports pause, save the session at this prompt.
After the runtime has released the compute slot, resume and run this line.

```python
print(next(source).strip(), flags["A-17"])
```

| What the analyst kept | Result in the local trial |
| --- | --- |
| A byte-for-byte copy of the input file | A fresh interpreter started at `A-17`. The flag was gone. |
| The input and a 122-byte JSON record containing its SHA-256 digest, the number of rows reviewed and the flags | Checking the digest and skipping one row recovered `B-04 recheck`. Reordering the last two rows caused a digest mismatch. |
| A QEMU snapshot of the running Linux guest | After the original emulator exited, a new process restored the open reader and printed `B-04 recheck`. Loading the same snapshot again returned `B-04` a second time. |

QEMU 11.1.3 on macOS reported 220 MiB of saved machine state for this
512 MiB Linux guest, including its memory-backed filesystem. The review
record held everything the analyst needed in this example. Ask what else a
lab would have to reconstruct, such as an array the analyst had calibrated
by hand. [QEMU VM snapshots](https://www.qemu.org/docs/master/system/images.html#vm-snapshots)

## Can Boxie give the slot to someone else?

Today a Boxie terminal can reconnect to a surviving process. By default,
cleanup starts after two minutes disconnected, and Boxie releases the slot
when Docker confirms deletion. The Docker restore path documented by gVisor
expects the original container to exist. The gVisor runtime, `runsc`, can
restore into a new container directly. On native Linux, test whether
Boxie's supervisor can reconnect a terminal to the open Python reader,
enforce the original isolation profile and remove the restored container
when the review ends.
[Boxie sandbox lifetime](../../packages/boxie/docs/execution.md#deadlines-and-shutdown)
and [gVisor checkpoint and restore](https://gvisor.dev/docs/user_guide/checkpoint_restore/)

For the pilot, use one host and an operator-approved Bash and Python
image. The private app would let only the analyst who saved a session
reopen it. Boxie would check the consumer's disk budget, encrypt the
snapshot on the host and retain the exact image and input artifact for a
24-hour restore window. Show **Paused** once the saved state is complete
and the old execution has released its slot. Resume would reserve a slot
with the remaining execution time. If the host is full, show the expiry
time and let the analyst retry. Repeated requests to resume a checkpoint
would return the same execution.

## When would a lab adopt it?

Ask two research groups with shared private hosts to bring reviews they
have interrupted. At each lab, try a small review file and an E2B Embed
memory snapshot on comparable lists. Reverse the order for the second
lab. Count hands-on minutes spent saving state and returning to the first
unreviewed candidate with all prior flags and needed arrays intact.

Pursue native Boxie support if both labs recover every decision within
their disk budgets, another analyst uses the slot during each pause and
each lab saves at least five hands-on minutes per return. Ask an operator
who meets those targets to bring a second workload they would move to
their existing Boxie host. Where the review file is sufficient, the lab
can use it with its current Python installation.
