# Check an invoice against a private XML schema from n8n

When an invoice fails a check, the intake team needs to know who can fix it.
A supplier can correct an invalid amount. A missing schema needs the team's
operator. A proposed workflow for self-hosted n8n would send each invoice ZIP
to Boxie, Sanctuary's private sandbox runtime, and record that distinction in
the team's intake table.

## How existing n8n templates handle invoices

Samet Sen's n8n template converts an XML attachment to JSON and checks fields
and totals inside the workflow. Invoapi's template sends the attachment to its
validation service. A Boxie integration would suit a team that already maintains
its own validator and needs to keep invoices on its private network.
[Samet Sen's invoice workflow](https://n8n.io/workflows/17864-validate-incoming-xrechnung-invoices-from-imap-and-archive-them-with-data-tables/)
and [Invoapi's validation workflow](https://n8n.io/workflows/22037-check-register-and-remind-on-supplier-e-invoices-with-gmail-invoapi-google-drive-sheets-and-anthropic/)

n8n disables its Execute Command node by default as of version 2.0.
In a Docker installation, that node runs commands inside the n8n container.
Calling Boxie over HTTP would let an operator update the validator without
rebuilding the n8n workers. [n8n Execute Command](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.executecommand/)

## One validator and three outcomes

For the pilot, an operator would package `xmllint` and the reviewed schema in
a sandbox image pinned by digest. The operator would grant the workflow's
Boxie consumer an `invoice-v1` job profile with this exact argument list.
Each trial ZIP contains `invoice.xml` at its root.
[Boxie job profiles](../../packages/boxie/docs/configuration.md#choose-the-sandbox-image)

```json
["/usr/bin/xmllint", "--noout", "--schema", "/opt/schemas/invoice.xsd", "/opt/artifact/invoice.xml"]
```

The example schema requires a decimal `amount`. In a local check with libxml2
2.9.13, `xmllint` wrote to stderr even when the invoice passed. The workflow
would use the exit code to decide which status to display. [xmllint diagnostics](https://gnome.pages.gitlab.gnome.org/libxml2/xmllint.html)

| Input to the local check | Exit code | Proposed intake status |
| --- | --- | --- |
| `<invoice><amount>12.50</amount></invoice>` | 0 | Schema passed |
| The same invoice with `twelve` as its amount | 3 | Schema mismatch |
| The valid invoice with the schema file missing | 5 | Needs review |

## Recover a delivery after a lost reply

The template would use a fixed private API address and a Boxie bearer secret
stored in an n8n credential. The intake system would supply the original ZIP
and a stable delivery UUID.

1. **Identify the delivery.** Hash the ZIP with n8n's Crypto node and look up
   the delivery UUID in the intake table. For a matching digest, resume from
   the saved step or return the recorded decision. Flag a different digest
   under the same UUID for review. For a new upload, save the hex SHA-256
   digest in the row and send it in `X-Content-SHA256` on
   `PUT /v1/artifacts/{uuid}`. Select **n8n Binary File** as the HTTP Request
   body. Keep the original bytes for retries because changing a ZIP timestamp
   changes the digest.
   [n8n Crypto](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.crypto/)
   and [HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/)
2. **Submit the check.** Save the key `invoice-v1/<delivery UUID>` in the row.
   Send it as the `Idempotency-Key` on `POST /v1/jobs` with the artifact ID,
   profile ID and approved arguments. If the reply is lost, repeat that same
   submission. Save the returned job ID and poll `GET /v1/jobs/{id}`.
3. **Record the outcome.** For `succeeded` or `failed`, read
   `GET /v1/jobs/{id}/result` and use the exit code as shown above. Route any
   other exit, an expired result, `not_started`, or `outcome_unknown` to
   **Needs review**. Save the decision before retiring the artifact. Keep
   diagnostic text out of the intake row and set a retention period for n8n's
   execution data, which can contain invoice contents. [Boxie job API](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)
   and [n8n execution data](https://docs.n8n.io/hosting/scaling/execution-data/)

In a local Boxie API test backed by PostgreSQL, uploading the same ZIP after
artifact retirement returned HTTP 409. Repeating the original job submission
recovered the first job ID with only one start queued.

## Decide whether to support a second validator

Give two teams a private Boxie trial and the template to import into
self-hosted n8n with Execute Command disabled. Time each team from import to
the three expected outcomes on synthetic invoices. Measure the operator's
profile setup time separately. Drop one submission reply, then redeliver the
original ZIP after retirement. Try a second validator if both teams finish
within 30 minutes, each replay produces one job ID and one intake row for
that delivery, and one team brings another checker it wants to use.
