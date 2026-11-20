import argparse
import ast
import json
import os
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO
from uuid import uuid4

import pytest
from boxie.sandbox.execution.ownership import acquire_owner_lock
from boxie_infra import recovery


def test_operator_tool_parses_on_python_312() -> None:
    assert recovery.__file__ is not None
    ast.parse(Path(recovery.__file__).read_text(), feature_version=(3, 12))


@pytest.fixture(scope="module")
def deployed_tls(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tls = tmp_path_factory.mktemp("recovery-keys") / "tls"
    script = Path(recovery.__file__).resolve().parents[1] / "certificates.sh"
    subprocess.run(["bash", str(script), str(tls), str(os.getuid()), str(os.getgid())], check=True)
    return tls


def test_recovery_inventory_covers_deployed_certificates(deployed_tls: Path) -> None:
    assert recovery.tls_files() == {
        path.relative_to(deployed_tls)
        for path in deployed_tls.rglob("*")
        if path.suffix in {".key", ".pem"}
    }


@pytest.mark.parametrize(
    "name", ["api/boxie-api.pem", "api/frontend-ca.pem", "server/client-ca.pem", "ca/client.key"]
)
@pytest.mark.parametrize("empty", [False, True])
def test_capture_rejects_incomplete_tls(
    tmp_path: Path, deployed_tls: Path, name: str, empty: bool
) -> None:
    config, data, output = tmp_path / "config", tmp_path / "data", tmp_path / "capture"
    shutil.copytree(deployed_tls, config / "tls")
    for filename in recovery.RECOVERY_FILES:
        path = config / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    data.mkdir()
    (data / "owner.lock").touch()
    missing = config / "tls" / name
    if empty:
        missing.write_bytes(b"")
    else:
        missing.unlink()
    with pytest.raises(recovery.RecoveryError, match=f"missing or empty TLS file {name}"):
        recovery.capture(argparse.Namespace(config=config, data=data, output=output))
    assert not output.exists()


def test_running_supervisor_prevents_capture(tmp_path: Path) -> None:
    with (
        acquire_owner_lock(tmp_path),
        pytest.raises(recovery.RecoveryError, match="still owns"),
        recovery.stopped_owner(tmp_path),
    ):
        pytest.fail("capture acquired the active supervisor's lock")


def test_unsettled_work_prevents_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def sql(container: str, database: str, query: str) -> str:
        assert container == "source"
        assert (database, query) in {("postgres", recovery.IDLE), ("boxie", recovery.DRAINED)}
        return "t" if query == recovery.IDLE else "f"

    monkeypatch.setattr(recovery, "sql", sql)
    with pytest.raises(recovery.RecoveryError, match="accounting is unsettled"):
        recovery.drain_check("source", tmp_path, tmp_path)


def test_publish_requires_readback_before_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = tmp_path / "manifest.json"
    installation = uuid4()
    metadata.write_text(
        json.dumps(
            {"installation_id": str(installation), "recovery_point": datetime.now(UTC).isoformat()}
        )
    )
    with tarfile.open(tmp_path / recovery.ARCHIVE, "w") as archive:
        archive.add(metadata, metadata.name)
    snapshot = "a" * 64

    def restic_backup(args: list[str]) -> bytes:
        assert args[:3] == ["restic", "backup", "--json"]
        return json.dumps({"message_type": "summary", "snapshot_id": snapshot}).encode()

    def bad_readback(identifier: str, target: Path) -> None:
        assert identifier == snapshot
        target.write_bytes(b"different bytes")

    def ping(path: Path, *, failure: bool, body: bytes = b"") -> None:
        pytest.fail("backup issued a success ping before checksum verification")

    monkeypatch.setattr(recovery, "run", restic_backup)
    monkeypatch.setattr(recovery, "restic_archive", bad_readback)
    monkeypatch.setattr(recovery, "post_ping", ping)
    args = argparse.Namespace(
        capture=tmp_path,
        installation=installation,
        max_age_seconds=120,
        ping_file=tmp_path / "ping",
    )
    with pytest.raises(recovery.RecoveryError, match="readback checksum"):
        recovery.publish(args)


def test_stale_capture_cannot_refresh_monitor() -> None:
    old = datetime.now(UTC) - timedelta(minutes=5)
    with pytest.raises(recovery.RecoveryError, match="exceeds configured backup age"):
        recovery.require_recent(old.isoformat(), 60)


def test_receive_cleans_partial_output_when_checksum_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "receipt.json"
    output = tmp_path / "out"
    snapshot = "a" * 64
    receipt.write_text(json.dumps({"snapshot": snapshot, "sha256": "b" * 64}))

    def readback(identifier: str, target: Path) -> None:
        assert identifier == snapshot
        target.write_bytes(b"different bytes")

    monkeypatch.setattr(recovery, "restic_archive", readback)
    with pytest.raises(recovery.RecoveryError, match="archive checksum differs"):
        recovery.receive(argparse.Namespace(receipt=receipt, output=output))
    assert not output.exists()


def test_restore_checks_every_database_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    postgres_image = "postgres@sha256:" + "a" * 64
    (tmp_path / "manifest.json").write_text(json.dumps({"postgres_image": postgres_image}))
    (tmp_path / "databases").mkdir()
    for database in recovery.DATABASES:
        (tmp_path / "databases" / f"{database}.dump").touch()
    monkeypatch.setattr(recovery, "image", lambda _: postgres_image)
    archives_checked = []

    def sql(container: str, database: str, query: str) -> str:
        assert container == "target"
        if query == recovery.IDLE:
            return "t"
        if query == recovery.EMPTY:
            return "f" if database == "temporal_visibility" else "t"
        return recovery.DATABASES[database]

    def pg(container: str, *command: str, source: IO[bytes]) -> bytes:
        assert container == "target"
        assert command == ("pg_restore", "--list")
        archives_checked.append(Path(os.fsdecode(source.name)).name)
        return b""

    monkeypatch.setattr(recovery, "sql", sql)
    monkeypatch.setattr(recovery, "pg", pg)
    with pytest.raises(recovery.RecoveryError, match="temporal_visibility is not empty"):
        recovery.restore_databases(argparse.Namespace(postgres="target", capture=tmp_path))
    assert archives_checked == ["boxie.dump", "temporal.dump"]
