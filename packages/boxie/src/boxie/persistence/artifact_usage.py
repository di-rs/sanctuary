"""Artifact quotas use the supervisor's exclusive ownership of the storage root."""

import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, union_all
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from boxie.domain.errors import BoxieError
from boxie.persistence.artifacts import MAX_UPLOAD_BYTES, ArtifactLimits, ArtifactQuota
from boxie.persistence.models import Artifact, ArtifactUpload


def storage_id(name: str) -> UUID | None:
    try:
        return UUID(name.removeprefix(".upload-"))
    except ValueError:
        return None


def _raise_scan_error(error: OSError) -> None:
    raise error


def _directory_bytes(path: Path) -> int:
    return sum(
        (Path(directory) / name).lstat().st_size
        for directory, _, files in os.walk(path, onerror=_raise_scan_error)
        for name in files
    )


def _legacy_usage(
    root: Path, retained: dict[UUID, int | None], staging: set[UUID]
) -> tuple[dict[UUID, int], dict[str, int]]:
    measured, orphans = {}, {}
    with os.scandir(root) as entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            identifier = storage_id(entry.name)
            if identifier in staging:
                continue
            if identifier is not None and entry.name == str(identifier) and identifier in retained:
                if retained[identifier] is None:
                    measured[identifier] = _directory_bytes(Path(entry.path))
            elif identifier is not None or entry.name.startswith(".upload-"):
                orphans[entry.name] = _directory_bytes(Path(entry.path))
    return measured, orphans


async def inventory_legacy(session: AsyncSession, root: Path) -> dict[str, int]:
    """Measure old retained and interrupted uploads before admitting new bytes."""
    rows = (await session.exec(select(Artifact).where(col(Artifact.collected_at).is_(None)))).all()
    staging = set((await session.exec(select(ArtifactUpload.storage_id))).all())
    measured, orphans = await asyncio.to_thread(
        _legacy_usage, root, {row.storage_id: row.expanded_bytes for row in rows}, staging
    )
    for row in rows:
        if row.storage_id in measured:
            row.expanded_bytes = measured[row.storage_id]
    return orphans


async def reserve_upload(
    session: AsyncSession,
    consumer_id: str,
    limits: ArtifactLimits,
    quota: ArtifactQuota,
    legacy_orphans: dict[str, int],
) -> ArtifactUpload:
    usage = union_all(
        select(
            col(Artifact.consumer_id).label("owner"),
            func.coalesce(Artifact.expanded_bytes, MAX_UPLOAD_BYTES).label("size"),
        ).where(col(Artifact.collected_at).is_(None)),
        select(ArtifactUpload.consumer_id, ArtifactUpload.reserved_bytes),
    ).subquery()
    owner = usage.c.owner == consumer_id
    total_bytes, total_objects, owner_bytes, owner_objects = (
        await session.exec(
            select(
                func.coalesce(func.sum(usage.c.size), 0),
                func.count(),
                func.coalesce(func.sum(usage.c.size).filter(owner), 0),
                func.count().filter(owner),
            ).select_from(usage)
        )
    ).one()
    available = min(
        quota.consumer_bytes - int(owner_bytes),
        quota.total_bytes - int(total_bytes) - sum(legacy_orphans.values()),
    )
    if (
        available <= 0
        or owner_objects >= quota.consumer_objects
        or total_objects + len(legacy_orphans) >= quota.total_objects
    ):
        raise BoxieError(429, "artifact storage quota reached")
    upload = ArtifactUpload(
        storage_id=uuid4(),
        consumer_id=consumer_id,
        reserved_bytes=min(available, limits.compressed_bytes + limits.expanded_bytes),
    )
    session.add(upload)
    return upload
