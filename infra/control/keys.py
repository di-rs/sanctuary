"""Operator-owned Boxie key lifecycle. Callers serialize changes under the host lock."""

import hashlib
import json
import os
import secrets
import tempfile
import time
from pathlib import Path


def write_atomic(path: Path, data: bytes, mode: int = 0o600, uid: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stage = Path(stream.name)
        try:
            os.fchmod(stream.fileno(), mode)
            if uid is not None:
                os.fchown(stream.fileno(), uid, -1)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(stage, path)
        finally:
            stage.unlink(missing_ok=True)


def record_path(directory: Path, secret: bytes) -> Path:
    return directory / hashlib.sha256(secret.strip()).hexdigest()


def key_for(
    directory: Path,
    destination: Path,
    consumer: str,
    expires: int | None,
    *,
    rotate: bool = False,
    uid: int | None = None,
) -> None:
    current = destination.read_bytes().strip() if destination.exists() else b""
    live = record_path(directory, current)
    # A revoked key can only be re-enabled by issuing a fresh secret.
    token = current
    if rotate or not current or not live.exists():
        token = ("sk1_" + secrets.token_hex(32)).encode()
    record = json.dumps({"consumer": consumer, "expires_at": expires}).encode()
    write_atomic(record_path(directory, token), record, 0o444)
    if token != current:
        write_atomic(destination, token + b"\n", uid=uid)
    # Sweep superseded entries too, including a rotation interrupted after rename.
    for path in directory.iterdir():
        if (
            len(path.name) == 64
            and path != record_path(directory, token)
            and json.loads(path.read_bytes())["consumer"] == consumer
        ):
            path.unlink()


def revoke(directory: Path, destination: Path, consumer: str) -> None:
    if directory.exists():
        for path in directory.iterdir():
            if len(path.name) == 64 and json.loads(path.read_bytes())["consumer"] == consumer:
                path.unlink()
    destination.unlink(missing_ok=True)


def lease_live(expires: int) -> bool:
    return expires > time.time()
