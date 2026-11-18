"""Reconcile outstanding Docker operations before replacing a pre-start job container."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from boxie.domain.errors import BoxieError
from boxie.domain.models import TerminationReason
from boxie.sandbox import capture_binary
from boxie.sandbox.execution.job import JobRunner
from boxie.sandbox.execution.supervisor import Supervisor
from lifecycle_support import setup


@pytest.mark.parametrize("limits", [{"pids": 1}, {"nofile": 8}])
def test_small_profiles_reject_new_jobs_and_clean_legacy_admissions(
    tmp_path: Path, limits: dict[str, int]
) -> None:
    async def exercise() -> None:
        owner, request, docker, _, _ = await setup(tmp_path, is_job=True, limits=limits)
        with pytest.raises(BoxieError, match="job capture requires"):
            await owner.resolve_admission(request.spec)
        assert (
            owner.profiles.resolve_profile("shell", ("/bin/sh",), {}).limits
            == request.profile_snapshot.limits
        )
        activity = owner.executions[request.ref.id].activity
        assert activity is not None
        await activity
        observation = await owner.inspect(request.ref)
        assert (
            observation.removal_confirmed
            and observation.reason == TerminationReason.PROVISIONING_FAILED
        )
        assert docker.creates == 0 and not docker.started
        await owner.close()

    asyncio.run(exercise())


def test_retained_unstarted_container_is_upgraded_before_launch(tmp_path: Path) -> None:
    async def exercise() -> None:
        old, request, docker, clock, guard = await setup(tmp_path, is_job=True)
        old.jobs = AsyncMock(spec=JobRunner)
        activity = old.executions[request.ref.id].activity
        assert activity is not None
        await activity
        name = old.records[request.ref.id].name
        legacy = docker.resources[name].model_copy(update={"capture_ready": False})
        docker.resources[name] = legacy
        runner = AsyncMock(spec=JobRunner)
        replacement = Supervisor(
            old.config, docker, old.artifact_path, guard, clock, clock.monotonic, jobs=runner
        )
        await replacement.start()
        try:
            with pytest.raises(BoxieError, match="removal pending"):
                await replacement.ensure_ready(request)
            runner.launch.assert_not_awaited()
            upgraded = await replacement.ensure_ready(request)
            assert upgraded.container_id is not None and upgraded.container_id != legacy.id
            assert docker.deleted_ids == [legacy.id] and docker.creates == 2
            runner.launch.assert_awaited_once_with(
                replacement.executions[request.ref.id], upgraded.container_id
            )
        finally:
            await replacement.close()

    asyncio.run(exercise())


def test_capture_install_failure_precedes_docker_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        owner, request, docker, _, _ = await setup(tmp_path, is_job=True)

        def full_volume(*args: Any, **kwargs: Any) -> None:
            raise OSError("capture volume full")

        monkeypatch.setattr(capture_binary, "atomic_write", full_volume)
        activity = owner.executions[request.ref.id].activity
        assert activity is not None
        await activity
        observation = await owner.inspect(request.ref)
        assert observation.reason == TerminationReason.PROVISIONING_FAILED
        assert observation.removal_confirmed and not observation.cleanup_pending
        assert not owner.records[request.ref.id].creation_uncertain
        assert docker.creates == 0
        await owner.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("stop_first", [True, False], ids=["stop", "adopt"])
def test_missing_create_survives_redelivery_and_late_arrival(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop_first: bool
) -> None:
    async def exercise() -> None:
        old, request, docker, clock, guard = await setup(tmp_path, is_job=True)
        release = docker.create_gate = asyncio.Event()
        create = docker.create
        daemon_task: asyncio.Task[None] | None = None

        async def delayed_create(name: str, config: dict[str, Any]) -> None:
            nonlocal daemon_task
            if daemon_task is not None:
                pytest.fail("replacement issued another create")
            daemon_task = asyncio.create_task(create(name, config))
            await asyncio.shield(daemon_task)

        monkeypatch.setattr(docker, "create", delayed_create)
        await docker.create_entered.wait()
        await old.close()
        runner = AsyncMock(spec=JobRunner)
        replacement = Supervisor(
            old.config, docker, old.artifact_path, guard, clock, clock.monotonic, jobs=runner
        )
        await replacement.start()
        try:
            for _ in range(2):
                with pytest.raises(BoxieError, match="creation pending"):
                    await replacement.ensure_ready(request)
            assert docker.creates == 1 and not docker.started
            if stop_first:
                stopped = await replacement.remove(request.ref, TerminationReason.REQUESTED)
                assert stopped.cleanup_pending and not stopped.removal_confirmed
            release.set()
            assert daemon_task is not None
            await daemon_task
            if not stop_first:
                original = docker.resources[old.records[request.ref.id].name]
                observation = await replacement.ensure_ready(request)
                assert observation.container_id == original.id
                runner.launch.assert_awaited_once_with(
                    replacement.executions[request.ref.id], original.id
                )
            removed = await replacement.remove(request.ref, TerminationReason.REQUESTED)
            assert removed.removal_confirmed and docker.creates == 1
            assert len(docker.deleted_ids) == 1 and not docker.resources
        finally:
            release.set()
            await replacement.close()

    asyncio.run(exercise())


def test_lost_prestart_delete_ack_is_reconciled_before_new_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        old, request, docker, clock, guard = await setup(tmp_path, is_job=True)
        old.jobs = AsyncMock(spec=JobRunner)
        activity = old.executions[request.ref.id].activity
        assert activity is not None
        await activity
        original = old.records[request.ref.id].container_id
        assert original is not None
        delete = docker.delete

        async def lose_ack(identifier: str) -> None:
            await delete(identifier)
            raise OSError("Docker delete acknowledgement lost")

        monkeypatch.setattr(docker, "delete", lose_ack)
        await old.close()
        assert old.records[request.ref.id].discarding_container and not docker.resources
        monkeypatch.setattr(docker, "delete", delete)
        replacement = Supervisor(
            old.config,
            docker,
            old.artifact_path,
            guard,
            clock,
            clock.monotonic,
            jobs=AsyncMock(spec=JobRunner),
        )
        await replacement.start()
        try:
            observation = await replacement.ensure_ready(request)
            assert observation.container_id is not None and observation.container_id != original
            assert not replacement.records[request.ref.id].discarding_container
            assert docker.creates == 2 and docker.deleted_ids == [original]
        finally:
            await replacement.close()

    asyncio.run(exercise())
