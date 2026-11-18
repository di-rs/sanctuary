"""Concurrent admission, single-use authorization and atomic result publication."""

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from boxie.domain.errors import BoxieError
from boxie.domain.lifecycle import EnsureRequest
from boxie.domain.models import TerminationReason
from boxie.persistence.jobs import JobReceipts
from boxie.persistence.models import JobResult
from boxie.persistence.start_guard import PostgresStartGuard
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.temporal.activities import LifecycleActivities
from boxie_test_support.execution import Daemon
from boxie_test_support.supervisor import Clock
from database_support import OWNER, add_check, counts, database, upload
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

pytestmark = pytest.mark.integration


def test_concurrent_retries_and_lost_result_transaction(postgres_dsn: str, tmp_path: Path) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (life, artifacts, sessions, config):
            spec = replace(await upload(artifacts), is_job=True)
            first, second = await asyncio.gather(
                life.submit_job(OWNER, "concurrent", spec),
                life.submit_job(OWNER, "concurrent", spec),
            )
            assert first == second and await counts(sessions) == (1, 1, 1, 1)
            request = EnsureRequest.from_request(await life.load_request(first.id))
            receipts, boot = JobReceipts(sessions), uuid4()
            assert await life.bind_supervisor_boot(OWNER, config.identity, first.id, 1, None, boot)
            claims = await asyncio.gather(
                receipts.authorize(request, boot), receipts.authorize(request, boot)
            )
            assert sorted(claims) == [False, True]
            await receipts.started(first.id, boot)

            await add_check(sessions, col(JobResult.exit_code) != 7, "fixture_reject_result")
            result = JobResult(
                sandbox_id=first.id, exit_code=7, stdout=b"private", stderr=b"", truncated=False
            )
            with pytest.raises(IntegrityError):
                await receipts.complete(boot, result)
            assert (await life.get_job(OWNER, first.id)).state == "running"
            async with sessions() as session:
                assert await session.get(JobResult, first.id) is None
            new_boot = uuid4()
            assert await life.bind_supervisor_boot(
                OWNER, config.identity, first.id, 1, boot, new_boot
            )
            assert (await life.get_job(OWNER, first.id)).state == "outcome_unknown"
            with pytest.raises(BoxieError, match="no longer owns"):
                await receipts.complete(boot, result)
            assert not await receipts.authorize(request, new_boot)

    asyncio.run(exercise())


def test_stop_before_authorization_reports_not_started(postgres_dsn: str, tmp_path: Path) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (life, artifacts, sessions, config):
            spec = replace(await upload(artifacts), is_job=True)
            job = await life.submit_job(OWNER, "never-started", spec)
            await life.terminate(OWNER, job.id, TerminationReason.EXPIRED, include_jobs=True)
            clock, docker = Clock(), Daemon()
            supervisor = Supervisor(
                config, docker, artifacts.path, PostgresStartGuard(sessions), clock, clock.monotonic
            )
            try:
                await LifecycleActivities(life, supervisor).remove_sandbox(str(job.id))
                assert (await life.get_job(OWNER, job.id)).state == "not_started"
                assert (await counts(sessions))[1:3] == (0, 0) and docker.creates == 0
            finally:
                await supervisor.close()

    asyncio.run(exercise())
