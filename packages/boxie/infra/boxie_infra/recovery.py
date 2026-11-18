"""Capture, publish and stage a drained Boxie installation for off-host recovery."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO
from uuid import UUID

DATABASES = {"boxie": "boxie", "temporal": "temporal", "temporal_visibility": "visibility"}
CONFIG = ("boxie", "tls", "boxie.env", "boxie-image.env", "temporal-schema-ready")
RECOVERY_FILES = (
    "boxie/api.json",
    "boxie/supervisor.json",
    "boxie/profiles.json",
    "boxie/consumer.secret",
    "boxie/supervisor.secret",
    "boxie/postgres-dsn.secret",
    "boxie/postgres-password",
    "boxie/boxie-password",
    "boxie/temporal-password",
    "boxie/visibility-password",
    "tls/complete",
    "tls/server/frontend.key",
    "tls/server/internode.key",
    "tls/api/boxie-api.key",
    "tls/supervisor/boxie-supervisor.key",
    "tls/operator/operator.key",
    "tls/ui/ui-client.key",
)
ARCHIVE = "boxie-recovery.tar"
TAG = "boxie-recovery-v1"
DRAINED = """
SELECT NOT (
    EXISTS (SELECT FROM sandboxes WHERE cleaned_at IS NULL)
 OR EXISTS (SELECT FROM capacity_slots WHERE sandbox_id IS NOT NULL)
 OR EXISTS (SELECT FROM sandbox_artifact_refs)
 OR EXISTS (SELECT FROM outbox WHERE delivered_at IS NULL)
 OR EXISTS (SELECT FROM jobs WHERE state IN ('queued', 'starting', 'running'))
 OR EXISTS (
    SELECT FROM sandboxes s LEFT JOIN job_results r ON r.sandbox_id = s.id
    WHERE s.reserved_result_bytes <> coalesce(octet_length(r.stdout) + octet_length(r.stderr), 0)
 )
)
"""
IDLE = """
SELECT NOT EXISTS (
    SELECT FROM pg_stat_activity
    WHERE datname IN ('boxie', 'temporal', 'temporal_visibility')
      AND backend_type = 'client backend'
)
"""
EMPTY = """
SELECT NOT (
    EXISTS (SELECT FROM pg_namespace WHERE nspname NOT IN ('public', 'information_schema')
            AND left(nspname, 3) <> 'pg_')
 OR EXISTS (SELECT FROM pg_class WHERE relnamespace = 'public'::regnamespace)
 OR EXISTS (SELECT FROM pg_proc WHERE pronamespace = 'public'::regnamespace)
 OR EXISTS (SELECT FROM pg_type WHERE typnamespace = 'public'::regnamespace)
 OR EXISTS (SELECT FROM pg_extension WHERE extname <> 'plpgsql')
)
"""


class RecoveryError(RuntimeError):
    """An operation stopped before its recovery guarantees were established."""


def run(
    args: list[str], *, source: IO[bytes] | None = None, output: IO[bytes] | None = None
) -> bytes:
    result = subprocess.run(
        args,
        stdin=source if source is not None else subprocess.DEVNULL,
        stdout=output if output is not None else subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        operation = args[4] if args[:3] == ["docker", "exec", "-i"] else args[1]
        raise RecoveryError(f"{args[0]} {operation} failed (exit {result.returncode})")
    return result.stdout or b""


def pg(container: str, *args: str, **streams: IO[bytes]) -> bytes:
    return run(["docker", "exec", "-i", container, *args], **streams)


def sql(container: str, database: str, query: str) -> str:
    return (
        pg(
            container,
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            database,
            "-c",
            query,
        )
        .decode()
        .strip()
    )


def image(container: str) -> str:
    value = run(["docker", "inspect", "--format", "{{.Config.Image}}", container]).decode().strip()
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value):
        raise RecoveryError("recovery requires digest-pinned images")
    return value


def required(value: bool, message: str) -> None:
    if not value:
        raise RecoveryError(message)


def drain_check(postgres: str, data: Path, identity: Path) -> None:
    required(sql(postgres, "postgres", IDLE) == "t", "database clients are still connected")
    required(sql(postgres, "boxie", DRAINED) == "t", "Boxie work or accounting is unsettled")
    expected = {
        "installation_id": str(UUID((identity / "installation-id").read_text().strip())),
        "host_id": (identity / "host-id").read_text().strip(),
    }
    journal = data / "execution.json"
    if journal.exists() or journal.is_symlink():
        required(journal.is_file() and not journal.is_symlink(), "invalid supervisor journal")
        contents = json.loads(journal.read_bytes())
        required(contents.get("records") == [], "journal is not drained")
        required(contents.get("identity") == expected, "journal identity differs")
    else:
        required(
            sql(
                postgres,
                "boxie",
                "SELECT NOT EXISTS (SELECT FROM jobs UNION ALL SELECT FROM sandboxes)",
            )
            == "t",
            "installation with execution history is missing its journal",
        )
    rows = sql(postgres, "boxie", "SELECT storage_id FROM artifacts WHERE NOT retired")
    for storage in rows.splitlines():
        directory = data / "artifacts" / str(UUID(storage)) / "files"
        required(
            directory.is_dir() and any(path.is_file() for path in directory.rglob("*")),
            "active artifact bytes are missing",
        )


def schemas(postgres: str) -> dict[str, str]:
    return {
        "boxie": sql(postgres, "boxie", "SELECT version_num FROM alembic_version"),
        **{
            name: sql(postgres, name, "SELECT curr_version FROM schema_version")
            for name in ("temporal", "temporal_visibility")
        },
    }


@contextmanager
def stopped_owner(data: Path) -> Iterator[None]:
    lock_path = data / "owner.lock"
    required(lock_path.is_file() and not lock_path.is_symlink(), "supervisor lock is missing")
    with lock_path.open("rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecoveryError("supervisor still owns the data directory") from None
        yield


def archive_entry(member: tarfile.TarInfo) -> tarfile.TarInfo:
    required(member.isfile() or member.isdir(), "capture contains a special file or link")
    return member


@contextmanager
def new_private_directory(path: Path) -> Iterator[None]:
    path.mkdir(mode=0o700)
    try:
        yield
    except BaseException:
        shutil.rmtree(path)
        raise


def capture(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    for source in (args.config, args.data):
        required(not output.is_relative_to(source.resolve()), "capture output overlaps source")
    with stopped_owner(args.data), new_private_directory(args.output):
        for name in RECOVERY_FILES:
            required((args.config / name).is_file(), f"missing deployment file {name}")
        identity = args.config / "boxie"
        installation = str(UUID((identity / "installation-id").read_text().strip()))
        host = (identity / "host-id").read_text().strip()
        remaining = run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=boxie.installation={installation}",
                "--filter",
                f"label=boxie.host={host}",
            ]
        )
        required(not remaining, "the supervisor still has Docker resources")
        required(
            run(["docker", "inspect", "--format", "{{.State.Status}}", args.temporal]).strip()
            == b"exited",
            "Temporal must be stopped",
        )
        recovery_point = datetime.now(UTC).isoformat()
        drain_check(args.postgres, args.data, identity)
        metadata = {
            "format": 1,
            "installation_id": installation,
            "host_id": host,
            "recovery_point": recovery_point,
            "revision": args.revision,
            "postgres_image": image(args.postgres),
            "temporal_image": image(args.temporal),
            "schemas": schemas(args.postgres),
        }
        with (
            tempfile.TemporaryDirectory(dir=args.output) as temporary,
            tarfile.open(args.output / ARCHIVE, "w") as archive,
        ):
            scratch = Path(temporary)
            for name in DATABASES:
                dump = scratch / f"{name}.dump"
                with dump.open("wb") as stream:
                    pg(args.postgres, "pg_dump", "-U", "postgres", "-Fc", "-d", name, output=stream)
                archive.add(dump, f"databases/{dump.name}", filter=archive_entry)
            for name in CONFIG:
                archive.add(args.config / name, f"config/{name}", filter=archive_entry)
            journal = args.data / "execution.json"
            if journal.exists():
                archive.add(journal, "data/execution.json", filter=archive_entry)
            archive.add(args.data / "artifacts", "data/artifacts", filter=archive_entry)
            drain_check(args.postgres, args.data, identity)
            manifest = scratch / "manifest.json"
            manifest.write_text(json.dumps(metadata))
            archive.add(manifest, manifest.name)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def restic_archive(snapshot: str, path: Path) -> None:
    with path.open("xb") as output:
        run(["restic", "dump", "--no-cache", snapshot, f"/{ARCHIVE}"], output=output)


def sha256(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("expected a full SHA-256 identifier")
    return value


def post_ping(path: Path, *, failure: bool, body: bytes = b"") -> None:
    required(not (path.stat().st_mode & 0o077), "monitor URL file must be private")
    url = urllib.parse.urlsplit(path.read_text().strip())
    required(
        url.scheme == "https"
        and bool(url.hostname)
        and not (url.query or url.fragment or url.username or url.password),
        "monitor URL must be HTTPS with no query or fragment",
    )
    endpoint = url.geturl().rstrip("/") + ("/fail" if failure else "")
    request = urllib.request.Request(endpoint, data=body)
    # A redirect can disclose the check's secret and falsely acknowledge success.
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            required(response.status == 200, "monitor rejected the ping")
    except urllib.error.URLError, TimeoutError:
        raise RecoveryError("monitor ping failed") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_302(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: object,
    ) -> None:
        raise RecoveryError("monitor redirected the ping")

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def require_recent(point: str, max_age: int) -> None:
    timestamp = datetime.fromisoformat(point)
    required(timestamp.utcoffset() is not None, "recovery point must include a timezone")
    age = (datetime.now(UTC) - timestamp).total_seconds()
    required(0 <= age <= max_age, "recovery point exceeds configured backup age")


def publish(args: argparse.Namespace) -> None:
    path = args.capture / ARCHIVE
    with tarfile.open(path, "r") as archive:
        manifest = archive.extractfile("manifest.json")
        if manifest is None:
            raise RecoveryError("capture has no manifest")
        metadata = json.load(manifest)
    required(metadata["installation_id"] == str(args.installation), "capture installation differs")
    require_recent(metadata["recovery_point"], args.max_age_seconds)
    expected = digest(path)
    output = run(
        [
            "restic",
            "backup",
            "--json",
            "--host",
            str(args.installation),
            "--tag",
            TAG,
            "--stdin-filename",
            ARCHIVE,
            "--stdin-from-command",
            "--",
            "cat",
            str(path.absolute()),
        ]
    )
    summaries = [
        record
        for line in output.splitlines()
        if (record := json.loads(line)).get("message_type") == "summary"
    ]
    snapshot = sha256(summaries[-1]["snapshot_id"])
    with tempfile.TemporaryDirectory(dir=args.capture) as temporary:
        readback = Path(temporary) / ARCHIVE
        restic_archive(snapshot, readback)
        required(digest(readback) == expected, "off-host readback checksum does not match")
    require_recent(metadata["recovery_point"], args.max_age_seconds)
    receipt = json.dumps(
        {
            "snapshot": snapshot,
            "sha256": expected,
            "recovery_point": metadata["recovery_point"],
            "verified_at": datetime.now(UTC).isoformat(),
        }
    )
    print(receipt, flush=True)
    post_ping(args.ping_file, failure=False, body=receipt.encode())


def receive(args: argparse.Namespace) -> None:
    receipt = json.loads(args.receipt.read_bytes())
    with new_private_directory(args.output):
        archive_path = args.output / ARCHIVE
        restic_archive(sha256(receipt["snapshot"]), archive_path)
        required(digest(archive_path) == sha256(receipt["sha256"]), "archive checksum differs")
        with tarfile.open(archive_path, "r") as archive:
            for member in archive.getmembers():
                archive_entry(member)
            archive.extractall(args.output, filter="data")
        archive_path.unlink()
        metadata = json.loads((args.output / "manifest.json").read_bytes())
        required(
            metadata["format"] == 1 and metadata["recovery_point"] == receipt["recovery_point"],
            "archive manifest does not match the recovery receipt",
        )
        print(json.dumps(metadata))


def restore_databases(args: argparse.Namespace) -> None:
    metadata = json.loads((args.capture / "manifest.json").read_bytes())
    required(image(args.postgres) == metadata["postgres_image"], "wrong PostgreSQL image")
    required(sql(args.postgres, "postgres", IDLE) == "t", "database clients are still connected")
    for name, owner in DATABASES.items():
        actual = sql(
            args.postgres,
            name,
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()",
        )
        required(actual == owner, f"unexpected database owner for {name}")
        required(sql(args.postgres, name, EMPTY) == "t", f"{name} is not empty")
        with (args.capture / "databases" / f"{name}.dump").open("rb") as stream:
            pg(args.postgres, "pg_restore", "--list", source=stream)
    for name in DATABASES:
        with (args.capture / "databases" / f"{name}.dump").open("rb") as stream:
            pg(
                args.postgres,
                "pg_restore",
                "-U",
                "postgres",
                "--single-transaction",
                "-d",
                name,
                source=stream,
            )
    required(schemas(args.postgres) == metadata["schemas"], "restored schemas differ")
    drain_check(args.postgres, args.capture / "data", args.capture / "config/boxie")


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("capture", help="capture the stopped and drained source")
    for option in ("config", "data", "output"):
        command.add_argument(f"--{option}", type=Path, required=True)
    for option in ("postgres", "temporal", "revision"):
        command.add_argument(f"--{option}", required=True)

    command = commands.add_parser("publish", help="store and read back the encrypted capture")
    command.add_argument("--capture", type=Path, required=True)
    command.add_argument("--installation", type=UUID, required=True)
    command.add_argument("--max-age-seconds", type=int, required=True)
    command.add_argument("--ping-file", type=Path, required=True)

    command = commands.add_parser("receive", help="verify and unpack a specific recovery receipt")
    command.add_argument("--receipt", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)

    command = commands.add_parser("restore-databases", help="load three empty databases")
    command.add_argument("--capture", type=Path, required=True)
    command.add_argument("--postgres", required=True)

    command = commands.add_parser("report-failure", help="signal a failed backup to the monitor")
    command.add_argument("--ping-file", type=Path, required=True)

    args = parser.parse_args()
    try:
        match args.command:
            case "capture":
                required(bool(re.fullmatch(r"[0-9a-f]{40}", args.revision)), "invalid revision")
                capture(args)
            case "publish":
                required(args.max_age_seconds > 0, "maximum backup age must be positive")
                publish(args)
            case "receive":
                receive(args)
            case "restore-databases":
                restore_databases(args)
            case "report-failure":
                post_ping(args.ping_file, failure=True)
    except RecoveryError as error:
        parser.exit(1, f"boxie recovery: {error}\n")
    except OSError, tarfile.TarError, ValueError, IndexError, KeyError, TypeError, AttributeError:
        parser.exit(1, "boxie recovery: invalid or unavailable recovery input\n")


if __name__ == "__main__":
    main()
