"""Bound ZIP directory reads before ZipFile allocates its member table."""

import io
import struct
from zipfile import BadZipFile

MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
END_RECORD = struct.Struct("<4s4H2IH")
ZIP64_LOCATOR = struct.Struct("<4sIQI")
ZIP64_END_RECORD = struct.Struct("<4sQHHIIQQQQ")
MEMBER_HEADER_BYTES = 46


def _directory(source: io.BufferedIOBase) -> tuple[int, int, int]:
    """Return the physical directory bounds and the declared entry count."""
    length = source.seek(0, io.SEEK_END)
    tail_start = max(0, length - 65535 - END_RECORD.size)
    source.seek(tail_start)
    tail = source.read(65535 + END_RECORD.size)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or len(tail) - marker < END_RECORD.size:
        raise BadZipFile("missing ZIP end record")
    _, disk, central_disk, disk_entries, entries, size, offset, comment_size = (
        END_RECORD.unpack_from(tail, marker)
    )
    end = tail_start + marker
    if marker + END_RECORD.size + comment_size != len(tail):
        raise BadZipFile("invalid ZIP comment length")

    if end >= ZIP64_LOCATOR.size:
        locator_start = end - ZIP64_LOCATOR.size
        source.seek(locator_start)
        locator = source.read(ZIP64_LOCATOR.size)
        if locator.startswith(b"PK\x06\x07"):
            _, locator_disk, record_offset, disks = ZIP64_LOCATOR.unpack(locator)
            last_record_start = locator_start - ZIP64_END_RECORD.size
            if locator_disk != 0 or disks != 1 or record_offset > last_record_start:
                raise BadZipFile("invalid ZIP64 locator")
            source.seek(record_offset)
            record = source.read(ZIP64_END_RECORD.size)
            end = record_offset
            # ZipFile also tries the fixed-size footer position for a prepended archive.
            if not record.startswith(b"PK\x06\x06") and record_offset != last_record_start:
                end = last_record_start
                source.seek(end)
                record = source.read(ZIP64_END_RECORD.size)
            if len(record) != ZIP64_END_RECORD.size or not record.startswith(b"PK\x06\x06"):
                raise BadZipFile("invalid ZIP64 end record")
            (_, record_size, _, _, disk, central_disk, disk_entries, entries, size, offset) = (
                ZIP64_END_RECORD.unpack(record)
            )
            if end + record_size + 12 != locator_start or offset + size != record_offset:
                raise BadZipFile("invalid ZIP64 directory bounds")

    if disk != 0 or central_disk != 0 or disk_entries != entries:
        raise BadZipFile("split ZIP archives are not supported")
    if offset > end - size:
        raise BadZipFile("invalid ZIP directory offset")
    return end - size, end, entries


def validate_directory(source: io.BufferedIOBase, max_entries: int) -> None:
    """Apply Boxie's byte and entry limits using only fixed-size member reads."""
    start, end, entries = _directory(source)
    if end - start > MAX_DIRECTORY_BYTES:
        raise ValueError("ZIP central directory is too large")
    if entries > max_entries:
        raise ValueError("too many archive members")

    # Derive the same physical region as ZipFile, including any prepended data.
    source.seek(start)
    count = 0
    while source.tell() < end:
        header = source.read(min(MEMBER_HEADER_BYTES, end - source.tell()))
        if len(header) != MEMBER_HEADER_BYTES or not header.startswith(b"PK\x01\x02"):
            raise BadZipFile("invalid ZIP directory member")
        count += 1
        if count > max_entries:
            raise ValueError("too many archive members")
        name_size, extra_size, comment_size = struct.unpack_from("<HHH", header, 28)
        next_offset = source.tell() + name_size + extra_size + comment_size
        if next_offset > end:
            raise BadZipFile("truncated ZIP directory member")
        source.seek(next_offset)
    if count != entries:
        raise BadZipFile("ZIP directory count mismatch")
