"""Read the named demonstrations a contributor can choose to record."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .workspace import load_toml


class Demo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    args: list[str]
    stdin: str | None = None
    setup: str | None = None
    after: str | None = None
    ready: str | None = None
    keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def interactive_input(self) -> Self:
        if bool(self.ready) != bool(self.keys):
            raise ValueError("interactive demos need both ready text and keys")
        return self


class Demos(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    cases: list[Demo] = Field(min_length=1)

    @classmethod
    def read(cls, path: Path) -> dict[str, Demo]:
        cases = cls.model_validate(load_toml(path)).cases
        names = {case.name: case for case in cases}
        if len(names) != len(cases):
            raise ValueError("demo names must be unique within a CLI")
        return names
