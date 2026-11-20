"""Wire format shared by the trusted publisher and the host pull service."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

SERVICES = ("postgres", "temporal", "observability", "boxie", "playground", "edge")
IMAGES = {"boxie": ("boxie", "sandbox"), "playground": ("playground",)}
MAX_BUNDLE = 512 * 1024**2
MAX_IMAGE = 3 * 1024**3


def sha(value: object, length: int) -> str:
    if not isinstance(value, str) or not re.fullmatch(f"[0-9a-f]{{{length}}}", value):
        raise ValueError("invalid content identifier")
    return value


def preview_number(name: str) -> int:
    if not re.fullmatch(r"pr-[1-9][0-9]{0,9}", name):
        raise ValueError("invalid preview name")
    return int(name[3:])


@dataclass(frozen=True)
class Release:
    name: str
    commit: str
    blobs: dict[str, str]
    expires: int = 0

    def __post_init__(self) -> None:
        sha(self.commit, 40)
        if type(self.expires) is not int:
            raise ValueError("invalid release lifetime")
        if self.name in SERVICES:
            if self.expires:
                raise ValueError("shared services have a persistent lifetime")
            expected = set(IMAGES.get(self.name, ()))
            if self.name == "playground":
                expected.add("bundle")
        else:
            preview_number(self.name)
            expected = {"bundle"}
            if self.expires <= 0:
                raise ValueError("preview lease is required")
        if not isinstance(self.blobs, dict) or self.blobs.keys() != expected:
            raise ValueError("unexpected release contents")
        for digest in self.blobs.values():
            sha(digest, 64)

    def encode(self) -> bytes:
        return (json.dumps(asdict(self), sort_keys=True) + "\n").encode()

    @classmethod
    def decode(cls, name: str, data: bytes) -> Release:
        if len(data) > 4096:
            raise ValueError("oversized release record")
        payload = json.loads(data)
        if not isinstance(payload, dict) or payload.keys() != {
            "name",
            "commit",
            "blobs",
            "expires",
        }:
            raise ValueError("invalid release record")
        if not isinstance(payload["name"], str):
            raise ValueError("invalid release name")
        release = cls(**payload)
        if release.name != name:
            raise ValueError("release name mismatch")
        return release


def digest(path: Path) -> str:
    import hashlib

    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
