# Check a JSON import against its worker's memory limit

A release engineer has 64 MiB of memory per worker for a nightly inventory
import. Each supplier record must produce one line, even an empty object
that the importer will flag for review. A proposed local check in Sanctuary's
`cli-bench` would show which filter finishes within that limit and where
its output first differs from what the importer expects.

A jq user reported that converting a roughly 1 GB JSON array to one object per
line took nearly 5 GB of RAM. They supplied a generator because they couldn't
share the input. A contributor suggested a streaming filter that worked on
the reporter's sample. [jq issue and streaming filter](https://github.com/jqlang/jq/issues/1897)

## Which filter keeps all 200,001 records?

A local trial used a JSON array with 200,000 synthetic inventory records and
one final `{}`. Each run used the same jq 1.8.2 image on Docker Desktop's
Linux arm64 VM with the `runc` runtime and swap disabled. The expected output
was the sequence of lines used to construct the array.

| Filter | Container memory | Exit | Observed output |
| --- | ---: | ---: | --- |
| Read the whole array with `.[]` | 512 MiB | 0 | All 200,001 lines matched byte for byte |
| Read the whole array with `.[]` | 64 MiB | 137 | No lines. Docker recorded an out-of-memory kill |
| Stream with the issue's `truncate_stream` filter | 64 MiB | 0 | 200,000 lines. The final `{}` was missing |
| Stream and preserve empty objects | 64 MiB | 0 | All 200,001 lines matched byte for byte |

jq represents an empty object as a value at its array index. The issue's
filter drops paths that contain only that index. The filter below removes
the index and passes the empty value on to the output. [jq streaming format](https://jqlang.org/manual/v1.8/#streaming)

To repeat the last row, start in an empty directory with Biggie installed
and the jq 1.8.2 image pulled into Docker for Linux containers. The check
runs offline. Matching Docker's memory and memory-plus-swap limits disables swap.
[Biggie record generator](../../packages/biggie/README.md#literal-records-records)
and [Docker memory limits](https://docs.docker.com/engine/containers/resource_constraints/#prevent-a-container-from-using-swap)

```sh
biggie records --record '{"sku":"A-17","stock":[2,4]}' --repeat 200000 - > expected.ndjson
printf '%s\n' '{}' >> expected.ndjson
{
  printf '[\n'
  paste -sd, expected.ndjson
  printf ']\n'
} > batch.json

docker run --rm -i --pull=never --network none --memory 64m --memory-swap 64m \
  ghcr.io/jqlang/jq:1.8.2 -cn --stream \
  'fromstream(inputs | select(.[0] != []) | .[0] |= .[1:])' \
  < batch.json > actual.ndjson && cmp expected.ndjson actual.ndjson
```

## What the release reviewer would see

`cli-bench` can generate input with Biggie and compare two commands'
stdout before timing them. On a two-record sample it caught the missing
empty object. The run that passed also recorded peak resident memory in the
hyperfine report. Today the engineer sets any worker memory limit outside
the suite. The proposed check would pair that limit with the import owner's
expected output in one repeatable case.
[Sanctuary benchmark cases](../../tools/cli-bench/README.md#suite-format)
and [hyperfine 2.0 measurements](https://github.com/sharkdp/hyperfine/releases/tag/v2.0.0)

The runner would feed the sample to the team's image and compare stdout
locally. It would record the image digest, CPU architecture, runtime and
the container's memory and swap limits. For the 64 MiB case, the Linux
control group reported `memory.max=67108864` and `memory.swap.max=0`. A runner
unable to verify those settings would report **Limit unverified**.

Before removing the container, the runner would read its exit status and
Docker's `OOMKilled` flag. In a control run, jq deliberately exited 137 and
the flag was false. A reviewer would see **Command failed** for that case
and **Out of memory** for the killed run. The filter that dropped the
final record would show **Missing line 200,001** beside the expected `{}`.

## Try it on a private Linux worker

Recruit two import teams with a fixed memory allowance and a past failure
they can recreate with invented records. A team can already script Docker
and `cmp`. On Linux, BenchExec's `runexec` can also enforce a memory limit
and report when that limit killed the command. Use whichever workflow the
team would otherwise maintain as the comparison. [BenchExec resource limits](https://github.com/sosy-lab/benchexec/blob/main/doc/runexec.md)
and [termination reasons](https://github.com/sosy-lab/benchexec/blob/main/doc/run-results.md)

Give each team two sets of import changes to review on its worker's
architecture and runtime. Include a correct conversion, a dropped record,
a memory kill and an unrelated exit 137 in each set. Have two reviewers
use different workflows on the first set, then swap workflows for the
second. Count hands-on minutes from preparing the sample to deciding which
change can ship. Package the check if both teams choose the correct
conversion, identify all three failures, save at least 25% of review time
including setup, and keep a case for their next release.
