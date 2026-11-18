"""Boxie package, build context and standalone Compose contracts."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from boxie_test_support.packaging import check_installed_wheel, export_docker_context

ROOT = Path(__file__).resolve().parents[3]
BOXIE = ROOT / "packages/boxie"


def test_operations_manifest_keeps_docker_socket_out_of_operator_jobs() -> None:
    import yaml

    services = yaml.safe_load((ROOT / "packages/boxie/infra/compose.operations.yml").read_text())[
        "services"
    ]
    assert not any(
        "/var/run/docker.sock" in str(service.get("volumes", [])) for service in services.values()
    )


@pytest.mark.integration
def test_docker_context_contains_boxie_without_consumer_sources(tmp_path: Path) -> None:
    context = tmp_path / "context"
    own_source = Path("packages/boxie/src/boxie/__init__.py")
    consumer = Path("tools/cli-playground/src/cli_playground")
    for source in (own_source, consumer / "__init__.py", consumer / "static/stale.js"):
        (context / source).parent.mkdir(parents=True)
        (context / source).write_text("# " + source.name)

    output = export_docker_context(
        ROOT / "packages/boxie/infra/Boxie.Dockerfile", context, tmp_path / "output"
    )
    assert (output / own_source).read_text() == "# __init__.py"
    assert not (output / "tools").exists()


@pytest.mark.integration
def test_real_isolated_installation(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    package = checkout / "packages/boxie"
    package.mkdir(parents=True)
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        shutil.copyfile(ROOT / name, checkout / name)
    for name in ("pyproject.toml", "alembic.ini"):
        shutil.copyfile(BOXIE / name, package / name)
    for name in ("src", "alembic"):
        shutil.copytree(BOXIE / name, package / name)

    check_installed_wheel(
        tmp_path,
        checkout,
        "boxie",
        """
import asyncio
import importlib.util
import sys
from io import StringIO
from pathlib import Path

import boxie
import boxie.bootstrap.api
import boxie.bootstrap.supervisor
import boxie.bootstrap.workers
import boxie.observability.process
import boxie.sandbox.execution.sandbox
import httpx
from alembic import command
from boxie.api.app import ApiConfig, create_app
from boxie.bootstrap.api import ApiProcessConfig
from boxie.observability.telemetry.context import current_request_id
from boxie.observability.telemetry.logging import LogDispatcher
from boxie.persistence.migrate import migration_config
from boxie.sandbox.execution.sandbox import SandboxExecution

assert Path(boxie.__file__).is_relative_to(sys.prefix)
for name in (
    "cli_playground", "cli_playground_infra", "boxie_infra", "boxie_test_support", "pulumi", "pytest",
):
    assert importlib.util.find_spec(name) is None, name

config = migration_config("postgresql://localhost/boxie")
config.output_buffer = StringIO()
assert Path(config.get_main_option("script_location"), "script.py.mako").is_file()
command.upgrade(config, "head", sql=True)
assert "CREATE TABLE sandboxes" in config.output_buffer.getvalue()


class Ports:
    async def ready(self):
        return True


ports = Ports()
app = create_app(
    ApiConfig(release="isolated", consumers={"ordinary-client": b"isolated-secret"}),
    ports,
    ports,
    ports,
)


async def run():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://standalone"
    ) as client:
        for supplied in (None, "11111111-1111-1111-1111-111111111111"):
            headers = {"Authorization": "Bearer isolated-secret"}
            if supplied:
                headers["X-Request-ID"] = supplied
            response = await client.get("/readyz", headers=headers)
            assert response.status_code == 200
            selected = response.headers["x-request-id"]
            assert selected == supplied if supplied else len(selected) == 36
            assert current_request_id() is None


