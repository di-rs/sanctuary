"""Admission dependencies; deployment composition injects the concrete adapters."""

from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from boxie.contracts.common import ConsumerId, Positive

DependencyCheck = Callable[[], Awaitable[bool]]


class AdmissionReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    oldest_command_seconds: int = Field(default=30, gt=0)
    max_backlog: int = Field(default=100, gt=0)
    dependency_timeout_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)


class JobPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    profile_grants: Mapping[
        ConsumerId, frozenset[Annotated[str, Field(min_length=1, max_length=128)]]
    ] = Field(default_factory=dict, validate_default=True)
    consumer_result_bytes: Positive = 256 * 1024 * 1024
    total_result_bytes: Positive = 1024 * 1024 * 1024
    consumer_downloads: Positive = 2
    total_downloads: Positive = 4

    @field_validator("profile_grants")
    @classmethod
    def freeze_grants(cls, value: Mapping[str, frozenset[str]]) -> Mapping[str, frozenset[str]]:
        return MappingProxyType(dict(value))
