# Give a local assistant the totals from a charging export

A fleet analyst needs to quote the number of charging sessions and the energy
they delivered in a monthly report. Colleagues can read the draft and its
chat history. The driver IDs and site notes in the archived CSV must stay
private. Sanctuary could calculate the figures on the analyst's laptop and
let a local assistant cite the exact export used.

In 2024 an Open WebUI user asked a local model to summarize a charging export
of roughly 159 records. Search supplied five records and the model reported
five. Open WebUI now offers a Python interpreter that can read an attached
CSV. Monta lets operators export counts and energy totals directly from its
dashboard. Sanctuary's pilot would serve analysts who receive an archived
file and can share the totals and a file reference in chat.
[Open WebUI user report](https://github.com/open-webui/open-webui/discussions/2287),
[Open WebUI file analysis](https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution/python/)
and [Monta reporting](https://monta.com/help/en_US/monta-hub-reporting-compliance-data-exports-third-party-publishing/how-do-i-use-data-exports-in-hub)

## When one missing reading changes the answer

Two synthetic versions of `charges.csv` contained the same 159 session IDs.
In the first, 157 sessions delivered 1,000 watt-hours each, one recorded zero
and the last delivered 43,000. The second file had a blank in place of the
zero.

| Version | Sessions | Readings present | Sum of known energy | What the analyst can report |
| --- | ---: | ---: | ---: | --- |
| Recorded zero | 159 | 159 | 200,000 Wh | 159 sessions delivered 200 kWh. |
| Blank reading | 159 | 158 | 200,000 Wh | 159 sessions. The energy total is unknown because one reading is missing. |

Reproduce the comparison in an empty directory with Python 3 and the SQLite
CLI. Each file includes an invented driver ID and one note spanning two lines.

```sh
python3 - <<'PY'
import csv

for name, reading in (("zero.csv", 0), ("missing.csv", "")):
    with open(name, "x", encoding="utf-8", newline="") as output:
        rows = csv.writer(output)
        rows.writerow(["session_id", "driver_id", "watt_hours", "note"])
        for n, wh in enumerate([1000] * 157 + [reading, 43000], 1):
            note = "PRIVATE_STOP, BAY\nTWO" if n == 90 else ""
            rows.writerow([f"S{n:03}", "DRIVER_PRIVATE_193", wh, note])
PY

for csv_file in zero.csv missing.csv; do
  sqlite3 -header -column -nullvalue unknown :memory: <<SQL
.import --csv $csv_file charges
WITH meter AS (
  SELECT cast(nullif(watt_hours, '') AS integer) AS wh FROM charges
)
SELECT count(*) AS sessions, count(wh) AS readings, sum(wh) AS known_wh,
       CASE WHEN count(wh) = count(*) THEN sum(wh) END AS total_wh
FROM meter;
SQL
done
```

## What reaches the model

The analyst would choose a file already filtered for the reporting period.
For each export format, the team would identify the session ID and integer
watt-hour columns. A local prototype hashed the file and passed the same
bytes to Sanctuary's `cutr`, looking up column positions by header name.
It handled reordered columns and the multiline note. A duplicate ID, a
short row or an unrecognized unit prevented it from issuing totals.
[How cutr reads CSV fields](../../buildins/cutr/README.md#before-using-it)

After reviewing the filename and figures, the analyst could approve the
summary and ask, “How many sessions and kWh are in report `5d06240b372e`?”
A local tool would read a directory of approved summaries and return the
counts, energy and full SHA-256 digest for the requested report. A correction
at the same filename would get a new reference. An unknown or ambiguous
reference would return **Report unavailable**. LM Studio can connect to the tool
through the Model Context Protocol (MCP) and run a downloaded model offline.
[LM Studio tool support](https://lmstudio.ai/docs/app/mcp) and
[offline operation](https://lmstudio.ai/docs/app/offline)

In a test client with networking disabled, a local Qwen3.8-27B model called
the prototype's MCP tool over standard input and output. It cited the correct
file reference in both answers, reported 200 kWh for the first and explained
the missing reading for the second. The only file data in the model's input
were the counts, energy figure and checksum.
[Model used in the trial](https://huggingface.co/lmstudio-community/Qwen3.8-27B-MLX-6bit)

## Would analysts use it next month?

Ask two fleet analysts to write a monthly report line for matched exports,
including a same-name correction and a missing reading. Have each analyst
alternate the proposed LM Studio tool with copying figures into the same chat.
For the manual route, offer the importer's summary alongside their usual
spreadsheet or saved query. Time from selecting the export to verifying the
cited answer. Inspect the model inputs for the invented driver ID and site note.

Keep the connector if both analysts cite the right file and figures on every
case, the private fields stay out of chat, and time saved at their reporting
frequency covers setup and column mapping within a quarter. If copying the
summary is as quick, keep the local calculation on its own.