asyncio.run(run())
""",
    )


@pytest.mark.integration
@pytest.mark.parametrize("manifest", ["compose.yml", "compose.production.yml"])
@pytest.mark.parametrize("project_override", [False, True])
def test_resolved_compose_isolated_topology(
    tmp_path: Path, manifest: str, project_override: bool
) -> None:
    values = {
        "BOXIE_IMAGE": "boxie:test",
        "BOXIE_API_CONFIG": str(tmp_path / "api.json"),
        "BOXIE_POSTGRES_DSN_FILE": str(tmp_path / "postgres-dsn.secret"),
        "BOXIE_TEMPORAL_CA_FILE": str(tmp_path / "ca.pem"),
        "BOXIE_API_TEMPORAL_CERT_FILE": str(tmp_path / "api.pem"),
        "BOXIE_API_TEMPORAL_KEY_FILE": str(tmp_path / "api.key"),
        "BOXIE_SUPERVISOR_TEMPORAL_CERT_FILE": str(tmp_path / "supervisor.pem"),
        "BOXIE_SUPERVISOR_TEMPORAL_KEY_FILE": str(tmp_path / "supervisor.key"),
        "BOXIE_SUPERVISOR_CONFIG": str(tmp_path / "supervisor.json"),
        "BOXIE_PROFILES_FILE": str(tmp_path / "profiles.json"),
        "BOXIE_SUPERVISOR_CREDENTIAL_FILE": str(tmp_path / "supervisor.secret"),
        "BOXIE_CONSUMER_CREDENTIAL_FILE": str(tmp_path / "consumer.secret"),
        "BOXIE_DATA_DIR": str(tmp_path / "data"),
        "BOXIE_CONSUMER_NETWORK": "test-consumers",
        "BOXIE_CONTROL_NETWORK": "test-control",
    }
    if project_override:
        values["BOXIE_PROJECT_NAME"] = "operator-boxie"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COMPOSE_", "BOXIE_"))
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-f",
            str(BOXIE / "infra" / manifest),
            "config",
            "--format",
            "json",
        ],
        env={**environment, **values},
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    assert config["name"] == values.get("BOXIE_PROJECT_NAME", "boxie")
    assert set(config["services"]) == {"api", "supervisor"}
    for name, entry in config["services"].items():
        targets = {v["target"]: v["source"] for v in entry.get("volumes", [])}
        assert ("/var/run/docker.sock" in targets) == (name == "supervisor")
        assert not entry.get("ports")
        if name == "supervisor":
            assert targets[values["BOXIE_DATA_DIR"]] == values["BOXIE_DATA_DIR"]
            assert set(entry["networks"]) == {"control"}
        else:
            assert values["BOXIE_DATA_DIR"] not in targets
    assert all(net["external"] for net in config["networks"].values())
    assert all(volume["external"] for volume in config.get("volumes", {}).values())


def test_boxie_configuration_cli_is_product_independent(tmp_path: Path) -> None:
    import subprocess
    import sys

    from boxie.bootstrap.api import load_configuration
    from boxie.bootstrap.config import SupervisorConfig

    supervisor_secret = tmp_path / "supervisor.secret"
    consumer_secret = tmp_path / "consumer.secret"
    for path, value in [
        (supervisor_secret, "test-supervisor-credential"),
        (consumer_secret, "test-consumer-credential"),
    ]:
        path.write_text(value)
        path.chmod(0o600)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "boxie_infra.config",
            "--output",
            str(tmp_path),
            "--data-dir",
            str(tmp_path / "data"),
            "--installation-id",
            "00000000-0000-0000-0000-000000000001",
            "--host-id",
            "generic-host",
            "--consumer-id",
            "generic-consumer",
            "--supervisor-credential",
            str(supervisor_secret),
            "--consumer-credential",
            str(consumer_secret),
        ],
        check=True,
    )
    supervisor = SupervisorConfig.from_file(tmp_path / "supervisor.json")
    api = load_configuration(tmp_path / "api.json")
    assert supervisor.identity.host_id == "generic-host"
    generated = json.loads((tmp_path / "supervisor.json").read_text())
    assert "max_sandboxes" not in generated
    generated["max_sandboxes"] = 4
    (tmp_path / "supervisor.json").write_text(json.dumps(generated))
    with pytest.raises(ValueError, match="extra_forbidden"):
        SupervisorConfig.from_file(tmp_path / "supervisor.json")
    assert api.supervisor_url == "http://supervisor:8091"
    assert "cli-playground" not in (tmp_path / "api.json").read_text().lower()
    assert "cli-playground" not in (tmp_path / "supervisor.json").read_text().lower()


@pytest.mark.parametrize("capacity", [1, 4, 8])
def test_supervisor_configuration_rejects_unsupported_capacity(
    tmp_path: Path, capacity: int
) -> None:
    from boxie.bootstrap.config import SupervisorConfig

    config = tmp_path / "supervisor.json"
    config.write_text(
        json.dumps(
            {
                "data_dir": str(tmp_path),
                "profiles_file": "/etc/boxie/profiles.json",
                "credential_file": "/run/secrets/supervisor",
                "identity": {"installation_id": str(uuid4()), "host_id": "test"},
                "max_sandboxes": capacity,
            }
        )
    )
    with pytest.raises(ValueError, match="extra_forbidden"):
        SupervisorConfig.from_file(config)
