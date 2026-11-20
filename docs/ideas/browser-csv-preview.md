# Preview a cutr command on a private CSV

A support engineer needs the ticket summary and ID from a weekly export that
also contains requester details. A link from the `cutr` guide could open a
page where the engineer chooses a local CSV, previews the selected columns
and copies a shell command for next week. The file would stay on the device.

Suppose `tickets.csv` contains these records.

```csv
id,requester,summary
41,Ada,"Login, mobile"
```

Selecting fields `3,1` would show the summary first. The comma inside the
summary stays inside its quotes.

```csv
summary,id
"Login, mobile",41
```

The native command for this file is `cutr -d , -f 3,1 < 'tickets.csv'`.
With the same ticket in the order `id,summary,requester`, that command
exits zero and prints `Ada,41` under `requester,id`. A Metabase user
downgraded from 0.41.6 after emailed and downloaded CSVs lost their
configured column order.
[How cutr selects fields](../../buildins/cutr/README.md#before-using-it)
and [the Metabase export report](https://github.com/metabase/metabase/issues/19796)

For weekly reuse, Sanctuary could add selection by header name to `cutr`.
**Copy command** would put the selected names, in order, into the command
that runs on the next file. A local prototype parsed the header and passed
the matching positions and the same input bytes to today's `cutr`. It
preserved a multiline summary and a zero-padded ID after the columns moved.
If a selected heading was missing or ambiguous, it returned a diagnostic
and no CSV.

## What teams can do with DuckDB today

A team that controls its Freshdesk Analytics schedule can choose which
ticket fields to export. For someone who receives the file, DuckDB already
offers a local workflow. In its web shell, choose **Import**, select
`tickets.csv` and enter `.mode csv`. Read the first record as data to see
the original headings.
[Freshdesk scheduled exports](https://support.freshdesk.com/support/solutions/articles/50000000033-exporting-your-data-in-analytics)
and [DuckDB Web Shell](https://shell.duckdb.org/)

```sql
SELECT *
FROM read_csv('tickets.csv', delim = ',', header = false, all_varchar = true)
LIMIT 1;
```

If `summary` and `id` each appear once, counting `Summary` and `summary`
together, run the selection below. Save it as `select.sql` to reuse it
at the command line. After checking the next file's headings,
run `duckdb -csv < select.sql` from the directory containing both files.
Reading the fields as text preserves IDs such as `0042`.
[DuckDB CSV options](https://duckdb.org/docs/2.0/data/csv/overview)
and [identifier rules](https://duckdb.org/docs/2.0/sql/dialect/keywords_and_identifiers)

```sql
SELECT summary, id
FROM read_csv('tickets.csv', delim = ',', header = true, all_varchar = true);
```

DuckDB 2.0.0 returned `"Login, mobile",41` after the columns moved, both
in its native CLI and in Chrome with the tab offline before file selection.
Renaming `summary` to `title` stopped the query. With the header
`id,summary,summary` and the row `41,Ada,"Login, mobile"`, the selection
alone returned `Ada,41` under `summary,id`. The first query showed both
original headings.

## How qsv and jq handle input

The qsv Web demo pairs a CSV file picker with a field for the column selection
and a raw output preview. Its hosted form uses Appwrite to run qsv on the
submitted file and asks users to keep sensitive data out of the demo.
[qsv Web column selection](https://qsv.dathere.com/web/select)

The jq playground runs JSON filters in the browser with WebAssembly and sends
a snippet to its server when the user chooses to share it. Sanctuary could
borrow qsv's file picker and jq's local execution. A team could then pass
around the shell command while each person works on their own export.
[jq playground design](https://github.com/jqlang/playground#how-it-works)

## What can run in the tab

Sanctuary's PR playground runs native binaries in a Boxie sandbox. The CSV
page would load a WebAssembly module built from a reviewed `cutr` revision.
A browser worker would pass the selected file to the module as standard input
and collect stdout and stderr in memory. A team could host the page, worker
and module as static files on its intranet.
[Current playground execution](../../tools/cli-playground/docs/architecture.md#from-pull-request-to-terminal)

The CLI's logger uses the process ID to identify an invocation, even with
`SANCTUARY_LOG_LEVEL=off`. The full `cutr` executable compiled for
`wasm32-wasip1` with `nightly-2026-11-17`. In a Chromium worker it stopped
before reading the CSV and reported `no pids on this platform`.
[Logger initialization](../../utils/cli-log/src/lib.rs)

A temporary adapter called the field extractor in the `cutr` library directly.
Its WebAssembly module was 156 KiB before compression. Version 0.4.2 of the
browser WASI shim supplied its input and output streams. With the tab offline,
the adapter matched native stdout, stderr and exit status for the example
above, repeated fields (`3,3`) and a row with too few fields. On the short row,
both returned status 65 with the header already on stdout. The page should
mark that preview incomplete and show the diagnostic beside it.
[cutr field extraction](../../buildins/cutr/src/lib.rs) and
[browser WASI shim](https://github.com/bjorn3/browser_wasi_shim)

## Decide whether to add a second command

Start with one comma-delimited UTF-8 file per run. Cap the file and the
captured output at 1 MiB each. Load the assets before enabling the file picker.
**Clear** would discard the input and output held by the page. Use a browser
network trace to verify zero requests from file selection through **Clear**,
including when a synthetic file triggers a parse error.

Recruit five support engineers who receive exports they cannot change at
the source. Have each try the picker and DuckDB on matched sets of
synthetic tickets. Preinstall both CLIs and supply the two DuckDB queries.
Alternate which tool goes first. Ask each engineer to preview one export,
reuse the command or saved SQL at the terminal on a reordered file, and
flag a third file with a duplicate heading. Time from opening the first
export to checking the last file.

To justify a second Sanctuary filter, all five must withhold the ambiguous
file and share only the requested fields on valid exports. At least four
must finish the sequence unaided with Sanctuary in five minutes or less
and beat their own DuckDB time. If the saved query serves the team as
quickly, keep using it.
