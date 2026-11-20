"""Artifact quota and publication recovery against real PostgreSQL."""

import asyncio
import hashlib
import os
import shutil
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from alembic import command
from boxie.api.app import ApiConfig, create_app
from boxie.bootstrap.supervisor import create_supervisor_app
from boxie.domain.errors import BoxieError
from boxie.persistence.artifacts import ArtifactLimits, ArtifactQuota
from boxie.persistence.database import database as session_database
from boxie.persistence.migrate import migration_config
from boxie.persistence.models import Artifact, ArtifactUpload
from boxie.persistence.postgres_artifacts import PostgresArtifactStore
from boxie.persistence.start_guard import PostgresStartGuard
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.sandbox.transport.client import SupervisorClient
from boxie_test_support.api import CONSUMER_AUTH, FOREIGN_AUTH, serve
from boxie_test_support.archive import chunks as archive_chunks
from boxie_test_support.execution import Daemon
from boxie_test_support.supervisor import Clock, bundle
from database_support import OWNER, database, upload
from sqlalchemy import func, update
from sqlalchemy.exc import DBAPIError
from sqlmodel import select

from integration.faults import Faults

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("loss", ["disconnect", "deadline"])
def test_committed_metadata_survives_lost_ack_and_competing_collection(
    postgres_dsn: str, tmp_path: Path, loss: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        if loss == "deadline":
            monkeypatch.setattr("boxie.persistence.postgres_artifacts.OPERATION_SECONDS", 0.3)
        async with database(postgres_dsn, tmp_path) as (_, _, direct_sessions, _):
            info = psycopg.conninfo.conninfo_to_dict(postgres_dsn)
            faults = Faults(tmp_path / "faults", str(info["host"]), int(str(info["port"])))
            server = await asyncio.start_server(faults.postgres, "127.0.0.1", 0)
            info.update(
                host="127.0.0.1", port=str(server.sockets[0].getsockname()[1]), sslmode="disable"
            )
            dsn = psycopg.conninfo.make_conninfo("", **info)
            async with (
                server,
                session_database(dsn) as sessions,
            ):
                store = PostgresArtifactStore(sessions, tmp_path / "bytes")
                identifier, data = uuid4(), bundle({"proof": b"committed"})

                async def chunks() -> Any:
                    yield data

                (faults.root / "hold_commit").touch()
                upload = asyncio.create_task(
                    store.put(OWNER, identifier, hashlib.sha256(data).hexdigest(), chunks())
                )
                collection = None
                try:
                    async with asyncio.timeout(10):
                        while not (faults.root / "commit_seen").exists():
                            await asyncio.sleep(0.01)
                    async with direct_sessions() as session:
                        row = await session.get(Artifact, identifier)
                        assert not (await session.exec(select(ArtifactUpload))).all()
                    assert row is not None and row.expanded_bytes == len(b"committed")
                    path = store.root / str(row.storage_id)
                    assert (path / "files/proof").read_bytes() == b"committed"
                    os.utime(path, (time.time() - 7200,) * 2)
                    collection = asyncio.create_task(store.collect_orphans(minimum_age_seconds=60))
                    await asyncio.sleep(0.05)
                    assert not collection.done() and path.exists()
                    if loss == "disconnect":
                        (faults.root / "hold_commit").unlink()
                        with pytest.raises(DBAPIError):
                            await asyncio.wait_for(upload, 10)
                    else:
                        with pytest.raises(BoxieError) as expired:
                            await asyncio.wait_for(upload, 10)
                        assert expired.value.status == 503
                        (faults.root / "hold_commit").unlink()
                    if loss == "deadline":
                        with pytest.raises(BoxieError) as waiting:
                            await asyncio.wait_for(collection, 10)
                        assert waiting.value.status == 503
                        assert await store.collect_orphans(minimum_age_seconds=60) == 0
                    else:
                        assert await asyncio.wait_for(collection, 10) == 0
                    restarted = PostgresArtifactStore(direct_sessions, store.root)
                    assert await restarted.collect_orphans(minimum_age_seconds=60) == 0
                    retry = await restarted.put(
                        OWNER, identifier, hashlib.sha256(data).hexdigest(), chunks()
                    )
                    assert not retry.created
                    assert (
                        await restarted.path(OWNER, identifier) / "proof"
                    ).read_bytes() == b"committed"
                finally:
                    (faults.root / "hold_commit").unlink(missing_ok=True)
                    upload.cancel()
                    if collection:
                        collection.cancel()
                    await asyncio.gather(
                        upload, *([collection] if collection else []), return_exceptions=True
                    )

    asyncio.run(exercise())


def test_native_fixture_compose_resolves_owned_fault_boundaries(tmp_path: Path) -> None:
    import json

    from integration.stack import LifecycleStack

    stack = LifecycleStack(tmp_path)
    stack.env["BOXIE_TEST_API_PORT"] = "18890"
    stack.env["BOXIE_TEST_PRODUCT_PORT"] = "18888"
    stack.env["BOXIE_TEST_DATA_MODE"] = "ro"
    config = json.loads(stack.runtime_command("config", "--format", "json"))
    services = config["services"]
    for service, published, target in (("api", "18890", 8090),):
        assert [
            (port["host_ip"], port["published"], port["target"], port["protocol"])
            for port in services[service]["ports"]
        ] == [("127.0.0.1", published, target, "tcp")]
    for name in ("api",):
        assert not any("docker.sock" in str(mount) for mount in services[name].get("volumes", []))
    assert services["supervisor"]["environment"]["DOCKER_HOST"] == "unix:///faults/docker.sock"
    assert not any(m["target"] == "/var/run/docker.sock" for m in services["supervisor"]["volumes"])
    assert any(m["target"] == "/var/run/docker.sock" for m in services["faults"]["volumes"])
    mounts = {m["target"]: m for m in services["supervisor"]["volumes"]}
    assert mounts[str(tmp_path / "data")]["read_only"] is True
    assert not mounts[str(tmp_path / "data/profiles")].get("read_only", False)
    assert mounts["/fixture/supervisor_fixture.py"]["read_only"] is True
    assert all(service.get("restart") == "no" for service in services.values())


def test_disconnected_upload_waiter_and_collector_have_one_total_deadline(
    postgres_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (_, store, sessions, config):
            monkeypatch.setattr(
                "boxie.persistence.postgres_artifacts.OPERATION_SECONDS", 0.15, raising=False
            )
            clock = Clock()
            supervisor = Supervisor(
                config, Daemon(), store.path, PostgresStartGuard(sessions), clock, clock.monotonic
            )

            app = create_supervisor_app(supervisor, store, credential=b"supervisor-test-secret")
            async with serve(app) as origin:
                await store._files_lock.acquire()
                try:
                    async with SupervisorClient(
                        origin, b"supervisor-test-secret", timeout=0.05
                    ) as upstream:

                        async def chunks() -> Any:
                            yield bundle()

                        with pytest.raises(BoxieError) as error:
                            await upstream.put(
                                OWNER, uuid4(), hashlib.sha256(bundle()).hexdigest(), chunks()
                            )
                        assert error.value.status == 503
                    # Upstream already disconnected; the supervisor's own deadline must
                    # evict its waiter without needing to read another body byte.
                    await asyncio.sleep(0.2)
                    assert not store._files_lock._waiters
                    with pytest.raises(BoxieError) as timeout:
                        await asyncio.wait_for(store.collect(), 0.4)
                    assert timeout.value.status == 503
                finally:
                    store._files_lock.release()
                assert await store.collect() == 0
                assert not list(store.root.glob(".upload-*"))

    asyncio.run(exercise())


def test_cancelled_invalid_and_oversized_uploads_never_publish(
    postgres_dsn: str, tmp_path: Path
) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (_, store, sessions, _):

            async def interrupted() -> Any:
                yield b"first chunk"
                raise asyncio.CancelledError

            with pytest.raises(asyncio.CancelledError):
                await store.put(OWNER, uuid4(), "0" * 64, interrupted())
            data = bundle()

            async def chunks() -> Any:
                yield data

            with pytest.raises(BoxieError) as mismatch:
                await store.put(OWNER, uuid4(), "0" * 64, chunks())
            assert mismatch.value.status == 422
            limited = PostgresArtifactStore(
                sessions, store.root, ArtifactLimits(compressed_bytes=10)
            )
            with pytest.raises(BoxieError) as oversized:
                await limited.put(OWNER, uuid4(), hashlib.sha256(data).hexdigest(), chunks())
            assert oversized.value.status == 413
            quota = ArtifactQuota(total_bytes=len(data) - 1)
            limited = PostgresArtifactStore(sessions, store.root, quota=quota)
            with pytest.raises(BoxieError) as staging_full:
                await limited.put(OWNER, uuid4(), hashlib.sha256(data).hexdigest(), chunks())
            assert staging_full.value.status == 429
            assert not list(store.root.iterdir())
            async with sessions() as session:
                assert (await session.exec(select(Artifact))).all() == []
                assert (await session.exec(select(ArtifactUpload))).all() == []

    asyncio.run(exercise())


@pytest.mark.parametrize("budget", ["bytes", "objects"])
def test_quota_scopes_and_exact_retry_through_api(
    postgres_dsn: str, tmp_path: Path, budget: str
) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (life, store, sessions, config):
            data = bundle({"small": b"a" * 64})
            store.quota = (
                ArtifactQuota(consumer_bytes=len(data) + 64, total_bytes=len(data) + 128)
                if budget == "bytes"
                else ArtifactQuota(consumer_objects=1, total_objects=2)
            )
            clock = Clock()
            supervisor = Supervisor(
                config, Daemon(), store.path, PostgresStartGuard(sessions), clock, clock.monotonic
            )
            async with (
                serve(
                    create_supervisor_app(supervisor, store, credential=b"supervisor-test-secret")
                ) as origin,
                SupervisorClient(origin, b"supervisor-test-secret") as upstream,
            ):
                app = create_app(
                    ApiConfig(
                        release="test",
                        consumers={
                            "one": b"consumer-one-secret",
                            "two": b"consumer-two-secret",
                            "three": b"consumer-three-secret",
                        },
                    ),
                    life,
                    upstream,
                    upstream,
                )
                async with serve(app) as url, httpx.AsyncClient(base_url=url) as client:

                    async def put(
                        identifier: UUID, auth: dict[str, str], content: bytes = data
                    ) -> httpx.Response:
                        return await client.put(
                            f"/v1/artifacts/{identifier}",
                            headers={**auth, "X-Content-SHA256": hashlib.sha256(data).hexdigest()},
                            content=content,
                        )

                    contenders = (uuid4(), uuid4(), uuid4())
                    responses = await asyncio.gather(
                        *(put(item, CONSUMER_AUTH) for item in contenders)
                    )
                    assert sorted(response.status_code for response in responses) == [201, 429, 429]
                    winner = contenders[
                        next(
                            i for i, response in enumerate(responses) if response.status_code == 201
                        )
                    ]
                    assert (await put(winner, CONSUMER_AUTH)).status_code == 200
                    assert (await put(winner, CONSUMER_AUTH, data + b"x")).status_code == 422
                    assert (await put(winner, FOREIGN_AUTH)).status_code == 404
                    assert (await put(uuid4(), FOREIGN_AUTH)).status_code == 201
                    full = await put(uuid4(), {"Authorization": "Bearer consumer-three-secret"})
                    assert full.status_code == 429
                    assert full.json() == {"detail": "artifact storage quota reached"}
                    async with sessions() as session:
                        assert (await session.exec(select(Artifact.expanded_bytes))).all() == [
                            64,
                            64,
                        ]
                        assert not (await session.exec(select(ArtifactUpload))).all()

    asyncio.run(exercise())


def test_interrupted_upload_and_retirement_keep_capacity_until_collection(
    postgres_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (_, original, sessions, _):
            quota = ArtifactQuota(consumer_objects=1)
            store = PostgresArtifactStore(sessions, original.root, quota=quota)
            entered = asyncio.Event()

            async def interrupted() -> AsyncIterator[bytes]:
                yield b"first chunk"
                entered.set()
                await asyncio.Future[None]()

            operation = asyncio.create_task(store.put(OWNER, uuid4(), "0" * 64, interrupted()))
            async with asyncio.timeout(5):
                await entered.wait()
            (staged,) = store.root.iterdir()
            async with sessions() as session:
                (reservation,) = (await session.exec(select(ArtifactUpload))).all()
                assert reservation.consumer_id == OWNER.consumer_id
                assert reservation.reserved_bytes >= (staged / "archive.zip").stat().st_size

            def unavailable(*args: object, **kwargs: object) -> None:
                raise OSError("disposable filesystem deletion failure")

            with monkeypatch.context() as patch:
                patch.setattr(shutil, "rmtree", unavailable)
                operation.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await operation
                assert (staged / "archive.zip").read_bytes() == b"first chunk"
                async with sessions.begin() as session:
                    await session.exec(
                        update(ArtifactUpload).values(
                            created_at=func.clock_timestamp() - timedelta(hours=2)
                        )
                    )
                restarted = PostgresArtifactStore(sessions, store.root, quota=quota)
                assert await restarted.collect_orphans() == 0
                with pytest.raises(BoxieError) as still_staged:
                    await upload(restarted)
                assert still_staged.value.status == 429
                assert staged.is_dir()

            async with sessions.begin() as session:
                await session.exec(
                    update(ArtifactUpload).values(retry_after=func.clock_timestamp())
                )
            assert await restarted.collect_orphans() == 1
            assert not staged.exists()
            artifact = (await upload(restarted)).artifact_id
            path = await restarted.path(OWNER, artifact)
            with monkeypatch.context() as patch:
                patch.setattr(shutil, "rmtree", unavailable)
                await restarted.retire(OWNER, artifact)
                restarted = PostgresArtifactStore(sessions, store.root, quota=quota)
                with pytest.raises(BoxieError) as still_retained:
                    await upload(restarted)
                assert still_retained.value.status == 429
                assert path.is_dir()

            assert await restarted.collect() == 1
            assert not path.exists()
            await upload(restarted)

    asyncio.run(exercise())


def test_failed_orphan_yields_to_younger_reservation_and_legacy_files(
    postgres_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (_, store, sessions, _):
            blocked, removable = uuid4(), uuid4()
            async with sessions.begin() as session:
                for hours, identifier in ((3, blocked), (2, removable)):
                    session.add(
                        ArtifactUpload(
                            storage_id=identifier,
                            consumer_id=OWNER.consumer_id,
                            reserved_bytes=10,
                            created_at=datetime.now(UTC) - timedelta(hours=hours),
                        )
                    )
                    (store.root / f".upload-{identifier}").mkdir()
            blocked_path = store.root / f".upload-{blocked}"
            remove = shutil.rmtree

            def remove_unless_blocked(path: Path) -> None:
                if path == blocked_path:
                    raise PermissionError("blocked reservation")
                remove(path)

            with monkeypatch.context() as patch:
                patch.setattr(shutil, "rmtree", remove_unless_blocked)
                assert await store.collect_orphans(limit=1) == 0
                restarted = PostgresArtifactStore(sessions, store.root)
                assert await restarted.collect_orphans(limit=1) == 1
                assert not (store.root / f".upload-{removable}").exists()
                legacy = store.root / ".upload-legacy"
                legacy.mkdir()
                os.utime(legacy, (time.time() - 7200,) * 2)
                # Each later sweep can retry the blocked row and still advance the legacy scan.
                for _ in range(2):
                    async with sessions.begin() as session:
                        await session.exec(
                            update(ArtifactUpload).values(retry_after=func.clock_timestamp())
                        )
                    await restarted.collect_orphans(limit=1)
                assert not legacy.exists()
                assert blocked_path.is_dir()
                async with sessions() as session:
                    (reservation,) = (await session.exec(select(ArtifactUpload))).all()
                    assert reservation.storage_id == blocked
                    assert reservation.reserved_bytes == 10
                    assert reservation.retry_after is not None
            async with sessions.begin() as session:
                await session.exec(
                    update(ArtifactUpload).values(retry_after=func.clock_timestamp())
                )
            assert await restarted.collect_orphans(limit=1) == 1
            assert not blocked_path.exists()

    asyncio.run(exercise())


def test_quota_upgrade_accounts_for_existing_files_and_legacy_staging(
    postgres_dsn: str, tmp_path: Path
) -> None:
    async def exercise() -> None:
        async with database(postgres_dsn, tmp_path) as (_, store, sessions, _):
            identifier = (await upload(store)).artifact_id
            path = await store.path(OWNER, identifier)
            legacy = store.root / ".upload-previous"
            legacy.mkdir()
            (legacy / "archive.zip").write_bytes(b"legacy stage")
            os.utime(legacy, (time.time() - 7200,) * 2)
            config = migration_config(postgres_dsn)
            await asyncio.to_thread(command.downgrade, config, "0008_job_output_budget")
            await asyncio.to_thread(command.upgrade, config, "head")

            restarted = PostgresArtifactStore(
                sessions, store.root, quota=ArtifactQuota(total_objects=2)
            )
            await restarted.prepare()
            data = bundle()
            retry = await restarted.put(
                OWNER, identifier, hashlib.sha256(data).hexdigest(), archive_chunks(data)
            )
            assert not retry.created
            async with sessions() as session:
                row = await session.get_one(Artifact, identifier)
                assert row.expanded_bytes == (path / "nested/hello.txt").stat().st_size
                assert row.consumer_id == OWNER.consumer_id
            with pytest.raises(BoxieError) as full:
                await upload(restarted)
            assert full.value.status == 429
            assert await restarted.collect_orphans() == 1
            await upload(restarted)

    asyncio.run(exercise())
