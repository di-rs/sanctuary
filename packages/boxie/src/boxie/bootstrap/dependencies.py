"""Shared explicit SQL/mTLS construction. Deployment migrations remain operator jobs."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    DescribeNamespaceResponse,
    DescribeTaskQueueRequest,
    DescribeTaskQueueResponse,
)
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import TLSConfig

from boxie.bootstrap.config import LifecycleConfig, read_credential, validate_file_model
from boxie.domain.models import SupervisorIdentity
from boxie.persistence.database import SessionFactory, database
from boxie.temporal.contracts import TASK_QUEUE, lifecycle_queue

# Temporal 1.32.0's matching long poll defaults to 60 seconds. Poller access
# timestamps refresh between polls, so allow another 30 seconds for scheduling
# and network delay. Revisit this bound if the production server setting changes.
WORKER_PRESENCE_SECONDS = 90
_PROBE_RPC_TIMEOUT = timedelta(seconds=5)


def lifecycle_config(data: dict[str, Any]) -> LifecycleConfig:
    converted: dict[str, Any] = {
        key: Path(value) if key.endswith("_file") else value for key, value in data.items()
    }
    return validate_file_model(LifecycleConfig, converted)


def supervisor_identity(data: dict[str, str]) -> SupervisorIdentity:
    return SupervisorIdentity(UUID(data["installation_id"]), data["host_id"])


def database_for(path: Path) -> AbstractAsyncContextManager[SessionFactory]:
    return database(read_credential(path, allow_spaces=True).decode())


async def temporal_client(config: LifecycleConfig, *, lazy: bool = False) -> Client:
    # No plaintext/test-server alternative is accepted by this composition root.
    return await Client.connect(
        config.temporal_address,
        namespace=config.temporal_namespace,
        lazy=lazy,
        data_converter=pydantic_data_converter,
        tls=TLSConfig(
            server_root_ca_cert=config.temporal_ca_file.read_bytes(),
            domain=config.temporal_server_name,
            client_cert=config.temporal_cert_file.read_bytes(),
            client_private_key=config.temporal_key_file.read_bytes(),
        ),
    )


class SupervisorReadiness(Protocol):
    async def ready(self) -> bool: ...


class TemporalHealth(Protocol):
    async def check_health(self) -> bool: ...


class TemporalReadinessService(Protocol):
    def describe_namespace(
        self, req: DescribeNamespaceRequest, /, *, timeout: timedelta
    ) -> Awaitable[DescribeNamespaceResponse]: ...
    def describe_task_queue(
        self, req: DescribeTaskQueueRequest, /, *, timeout: timedelta
    ) -> Awaitable[DescribeTaskQueueResponse]: ...


class TemporalReadiness(Protocol):
    @property
    def namespace(self) -> str: ...
    @property
    def service_client(self) -> TemporalHealth: ...
    @property
    def workflow_service(self) -> TemporalReadinessService: ...


async def temporal_namespace_ready(temporal: TemporalReadiness) -> bool:
    await temporal.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=temporal.namespace), timeout=_PROBE_RPC_TIMEOUT
    )
    return True


async def temporal_poller_ready(
    temporal: TemporalReadiness, queue_name: str, kind: TaskQueueType.ValueType
) -> bool:
    """Check for a worker poll within the presence window."""
    queue = await temporal.workflow_service.describe_task_queue(
        DescribeTaskQueueRequest(
            namespace=temporal.namespace,
            task_queue=TaskQueue(name=queue_name),
            task_queue_type=kind,
        ),
        timeout=_PROBE_RPC_TIMEOUT,
    )
    return any(
        (datetime.now(UTC) - poller.last_access_time.ToDatetime(tzinfo=UTC)).total_seconds()
        < WORKER_PRESENCE_SECONDS
        for poller in queue.pollers
    )


class Dependencies:
    def __init__(
        self,
        supervisor: SupervisorReadiness,
        temporal: TemporalReadiness,
        identity: SupervisorIdentity | None = None,
        schedules: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.supervisor, self.temporal = supervisor, temporal
        self.identity, self.schedules = identity, schedules

    async def __call__(self) -> bool:
        async with asyncio.timeout(5):
            if (
                not await self.supervisor.ready()
                or not await self.temporal.service_client.check_health()
            ):
                return False
            await temporal_namespace_ready(self.temporal)
            for kind in (
                TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
                TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
            ):
                queue_name = lifecycle_queue(self.identity) if self.identity else TASK_QUEUE
                if not await temporal_poller_ready(self.temporal, queue_name, kind):
                    return False
            if self.schedules is not None:
                await self.schedules()
            return True
