"""Small, low-cardinality metrics endpoint on the private telemetry network."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Counter, start_http_server

registry = CollectorRegistry()
requests = Counter(
    "cli_playground_http_requests_total",
    "Completed gateway requests",
    ["status_class"],
    registry=registry,
)


@contextmanager
def listener() -> Iterator[None]:
    host = os.getenv("CLI_PLAYGROUND_METRICS_HOST")
    if not host:
        yield
        return
    server, thread = start_http_server(9104, addr=host, registry=registry)
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
