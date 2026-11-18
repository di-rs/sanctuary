"""Concurrent admission, single-use authorization and atomic result publication."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from boxie.application.admission import JobPolicy
from boxie.domain.errors import BoxieError
from boxie.domain.lifecycle import EnsureRequest, SupervisorObservation
from boxie.domain.models import Principal, SandboxLimits, SandboxState, TerminationReason
from boxie.persistence.jobs import JobReceipts
from boxie.persistence.models import JobResult, Sandbox
from boxie.persistence.postgres import PostgresLifecycle
from boxie.persistence.start_guard import PostgresStartGuard
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.temporal.activities import LifecycleActivities
from boxie_test_support.execution import Daemon
from boxie_test_support.supervisor import Clock
from database_support import OWNER, add_check, counts, database, upload
from psycopg.conninfo import make_conninfo
from sqlalchemy import func, update
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
            async with sessions() as session:
                row = await session.get(Sandbox, first.id)
                assert row is not None and row.reserved_result_bytes == 0
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
                async with sessions() as session:
                    row = await session.get(Sandbox, job.id)
                    assert row is not None and row.reserved_result_bytes == 0
                assert (await counts(sessions))[1:3] == (0, 0) and docker.creates == 0
            finally:
                await supervisor.close()

    asyncio.run(exercise())


def test_consumer_grants_and_concurrent_result_reservations(
    postgres_dsn: str, tmp_path: Path
) -> None:
    async def exercise() -> None:
        dsn = make_conninfo(
            postgres_dsn, options=r"-c default_transaction_isolation=repeatable\ read"
        )
        async with database(dsn, tmp_path) as (life, artifacts, sessions, config):
            other = Principal("two")
            limit = SandboxLimits().output_bytes
            policy = JobPolicy(
                profile_grants={"one": frozenset({"shell"}), "two": frozenset({"shell"})},
                consumer_result_bytes=limit + 3,
                total_result_bytes=limit * 2 + 2,
            )
            apps = PostgresLifecycle(
                sessions, life.resolver, life.identity, life.dependencies, job_policy=policy
            )
            revoked = PostgresLifecycle(sessions, life.resolver, life.identity, life.dependencies)
            spec = replace(await upload(artifacts), is_job=True)
            second_spec = replace(await upload(artifacts, other), is_job=True)
            with pytest.raises(BoxieError) as denied:
                await revoked.submit_job(OWNER, "new", spec)
            assert denied.value.status == 403 and await counts(sessions) == (0, 0, 0, 0)

            # Different artifacts and keys exercise the quota lock across independent admissions.
            specs = [spec, replace(await upload(artifacts), is_job=True)]
            attempts = await asyncio.gather(
                *(apps.submit_job(OWNER, str(i), value) for i, value in enumerate(specs)),
                return_exceptions=True,
            )
            failures = [value for value in attempts if isinstance(value, BoxieError)]
            assert len(failures) == 1 and failures[0].status == 429
            admitted = next(
                i for i, value in enumerate(attempts) if not isinstance(value, BaseException)
            )
            first = await revoked.submit_job(OWNER, str(admitted), specs[admitted])
            assert first == attempts[admitted]
            with pytest.raises(BoxieError) as conflict:
                await revoked.submit_job(OWNER, str(admitted), specs[1 - admitted])
            assert conflict.value.status == 409
            assert await counts(sessions) == (1, 1, 1, 1)

            await apps.submit_job(other, "other", second_spec)
            request = EnsureRequest.from_request(await apps.load_request(first.id))
            receipts, boot = JobReceipts(sessions), uuid4()
            assert await apps.bind_supervisor_boot(OWNER, config.identity, first.id, 1, None, boot)
            assert await receipts.authorize(request, boot)
            await receipts.started(first.id, boot)
            await receipts.complete(
                boot,
                JobResult(
                    sandbox_id=first.id, exit_code=0, stdout=b"12", stderr=b"3", truncated=False
                ),
            )
            assert (await revoked.get_result(OWNER, first.id)).exit_code == 0
            assert await apps.record_observation(
                SupervisorObservation(
                    first.id,
                    OWNER,
                    config.identity,
                    1,
                    boot,
                    1,
                    datetime.now(UTC),
                    SandboxState.TERMINATED,
                    False,
                    removal_confirmed=True,
                )
            )
            # The three retained bytes fit this consumer's budget but put the
            # combined reservation one byte over the installation budget.
            with pytest.raises(BoxieError) as full:
                await apps.submit_job(OWNER, "next", spec)
            assert full.value.status == 429
            async with sessions.begin() as session:
                row = await session.get(Sandbox, first.id)
                assert row is not None and row.reserved_result_bytes == 3
                await session.exec(
                    update(Sandbox)
                    .where(col(Sandbox.id) == first.id)
                    .values(cleaned_at=func.clock_timestamp() - timedelta(days=8))
                )
            assert await apps.purge_retained() == 1
            async with sessions() as session:
                row = await session.get(Sandbox, first.id)
                assert row is not None and row.reserved_result_bytes == 0
            assert (await apps.submit_job(OWNER, "next", spec)).id != first.id
            assert (await revoked.submit_job(OWNER, str(admitted), specs[admitted])).id == first.id

    asyncio.run(exercise())
