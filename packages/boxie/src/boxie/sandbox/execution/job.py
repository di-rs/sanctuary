"""Run one authorized non-TTY command and publish its bounded result."""

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from aiodocker.stream import Stream

from boxie.domain.models import TerminationReason
from boxie.persistence.jobs import JobReceipts
from boxie.persistence.models import JobResult
from boxie.sandbox.docker import DockerBackend

if TYPE_CHECKING:
    from boxie.sandbox.execution.sandbox import SandboxExecution


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
        stdout, stderr = bytearray(), bytearray()
        remaining = record.snapshot.limits.output_bytes
        truncated = False
        reason = TerminationReason.EXITED
        try:
            while (frame := await stream.read_out()) is not None:
                if frame.stream not in (1, 2):
                    raise RuntimeError("unsupported job output stream")
                data = frame.data[:remaining]
                (stdout if frame.stream == 1 else stderr).extend(data)
                truncated |= len(data) < len(frame.data)
                remaining -= len(data)
            code = await self.docker.job_exit_code(identifier)
            await self.receipts.complete(
                owner.boot_id,
                JobResult(
                    sandbox_id=record.id,
                    exit_code=code,
                    stdout=bytes(stdout),
                    stderr=bytes(stderr),
                    truncated=truncated,
                ),
            )
        except Exception:
            reason = TerminationReason.PROVISIONING_FAILED
        finally:
            with suppress(Exception):
                await stream.close()
        await owner.remove(record.ref, reason)
