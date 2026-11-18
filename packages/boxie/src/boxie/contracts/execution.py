"""Execution wire contracts."""

from collections.abc import Mapping
from typing import Annotated
from uuid import UUID

from pydantic import Field

from boxie.contracts.common import Positive, WireModel
from boxie.contracts.consumer import PolicyWire, ProfileRequest
from boxie.domain.models import (
    ProfileSnapshot,
    SandboxLimits,
    SupervisorIdentity,
)


class LimitsWire(WireModel):
    memory_bytes: Positive = 536870912
    cpu_nanos: Positive = 1000000000
    pids: Positive = 256
    workspace_bytes: Positive = 67108864
    tmp_bytes: Positive = 16777216
    nofile: Positive = 1024
    output_bytes: Positive = 16777216

    def domain(self) -> SandboxLimits:
        return SandboxLimits(**self.model_dump())


class AdmissionProfileRequest(ProfileRequest):
    policy: PolicyWire = Field(default_factory=PolicyWire)


class ProfileMetadata(WireModel):
    config_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    image_digest: str
    artifact_target: str
    limits: LimitsWire

    def snapshot(
        self, profile_id: str, command: tuple[str, ...], env: Mapping[str, str]
    ) -> ProfileSnapshot:
        return ProfileSnapshot(
            profile_id,
            self.config_digest,
            self.image_digest,
            command,
            env,
            self.artifact_target,
            self.limits.domain(),
        )


class JobProfileApproval(WireModel):
    profile: ProfileMetadata
    policy: PolicyWire


class SnapshotWire(ProfileRequest, ProfileMetadata):
    def domain(self) -> ProfileSnapshot:
        return self.snapshot(self.profile_id, self.command, self.env)

    @classmethod
    def from_domain(cls, snapshot: ProfileSnapshot) -> SnapshotWire:
        return cls.model_validate(snapshot, from_attributes=True)


class IdentityWire(WireModel):
    installation_id: UUID
    host_id: Annotated[str, Field(min_length=1, max_length=128)]

    def domain(self) -> SupervisorIdentity:
        return SupervisorIdentity(self.installation_id, self.host_id)


class ReadyWire(WireModel):
    identity: IdentityWire
    dependencies: dict[str, bool]
