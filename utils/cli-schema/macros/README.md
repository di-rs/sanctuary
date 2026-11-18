# CLI schema derive

This procedural macro supplies `cli_schema::Schema` for root CLI parser structs.
Use it through the [`cli-schema` library](../README.md), which owns the
export contract and usage examples. The derive implements metadata support; the
shared runner invokes it before ordinary startup. It installs no startup hooks
and does not replace Clap parsing.
