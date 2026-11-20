"""Credentials are injected by composition; all comparisons are constant-time."""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Mapping
from pathlib import Path

from boxie.domain.errors import BoxieError
from boxie.domain.models import Principal


class ConsumerAuth:
    def __init__(self, credentials: Mapping[str, bytes], directory: Path | None = None) -> None:
        self._credentials = dict(credentials)
        self._directory = directory

    def resolve(self, header: str) -> Principal:
        candidate = header.encode()
        found: str | None = None
        for consumer, secret in self._credentials.items():
            if hmac.compare_digest(candidate, b"Bearer " + secret):
                found = consumer
        if found is None and self._directory is not None:
            found = self._managed(header)
        if found is None:
            raise BoxieError(401, "invalid consumer credential")
        return Principal(found)

    def _managed(self, header: str) -> str | None:
        # The operator mounts this directory read-only. Its filenames are hashes,
        # so reading it cannot disclose a usable bearer token.
        match = re.fullmatch(r"Bearer (sk1_[0-9a-f]{64})", header)
        if not match or self._directory is None:
            return None
        key = hashlib.sha256(match[1].encode("ascii")).hexdigest()
        try:
            record = json.loads((self._directory / key).read_bytes())
            consumer, expires = record["consumer"], record["expires_at"]
            if isinstance(consumer, str) and re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", consumer
            ):
                if expires is None or (type(expires) is int and expires > time.time()):
                    return consumer
        except OSError, ValueError, TypeError, KeyError:
            pass
        return None

    def accepts(self, header: str) -> bool:
        try:
            self.resolve(header)
        except BoxieError:
            return False
        return True
