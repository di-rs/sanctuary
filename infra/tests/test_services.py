"""Run the shipped manifests on disposable networks with synthetic inputs."""

import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from infra.control.runtime import Site

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "infra/services"


@pytest.fixture
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    site = "sanctuary-check-" + uuid4().hex[:9]
    values = {
        "SANCTUARY_STATE": str(tmp_path),
        "SITE": site,
        "STATE": str(tmp_path),
        "INSTANCE": str(tmp_path),
        "WEB_ALIAS": "playground",
        "DOCKER_GID": "1",
        "BOXIE_IMAGE": "sanctuary-check/boxie:test",
        "PLAYGROUND_IMAGE": "sanctuary-check/playground:test",
        "TEMPORAL_ADDRESS": "temporal:7233",
        "TEMPORAL_NAMESPACE": "boxie",
        "TEMPORAL_SERVER_NAME": "temporal",
        "PLAYGROUND_HOST": "play.example.net",
        "GRAFANA_HOST": "grafana.example.net",
        "TEMPORAL_HOST": "temporal.example.net",
        "PREVIEW_ZONE": "example.net",
        "ACCESS_TEAM_HOST": "test.cloudflareaccess.com",
        "GRAFANA_ACCESS_AUD": "test-audience",
        "ADMIN_EMAIL": "test@example.net",
        "TUNNEL_TOKEN_FILE": str(tmp_path / "token"),
        "ALERT_WEBHOOK_FILE": str(tmp_path / "webhook"),
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    for path in ("secrets/boxie/endpoints.env", "secrets/temporal/database.env", "web.env"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    return os.environ | values


def compose(env: dict[str, str], component: str, *args: str, sql: str | None = None) -> str:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            env["SITE"] + "-" + component,
            "-f",
            str(SERVICES / f"compose.{component}.yml"),
            *args,
        ],
        env=env,
        text=True,
        input=sql,
        stdout=subprocess.PIPE,
        check=True,
        timeout=240,
    )
    return result.stdout.strip()


def test_compose_boundaries(deployment: dict[str, str]) -> None:
    for manifest in SERVICES.glob("compose.*.yml"):
        services = json.loads(
            compose(
                deployment, manifest.stem.removeprefix("compose."), "config", "--format", "json"
            )
        )["services"]
        for name, service in services.items():
            assert not service.get("ports")
            sources = {v.get("source") for v in service.get("volumes", [])}
            assert ("/var/run/docker.sock" in sources) == (name == "supervisor")
            if name in {"web", "api", "supervisor"}:
                assert service["read_only"] and service["pull_policy"] == "never"
            if name == "grafana":
                assert service["environment"]["GF_AUTH_JWT_ENABLED"] == "true"
                assert (
                    json.loads(service["environment"]["GF_AUTH_JWT_EXPECT_CLAIMS"])["email"]
                    == "test@example.net"
                )


@pytest.fixture
def networks(deployment: dict[str, str]) -> Iterator[None]:
    created = []
    try:
        for kind in ("database", "temporal", "admin"):
            name = deployment["SITE"] + "-" + kind
            subprocess.run(["docker", "network", "create", "--internal", name], check=True)
            created.append(name)
        yield
    finally:
        for name in reversed(created):
            subprocess.run(["docker", "network", "rm", name], check=True)


@pytest.mark.integration
def test_temporal_mtls_and_separate_database_roles(
    deployment: dict[str, str], networks: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = tmp_path / "secrets/postgres/admin"
    admin.parent.mkdir(parents=True)
    admin.write_text("database-test-credential")
    subprocess.run(["sh", str(ROOT / "infra/control/credentials.sh")], env=deployment, check=True)
    # Docker manages database storage so the database user owns its test volume on Linux and macOS.
    override = tmp_path / "pg.yml"
    override.write_text(
        "services:\n  db:\n    volumes:\n      - pg:/var/lib/postgresql\nvolumes:\n  pg: {}\n"
    )

    def pg(*args: str, sql: str | None = None) -> str:
        return compose(deployment, "postgres", "-f", str(override), *args, sql=sql)

    def query(sql: str) -> str:
        return pg(
            "exec", "-T", "db", "psql", "-XqtA", "-U", "postgres", "-v", "ON_ERROR_STOP=1", sql=sql
        )

    site = Site()
    monkeypatch.setattr(site, "psql", query)
    try:
        pg("up", "-d", "--wait", "--wait-timeout", "90")
        password = site.database("temporal", "temporal")
        site.database("temporal", "temporal_visibility")
        site.database("boxie", "boxie")
        site.database("playground_pr_7", "playground_pr_7")
        assert (
            query(
                "SELECT has_database_privilege('playground_pr_7','boxie','CONNECT'),has_database_privilege('temporal','playground_pr_7','CONNECT')"
            )
            == "f|f"
        )
        (tmp_path / "secrets/temporal/database.env").write_text(
            f"POSTGRES_USER=temporal\nPOSTGRES_PWD={password}\n"
        )
        for _ in range(2):
            compose(deployment, "temporal", "run", "--rm", "--no-deps", "schema")
        compose(
            deployment,
            "temporal",
            "up",
            "-d",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "120",
            "temporal",
            "ui",
        )
        command = (
            "run",
            "--rm",
            "--no-deps",
            "-v",
            f"{tmp_path}/tls/operator:/tls:ro",
            "--entrypoint",
            "temporal",
            "schema",
            "operator",
            "cluster",
            "health",
            "--address",
            "temporal:7233",
        )
        for attempt in range(15):
            try:
                compose(
                    deployment,
                    "temporal",
                    *command,
                    "--tls-ca-path",
                    "/tls/ca.pem",
                    "--tls-cert-path",
                    "/tls/cert.pem",
                    "--tls-key-path",
                    "/tls/key.pem",
                    "--tls-server-name",
                    "temporal",
                )
                break
            except subprocess.CalledProcessError:
                if attempt == 14:
                    diagnostics = compose(
                        deployment, "temporal", "logs", "--tail", "16", "temporal"
                    )
                    pytest.fail(diagnostics.replace(password, "[redacted]")[-4000:])
                time.sleep(2)
        with pytest.raises(subprocess.CalledProcessError):
            compose(deployment, "temporal", *command, "--command-timeout", "3s")
    finally:
        compose(deployment, "temporal", "down", "--volumes")
        pg("down", "--volumes")


@pytest.mark.integration
def test_monitoring_vendor_configurations() -> None:
    services = yaml.safe_load((SERVICES / "compose.observability.yml").read_text())["services"]
    directory = SERVICES / "monitoring"

    def check(name: str, arguments: list[str], binary: str | None = None) -> None:
        command = ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/check:ro"]
        if binary:
            command += ["--entrypoint", binary]
        subprocess.run([*command, services[name]["image"], *arguments], check=True, timeout=180)

    check("collector", ["validate", "--config=/check/collector.yml"])
    check("prometheus", ["test", "rules", "/check/rules-test.yml"], "/bin/promtool")
    check("loki", ["-verify-config", "-config.file=/check/loki.yml"])
