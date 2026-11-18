"""Supervisor-only concrete artifact bytes; PostgreSQL is the sole metadata authority."""

import asyncio
import hashlib
import os
import re
import shutil
import time
import zipfile
from collections.abc import AsyncIterable, AsyncIterator, Iterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from boxie.domain.errors import BoxieError
from boxie.domain.models import ArtifactPutResult, ArtifactView, Principal
from boxie.persistence.artifact_files import extract_archive
from boxie.persistence.artifact_usage import inventory_legacy, reserve_upload, storage_id
from boxie.persistence.artifacts import ArtifactLimits, ArtifactQuota
from boxie.persistence.atomic import sync_directory
from boxie.persistence.database import SessionFactory
from boxie.persistence.models import Artifact, ArtifactUpload, SandboxArtifactRef
from boxie.persistence.postgres import keyed_lock

OPERATION_SECONDS = 20.0


class PostgresArtifactStore:
    def __init__(
        self,
        sessions: SessionFactory,
        root: Path,
        limits: ArtifactLimits | None = None,
        *,
        quota: ArtifactQuota | None = None,
    ) -> None:
        self.sessions, self.root, self.limits = sessions, root, limits or ArtifactLimits()
        self.quota = quota or ArtifactQuota()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # One supervisor owns this directory. Serializes uploads with orphan collection.
        self._files_lock = asyncio.Lock()
        self._scan: Iterator[os.DirEntry[str]] | None = None
        self._legacy_orphans: dict[str, int] | None = None

    @asynccontextmanager
    async def _operation(self) -> AsyncIterator[None]:
        # One total deadline includes waiting for publication/collection ownership.
        # Uncertain commit bytes stay published for subsequent SQL reconciliation.
        try:
            async with asyncio.timeout(OPERATION_SECONDS), self._files_lock:
                yield
        except TimeoutError:
            raise BoxieError(503, "artifact storage unavailable") from None

    async def prepare(self) -> None:
        async with self._files_lock:
            await self._inventory()

    async def _inventory(self) -> dict[str, int]:
        if self._legacy_orphans is None:
            async with self.sessions() as session, session.begin():
                orphans = await inventory_legacy(session, self.root)
            self._legacy_orphans = orphans
        return self._legacy_orphans

    async def _read(
        self,
        chunks: AsyncIterable[bytes],
        sha256: str,
        *,
        output: BinaryIO | None = None,
        reserved_bytes: int | None = None,
    ) -> int:
        digest, size = hashlib.sha256(), 0
        async for chunk in chunks:
            size += len(chunk)
            if size > self.limits.compressed_bytes:
                raise BoxieError(413, "compressed artifact is too large")
            if reserved_bytes is not None and size > reserved_bytes:
                raise BoxieError(429, "artifact storage quota reached")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        if digest.hexdigest() != sha256:
            raise BoxieError(422, "artifact digest mismatch")
        return size

    @staticmethod
    def _retry(row: Artifact, principal: Principal, sha256: str) -> ArtifactPutResult:
        if row.consumer_id != principal.consumer_id:
            raise BoxieError(404, "artifact not found")
        if row.digest != sha256 or row.retired:
            raise BoxieError(409, "artifact ID is immutable or retired")
        return ArtifactPutResult(ArtifactView(row.id, sha256, False), False)

    async def put(
        self, principal: Principal, artifact_id: UUID, sha256: str, chunks: AsyncIterable[bytes]
    ) -> ArtifactPutResult:
        if not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise BoxieError(422, "invalid SHA-256 digest")
        async with self._operation():
            async with self.sessions() as session:
                old = await session.get(Artifact, artifact_id)
            if old is not None:
                self._retry(old, principal, sha256)
                # The accepted digest identifies the already validated ZIP. Verify
                # the retry body without creating staging files or spending quota.
                await self._read(chunks, sha256)
                async with self.sessions() as session:
                    return self._retry(
                        await session.get_one(Artifact, artifact_id), principal, sha256
                    )

            legacy = await self._inventory()
            async with self.sessions() as session, session.begin():
                upload = await reserve_upload(
                    session, principal.consumer_id, self.limits, self.quota, legacy
                )
            return await self._stage(principal, artifact_id, sha256, chunks, upload)

    async def _stage(
        self,
        principal: Principal,
        artifact_id: UUID,
        sha256: str,
        chunks: AsyncIterable[bytes],
        upload: ArtifactUpload,
    ) -> ArtifactPutResult:
        staged = self.root / f".upload-{upload.storage_id}"
        archive = staged / "archive.zip"
        published = False
        try:
            staged.mkdir(mode=0o700)
            with archive.open("xb") as output:
                compressed = await self._read(
                    chunks, sha256, output=output, reserved_bytes=upload.reserved_bytes
                )
                output.flush()
                os.fsync(output.fileno())
            expanded = await extract_archive(
                staged, self.limits, staging_bytes=upload.reserved_bytes - compressed
            )
            archive.unlink()
            for directory, _, _ in os.walk(staged, topdown=False):
                sync_directory(Path(directory))
            async with self.sessions() as session, session.begin():
                await keyed_lock(session, "artifact:" + str(artifact_id))
                old = await session.get(Artifact, artifact_id, with_for_update=True)
                if old is not None:
                    return self._retry(old, principal, sha256)
                # Preserve the bytes and their reservation if publication's COMMIT
                # fails or its acknowledgement is lost.
                staged.rename(self.root / str(upload.storage_id))
                published = True
                sync_directory(self.root)
                session.add(
                    Artifact(
                        id=artifact_id,
                        consumer_id=principal.consumer_id,
                        digest=sha256,
                        storage_id=upload.storage_id,
                        expanded_bytes=expanded,
                    )
                )
                await session.delete(upload)
            return ArtifactPutResult(ArtifactView(artifact_id, sha256, False), True)
        except (
            zipfile.BadZipFile,
            NotImplementedError,
            RuntimeError,
            EOFError,
            FileExistsError,
            NotADirectoryError,
            IsADirectoryError,
            ValueError,
        ) as error:
            raise BoxieError(422, "invalid ZIP artifact") from error
        finally:
            if not published:
                # A failed cleanup leaves the durable reservation for the collector.
                with suppress(OSError, SQLAlchemyError):
                    self._remove(staged)
                    async with self.sessions() as session, session.begin():
                        await session.delete(upload)

    def _remove(self, *paths: Path) -> int:
        removed = 0
        for path in paths:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                continue
            removed += 1
        sync_directory(self.root)
        return removed

    async def path(self, principal: Principal, artifact_id: UUID) -> Path:
        async with self.sessions() as session:
            row = await session.get(Artifact, artifact_id)
            if row is None or row.consumer_id != principal.consumer_id:
                raise BoxieError(404, "artifact not found")
            path = self.root / str(row.storage_id) / "files"
            if not path.is_dir():
                raise BoxieError(409, "artifact bytes unavailable")
            return path.resolve()

    async def retire(self, principal: Principal, artifact_id: UUID) -> None:
        async with self.sessions() as session, session.begin():
            row = (
                await session.exec(
                    select(Artifact).where(Artifact.id == artifact_id).with_for_update()
                )
            ).one_or_none()
            if row is None or row.consumer_id != principal.consumer_id:
                raise BoxieError(404, "artifact not found")
            row.retired = True
            row.collection_pending = row.collected_at is None
        # Physical deletion is separately retryable; retirement remains committed even if
        # this process exits now. The supervisor's collector periodically calls collect.
        await self.collect()

    async def collect(self, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("collection limit must be 1..1000")
        collected = 0
        async with self._operation(), self.sessions() as session, session.begin():
            rows = (
                await session.exec(
                    select(Artifact)
                    .where(
                        col(Artifact.retired).is_(True),
                        col(Artifact.collection_pending).is_(True),
                        ~select(SandboxArtifactRef)
                        .where(SandboxArtifactRef.artifact_id == Artifact.id)
                        .exists(),
                    )
                    .order_by(col(Artifact.created_at))
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).all()
            for row in rows:
                path = self.root / str(row.storage_id)
                try:
                    self._remove(path)
                except OSError:
                    continue
                row.collection_pending = False
                row.collected_at = cast(
                    datetime, await session.scalar(select(func.clock_timestamp()))
                )
                collected += 1
        return collected

    async def collect_orphans(self, *, minimum_age_seconds: int = 3600, limit: int = 100) -> int:
        """Retry abandoned reservations and scan for pre-quota directories."""
        if minimum_age_seconds < 60 or not 1 <= limit <= 1000:
            raise ValueError("orphan collection requires bounded limit and >=60s grace")
        async with self._operation(), self.sessions() as session, session.begin():
            uploads = (
                await session.exec(
                    select(ArtifactUpload)
                    .where(
                        ArtifactUpload.created_at
                        < func.clock_timestamp() - timedelta(seconds=minimum_age_seconds)
                    )
                    .order_by(col(ArtifactUpload.created_at))
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).all()
            count = 0
            for upload in uploads:
                identifier = upload.storage_id
                try:
                    count += self._remove(
                        self.root / f".upload-{identifier}", self.root / str(identifier)
                    )
                except OSError:
                    continue
                await session.delete(upload)
            return count + await self._collect_legacy(
                session, minimum_age_seconds, limit - len(uploads)
            )

    async def _collect_legacy(self, session: AsyncSession, age: int, limit: int) -> int:
        count = 0
        if self._scan is None:
            self._scan = os.scandir(self.root)
        for _ in range(limit):
            entry = next(self._scan, None)
            if entry is None:
                self._scan = None
                break
            if not entry.is_dir(follow_symlinks=False) or time.time() - entry.stat().st_mtime < age:
                continue
            identifier = storage_id(entry.name)
            if identifier is None and not entry.name.startswith(".upload-"):
                continue
            if identifier is not None:
                if await session.get(ArtifactUpload, identifier) is not None:
                    continue
                exists = (
                    await session.exec(select(Artifact.id).where(Artifact.storage_id == identifier))
                ).first()
                if exists:
                    continue
            count += self._remove(Path(entry.path))
            if self._legacy_orphans is not None:
                self._legacy_orphans.pop(entry.name, None)
        return count
