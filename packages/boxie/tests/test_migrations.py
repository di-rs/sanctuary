"""An installed migration package can render the full schema without a database."""

from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from boxie.persistence.migrate import migration_config


@pytest.mark.parametrize("operator_config", [False, True])
def test_initial_revision_renders_schema_and_capacity_seed(
    monkeypatch: pytest.MonkeyPatch, operator_config: bool
) -> None:
    # An explicit migration target must win over an unrelated operator environment.
    monkeypatch.setenv("BOXIE_POSTGRES_DSN_FILE", "/missing/unrelated-database-secret")
    output = StringIO()
    config = migration_config("postgresql://localhost/boxie")
    if operator_config:
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", "postgresql+psycopg://localhost/boxie")
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    schema = output.getvalue()
    assert "CREATE TABLE sandboxes" in schema
    assert "CREATE TABLE alembic_version" in schema
    assert "UNIQUE (consumer_id, idempotency_key)" in schema
    assert schema.count("INSERT INTO capacity_slots") == 8


@pytest.mark.integration
def test_initial_revision_matches_mapped_metadata(postgres_dsn: str) -> None:
    from boxie.persistence.migrate import migrate, migration_config

    migrate(postgres_dsn)
    command.check(migration_config(postgres_dsn))


def test_observability_revision_preserves_unknown_cleanup_age() -> None:
    output = StringIO()
    config = migration_config("postgresql://localhost/boxie")
    config.output_buffer = output
    command.upgrade(config, "0002_command_outbox:0004_observability_cleanup", sql=True)
    schema = output.getvalue()
    assert "ADD COLUMN provisioning_outcome" in schema
    assert "ADD COLUMN provisioning_ready_observed_at" in schema
    assert "ADD COLUMN cleanup_pending_since" in schema
    assert "sandbox_provisioning_outcome" in schema
    assert "DROP CONSTRAINT provisioning_ready_evidence" in schema
    assert "DROP COLUMN provisioning_ready_observed_at" in schema
    assert "CREATE INDEX sandbox_cleanup_pending" in schema
    assert "UPDATE sandboxes" not in schema


@pytest.mark.integration
def test_forward_observability_revision_removes_unread_timestamp(postgres_dsn: str) -> None:
    from boxie.persistence.database import database_url
    from sqlalchemy import create_engine, inspect

    config = migration_config(postgres_dsn)
    command.upgrade(config, "0002_command_outbox")
    command.upgrade(config, "0003_observability")
    command.upgrade(config, "head")
    engine = create_engine(database_url(postgres_dsn))
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("sandboxes")}
        assert "provisioning_ready_observed_at" not in columns
        assert {"provisioning_outcome", "cleanup_pending_since"} <= columns
        command.check(config)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_request_correlation_migration_preserves_existing_rows(
    postgres_dsn: str, tmp_path: Path
) -> None:
    import asyncio

    from boxie.persistence.models import Outbox, Sandbox
    from database_support import OWNER, database, upload
    from sqlmodel import select

    async def seed() -> object:
        async with database(postgres_dsn, tmp_path) as (life, artifacts, _, _):
            return (await life.submit(OWNER, "before-upgrade", await upload(artifacts))).id

    identifier = asyncio.run(seed())
    config = migration_config(postgres_dsn)
    command.downgrade(config, "0005_component_names")
    command.upgrade(config, "head")

    async def verify() -> None:
        async with database(postgres_dsn, tmp_path) as (_, _, sessions, _):
            async with sessions() as session:
                row = await session.get(Sandbox, identifier)
                assert (
                    row is not None
                    and row.creation_request_id is None
                    and row.stop_request_id is None
                )
                commands = (
                    await session.exec(select(Outbox).where(Outbox.sandbox_id == identifier))
                ).all()
                assert len(commands) == 1 and commands[0].request_id is None

    asyncio.run(verify())
    command.check(config)


@pytest.mark.integration
def test_job_migration_preserves_receipts_and_rebuilds_reservations(
    postgres_dsn: str, tmp_path: Path
) -> None:
    import asyncio
    from dataclasses import replace
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from boxie.domain.lifecycle import EnsureRequest, SupervisorObservation
    from boxie.domain.models import SandboxState
    from boxie.persistence.jobs import JobReceipts
    from boxie.persistence.models import Job, JobResult, Outbox, Sandbox
    from database_support import OWNER, database, upload
    from sqlalchemy import func, update
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import col

    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (life, artifacts, sessions, supervisor):
            spec = replace(await upload(artifacts), is_job=True)
            queued = await life.submit_job(OWNER, "queued", spec)
            done = await life.submit_job(OWNER, "done", spec)
            request = EnsureRequest.from_request(await life.load_request(done.id))
            receipts, boot = JobReceipts(sessions), uuid4()
            assert await life.bind_supervisor_boot(
                OWNER, supervisor.identity, done.id, 1, None, boot
            )
            assert await receipts.authorize(request, boot)
            await receipts.started(done.id, boot)
            await receipts.complete(
                boot,
                JobResult(
                    sandbox_id=done.id, exit_code=7, stdout=b"out", stderr=b"err", truncated=False
                ),
            )
            config = migration_config(postgres_dsn)
            await asyncio.to_thread(command.downgrade, config, "0007_job_recovery")
            with pytest.raises(IntegrityError, match="cannot_downgrade_with_job_receipts"):
                await asyncio.to_thread(command.downgrade, config, "0006_request_correlation")
            await asyncio.to_thread(command.upgrade, config, "head")
            async with sessions() as session:
                active = await session.get(Sandbox, queued.id)
                retained = await session.get(Sandbox, done.id)
                assert (
                    active
                    and active.reserved_result_bytes == request.profile_snapshot.limits.output_bytes
                )
                assert retained and retained.reserved_result_bytes == 6
            assert (await life.submit_job(OWNER, "done", spec)).id == done.id
            assert (await life.get_result(OWNER, done.id)).exit_code == 7

            # Exercise the same guard after the real retention sweep removes
            # every result and lifecycle row and leaves only permanent job keys.
            assert await life.bind_supervisor_boot(
                OWNER, supervisor.identity, queued.id, 1, None, boot
            )
            for identifier in (queued.id, done.id):
                assert await life.record_observation(
                    SupervisorObservation(
                        identifier,
                        OWNER,
                        supervisor.identity,
                        1,
                        boot,
                        1,
                        datetime.now(UTC),
                        SandboxState.TERMINATED,
                        False,
                        removal_confirmed=True,
                    )
                )
            expired = func.clock_timestamp() - timedelta(days=8)
            async with sessions.begin() as session:
                await session.exec(
                    update(Sandbox)
                    .where(col(Sandbox.id).in_((queued.id, done.id)))
                    .values(cleaned_at=expired)
                )
                await session.exec(
                    update(Outbox)
                    .where(col(Outbox.sandbox_id).in_((queued.id, done.id)))
                    .values(delivered_at=expired)
                )
            assert await life.purge_retained() == 2
            with pytest.raises(IntegrityError, match="cannot_downgrade_with_job_receipts"):
                await asyncio.to_thread(command.downgrade, config, "0006_request_correlation")
            async with sessions() as session:
                assert (
                    await session.get(Job, done.id) and await session.get(Sandbox, done.id) is None
                )
            assert (await life.submit_job(OWNER, "done", spec)).id == done.id

    asyncio.run(exercise())
