"""Installation credentials are stable, private, and never silently repaired."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "packages/boxie/infra/credentials.sh"


def credentials(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), str(directory)], text=True, capture_output=True)


def test_configuration_rerun_preserves_job_policy_and_consumer_credentials(tmp_path: Path) -> None:
    generate = [
        sys.executable,
        str(ROOT / "packages/boxie/infra/boxie_infra/config.py"),
        "--output",
        str(tmp_path),
        "--data-dir",
        str(tmp_path / "data"),
        "--installation-id",
        "00000000-0000-0000-0000-000000000001",
        "--host-id",
        "host",
    ]
    first = [*generate, "--consumer-id", "first"]
    subprocess.run([*first, "--consumer-credential", "/run/secrets/first"], check=True)
    api, supervisor = tmp_path / "api.json", tmp_path / "supervisor.json"
    assert not json.loads(api.read_text())["job_policy"].get("profile_grants")
    subprocess.run(
        [
            *generate,
            "--consumer-id",
            "second",
            "--consumer-credential",
            "/run/secrets/second",
            "--job-profile",
            "exports",
        ],
        check=True,
    )
    settings = json.loads(api.read_text())
    policy = {
        "profile_grants": {"first": ["reports"], "second": ["exports"]},
        "consumer_result_bytes": 4096,
        "total_downloads": 1,
    }
    settings["job_policy"] = policy
    api.write_text(json.dumps(settings))
    limits = {"max_seconds": 120, "idle_seconds": 30, "disconnect_seconds": 15}
    supervisor.write_text(
        json.dumps({**json.loads(supervisor.read_text()), "policy_maximum": limits})
    )

    subprocess.run(first, check=True)
    assert json.loads(api.read_text()) == settings
    assert json.loads(supervisor.read_text())["policy_maximum"] == limits

    subprocess.run([*first, "--job-profile", "print", "--job-profile", "lint"], check=True)
    updated = json.loads(api.read_text())
    assert updated["job_policy"] == {
        **policy,
        "profile_grants": {"first": ["print", "lint"], "second": ["exports"]},
    }
    assert updated["consumer_credential_files"] == {
        "first": "/run/secrets/first",
        "second": "/run/secrets/second",
    }
    failed = subprocess.run(
        [*generate, "--consumer-id", "third", "--consumer-credential", "/run/secrets/second"],
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 2 and "distinct --consumer-credential" in failed.stderr
    assert json.loads(api.read_text()) == updated


def test_generated_credentials_survive_rerun_without_output(tmp_path: Path) -> None:
    directory = tmp_path / "boxie"
    first = credentials(directory)
    assert first.returncode == 0, first.stderr
    before = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    assert "preview-token" not in before
    assert len(before["consumer.secret"].strip()) >= 48
    assert before["consumer.secret"] != before["supervisor.secret"]
    (tmp_path / "data").write_text("persistent sentinel")
    second = credentials(directory)
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout == ""
    assert before == {
        path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()
    }
    assert (tmp_path / "data").read_text() == "persistent sentinel"
    assert all(path.stat().st_mode & 0o077 == 0 for path in directory.iterdir() if path.is_file())


def test_partial_credentials_fail_without_changing_any_file(tmp_path: Path) -> None:
    directory = tmp_path / "boxie"
    directory.mkdir(mode=0o700)
    secret = directory / "consumer.secret"
    secret.write_text("existing-secret")
    secret.chmod(0o600)
    result = credentials(directory)
    assert result.returncode == 1
    assert "partial" in result.stderr.lower()
    assert secret.read_text() == "existing-secret"
    assert set(directory.iterdir()) == {secret}
    assert "existing-secret" not in result.stdout + result.stderr


def test_credentials_refuse_symlink_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    result = credentials(link)
    assert result.returncode == 1
    assert not list(target.iterdir())


@pytest.mark.parametrize("mode", [0o644, 0o640])
def test_credentials_reject_group_or_world_readable_files(tmp_path: Path, mode: int) -> None:
    directory = tmp_path / "boxie"
    assert credentials(directory).returncode == 0
    secret = directory / "consumer.secret"
    secret.chmod(mode)
    result = credentials(directory)
    assert result.returncode == 1
    assert "private" in result.stderr.lower()
    assert secret.stat().st_mode & 0o777 == mode


def test_failed_certificate_generation_leaves_no_final_directory(tmp_path: Path) -> None:
    root = tmp_path / "tls"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    openssl = fake_bin / "openssl"
    openssl.write_text("#!/bin/sh\nexit 17\n")
    openssl.chmod(0o755)
    script = ROOT / "packages/boxie/infra/certificates.sh"
    failed = subprocess.run(
        ["bash", str(script), str(root), str(os.getuid()), str(os.getgid())],
        env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 17
    assert not root.exists()
    assert not list(tmp_path.glob("tls.new.*"))
    retry = subprocess.run(
        ["bash", str(script), str(root), str(os.getuid()), str(os.getgid())],
        capture_output=True,
        text=True,
    )
    assert retry.returncode == 0, retry.stderr
    assert (root / "complete").is_file()


def test_certificates_have_separate_identities_and_private_ca(tmp_path: Path) -> None:
    root = tmp_path / "tls"
    command = [
        "bash",
        str(ROOT / "packages/boxie/infra/certificates.sh"),
        str(root),
        str(os.getuid()),
        str(os.getgid()),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    keys = [
        root / name / file
        for name, file in (
            ("server", "frontend.key"),
            ("server", "internode.key"),
            ("api", "boxie-api.key"),
            ("supervisor", "boxie-supervisor.key"),
            ("ui", "ui-client.key"),
            ("operator", "operator.key"),
        )
    ]
    key_contents = {key: key.read_bytes() for key in keys}
    assert len(set(key_contents.values())) == 6
    assert not any(path.name.endswith(".key") for path in (root / "server").glob("*ca*"))
    check = subprocess.run(
        [
            "openssl",
            "verify",
            "-CAfile",
            str(root / "server/client-ca.pem"),
            str(root / "api/boxie-api.pem"),
        ],
        capture_output=True,
    )
    assert check.returncode == 0
    assert all(key.stat().st_mode & 0o077 == 0 for key in keys)

    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert {key: key.read_bytes() for key in keys} == key_contents

    internode_key = root / "server/internode.key"
    internode_key.unlink()
    assert subprocess.run(command, capture_output=True, text=True).returncode == 1
    assert not internode_key.exists()


def test_temporal_schema_setup_can_resume_one_database(tmp_path: Path) -> None:
    command = tmp_path / "temporal-sql-tool"
    command.write_text('#!/bin/sh\nprintf "%s:%s\\n" "$SQL_DATABASE" "$*" >> "$COMMAND_LOG"\n')
    command.chmod(0o755)
    log = tmp_path / "calls"
    result = subprocess.run(
        ["sh", str(ROOT / "packages/boxie/infra/temporal/schema.sh"), "setup", "visibility"],
        env={
            **os.environ,
            "PATH": str(tmp_path) + ":" + os.environ["PATH"],
            "COMMAND_LOG": str(log),
            "TEMPORAL_DB_PASSWORD": "secret1",
            "VISIBILITY_DB_PASSWORD": "secret2",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        "temporal_visibility:setup-schema -v 0.0",
        "temporal_visibility:update-schema -d /etc/temporal/schema/postgresql/v12/visibility/versioned",
    ]


def test_boxie_render_seeds_default_shell_without_product_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from boxie_infra.installation import render

    directory = tmp_path / "boxie"
    assert credentials(directory).returncode == 0
    for name in (
        "BOXIE_IMAGE",
        "BOXIE_SANDBOX_IMAGE",
        "OBS_COLLECTOR_IMAGE",
        "OBS_JOURNAL_GROUP_GID",
        "OPERATOR_GRAFANA_HOSTNAME",
        "OPERATOR_TUNNEL_ID",
        "OPERATOR_TEAM_NAME",
        "OPERATOR_TEMPORAL_HOSTNAME",
        "OPERATOR_GRAFANA_AUDIENCE",
        "OPERATOR_TEMPORAL_AUDIENCE",
    ):
        monkeypatch.setenv(name, "setting")
    for name in tuple(os.environ):
        if name.startswith("CLI_PLAYGROUND_") or name in {"ACME_EMAIL", "CLOUDFLARE_DNS_API_TOKEN"}:
            monkeypatch.delenv(name)
    render(tmp_path, ROOT)
    assert json.loads((directory / "profiles.json").read_text()) == {
        "default": {
            "image_digest": "setting",
            "commands": [["/opt/boxie/shell.sh"]],
            "env": {"TERM": ["xterm-256color"]},
            "artifact_target": "/opt/artifact",
        }
    }
    assert (tmp_path / "boxie.env").is_file()
    assert not (tmp_path / "cli-playground.env").exists()
