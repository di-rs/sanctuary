"""A killable supervisor with barriers around real SQL commits and Docker start."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import uvicorn
from boxie.bootstrap.config import SupervisorConfig
from boxie.bootstrap.supervisor import create_supervisor_app
from boxie.bootstrap.workers import lifecycle_worker
from boxie.domain.lifecycle import EnsureRequest, SupervisorObservation
from boxie.persistence.database import database
from boxie.persistence.jobs import JobReceipts
from boxie.persistence.models import JobResult
from boxie.persistence.postgres import PostgresLifecycle
from boxie.persistence.postgres_artifacts import PostgresArtifactStore
from boxie.persistence.start_guard import PostgresStartGuard
from boxie.sandbox.docker import DockerBackend
from boxie.sandbox.execution.job import JobRunner
from boxie.sandbox.execution.ownership import acquire_owner_lock
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.temporal.activities import LifecycleActivities
from boxie.temporal.contracts import lifecycle_queue
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter


def run_supervisor(
    config: SupervisorConfig,
    dsn: str,
    address: str,
    listener: socket.socket,
    root: Path,
    interrupt: str | None,
    runtime: str,
) -> None:
    async def barrier(point: str) -> None:
        if point == interrupt:
            (root / "barrier").write_text(point)
            await asyncio.Event().wait()

    class Receipts(JobReceipts):
        async def authorize(self, request: EnsureRequest, boot: UUID) -> bool:
            await barrier("before_authorization")
            claimed = await super().authorize(request, boot)
            if claimed:
                await barrier("before_start_journal")
            return claimed

        async def complete(self, boot: UUID, result: JobResult) -> None:
            await barrier("after_effect")
            await super().complete(boot, result)
            await barrier("after_result")

    class Docker(DockerBackend):
        async def create(self, name: str, config: dict[str, Any]) -> None:
            assert not config["Tty"] and not config["OpenStdin"] and not config["AttachStdin"]
            # Only this fixture can write the independent command-effect counter.
            config["HostConfig"]["Runtime"] = runtime
            config["HostConfig"]["Mounts"].append(
                {"Type": "bind", "Source": str(root / "counter"), "Target": "/evidence"}
            )
            await super().create(name, config)

        async def start(self, identifier: str) -> None:
            await barrier("after_authorization")
            await super().start(identifier)

    async def run() -> None:
        client = await Client.connect(address, data_converter=pydantic_data_converter)
        async with database(dsn) as sessions:
            docker = Docker()
            artifacts = PostgresArtifactStore(sessions, config.data_dir / "artifacts")
            supervisor = Supervisor(
                config,
                docker,
                artifacts.path,
                PostgresStartGuard(sessions),
                lambda: datetime.now(UTC),
                time.monotonic,
                jobs=JobRunner(docker, Receipts(sessions)),
            )
            repository = PostgresLifecycle(sessions, supervisor, config.identity, docker.ready)

            async def observe(observation: SupervisorObservation) -> None:
                await repository.record_observation(observation)

            supervisor.observer = observe

            @asynccontextmanager
            async def workers() -> AsyncIterator[None]:
                async with lifecycle_worker(
                    client,
                    LifecycleActivities(repository, supervisor),
                    task_queue=lifecycle_queue(config.identity),
                ):
                    yield

            app = create_supervisor_app(
                supervisor, artifacts, credential=b"supervisor-test-secret", workers=workers
            )
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
            await server.serve(sockets=[listener])

    with acquire_owner_lock(config.data_dir):
        asyncio.run(run())
