# Test a log filter while its input is still open

A build watcher starts the next job when its log filter prints `READY 17`.
A release engineer upgrading the filter can replay yesterday's log and get
the right line even if it arrives too late to start the job. A proposed local
check in Sanctuary's `cli-testing` tool would tell the engineer whether the
watcher receives that line while the build is still running.

A ripgrep user following the Linux system journal reported that small updates
stopped appearing in 15.0.0 despite `--line-buffered`. The project fixed the
regression in 15.1.0. A Claude Code user separately reported missing merge
events for up to an hour when the assistant's shell selected a bundled filter.
For a release check, the team would need to exercise the command its watcher
actually launches, including any wrapper.
[ripgrep journal report](https://github.com/BurntSushi/ripgrep/issues/3194),
[15.1.0 release notes](https://github.com/BurntSushi/ripgrep/releases/tag/15.1.0)
and [merge watcher report](https://github.com/anthropics/claude-code/issues/110234)

## Two builds with identical final output

On an Apple silicon Mac, a Sanctuary fixture piped `idle\nREADY 17\n` into
`rg --no-config --line-buffered '^READY '`. The catalog runner closes the input
pipe after writing the fixture. For both releases, `cli-testing compare`
reported `matched` against the macOS reference, `/usr/bin/grep '^READY '`.
[Candidate comparison](../../tools/cli-testing/README.md#compare-a-built-candidate)
and [pipe capture](../../tools/cli-testing/src/context.rs)

A second check sent the same bytes and kept stdin open while waiting up to two
seconds for a complete stdout line. It then closed stdin and collected the
rest. All six runs exited zero with empty stderr.

| ripgrep release | First stdout line while stdin was open | Total stdout after exit |
| --- | --- | --- |
| 15.0.0 | Deadline elapsed in all three runs | `READY 17\n` |
| 15.1.0 | `READY 17\n` in all three runs | `READY 17\n` |

## Decide whether to ship a watcher upgrade

Today's `cli-testing compare` requires a catalog whose binary name matches the
owning Cargo package. The proposed command would accept an executable and its
arguments directly, so a team packaging a Python watcher could check its
bundled filter on a laptop or private CI runner. The reviewer would supply a
small synthetic input file, the expected line and the team's delivery deadline.
[Catalog validation](../../tools/cli-testing/src/catalog.rs)

For this one-match case, a pass would require the line on stdout before the
deadline, exactly that line in the final output, empty stderr and exit 0. On
a miss, the reviewer could see whether the line appeared after input closed or
went to stderr. If a known-good build also times out on the same runner,
repeat the comparison before holding the upgrade.

Pexpect already offers a pipe-based check. In a local trial,
`PopenSpawn.expect_exact` in Pexpect 4.9.0 distinguished the two releases.
Running 15.1.0 with stdout redirected to stderr (`1>&2`) also gave Pexpect a
match because `PopenSpawn` combines the streams. The downstream watcher would
receive zero bytes in that case. Python's subprocess API can watch stdout
independently. Sanctuary packages can also write this check as a native
process test.
[Pexpect's pipe interface](https://pexpect.readthedocs.io/en/stable/api/popen_spawn.html),
[its stream setup](https://pexpect.readthedocs.io/en/stable/_modules/pexpect/popen_spawn.html)
and [Sanctuary's native test guide](../../tools/cli-testing/docs/testing.md#keep-involved-scenarios-in-ordinary-rust)

Try the proposed command with two teams that package filters for live watchers.
Give each team the two unlabeled releases, the stderr-only control and the
working Python check below. Have them choose which build to ship with each
method. Then time each team adapting both methods to a second filter from its
own watcher, alternating which method goes first across teams. Add the command
to `cli-testing` if both teams select 15.1.0, explain why the other two cases
fail and check their own filter faster with the command. If the script serves
them as quickly, keep it as the release check.

## Repeat the pipe check

To repeat the macOS check, place the 15.0.0 executable at `old/rg` and 15.1.0
at `new/rg`. The Python 3 example prints the line seen before closure, total
stdout, stderr and exit status for each build.
[Python subprocess streams](https://docs.python.org/3/library/asyncio-subprocess.html)

```sh
python3 - ./old/rg ./new/rg <<'PY'
import asyncio
import sys

async def check(binary):
    pipe = asyncio.subprocess.PIPE
    child = await asyncio.create_subprocess_exec(
        binary, "--no-config", "--line-buffered", "^READY ",
        stdin=pipe, stdout=pipe, stderr=pipe,
    )
    try:
        child.stdin.write(b"idle\nREADY 17\n")
        await child.stdin.drain()
        try:
            first = await asyncio.wait_for(child.stdout.readline(), timeout=2)
        except asyncio.TimeoutError:
            first = b""
        child.stdin.close()
        rest, errors = await asyncio.wait_for(child.communicate(), timeout=5)
        print(binary, first, first + rest, errors, child.returncode)
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()

for binary in sys.argv[1:]:
    asyncio.run(check(binary))
PY
```
