"""Run one authorized non-TTY command and publish its bounded result."""

import asyncio
import struct
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from aiodocker.stream import Message, Stream

from boxie.domain.models import TerminationReason
from boxie.persistence.jobs import JobReceipts
from boxie.persistence.models import JobResult
from boxie.sandbox.docker import DockerBackend

if TYPE_CHECKING:
    from boxie.sandbox.execution.sandbox import SandboxExecution


class CaptureStream(Protocol):
    async def read_out(self) -> Message | None: ...


class _CaptureReader:
    """Docker may split or combine the helper's writes at any byte boundary."""

    def __init__(self, stream: CaptureStream) -> None:
        self.stream = stream
        self.pending = bytearray()

    async def read(self, size: int) -> bytes:
        while len(self.pending) < size:
            message = await self.stream.read_out()
            if message is None or message.stream != 1:
                raise RuntimeError("job output capture interrupted")
            self.pending.extend(message.data)
        data = self.pending[:size]
        del self.pending[:size]
        return bytes(data)


async def captured_result(stream: CaptureStream, job_id: UUID, limit: int) -> JobResult:
    reader = _CaptureReader(stream)
    if await reader.read(4) != b"BXJ1":
        raise RuntimeError("job output capture unavailable")
    nonce = await reader.read(16)
    outputs = (bytearray(), bytearray())
    counts = [0, 0]
    remaining = limit
    while True:
        kind, size = struct.unpack(">BI", await reader.read(5))
        if kind == 3:
            if size != 33:
                raise RuntimeError("invalid job completion record")
            token, stdout_count, stderr_count, code = struct.unpack(
                ">16sQQB", await reader.read(33)
            )
            if token != nonce or (stdout_count, stderr_count) != tuple(counts):
                raise RuntimeError("job output capture incomplete")
            return JobResult(
                sandbox_id=job_id,
                exit_code=code,
                stdout=bytes(outputs[0]),
                stderr=bytes(outputs[1]),
                truncated=sum(counts) > limit,
            )
        if kind not in (1, 2) or not 0 < size <= 32768:
            raise RuntimeError("invalid job output frame")
        chunk = await reader.read(size)
        counts[kind - 1] += size
        retained = min(remaining, size)
        outputs[kind - 1].extend(chunk[:retained])
        remaining -= retained


class JobRunner:
    def __init__(self, docker: DockerBackend, receipts: JobReceipts) -> None:
        self.docker, self.receipts = docker, receipts

    async def launch(self, execution: SandboxExecution, identifier: str) -> None:
        record, owner = execution.record, execution.owner
        request, boot = record.request(), owner.boot_id
        async with asyncio.timeout(owner.config.docker_timeout):
            stream = await self.docker.attach_job(identifier)
        try:

            async def start() -> None:
                async with execution.lock:
                    if not owner._live(record):
                        raise RuntimeError("job start fenced")
                    # Survives a lost Docker start acknowledgement. SQL authorizes
                    # only once, even if this subsequent journal write is lost.
                    record.start_uncertain = True
                    owner._changed(record)
                    await self.docker.start(identifier)

            async with asyncio.timeout(owner.config.docker_timeout + 1):
                authorized = await self.receipts.authorize(request, boot)
                if not authorized or not await owner.guard.run_start_if_allowed(
                    request, boot, start
                ):
                    raise RuntimeError("job start unavailable")
                await self.receipts.started(record.id, boot)
            if not await owner._ready(record):
                raise RuntimeError("job stopped during start")
            execution.job_task = asyncio.create_task(self._collect(execution, identifier, stream))
        finally:
            if execution.job_task is None:
                with suppress(Exception):
                    await stream.close()

    async def _collect(self, execution: SandboxExecution, identifier: str, stream: Stream) -> None:
        owner, record = execution.owner, execution.record
        reason = TerminationReason.EXITED
        try:
            result = await captured_result(stream, record.id, record.snapshot.limits.output_bytes)
            if await self.docker.job_exit_code(identifier) != result.exit_code:
                raise RuntimeError("job exit status unconfirmed")
            await self.receipts.complete(owner.boot_id, result)
        except Exception:
            reason = TerminationReason.PROVISIONING_FAILED
        finally:
            with suppress(Exception):
                await stream.close()
        await owner.remove(record.ref, reason)
