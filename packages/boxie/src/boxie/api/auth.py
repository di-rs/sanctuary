"""Credentials are injected by composition; all comparisons are constant-time."""

import hashlib
import hmac
import re
from collections.abc import Mapping
from pathlib import Path

from boxie.domain.errors import BoxieError
from boxie.domain.models import Principal


class ConsumerAuth:
    def __init__(self, credentials: Mapping[str, bytes], grants_dir: Path | None = None) -> None:
        self._grants_dir = grants_dir
        self._credentials = dict(credentials)

    def resolve(self, header: str) -> Principal:
        candidate = header.encode()
        found: str | None = None
        for consumer, secret in self._credentials.items():
            if hmac.compare_digest(candidate, b"Bearer " + secret):
                found = consumer
        if (
            found is None
            and self._grants_dir
            and re.fullmatch(rb"Bearer scoped\.[0-9a-f]{64}", candidate)
        ):
            # Only the operator can write grants. Removing a digest revokes its bearer.
            digest = hashlib.sha256(candidate.removeprefix(b"Bearer ")).hexdigest()
            try:
                principal = (self._grants_dir / digest).read_text().strip()
            except FileNotFoundError:
                principal = ""
            if (
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", principal)
                and principal not in self._credentials
            ):
                return Principal(principal, scoped=True)
        if found is None:
            raise BoxieError(401, "invalid consumer credential")
        return Principal(found)

    def accepts(self, header: str) -> bool:
        try:
            self.resolve(header)
        except BoxieError:
            return False
        return True
