"""Process-owned telemetry background work, isolated from lifecycle availability."""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from functools import partial
from typing import TYPE_CHECKING, Any

from temporalio.api.enums.v1 import TaskQueueType

from boxie.observability.metrics import Metrics
from boxie.observability.telemetry.logging import LogDispatcher, run_process
from boxie.observability.telemetry.metrics import MetricsListener
from boxie.temporal.contracts import lifecycle_queue, maintenance_queue

if TYPE_CHECKING:
    from temporalio.client import Client

    from boxie.domain.models import SupervisorIdentity
    from boxie.persistence.database import SessionFactory
    from boxie.sandbox.execution.supervisor import Supervisor
    from boxie.sandbox.transport.client import SupervisorClient


def run_metrics_process(logs: LogDispatcher, role: str, run: Callable[[Metrics], None]) -> None:
    """Own the private listener beside logging, outside the application's loop."""
    listener: MetricsListener | None = None

    def start() -> None:
        nonlocal listener
        metrics = Metrics(role, logs=logs)
        try:
            listener = MetricsListener(
                metrics,
                os.environ.get("BOXIE_METRICS_HOST", "127.0.0.1"),
                {"api": 9101, "supervisor": 9103}[role],
            )
        except ValueError:
            logs.configuration_error()
        else:
            listener.start()
        run(metrics)

    def close_metrics(remaining: float) -> None:
        if listener is not None:
            listener.close(remaining)

    run_process(logs, start, close_metrics=close_metrics)


async def _probe(metrics: Metrics, name: str, check: Callable[[], Awaitable[bool]]) -> None:
    try:
        ready = await check()
    except Exception:
        ready = False
    metrics.dependency(name, ready)


async def sql_ready(sessions: SessionFactory) -> bool:
    from sqlmodel import select

    async with sessions() as session:
        await session.exec(select(1))
    return True


async def api_dependencies(
    metrics: Metrics,
    supervisor: SupervisorClient,
    temporal: Client,
    identity: SupervisorIdentity,
) -> None:
    from boxie.bootstrap.dependencies import temporal_namespace_ready, temporal_poller_ready

    async def poller(
        queue_name: Callable[[SupervisorIdentity], str], kind: TaskQueueType.ValueType
    ) -> bool:
        return await temporal_poller_ready(temporal, queue_name(identity), kind)

    workflow = TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW
    activity = TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY
    checks = (
        ("supervisor", supervisor.ready),
        ("temporal", temporal.service_client.check_health),
        ("namespace", partial(temporal_namespace_ready, temporal)),
        ("workflow_poller", partial(poller, lifecycle_queue, workflow)),
        ("activity_poller", partial(poller, lifecycle_queue, activity)),
        ("maintenance_workflow_poller", partial(poller, maintenance_queue, workflow)),
        ("maintenance_activity_poller", partial(poller, maintenance_queue, activity)),
    )
    while True:
        try:
            async with asyncio.timeout(5):
                await asyncio.gather(*(_probe(metrics, name, check) for name, check in checks))
        except TimeoutError:
            pass  # Cancelled probes retain their previous age; unknown is not false.
        await asyncio.sleep(15)


async def supervisor_cache(metrics: Metrics, supervisor: Supervisor) -> None:
    while True:
        remaining = [
            max(0, execution.deadlines.lease - supervisor.monotonic())
            for identifier, execution in supervisor.executions.items()
            if execution.deadlines is not None
            and identifier in supervisor.records
            and supervisor.records[identifier].state.value in ("accepted", "provisioning", "ready")
        ]
        metrics.refresh_lease(len(remaining), min(remaining) if remaining else None)
        metrics.dependency("execution", supervisor.execution_ready)
        await asyncio.sleep(1)


async def supervisor_dependencies(
    metrics: Metrics, supervisor: Supervisor, sessions: SessionFactory
) -> None:
    async def postgres() -> bool:
        return await sql_ready(sessions)

    while True:
        try:
            async with asyncio.timeout(5):
                await asyncio.gather(
                    _probe(metrics, "postgres", postgres),
                    _probe(metrics, "docker", supervisor.docker.ready),
                )
        except TimeoutError:
            pass
        await asyncio.sleep(15)


@asynccontextmanager
async def background(*operations: Coroutine[Any, Any, None]) -> AsyncIterator[None]:
    tasks = [asyncio.create_task(operation) for operation in operations]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
