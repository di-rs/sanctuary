# Compare two parcel importers in private chat

A support engineer deciding whether to resend a warehouse return needs to
know which importer will keep the damage reason. In self-hosted Open WebUI,
a proposed **Compare importers** tool would let the engineer enter one
sample in chat and see the fields each release would save.

In 2025 an Open WebUI Pipelines user reported that their installation pinned
Pydantic 2.7.1 while a tool using LangChain 0.3.21 required at least 2.7.4.
Open WebUI recommends an external OpenAPI tool server when Python tools need
incompatible packages. For trusted importers, one private server can call
each parser in its own virtual environment. A team that already packages
its parsers for Boxie, Sanctuary's sandbox runtime, could reuse those
images for chat.
[Operator's dependency report](https://github.com/open-webui/pipelines/issues/477)
and [Open WebUI's guidance on external packages](https://docs.openwebui.com/features/extensibility/plugin/tools/development/#external-packages)

## A return both versions accept

This synthetic importer recognizes ordinary parcels and returns. Save it as
`preview.py` in an empty directory. It prints the Pydantic version and the
field names the importer would save.

```python
import json
import sys
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, __version__


class Parcel(BaseModel):
    parcel_id: str


class Return(Parcel):
    reason: str


record = TypeAdapter(Parcel | Return).validate_json(Path(sys.argv[1]).read_bytes())
print(json.dumps({"version": __version__, "fields": sorted(record.model_dump())}))
```

With uv and Python 3.12, run both releases against the same file. Allow
network access for the first package download.

```sh
printf '%s\n' '{"parcel_id":"P17","reason":"damaged"}' > parcel.json
for version in 2.7.1 2.8.2; do
  uv run --no-project --isolated --python 3.12 --with "pydantic==$version" \
    python preview.py parcel.json
done
```

| Importer | Exit code | Fields kept for parcel P17 |
| --- | ---: | --- |
| Original (Pydantic 2.7.1) | 0 | `parcel_id` |
| Replacement (Pydantic 2.8.2) | 0 | `parcel_id`, `reason` |

Both parcel definitions accept the sample. The older validator selected the
first match. Starting with 2.8, Pydantic gives preference here to the model
that recognizes more fields. A local FastAPI test endpoint invoked both
interpreters and returned the two field lists in one request.
[Pydantic's rules for matching unions](https://pydantic.dev/docs/validation/2.8/concepts/unions/#number-of-valid-fields-set)

## Use the batch importers from chat

An administrator would connect a private OpenAPI server to Open WebUI and
enable it for the support team. The model running on the team's network
would pass a parcel ID and an optional reason to its single operation. The
server would keep the Boxie credential, upload a ZIP containing only
`parcel.json`, and submit one job per release against that upload.
[Open WebUI tool connections](https://docs.openwebui.com/features/extensibility/plugin/tools/openapi-servers/open-webui/#1-tool-servers-added-by-an-admin)

The operator would grant the server two Boxie profiles. Each would name the
batch image by digest and approve one fixed command that reads
`/opt/artifact/parcel.json`. A release engineer could then ship the parser
and its dependencies once for both batch checks and chat. On success, the
server would return the build identifiers and retained field names.
[Boxie job profiles](../../packages/boxie/docs/configuration.md#choose-the-sandbox-image)

In a local trial with Boxie's profile resolver and Docker Desktop's `runc`
runtime, pointing both profiles at the replacement image produced two
successful results saying `reason` survived. Checking the reported package
version against each release's pin caught the mix-up. For a team's own
importers, the tool would also check the reported parser build against the
release manifest. The engineer would see **Version mismatch** for a
disagreement or **Could not check** for a failed job or truncated output,
alongside the other release's result.
[Boxie job results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

## Would reusing the batch images save time?

Ask two teams with private Open WebUI installations and native Linux Boxie
hosts running gVisor to bring a pair of importers they still support.
Keep the model and chat tool the same.
Compare Boxie with the private tool server using two virtual environments,
or the team's own server if it already runs both images. Reverse the order
for the second team. Have support engineers check an ordinary parcel and a
return against direct runs of each importer. Then route the original check
to the replacement parser and withhold one result in a separate case.

Time an operator adding one release and rolling it back while the other
release stays in use. Continue if both teams report every field correctly,
recognize both failed comparisons, and get first and subsequent replies
within their existing chat tool timeout. Multiply the operator minutes
saved per release by the number of updates each team shipped last quarter.
Adopt Boxie for chat where that saving covers the extra setup and a
quarter of upkeep.
