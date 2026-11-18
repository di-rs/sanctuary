"""Only a complete capture and matching Docker exit code may publish a job result."""

import asyncio
import os
import struct
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiodocker import Docker
from aiodocker.containers import DockerContainer
from aiodocker.stream import Message, Stream
from boxie.domain.models import ProfileSnapshot, SandboxLimits, TerminationReason
from boxie.sandbox.docker import DockerBackend, container_config
from boxie.sandbox.execution.job import JobRunner, captured_result
from boxie_test_support.dependencies import POSTGRES_IMAGE

COOKIE = bytes(range(16))


class DockerOutput:
    def __init__(self, chunks: Iterable[bytes]) -> None:
        self.chunks = iter(chunks)

    async def read_out(self) -> Message | None:
        data = next(self.chunks, None)
        return None if data is None else Message(1, data)


def frame(kind: int, payload: bytes) -> bytes:
    return struct.pack(">BI", kind, len(payload)) + payload


def completion(out_size: int, err_size: int, code: int, cookie: bytes = COOKIE) -> bytes:
    return frame(3, struct.pack(">16sQQB", cookie, out_size, err_size, code))


def test_capture_requires_every_byte_of_the_authenticated_completion() -> None:
    async def exercise() -> None:
        job = uuid4()
        output = b"BXJ1" + COOKIE + frame(2, b"err") + frame(1, b"out\xff")
        wire = output + completion(4, 3, 7)
        for cut in range(len(wire)):
            with pytest.raises(RuntimeError):
                await captured_result(DockerOutput([wire[:cut]]), job, 5)
        # Losing a whole earlier frame, an old completion, and mismatched
        # per-stream accounting each invalidate even a fully received end.
        for invalid in (
            b"BXJ1" + COOKIE + frame(1, b"out\xff") + completion(4, 3, 7),
            output + completion(4, 3, 7, cookie=b"X" * 16),
            output + completion(3, 4, 7),
        ):
            with pytest.raises(RuntimeError, match="incomplete"):
                await captured_result(DockerOutput([invalid]), job, 5)
        result = await captured_result(DockerOutput(bytes([byte]) for byte in wire), job, 5)
        assert (result.exit_code, result.stderr, result.stdout, result.truncated) == (
            7,
            b"err",
            b"ou",
            True,
        )
        silent = await captured_result(
            DockerOutput([b"BXJ1" + COOKIE + completion(0, 0, 0)]), job, 5
        )
        assert (silent.exit_code, silent.stdout, silent.stderr, silent.truncated) == (
            0,
            b"",
            b"",
            False,
        )

    asyncio.run(exercise())


@pytest.mark.parametrize("complete", [True, False], ids=["helper-aborted", "connection-lost"])
def test_docker_exit_alone_cannot_publish_a_result(complete: bool) -> None:
    async def exercise() -> None:
        docker = Mock(job_exit_code=AsyncMock(return_value=137 if complete else 0))
        receipts = Mock(complete=AsyncMock())
        runner = JobRunner(docker, receipts)
        execution = Mock()
        execution.owner.remove = AsyncMock()
        execution.record.id = uuid4()
        execution.record.snapshot.limits.output_bytes = 64
        wire = b"BXJ1" + COOKIE + frame(1, b"one whole frame")
        if complete:
            wire += completion(len(b"one whole frame"), 0, 0)
        stream = Mock()
        stream.read_out = AsyncMock(side_effect=[Message(1, wire), None])
        stream.close = AsyncMock()
        await runner._collect(execution, "container", stream)
        receipts.complete.assert_not_awaited()
        execution.owner.remove.assert_awaited_once_with(
            execution.record.ref, TerminationReason.PROVISIONING_FAILED
        )

    asyncio.run(exercise())


def test_legacy_job_container_is_never_authorized_for_unverified_capture() -> None:
    async def exercise() -> None:
        container = Mock(show=AsyncMock(return_value={"Config": {"Entrypoint": []}}))
        client = Mock()
        client.containers.container.return_value = container
        receipts = Mock(authorize=AsyncMock())
        runner = JobRunner(DockerBackend(client=client), receipts)
        execution = Mock()
        execution.owner.config.docker_timeout = 1
        with pytest.raises(RuntimeError, match="lacks the required capture"):
            await runner.launch(execution, "legacy")
        container.attach.assert_not_called()
        receipts.authorize.assert_not_awaited()

    asyncio.run(exercise())


@asynccontextmanager
async def native_job(
    root: Path, argv: tuple[str, ...]
) -> AsyncIterator[tuple[DockerBackend, DockerContainer, Stream]]:
    artifact = root / "artifact"
    artifact.mkdir()
    profile = ProfileSnapshot(
        "batch", "1" * 64, POSTGRES_IMAGE, argv, {}, "/opt/artifact", SandboxLimits()
    )
    config = container_config(profile, artifact, {}, terminal=False, capture_root=root)
    config["HostConfig"]["Runtime"] = os.environ.get("BOXIE_JOB_TEST_RUNTIME", "runc")
    async with Docker() as docker:
        backend = DockerBackend(client=docker)
        container = await docker.containers.create(config, name="boxie-capture-test-" + uuid4().hex)
        try:
            stream = await backend.attach_job(container.id)
            try:
                await backend.start(container.id)
                yield backend, container, stream
            finally:
                await stream.close()
        finally:
            await container.delete(force=True)


@pytest.mark.integration
@pytest.mark.usefixtures("postgres_server")  # Supplies the pinned workload image.
@pytest.mark.parametrize(
    ("argv", "code", "stdout"),
    [
        (("/bin/true",), 0, b""),
        (
            (
                "/bin/sh",
                "-c",
                "if test -r /proc/1/fd/1 || test -w /proc/1/fd/1; then exit 99; fi; "
                "sleep 60 & printf done; exit 7",
            ),
            7,
            b"done",
        ),
    ],
    ids=["silent", "private-proc-and-background-child"],
)
def test_native_helper_clean_exit(
    tmp_path: Path, argv: tuple[str, ...], code: int, stdout: bytes
) -> None:
    async def exercise() -> None:
        async with native_job(tmp_path, argv) as (docker, container, stream), asyncio.timeout(10):
            result = await captured_result(stream, uuid4(), 64)
            assert await docker.job_exit_code(container.id) == result.exit_code == code
            assert (result.stdout, result.stderr, result.truncated) == (stdout, b"", False)

    asyncio.run(exercise())


@pytest.mark.integration
@pytest.mark.usefixtures("postgres_server")
def test_killed_native_helper_cannot_complete(tmp_path: Path) -> None:
    async def exercise() -> None:
        async with (
            native_job(tmp_path, ("/bin/sh", "-c", "printf x; sleep 60")) as (
                docker,
                container,
                stream,
            ),
            asyncio.timeout(10),
        ):
            received = 0

            class StopAfterOutput:
                async def read_out(self) -> Message | None:
                    nonlocal received
                    message = await stream.read_out()
                    if message is not None:
                        received += len(message.data)
                        # The prelude and one full one-byte output frame have arrived.
                        if received == 20 + 5 + 1:
                            await container.kill(signal="KILL")
                    return message

            with pytest.raises(RuntimeError, match="interrupted"):
                await captured_result(StopAfterOutput(), uuid4(), 64)
            assert await docker.job_exit_code(container.id) == 137

    asyncio.run(exercise())
