# Publish a Bash command builder in a Python CLI manual

A maintainer of a Python tool built with Click could put a command form
beside a worked example in the team's manual. An analyst importing monthly
delivery counts into SQLite needs both ZIP codes to keep their leading
zeros and the parcel count to sort as a number. The analyst would enter
the CSV path, a new database path and the two ZIP column names, then
choose **Copy Bash command**. A colleague could change the paths for next
month's export. The CSV and database would stay on the machine running Bash.

PyTorch's installation guide already turns choices such as operating
system and compute platform into a command to run locally. For Click
tools, the Trogon terminal interface lets users assemble a command from
its options. A Trogon user asked for a way to print the finished command
for reuse in scripts. Shell history took them back to the launcher, and
copying the command from terminal output meant removing line breaks.
[PyTorch's command selector](https://pytorch.org/get-started/locally/),
[Trogon for sqlite-utils](https://github.com/simonw/sqlite-utils-tui)
and [the user's request](https://github.com/Textualize/trogon/issues/121)

## Which import gives the busiest lane?

Try this in an empty directory with Bash and `sqlite-utils` 4.1 installed.
That release added `--type COLUMN TYPE` for setting column types when
creating a table. Each ZIP heading needs its own occurrence.
[sqlite-utils 4.1 release notes](https://github.com/simonw/sqlite-utils/releases/tag/4.1)

```sh
printf '%s\n' 'Origin ZIP,Destination ZIP,parcels' \
  '02108,00501,2' '00501,02108,12' > 'November lanes.csv'
sqlite-utils insert --csv \
  --type 'Origin ZIP' TEXT --type 'Destination ZIP' TEXT \
  -- lanes.db lanes 'November lanes.csv'
sqlite-utils query lanes.db 'select * from lanes order by parcels desc' --csv
```

With the same CSV and a fresh table for each run, all three imports exited
zero. The query returned a different first row for each.

| Column types selected | Origin ZIP | Destination ZIP | First parcel count |
| --- | --- | --- | --- |
| Automatic detection | `501` | `2108` | 12 (integer) |
| All text with `--no-detect-types` | `02108` | `00501` | 2 (text) |
| Both ZIP columns set to `TEXT` | `00501` | `02108` | 12 (integer) |

Changing the second heading in the command to `Arrival ZIP` also exited
zero. It created an extra column full of nulls and stored the busiest
lane's destination as `2108`. Put the check query and expected row beside
the form so the analyst can compare the result with the source.

For version 4.0, which rejects `--type`, the analyst can create the
typed table first. These two commands produced the same correct rows
with the CSV above. A team with a fixed file layout can save this recipe.

```sh
sqlite-utils create-table typed.db lanes 'Origin ZIP' text 'Destination ZIP' text parcels integer
sqlite-utils insert typed.db lanes 'November lanes.csv' --csv
```

## What a maintainer would publish

Sanctuary's playground already builds Bash drafts from the arguments
declared by its Rust CLIs. Its controls edit a running sandbox prompt.
A Click adapter could reuse the command schema and Bash quoting in a
static page on the publisher's existing docs site. In a build step with
the Python package pinned to the release, the maintainer would inspect
`insert` with Click's `Context.to_info_dict()` and export the arguments
used in the example.
The analyst would select the release printed by `sqlite-utils --version`.
[Playground command builder](../../tools/cli-playground/README.md#use-a-preview),
[Sanctuary's command schema](../../utils/cli-schema/README.md)
and [Click's documentation API](https://click.palletsprojects.com/en/stable/api/#click.Context.to_info_dict)

Click's `is_flag` field tells the adapter that `--csv` takes no value,
even though its `nargs` is 1. For `--type`, Click specifies two values
per occurrence and allows repeats. Sanctuary's schema can express both
properties. The current playground disables a flag button after its first
use, so the form would give each ZIP heading its own field and supply
`TEXT` as the second value. [Playground flag controls](../../tools/cli-playground/frontend/src/explorer/CommandReference.svelte)

In a local prototype, Sanctuary's schema validator accepted the selected
arguments from both releases. With Chrome offline, the 4.1 form generated
one Bash line for `-November's lanes.csv`. It quoted the filename and
placed it after `--` so the leading dash was part of the name. Running
the line preserved both ZIP codes and the count of 12. Selecting 4.0
displayed **Create the typed table first**.

## Test whether readers reuse the command

Recruit two teams whose analysts adapt CLI examples to different exports.
Have two readers per team prepare commands for a colleague, once with
the form and once with their usual guide or installed Trogon plugin.
Supply the worked example and check query in both workflows. Alternate
which workflow readers try first. Give each reader a 4.1 case and a 4.0
case in each workflow, with different headings and paths to adapt.

Time the handoff until the colleague reproduces the busiest lane in a
fresh database. Package the widget for other Click manuals if every form
handoff preserves both ZIP codes and the numeric count, at least three
readers save a minute against their usual method, and a maintainer
brings a second command they want to publish.
