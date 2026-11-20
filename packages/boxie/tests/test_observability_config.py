"""Integration boundaries for the committed native monitoring configuration."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

INFRA = Path(__file__).parents[1] / "infra"


def test_upstream_images_keep_version_tags_and_immutable_digests() -> None:
    monitoring = yaml.safe_load((INFRA / "observability/compose.yml").read_text())["services"]
    ingress = yaml.safe_load((INFRA / "ingress/compose.yml").read_text())["services"]
    for name, service in (monitoring | ingress).items():
        if name == "vector":
            continue  # The collector is built locally or supplied by the operator.
        assert re.fullmatch(r"[^\s@]+:[^\s:@]+@sha256:[a-f0-9]{64}", service["image"])
    collector = (INFRA / "observability/collector/Dockerfile").read_text()
    assert f"FROM {monitoring['storage-init']['image']} AS vector\n" in collector


def test_setup_recreates_only_prometheus_after_starting_observability(tmp_path: Path) -> None:
    installer = (INFRA / "install.sh").read_text()
    observability_commands = "\n".join(
        line for line in installer.splitlines() if '"$owner/observability/compose.yml" up' in line
    )
    timeout = tmp_path / "timeout"
    calls = tmp_path / "calls"
    timeout.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {str(calls)!r}\n")
    timeout.chmod(0o755)
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", observability_commands],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "owner": "/host",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    commands = calls.read_text().splitlines()
    assert len(commands) == 2
    assert commands[0].endswith("up -d --no-build --wait --wait-timeout 150")
    assert commands[1].endswith(
        "up -d --no-build --no-deps --force-recreate --wait --wait-timeout 150 prometheus"
    )


def compose(*files: Path) -> dict[str, Any]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OBS_", "OPERATOR_", "COMPOSE_"))
    }
    env.update(
        {
            key: "/tmp/boxie-test"
            for key in (
                "BOXIE_API_CONFIG",
                "BOXIE_SUPERVISOR_CONFIG",
                "BOXIE_PROFILES_FILE",
                "BOXIE_DATA_DIR",
                "BOXIE_SUPERVISOR_CREDENTIAL_FILE",
                "BOXIE_CONSUMER_CREDENTIAL_FILE",
                "BOXIE_POSTGRES_DSN_FILE",
                "BOXIE_TEMPORAL_CA_FILE",
                "BOXIE_API_TEMPORAL_CERT_FILE",
                "BOXIE_API_TEMPORAL_KEY_FILE",
                "BOXIE_SUPERVISOR_TEMPORAL_CERT_FILE",
                "BOXIE_SUPERVISOR_TEMPORAL_KEY_FILE",
                "TEMPORAL_CERTS_DIR",
                "TEMPORAL_OPERATOR_CERTS_DIR",
                "TEMPORAL_UI_CERTS_DIR",
            )
        }
    )
    env.update(
        BOXIE_CONTROL_NETWORK="control",
        BOXIE_CONSUMER_NETWORK="consumer",
        BOXIE_IMAGE="boxie:test",
        TEMPORAL_DB_PASSWORD="test",
        VISIBILITY_DB_PASSWORD="test",
        OBS_GRAFANA_HOSTNAME="grafana.example.com",
        OBS_GRAFANA_ADMIN_PASSWORD_FILE="/tmp/grafana-secret",
        OBS_GRAFANA_PLUGIN_DIR="/tmp/plugins",
        OBS_PROMETHEUS_CONFIG_FILE="/tmp/prometheus.yml",
        OBS_JOURNAL_GROUP_GID="190",
    )
    args = ["docker", "compose"]
    for file in files:
        args += ["-f", str(file)]
    result = subprocess.run(
        args + ["config", "--format", "json"],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    return json.loads(result.stdout)  # type: ignore[no-any-return]


@pytest.mark.parametrize("manifest", ["compose.yml", "compose.production.yml"])
def test_application_deploys_without_monitoring(manifest: str) -> None:
    base = compose(INFRA / manifest)
    assert set(base["networks"]) == {"consumer", "control"}
    monitored = compose(INFRA / manifest, INFRA / "compose.observability.yml")
    for role in ("api", "supervisor"):
        assert "metrics" in monitored["services"][role]["networks"]
        assert not monitored["services"][role].get("ports")


def test_monitoring_has_private_origins_independent_storage_and_bounded_defaults() -> None:
    config = compose(INFRA / "observability/compose.yml")
    assert len({volume["name"] for volume in config["volumes"].values()}) == 4
    for service in config["services"].values():
        assert not service.get("ports")
        assert not any("docker.sock" in mount["target"] for mount in service.get("volumes", []))
        assert int(service["mem_limit"]) > 0
    grafana = config["services"]["grafana"]
    assert int(grafana["mem_limit"]) == 268435456
    assert grafana["environment"]["GF_SERVER_ROOT_URL"] == "https://grafana.example.com"
    assert grafana["environment"]["GF_SECURITY_COOKIE_SECURE"] == "true"
    assert (
        "-retention.maxDiskSpaceUsageBytes=268435456"
        in config["services"]["victorialogs"]["command"]
    )
    assert all(not volume.get("external", False) for volume in config["volumes"].values())


def test_grafana_provisions_both_datasources_and_correlated_dashboard() -> None:
    root = INFRA / "observability/grafana"
    data = yaml.safe_load((root / "provisioning/datasources/operators.yml").read_text())
    assert {source["url"] for source in data["datasources"]} == {
        "http://prometheus:9090",
        "http://victorialogs:9428",
    }
    provider = yaml.safe_load((root / "provisioning/dashboards/operators.yml").read_text())
    assert provider["providers"][0]["options"]["path"] == "/etc/grafana/dashboards"
    dashboard = json.loads((root / "dashboards/boxie.json").read_text())
    assert {variable["name"] for variable in dashboard["templating"]["list"]} >= {
        "request_id",
        "sandbox_id",
    }
    assert {panel["datasource"]["uid"] for panel in dashboard["panels"]} == {
        "boxie-prometheus",
        "boxie-victorialogs",
    }


def test_temporal_monitoring_is_optional_and_origins_stay_private() -> None:
    base = compose(INFRA / "temporal/compose.yml")
    assert set(base["networks"]) == {"control"}
    monitored = compose(
        INFRA / "temporal/compose.yml", INFRA / "temporal/compose.observability.yml"
    )
    assert "metrics" in monitored["services"]["temporal"]["networks"]
    assert "operator-origin" in monitored["services"]["ui"]["networks"]
    assert all(not service.get("ports") for service in monitored["services"].values())


def test_installation_renders_metrics_and_distinct_operator_audiences(tmp_path: Path) -> None:
    credentials = tmp_path / "boxie"
    credentials.mkdir()
    for name in (
        "host-id",
        "installation-id",
        "postgres-password",
        "boxie-password",
        "temporal-password",
        "visibility-password",
    ):
        (credentials / name).write_text(f"test-{name}\n")
    image = "ghcr.io/test/sandbox@sha256:" + "a" * 64
    tunnel = "00000000-0000-0000-0000-000000000001"
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(INFRA / "boxie_infra/installation.py"),
            str(INFRA.parents[2]),
        ],
        env={
            **os.environ,
            "SANCTUARY_CONFIG_DIR": str(tmp_path),
            "BOXIE_IMAGE": "boxie:test",
            "BOXIE_SANDBOX_IMAGE": image,
            "OBS_COLLECTOR_IMAGE": "collector:test",
            "OBS_JOURNAL_GROUP_GID": "190",
            "OPERATOR_TUNNEL_ID": tunnel,
            "OPERATOR_TEAM_NAME": "operators",
            "OPERATOR_GRAFANA_HOSTNAME": "grafana.example.com",
            "OPERATOR_TEMPORAL_HOSTNAME": "temporal.example.com",
            "OPERATOR_GRAFANA_AUDIENCE": "grafana-aud",
            "OPERATOR_TEMPORAL_AUDIENCE": "temporal-aud",
        },
        check=True,
        timeout=15,
    )

    settings = tmp_path / "boxie.env"
    profiles = credentials / "profiles.json"
    for private in (settings, profiles):
        assert private.stat().st_mode & 0o777 == 0o600
    assert "POSTGRES_PASSWORD='test-postgres-password'\n" in settings.read_text()
    assert json.loads(profiles.read_text())["default"]["image_digest"] == image

    prometheus, ingress = tmp_path / "prometheus.yml", tmp_path / "cloudflared.yml"
    for public in (prometheus, ingress):
        assert public.stat().st_mode & 0o777 == 0o644
    scrapes = {
        job["job_name"]: job for job in yaml.safe_load(prometheus.read_text())["scrape_configs"]
    }
    for role in ("api", "supervisor"):
        filters = scrapes[f"boxie-{role}-sdk"]["metric_relabel_configs"]
        assert {"source_labels": ["namespace"], "regex": "boxie|", "action": "keep"} in filters
        assert {
            "source_labels": ["task_queue"],
            "regex": "boxie/test-installation-id/test-host-id/(lifecycle|maintenance)|",
            "action": "keep",
        } in filters

    config = yaml.safe_load(ingress.read_text())
    assert config["tunnel"] == tunnel
    assert config["credentials-file"] == "/run/secrets/tunnel.json"
    assert config["ingress"][-1] == {"service": "http_status:404"}
    assert len(config["ingress"]) == 3
    for route, hostname, service, audience in zip(
        config["ingress"][:2],
        ["grafana.example.com", "temporal.example.com"],
        ["http://grafana:3000", "http://temporal-ui:8080"],
        ["grafana-aud", "temporal-aud"],
        strict=True,
    ):
        assert route == {
            "hostname": hostname,
            "service": service,
            "originRequest": {
                "access": {"required": True, "teamName": "operators", "audTag": [audience]}
            },
        }
