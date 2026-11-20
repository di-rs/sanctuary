# Reproduce a join that multiplies rows

An analyst joins two six-row exports on customer ID and gets 26 rows. Their
support engineer can see counts, but the IDs must stay on the analyst's
machine. Sanctuary's test data generator, Biggie, could let the analyst
paste a short recipe into a ticket. The engineer would turn it into two
one-column CSV files with invented IDs and rerun the join.

DuckDB asks issue reporters to include a small dataset that maintainers can
use to reproduce the problem. Tonic Structural can build a test database
from selected rows and their related records. For a ticket about a join's
row count, the relationship between two key columns can be enough to build
a working example.
[DuckDB's issue submission guide](https://duckdb.org/community_support#issue-submission-guide)
and [Tonic Structural's guide to subsetting](https://docs.tonic.ai/app/generation/subsetting/subsetting-about)

## What the support engineer needs to see

The dplyr maintainers singled out many-to-many equality joins for a warning
because repeated matches can multiply the result. Suppose each export
contains two distinct IDs. One occurs five times and the other occurs once.
The result depends on which ID is frequent in each file.
[dplyr's account of the warning change](https://tidyverse.org/blog/2023/03/dplyr-1-1-1/#revisiting-multiple-matches)

| Most frequent ID | Matches for the first ID | Matches for the second ID | Inner join rows |
| --- | ---: | ---: | ---: |
| Same in both files | 5 × 5 | 1 × 1 | 26 |
| Different in each file | 5 × 1 | 1 × 5 | 10 |

## Make a recipe from two local exports

Start with an inner join on one non-null text key using exact equality.
Load the two key columns after filtering into local DuckDB tables named
`lhs` and `rhs`, both with an `id` column of type `VARCHAR` so that
values such as `01` and `1` stay distinct. This query counts each key
before joining, so the analyst can prepare the recipe without expanding
every match.

```sql
WITH l AS (SELECT id, count(*) AS n FROM lhs GROUP BY id),
     r AS (SELECT id, count(*) AS n FROM rhs GROUP BY id)
SELECT count(*) AS keys,
       coalesce(l.n, 0) AS left_per_key,
       coalesce(r.n, 0) AS right_per_key
FROM l FULL OUTER JOIN r USING (id)
GROUP BY l.n, r.n
ORDER BY left_per_key, right_per_key;
```

For the 26-row example, the entire recipe would fit in the ticket.

```csv
keys,left_per_key,right_per_key
1,1,1
1,5,5
```

The last line means one key appears five times on each side. A zero in
either frequency column would mark a key missing from that side. The
analyst would review the counts before sharing them because they reveal
volumes.

A proposed Biggie reader would assign fresh IDs and preview the two input
row counts and the expected number of matches before writing the files.
Each recipe line contributes `keys × left_per_key × right_per_key` matches.
Biggie already emits five copies of a key with
`biggie records --record K1 --repeat 5 -`. The existing `pair --copies`
option applies one count to every key in both files. The reader would take
the left and right counts separately for each group of keys.
[Biggie records](../../packages/biggie/README.md#literal-records-records)
and [sorted pairs](../../packages/biggie/README.md#sorted-pairs-pair)

In a local trial with DuckDB and Biggie, all six regenerated pairs had
the same inner join counts as their source pairs. The cases included both
rows of the table above, keys present on only one side, a header-only
export and text keys with leading zeros.

## Try it on support tickets

Ask two analytics support teams for two comparable row-count tickets
apiece. For one ticket, the analyst would prepare their usual hand-built
example. For the other, they would share the recipe. Alternate the order
between teams. Have an engineer who has never seen the source files report
the join count and the repeats that explain it. Time both preparation and
diagnosis. Package the reader if both recipe handoffs get the right count
and explanation on the first reply and each team spends less time than
with its hand-built example.
