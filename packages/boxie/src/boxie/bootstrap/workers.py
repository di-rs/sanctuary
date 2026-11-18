"""SDK workers embedded in the supervisor, with isolated maintenance capacity."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from temporalio.client import Client
from temporalio.worker import Worker

from boxie.bootstrap.schedules import ensure_schedules
from boxie.domain.lifecycle import SupervisorObservation
from boxie.observability.activity_context import ActivityContextResolver
from boxie.persistence.outbox import PostgresOutbox
from boxie.persistence.postgres import PostgresLifecycle
from boxie.persistence.postgres_artifacts import PostgresArtifactStore
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.temporal.activities import LifecycleActivities, SafeActivityErrors
from boxie.temporal.contracts import TASK_QUEUE, lifecycle_queue, maintenance_queue
from boxie.temporal.dispatcher import CommandDelivery
from boxie.temporal.maintenance import Maintenance, MaintenanceActivities
from boxie.temporal.workflows import SandboxLifecycle


async def _project_recovered_job(activities: LifecycleActivities, identifier: UUID) -> None:
    try:
        async with asyncio.timeout(5):
            await activities.inspect_and_renew(str(identifier))
    except Exception:
        # Normal lifecycle inspection retries when PostgreSQL is available again.
        logging.getLogger(__name__).warning("job recovery projection pending for %s", identifier)


@asynccontextmanager
async def lifecycle_worker(
    client: Client,
    activities: LifecycleActivities,
    *,
    task_queue: str = TASK_QUEUE,
    context_resolver: ActivityContextResolver | None = None,
) -> AsyncIterator[None]:
    # Bind retained jobs to this boot and report what startup found in Docker,
    # even when Temporal has no task to deliver to the replacement worker yet.
    await asyncio.gather(
        *(
            _project_recovered_job(activities, record.id)
            for record in activities.supervisor.records.values()
            if record.spec.is_job
        )
    )
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[SandboxLifecycle],
        activities=activities.registered(),
        interceptors=[SafeActivityErrors(context_resolver=context_resolver)],
        max_concurrent_activities=32,
        graceful_shutdown_timeout=timedelta(seconds=25),
    ):
        yield


@asynccontextmanager
async def embedded_workers(
    client: Client,
    repository: PostgresLifecycle,
    supervisor: Supervisor,
    artifacts: PostgresArtifactStore,
    *,
    context_resolver: ActivityContextResolver | None = None,
) -> AsyncIterator[None]:
    identity = supervisor.config.identity
    activities = LifecycleActivities(repository, supervisor)
    delivery = CommandDelivery(
        PostgresOutbox(repository.sessions, identity), client, lifecycle_queue(identity)
    )
    maintenance = MaintenanceActivities(delivery, repository, supervisor, artifacts)

    async def project(observation: SupervisorObservation) -> None:
        before = await repository.get(
            observation.principal, observation.sandbox_id, include_jobs=True
        )
        accepted = await repository.record_observation(observation)
        request = await repository.load_request(observation.sandbox_id)
        if not accepted or request.desired_stop or before.state == observation.state:
            return
        await client.get_workflow_handle(f"boxie/sandbox/{observation.sandbox_id}").signal(
            SandboxLifecycle.reconcile, str(observation.event_version)
        )

    supervisor.observer = project
    try:
        async with (
            lifecycle_worker(
                client,
                activities,
                task_queue=lifecycle_queue(identity),
                context_resolver=context_resolver,
            ),
            Worker(
                client,
                task_queue=maintenance_queue(identity),
                workflows=[Maintenance],
                activities=[maintenance.maintain],
                interceptors=[SafeActivityErrors(context_resolver=context_resolver)],
                max_concurrent_activities=4,
                graceful_shutdown_timeout=timedelta(seconds=25),
            ),
        ):
            await ensure_schedules(client, identity)
            await supervisor.compact()
            async with asyncio.TaskGroup() as recovery:
                relay = recovery.create_task(delivery.run())
                try:
                    yield
                finally:
                    relay.cancel()
    finally:
        supervisor.observer = None
