"""Private, noninteractive job contracts."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field

from boxie.contracts.common import WireModel
from boxie.domain.models import SandboxSpec


class JobProfileRequest(WireModel):
    profile_id: Annotated[str, Field(min_length=1, max_length=128)]
    command: Annotated[
        tuple[Annotated[str, Field(min_length=1, max_length=4096)], ...],
        Field(min_length=1, max_length=64),
    ]


class CreateJob(JobProfileRequest):
    artifact_id: UUID

    def domain(self) -> SandboxSpec:
        return SandboxSpec(self.artifact_id, self.profile_id, self.command, {}, is_job=True)


class JobState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_STARTED = "not_started"
    OUTCOME_UNKNOWN = "outcome_unknown"


class JobView(WireModel):
    id: UUID
    state: JobState


class JobCancellationView(JobView):
    cleanup_pending: bool


class JobResultView(WireModel):
    exit_code: int
    stdout_base64: str
    stderr_base64: str
    truncated: bool
