"""Concurrent admission, single-use authorization and atomic result publication."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from boxie.api.app import ApiConfig, create_app
from boxie.application.admission import JobPolicy
from boxie.domain.errors import BoxieError
from boxie.domain.lifecycle import EnsureRequest, SupervisorObservation
from boxie.domain.models import Principal, SandboxLimits, SandboxState
from boxie.persistence.jobs import JobReceipts
from boxie.persistence.models import JobResult, Outbox, Sandbox
from boxie.persistence.postgres import PostgresLifecycle
from boxie.persistence.start_guard import PostgresStartGuard
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.temporal.activities import LifecycleActivities
from boxie_test_support.api import CONSUMER_AUTH, FOREIGN_AUTH
from boxie_test_support.execution import Daemon
from boxie_test_support.supervisor import Clock
from database_support import OWNER, add_check, counts, database, upload
from psycopg.conninfo import make_conninfo
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

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


def test_cancel_job_before_authorization(postgres_dsn: str, tmp_path: Path) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (life, artifacts, sessions, config):
            sandbox_spec = await upload(artifacts)
            spec = replace(sandbox_spec, is_job=True)
            job = await life.submit_job(OWNER, "never-started", spec)
            sandbox = await life.submit(OWNER, "interactive", sandbox_spec)
            app = create_app(
                ApiConfig(
                    release="test",
                    consumers={"one": b"consumer-one-secret", "two": b"consumer-two-secret"},
                ),
                life,
                AsyncMock(),
                AsyncMock(),
                jobs=life,
            )
            request_id = uuid4()
            route = f"/v1/jobs/{job.id}"
            response = {"id": str(job.id), "state": "not_started", "cleanup_pending": True}
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                assert (await http.delete(route)).status_code == 401
                foreign = await http.delete(route, headers=FOREIGN_AUTH)
                unknown = await http.delete(f"/v1/jobs/{uuid4()}", headers=CONSUMER_AUTH)
                assert foreign.status_code == unknown.status_code == 404
                assert foreign.json() == unknown.json()
                assert (
                    await http.delete(f"/v1/jobs/{sandbox.id}", headers=CONSUMER_AUTH)
                ).status_code == 404
                assert (
                    await http.delete(f"/v1/sandboxes/{job.id}", headers=CONSUMER_AUTH)
                ).status_code == 404
                assert not (await life.load_request(job.id)).desired_stop
                cancelled = await http.delete(
                    route, headers={**CONSUMER_AUTH, "X-Request-ID": str(request_id)}
                )
                assert cancelled.status_code == 200 and cancelled.json() == response
                for retry in await asyncio.gather(
                    *(http.delete(route, headers=CONSUMER_AUTH) for _ in range(3))
                ):
                    assert retry.status_code == 200 and retry.json() == response
                assert (await http.get(route, headers=CONSUMER_AUTH)).json() == {
                    "id": str(job.id),
                    "state": "not_started",
                }
                assert (await http.get(route + "/result", headers=CONSUMER_AUTH)).status_code == 409
            assert not (await life.load_request(sandbox.id)).desired_stop
            assert await counts(sessions) == (2, 2, 2, 3)
            async with sessions() as session:
                stop = await session.scalar(select(Outbox).where(Outbox.kind == "stop"))
                row = await session.get(Sandbox, job.id)
                assert stop is not None and row is not None
                assert stop.request_id == row.stop_request_id == request_id
                assert (
                    row.desired_stop
                    and row.reason == "requested"
                    and row.reserved_result_bytes == 0
                )

            clock, docker = Clock(), Daemon()
            supervisor = Supervisor(
                config, docker, artifacts.path, PostgresStartGuard(sessions), clock, clock.monotonic
            )
            try:
                request = EnsureRequest.from_request(await life.load_request(job.id))
                assert await life.bind_supervisor_boot(
                    OWNER, config.identity, job.id, 1, None, supervisor.boot_id
                )
                assert not await JobReceipts(sessions).authorize(request, supervisor.boot_id)
                await LifecycleActivities(life, supervisor).remove_sandbox(str(job.id))
                settled = await life.cancel_job(OWNER, job.id)
                assert settled.state == "not_started" and not settled.cleanup_pending
                async with sessions() as session:
                    row = await session.get(Sandbox, job.id)
                    assert row is not None and row.reserved_result_bytes == 0
                assert await counts(sessions) == (2, 1, 1, 3) and docker.creates == 0
            finally:
                await supervisor.close()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "ordering", ["before_start", "completion_first", "cancel_first", "cleanup_first", "race"]
)
def test_cancel_job_after_authorization(postgres_dsn: str, tmp_path: Path, ordering: str) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (life, artifacts, sessions, config):
            spec = replace(await upload(artifacts), is_job=True)
            job = await life.submit_job(OWNER, "authorized", spec)
            request = EnsureRequest.from_request(await life.load_request(job.id))
            receipts, boot = JobReceipts(sessions), uuid4()
            assert await life.bind_supervisor_boot(OWNER, config.identity, job.id, 1, None, boot)
            assert await receipts.authorize(request, boot)
            assert not await receipts.authorize(request, boot)
            guard = PostgresStartGuard(sessions)
            start = AsyncMock()
            if ordering != "before_start":
                assert await guard.run_start_if_allowed(request, boot, start)
                start.assert_awaited_once()
                await receipts.started(job.id, boot)
            result = JobResult(
                sandbox_id=job.id, exit_code=7, stdout=b"private", stderr=b"", truncated=False
            )
            if ordering == "completion_first":
                await receipts.complete(boot, result)
            if ordering == "race":
                cancelled, _ = await asyncio.gather(
                    life.cancel_job(OWNER, job.id), receipts.complete(boot, result)
                )
                assert cancelled.state in ("running", "failed")
            else:
                cancelled = await life.cancel_job(OWNER, job.id)
                expected = {
                    "before_start": "starting",
                    "completion_first": "failed",
                    "cancel_first": "running",
                    "cleanup_first": "running",
                }
                assert cancelled.state == expected[ordering]
            assert cancelled.cleanup_pending
            retry = await life.cancel_job(OWNER, job.id)
            assert retry.state == ("failed" if ordering == "race" else cancelled.state)
            assert retry.cleanup_pending
            assert (await life.load_request(job.id)).desired_stop == (cancelled.state != "failed")
            assert await counts(sessions) == (1, 1, 1, 1 if cancelled.state == "failed" else 2)
            if ordering == "before_start":
                assert not await guard.run_start_if_allowed(request, boot, start)
                start.assert_not_awaited()
            if ordering == "cancel_first":
                # The capture receipt may commit while cancellation is pending.
                await receipts.complete(boot, result)
            assert await life.record_observation(
                SupervisorObservation(
                    job.id,
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
            settled = await life.cancel_job(OWNER, job.id)
            assert not settled.cleanup_pending and (await counts(sessions))[1:3] == (0, 0)
            if ordering in ("completion_first", "cancel_first", "race"):
                assert settled.state == "failed"
                retained = await life.get_result(OWNER, job.id)
                assert retained.exit_code == 7 and retained.stdout_base64 == "cHJpdmF0ZQ=="
            else:
                assert settled.state == "outcome_unknown"
                with pytest.raises(BoxieError, match="no longer owns"):
                    await receipts.complete(boot, result)
                with pytest.raises(BoxieError) as no_result:
                    await life.get_result(OWNER, job.id)
                assert no_result.value.status == 409
            async with sessions() as session:
                row = await session.get(Sandbox, job.id)
                assert row is not None
                assert row.reserved_result_bytes == (7 if settled.state == "failed" else 0)

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
