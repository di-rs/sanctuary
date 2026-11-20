# Check a story's count against a fresh notebook run

A draft says three park repair requests remain open. One request has since
closed. With a proposed private review tool, the editor could rerun the
reporter's Jupyter notebook on the corrected CSV and see **Draft 3 · Saved
notebook 2 · Fresh run 2**. They would know which sentence to revisit.

At the St. Louis Post-Dispatch, a reporter published a notebook and a copy
of the city's complaint data so readers could reproduce counts in a parks
story. At the New York Times, the team behind ArchieML described reporters
and editors writing graphics copy together in Google Docs. A desk with
both practices has two places to check when a count changes.
[Post-Dispatch reporter's account](https://source.opennews.org/articles/data-jupyter-notebook-journalists-st-louis/)
and [ArchieML at the Times](https://archieml.org/)

## What a passing notebook test can miss

To reproduce the handoff with invented data, put the following four records
in `repairs.csv` with the header shown. In the same directory, create a
Python notebook named `repairs.ipynb` with the single code cell below.

```csv
id,status
A,open
B,open
C,open
D,closed
```

```python
import csv

with open("repairs.csv", newline="") as records:
    print(sum(row["status"] == "open" for row in csv.DictReader(records)))
```

Run the cell, save the notebook, and copy the printed `3` into a draft.
Change record C to `closed`. With nbval installed in the notebook's Python
environment, run this command from that directory.

```sh
python -m pytest -q --nbval --current-env repairs.ipynb
```

nbval compares fresh output with the output saved in the notebook. The
command failed on the corrected CSV, then passed after rerunning the cell
and saving its new output. The draft still said three.
[nbval's comparison behavior](https://nbval.readthedocs.io/en/latest/#Command-line-usage)

| Handoff in the trial | Draft | Saved cell | Fresh count | What the editor could do |
| --- | ---: | ---: | ---: | --- |
| Original notebook and CSV | 3 | 3 | 3 | Confirm that the count reproduces |
| Corrected CSV, original notebook | 3 | 3 | 2 | Review the data correction with the reporter |
| Corrected CSV and resaved notebook | 3 | 2 | 2 | Revisit the sentence in the draft |
| Saved outputs cleared before sharing | 2 | — | 2 | Confirm the count from the fresh run |
| Count cell tagged `skip-execution` | 3 | 3 | — | Ask for an executable count cell |

In the last case, Jupyter's nbclient 0.11.0 finished successfully with
the corrected CSV and returned the skipped cell's old `3` and execution
number. The prototype cleared saved outputs in a working copy and checked
for the kernel's confirmation that the selected cell ran. It also withheld
the count when the CSV was missing or a later cell failed after the count
had printed.
[nbclient execution hooks](https://nbclient.readthedocs.io/en/latest/client.html#hooks-before-and-after-notebook-or-cell-execution)

## How a desk would use Boxie

The editor would select the cell that prints the count. The newsroom app
would send the notebook, CSV and cell ID to the desk's private Boxie host
in one ZIP. The operator would approve a fixed checker and pin a Python
image containing the newsroom's dependencies. Boxie would run the checker
in a sandbox with a fresh kernel. After the notebook finishes in file
order, the checker would return the whole number printed by the chosen cell.
[Jupyter cell IDs](https://nbformat.readthedocs.io/en/latest/format_description.html#cell-ids)
and [Boxie job API](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

Before submission, the app would save the quoted count, draft revision,
cell ID and ZIP digest. It would attach the returned job ID to that record.
The editor could reopen the comparison from another workstation using
the newsroom's sign-in. A change to the copy or either input file would
need a fresh check. A missing or truncated result would show **Count
unavailable**. The editor would still decide whether the analysis counted
the right requests.

The seven local cases used Boxie's ZIP extraction, job container settings
and output capture on Docker Desktop's Linux arm64 VM with the `runc`
runtime and networking disabled. The field trial would need to verify
kernel startup and capture on native Linux with gVisor.
[Boxie execution environment](../../packages/boxie/docs/execution.md#isolation-and-lifetime)

## When to build the review tool

A desk that writes stories in Quarto can insert a computed value directly
in a sentence. Test the proposed review with two desks that edit copy in
a separate system.
[Quarto inline code](https://quarto.org/docs/computations/inline-code.html)

Ask a reporter at each desk for two matched sets of handoffs from a past
story. Include a matching count, corrected data, a stale draft and a
skipped cell in each set. Have one editor use the proposed review and
another use the desk's usual notebook or private CI check plus a manual
comparison with the draft. Swap workflows for the second set.

Measure hands-on minutes per handoff, including the reporter's preparation
and each workflow's setup time spread over a typical month's checks. Build
the integration if both desks distinguish every matching count, discrepancy
and incomplete run, save at least 25% of the time and bring a second story
to check.
