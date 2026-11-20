# Did the green rerun pass the test that failed?

A release reviewer sees a failed test and a green rerun at the same
commit. Before clearing the failure, they need to know whether the same
test passed on the same platform. Sanctuary could let them ask a local
assistant which attempt last ran the test and open the result in that
attempt's report.

Tenstorrent documented a pull request check that stayed red after the failing
test passed on retry. The retry ran just one test, and the summary counted
both attempts. TestLedger already compares individual JUnit test results
in a local SQLite database. A reviewer can use its command line today if
they have the reports from both attempts.
[Tenstorrent's rerun report](https://github.com/tenstorrent/tt-xla/issues/5918)
and [TestLedger's comparison rules](https://github.com/Almeida96/testledger/blob/v0.3.0/README.md#comparison-rules)

## Two green reruns with different answers

Sanctuary's CI saves separate Linux and macOS artifacts with a JUnit
report and the tested commit. Its nextest profile sets retries to zero.
In a disposable macOS checkout, giving `catr` a nonempty file for its
`empty` test made it fail. The `headr` test of the same name passed.
After the empty file was restored, nextest 0.9.146 ran each test
separately. Both reruns exited zero.
[Sanctuary test workflow](../../.github/workflows/pull-request-check.yml),
[CI profile](../../.config/nextest.toml) and [nextest's JUnit format](https://nexte.st/docs/machine-readable/junit/)

| Rerun | Only test in the report | TestLedger result for the original `catr` failure |
| --- | --- | --- |
| Attempt 2 | `headr::catalog` / `empty` passed | `not_observed`. Attempt 1 still held the last recorded result for this test. |
| Attempt 3 | `catr::catalog` / `empty` passed | `recovered`. Attempt 3 records a pass for the previously failing test. |

TestLedger includes the relative XML path in a test's identity. Importing
the passing report from attempt 3 as `retry.xml` changed its comparison
to `not_observed`. The bytes were identical. When collecting reports
locally, copy `target/nextest/ci/junit.xml` after each run. Use the same
filename under separate import directories, such as `first/junit.xml`
and `retry/junit.xml`.

With Java 21 or later and TestLedger 0.3.0 on `PATH`, run this from the
private directory containing `first` and `retry`. Set `branch` and
`revision` to the shared branch and tested commit, and `first_started`
and `retry_started` to the respective UTC start times in ISO 8601 format.
The commands create the ledger in `.testledger/`.
[TestLedger installation and import](https://github.com/Almeida96/testledger/blob/v0.3.0/README.md#import-a-run)

```sh
testledger import --reports first --id attempt-1 --project sanctuary-macos \
  --branch "$branch" --commit "$revision" --at "$first_started"
testledger import --reports retry --id attempt-2 --project sanctuary-macos \
  --branch "$branch" --commit "$revision" --at "$retry_started"
testledger compare --base attempt-1 --head attempt-2
```

## What the reviewer could open

The name `tests-macos` identifies the platform. To identify the attempt,
the reviewer can use the artifact ID printed by that job's upload step.
A proposed import in Sanctuary's `sdev` launcher would pair the two
downloads with those IDs and their attempt numbers. It would check that
the repository, workflow run, job configuration and tested commit match,
then give TestLedger consistent report paths. A missing report or a
mismatch, such as a Linux result paired with a macOS retry, would show
**Cannot compare**. For a confirmed pass, the reviewer could open the
cited line in the original report for each attempt.
[GitHub's artifact upload step](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/src/shared/upload-artifact.ts)

TestLedger offers read-only tools through the Model Context Protocol
(MCP). In a trial with network access disabled, a local six-bit
Qwen3.8-27B model called `compare_runs` and `test_evidence` through a
test client. For attempt 2 it identified the missing result and cited
the original failure at line 7. For attempt 3 it also cited the pass at
line 4 of that attempt's `junit.xml`.
[Model used in the trial](https://huggingface.co/lmstudio-community/Qwen3.8-27B-MLX-6bit)

A desktop pilot could use LM Studio with a downloaded model to keep
failure messages on the reviewer's machine. In TestLedger 0.3.0's Java
command, placing `-Dkotlin-logging.logStartupMessage=false` before
`-cp` kept a startup message out of the MCP output.
[TestLedger's MCP setup](https://github.com/Almeida96/testledger/blob/v0.3.0/README.md#connect-your-agent)
and [LM Studio's MCP support](https://lmstudio.ai/docs/app/mcp)

## Would the importer save review time?

Ask two release teams that rerun selected tests to bring a past failure.
Give two reviewers per team a confirmed pass, a rerun covering only a
similarly named test, and a passing report from the wrong platform.
Have them alternate manual TestLedger import and Sanctuary-assisted
import across matched examples, with the same local assistant available
for both. Time the work from opening the artifacts to citing the result
or identifying the missing evidence, including setup. Try automatic CI
downloads if both teams classify every case correctly with Sanctuary
and cut median hands-on time by at least 25%.
