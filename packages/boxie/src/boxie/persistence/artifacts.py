"""Immutable service maxima for generic artifact uploads."""

from pydantic import BaseModel, ConfigDict, Field

MAX_UPLOAD_BYTES = 512 * 1024 * 1024


class ArtifactLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    compressed_bytes: int = Field(default=MAX_UPLOAD_BYTES, gt=0, le=MAX_UPLOAD_BYTES)
    expanded_bytes: int = Field(default=MAX_UPLOAD_BYTES, gt=0, le=MAX_UPLOAD_BYTES)
    member_bytes: int = Field(default=64 * 1024 * 1024, gt=0, le=64 * 1024 * 1024)
    files: int = Field(default=1024, gt=0, le=1024)


class ArtifactQuota(BaseModel):
    """Operator budgets for staging and retained ZIP artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    consumer_bytes: int = Field(default=8 * 1024**3, gt=0, lt=2**63)
    total_bytes: int = Field(default=16 * 1024**3, gt=0, lt=2**63)
    consumer_objects: int = Field(default=256, gt=0, lt=2**63)
    total_objects: int = Field(default=1024, gt=0, lt=2**63)
