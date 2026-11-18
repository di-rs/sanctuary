"""Trusted profile reloads freeze admitted versions and reject unsafe configuration."""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from boxie.contracts.jobs import CreateJob
from boxie.domain.errors import BoxieError
from boxie.domain.models import LifetimePolicy
from boxie.sandbox.profiles import ProfileRegistry
from boxie.sandbox.transport.client import SupervisorClient
from boxie_test_support.supervisor import AUTH, IMAGE, configuration
from boxie_test_support.terminal_network import network


def test_reload_is_atomic_and_retains_approved_snapshot(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    profiles = ProfileRegistry(config.profiles_file, config.data_dir / "profiles")
    original = profiles.resolve_profile("shell", ("/bin/sh",), {"TERM": "xterm-256color"})
    assert original.image_digest == IMAGE
    data = json.loads(config.profiles_file.read_text())
    data["shell"]["image_digest"] = "example.org/shell@sha256:" + "2" * 64
    config.profiles_file.write_text(json.dumps(data))
    profiles.reload()
    assert profiles.resolve_profile("shell", ("/bin/sh",), {}).image_digest != IMAGE
    assert profiles.validate_snapshot(original) == original
    restarted = ProfileRegistry(config.profiles_file, config.data_dir / "profiles")
    assert restarted.validate_snapshot(original) == original
    data["shell"]["limits"] = {"memory_bytes": 536870913}
    config.profiles_file.write_text(json.dumps(data))
    with pytest.raises(BoxieError):
        profiles.reload()
    assert profiles.resolve_profile("shell", ("/bin/sh",), {}).image_digest.endswith("2" * 64)


@pytest.mark.parametrize(
    "patch",
    [
        {"image_digest": "shell:latest"},
        {"artifact_target": "/etc"},
        {"commands": []},
        {"commands": [[""]]},
        {"env": {"BAD=KEY": ["value"]}},
        {"runtime": "runc"},
        {"limits": {"output_bytes": 0}},
    ],
)
def test_invalid_profiles_fail_closed(tmp_path: Path, patch: dict[str, object]) -> None:
    config = configuration(tmp_path)
    data = json.loads(config.profiles_file.read_text())
    data["shell"].update(patch)
    config.profiles_file.write_text(json.dumps(data))
    with pytest.raises(BoxieError):
        ProfileRegistry(config.profiles_file, config.data_dir / "profiles")


def test_local_content_addressed_image_is_approved(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    data = json.loads(config.profiles_file.read_text())
    data["shell"]["image_digest"] = "sha256:" + "3" * 64
    config.profiles_file.write_text(json.dumps(data))
    profiles = ProfileRegistry(config.profiles_file, config.data_dir / "profiles")
    assert profiles.resolve_profile("shell", ("/bin/sh",), {}).image_digest == "sha256:" + "3" * 64


def test_job_profile_resolution_fits_a_full_size_command(tmp_path: Path) -> None:
    async def exercise() -> None:
        async with network(tmp_path) as net:
            job = CreateJob(
                artifact_id=uuid4(), profile_id="batch", command=("/bin/true", *(["x" * 4086] * 16))
            )
            assert 65500 < len(job.model_dump_json().encode()) <= 65536
            net.config.profiles_file.write_text(
                json.dumps({"batch": {"image_digest": IMAGE, "commands": [job.command]}})
            )
            net.supervisor.profiles.reload()
            policy = LifetimePolicy(max_seconds=900, idle_seconds=300, disconnect_seconds=60)
            net.supervisor.config = net.config.model_copy(update={"policy_maximum": policy})
            async with (
                httpx.AsyncClient(base_url=net.supervisor_url, headers=AUTH) as control,
                SupervisorClient(net.supervisor_url, b"supervisor-test-secret") as resolver,
            ):
                approval = await control.post(
                    "/v1/profiles/resolve-job",
                    json=job.model_dump(mode="json", exclude={"artifact_id"}),
                )
                assert approval.status_code == 200 and len(approval.content) < 1024
                snapshot, effective = await resolver.resolve_admission(job.domain())
                assert snapshot.command == job.command and effective == policy
                assert (snapshot, effective) == await net.supervisor.resolve_admission(job.domain())

    asyncio.run(exercise())


@pytest.mark.integration
def test_service_sighup_reload_is_atomic(
    tmp_path: Path, postgres_dsn: str, temporal_stack: Any
) -> None:
    import signal
    import socket
    import sys

    async def exercise() -> None:
        from boxie.persistence.migrate import migrate
        from database_support import MIGRATIONS

        await asyncio.to_thread(migrate, postgres_dsn, MIGRATIONS)
        config = configuration(tmp_path)
        dsn_file = tmp_path / "postgres.secret"
        dsn_file.write_text(postgres_dsn)
        dsn_file.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        settings = tmp_path / "supervisor.json"
        settings.write_text(
            json.dumps(
                {
                    "data_dir": str(config.data_dir),
                    "profiles_file": str(config.profiles_file),
                    "credential_file": str(config.credential_file),
                    "identity": {
                        "installation_id": str(config.identity.installation_id),
                        "host_id": "host-1",
                    },
                    "bind_port": port,
                    "lifecycle": {
                        "postgres_dsn_file": str(dsn_file),
                        "temporal_address": temporal_stack.address,
                        "temporal_server_name": "temporal",
                        "temporal_ca_file": str(temporal_stack.root / "clients/frontend-ca.pem"),
                        "temporal_cert_file": str(
                            temporal_stack.root / "clients/boxie-supervisor.pem"
                        ),
                        "temporal_key_file": str(
                            temporal_stack.root / "clients/boxie-supervisor.key"
                        ),
                    },
                }
            )
        )
        with (tmp_path / "supervisor.log").open("wb") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "boxie.bootstrap.supervisor",
                "--config",
                str(settings),
                stdout=log,
                stderr=log,
            )
            try:
                async with httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{port}", headers=AUTH
                ) as client:
                    payload = {"profile_id": "shell", "command": ["/bin/sh"], "env": {}}
                    for _ in range(200):
                        try:
                            first = await client.post("/v1/profiles/resolve", json=payload)
                            break
                        except httpx.ConnectError:
                            await asyncio.sleep(0.01)
                    else:
                        raise AssertionError((tmp_path / "supervisor.log").read_text())
                    assert first.json()["image_digest"] == IMAGE
                    data = json.loads(config.profiles_file.read_text())
                    replacement = "sha256:" + "4" * 64
                    data["shell"]["image_digest"] = replacement
                    config.profiles_file.write_text(json.dumps(data))
                    process.send_signal(signal.SIGHUP)
                    for _ in range(200):
                        result = await client.post("/v1/profiles/resolve", json=payload)
                        if result.json()["image_digest"] == replacement:
                            break
                        await asyncio.sleep(0.01)
                    assert result.json()["image_digest"] == replacement
                    config.profiles_file.write_text('{"shell":{"image_digest":"untrusted:tag"}}')
                    process.send_signal(signal.SIGHUP)
                    await asyncio.sleep(0.05)
                    assert (await client.post("/v1/profiles/resolve", json=payload)).json()[
                        "image_digest"
                    ] == replacement
            finally:
                if process.returncode is None:
                    process.terminate()
                await asyncio.wait_for(process.wait(), 5)
        assert "supervisor-test-secret" not in (tmp_path / "supervisor.log").read_text()

    asyncio.run(exercise())
