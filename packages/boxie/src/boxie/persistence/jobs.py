"""The single start authorization and completion receipt for an admitted job."""

from base64 import b64encode
from datetime import timedelta
from uuid import UUID

from sqlalchemy import case, func, or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from boxie.contracts.jobs import JobResultView, JobState, JobView
from boxie.domain.errors import BoxieError
from boxie.domain.lifecycle import EnsureRequest
from boxie.domain.models import Principal
from boxie.persistence.database import SessionFactory
from boxie.persistence.models import Job, JobResult, Sandbox

RETENTION = timedelta(days=7)


async def job_view(session: AsyncSession, owner: Principal, identifier: UUID) -> JobView:
    state = await session.scalar(
        select(Job.state).where(Job.id == identifier, Job.consumer_id == owner.consumer_id)
    )
    if state is None:
        raise BoxieError(404, "job not found")
    return JobView(id=identifier, state=JobState(state))


async def job_result(session: AsyncSession, owner: Principal, identifier: UUID) -> JobResultView:
    view = await job_view(session, owner, identifier)
    if view.state not in (JobState.SUCCEEDED, JobState.FAILED):
        raise BoxieError(409, "job has no committed result")
    row = (
        await session.exec(
            select(JobResult)
            .join(Sandbox)
            .where(
                JobResult.sandbox_id == identifier,
                or_(
                    col(Sandbox.cleaned_at).is_(None),
                    Sandbox.cleaned_at > func.clock_timestamp() - RETENTION,
                ),
            )
        )
    ).one_or_none()
    if row is None:
        raise BoxieError(410, "job result expired")
    return JobResultView(
        exit_code=row.exit_code,
        stdout_base64=b64encode(row.stdout).decode("ascii"),
        stderr_base64=b64encode(row.stderr).decode("ascii"),
        truncated=row.truncated,
    )


async def settle_interrupted(session: AsyncSession, identifier: UUID) -> None:
    # A completion transaction may have committed despite a lost acknowledgement.
    await session.exec(
        update(Job)
        .where(col(Job.id) == identifier, col(Job.state).in_(("queued", "starting", "running")))
        .values(state=case((col(Job.state) == "queued", "not_started"), else_="outcome_unknown"))
    )


class JobReceipts:
    def __init__(self, sessions: SessionFactory) -> None:
        self.sessions = sessions

    async def authorize(self, request: EnsureRequest, boot: UUID) -> bool:
        # Commit separately from Docker I/O. A caller losing this commit's ACK
        # has no permission to launch. No transition ever returns to queued.
        async with self.sessions.begin() as session:
            live = (
                select(Sandbox.id)
                .where(
                    Sandbox.id == request.ref.id,
                    Sandbox.generation == request.ref.generation,
                    Sandbox.supervisor_boot_id == boot,
                    col(Sandbox.desired_stop).is_(False),
                    col(Sandbox.cleaned_at).is_(None),
                    Sandbox.absolute_deadline > func.clock_timestamp(),
                )
                .exists()
            )
            claim = await session.exec(
                update(Job)
                .where(
                    col(Job.id) == request.ref.id,
                    col(Job.consumer_id) == request.principal.consumer_id,
                    col(Job.state) == "queued",
                    live,
                )
                .values(state="starting", authorized_boot=boot)
            )
            return claim.rowcount == 1

    async def started(self, identifier: UUID, boot: UUID) -> None:
        async with self.sessions.begin() as session:
            await session.exec(
                update(Job)
                .where(
                    col(Job.id) == identifier,
                    col(Job.authorized_boot) == boot,
                    col(Job.state) == "starting",
                )
                .values(state="running")
            )

    async def complete(self, boot: UUID, result: JobResult) -> None:
        async with self.sessions.begin() as session:
            # Acquire locks in the same order as cleanup and boot handover.
            current = await session.scalar(
                select(Sandbox.id)
                .where(
                    Sandbox.id == result.sandbox_id,
                    Sandbox.supervisor_boot_id == boot,
                    col(Sandbox.cleaned_at).is_(None),
                )
                .with_for_update()
            )
            if current is None:
                raise BoxieError(409, "job attempt no longer owns completion")
            published = await session.exec(
                update(Job)
                .where(
                    col(Job.id) == result.sandbox_id,
                    col(Job.authorized_boot) == boot,
                    col(Job.state) == "running",
                )
                .values(state="succeeded" if result.exit_code == 0 else "failed")
            )
            if published.rowcount != 1:
                raise BoxieError(409, "job attempt no longer owns completion")
            session.add(result)
