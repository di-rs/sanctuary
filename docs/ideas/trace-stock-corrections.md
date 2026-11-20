# Find the pick lists issued from a superseded stock file

A supplier corrects one item's stock from 60 units to 6 and replaces the
morning `stock.csv`. The warehouse has already issued pick lists. For a team
that generates them with Boxie, Sanctuary's private sandbox runtime, the
reporting app could let a dispatch analyst select the withdrawn delivery and
see which lists to review before packing.

## Which lists need review?

In a local simulation, each pick list called for the smaller of the quantity
ordered and the stock available. The job for list 19 started before the
correction and finished after list 18.

| Issued pick list | Stock file used | Units ordered | Units on the list | Units using corrected stock |
| --- | --- | ---: | ---: | ---: |
| PICK-17 | Original | 5 | 5 | 5 |
| PICK-18 | Corrected | 10 | 6 | 6 |
| PICK-19 | Original | 10 | 10 | 6 |

The analyst would review **PICK-17** and **PICK-19**, then reduce PICK-19 by
four units.

DataHub already shows downstream dependencies in its lineage view. The question
here is which *editions* depended on one delivery. A Marquez user reported
that a run explicitly reading an older input version appeared linked to the
latest version. A late run like PICK-19 gives a team a way to check the answer
in its own catalog. [DataHub lineage views](https://docs.datahub.com/docs/features/feature-guides/lineage)
and [Marquez input version report](https://github.com/MarquezProject/marquez/issues/2733)

## Record the stock revision when a list is issued

The reporting app would hash the stock CSV bytes it packages with the order
and save that hash alongside the Boxie artifact ID. Boxie verifies the
SHA-256 of the uploaded ZIP. Compressing the same CSV two ways in the trial
produced two ZIP hashes. The CSV hash lets the publisher recognize the same
revision of the supplier's dated file in either upload.
[Boxie upload contract](../../packages/boxie/docs/consumer-api.md#manage-artifacts-and-sandboxes)

OpenLineage describes a run through events that name its inputs and outputs.
The reporting app knows when a list becomes visible to packers, so it would
publish those events. For one pick list per approved job, it could use the
Boxie job ID as the run ID and record `START` when Boxie accepts the job.
[OpenLineage run events](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md#core-lineage-model)

After the job succeeds with complete output, the app could issue the list
under an immutable edition ID. In the transaction that marks the list as
issued, it would queue a `COMPLETE` event pairing the source namespace, path
and CSV hash with that edition. A truncated result or an `outcome_unknown`
job would leave the list unissued. The private catalog would receive the
identifiers, run state and times needed for the lookup.
[Boxie job results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result),
[OpenLineage dataset versions](https://openlineage.io/docs/spec/facets/dataset-facets/version_facet/)

The OpenLineage Python client's file transport wrote the simulated events
to `events.jsonl` in append mode. With the withdrawn file saved as
`stock-original.csv`, this lookup returned
`PICK-17.csv` and `PICK-19.csv` even with a repeated completion event and
identical stock bytes from another supplier.
[OpenLineage file transport](https://openlineage.io/docs/client/python/configuration/#file)

```sh
stock_sha=$(shasum -a 256 stock-original.csv | cut -d ' ' -f 1)
jq -sr --arg rev "$stock_sha" '
  [.[] | select(.eventType == "COMPLETE")
   | select(any(.inputs[]?; .namespace == "s3://receiving"
       and .name == "supplier-a/2026-11-18/stock.csv"
       and .facets.version.datasetVersion == $rev))
   | .outputs[] | select(.namespace == "s3://dispatch") | .name]
  | unique[]
' events.jsonl
```

## Try it on a warehouse correction

Ask a team that already keeps a private data catalog to replay two past
corrections. Give one analyst the dispatch register with the source revision
and edition ID for each list. Give another the proposed lookup over the same
records, then switch tools for the second correction. Check their answers
against the archived pick lists. Include a list issued after the replacement
arrived and a job that produced no list.

Connect the reporting app to the team's catalog if analysts identify exactly
the editions issued from the withdrawn file and the amendments needed faster
on both corrections. If the dispatch register answers both questions as
quickly, keep the source revision and edition ID there.
