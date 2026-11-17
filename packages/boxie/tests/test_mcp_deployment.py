"""MCP credentials and private deployment boundaries."""

import io
import json
import os
import selectors
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import pytest
import yaml
from boxie_infra.mcp import provision

INFRA = Path(__file__).parents[1] / "infra"


def mcp_probe(command: list[str], tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Exercise the stdio handshake, tool discovery and one call with a deadline."""
    name = "sanctuary-mcp-probe-" + uuid4().hex[:12]
    assert command[:2] == ["docker", "run"]
    command = command[:2] + ["--name", name] + command[2:]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors
        )
        assert process.stdin is not None and process.stdout is not None
        pending = b""
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        def exchange(identifier: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
            nonlocal pending
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(
                (
                    json.dumps(
                        {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}
                    )
                    + "\n"
                ).encode()
            )
            process.stdin.flush()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    response: dict[str, Any] = json.loads(line)
                    if response.get("id") == identifier:
                        assert "error" not in response, response
                        result: dict[str, Any] = response["result"]
                        return result
                if selector.select(timeout=max(0, deadline - time.monotonic())):
                    data = os.read(process.stdout.fileno(), 65536)
                    assert data, "MCP process closed stdout before responding"
                    pending += data
            raise AssertionError("MCP response deadline exceeded")

        try:
            exchange(
                1,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "sanctuary-test", "version": "1"},
                },
            )
            process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            process.stdin.flush()
            listing = exchange(2, "tools/list", {})
            names = {entry["name"] for entry in listing["tools"]}
            assert tool in names
            assert not names.intersection(
                {"start_workflow", "terminate_workflow", "update_dashboard"}
            )
            result = exchange(3, "tools/call", {"name": tool, "arguments": arguments})
            assert not result.get("isError"), result
            return result
        finally:
            selector.close()
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, timeout=20)
            process.kill()
            process.wait(timeout=15)
            process.stdin.close()
            process.stdout.close()


def test_mcp_containers_have_no_public_ports_or_host_control() -> None:
    config = yaml.safe_load((INFRA / "mcp/compose.yml").read_text())
    for service in config["services"].values():
        assert not service.get("ports")
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert not any("docker.sock" in mount for mount in service["volumes"])
    assert config["services"]["grafana"]["networks"] == ["grafana-origin"]
    assert config["services"]["temporal"]["networks"] == ["control"]
    temporal = yaml.safe_load((INFRA / "mcp/temporal.yaml").read_text())
    assert temporal["targets"][0]["payload_handling"] == "omit"
    assert temporal["targets"][0]["namespace"] == "boxie"


def responses(*values: object) -> MagicMock:
    opener = MagicMock()
    opener.open.side_effect = [io.BytesIO(json.dumps(value).encode()) for value in values]
    return opener


def test_provision_creates_viewer_and_private_token(tmp_path: Path) -> None:
    password = tmp_path / "password"
    password.write_text("private-admin-password")
    token = tmp_path / "token"
    opener = responses(
        {"serviceAccounts": []},
        {"id": 7, "role": "Viewer", "login": "sa-sanctuary-mcp"},
        [],
        {"key": "private-token"},
    )
    with patch("boxie_infra.mcp.build_opener", return_value=opener):
        provision("http://grafana:3000", password, token)
    assert token.read_text() == "private-token\n"
    assert token.stat().st_mode & 0o777 == 0o600
    create = opener.open.call_args_list[1].args[0]
    assert json.loads(create.data) == {"name": "sanctuary-mcp", "role": "Viewer"}


def test_provision_reuses_token_and_checks_identity(tmp_path: Path) -> None:
    password = tmp_path / "password"
    password.write_text("private-admin-password")
    token = tmp_path / "token"
    token.write_text("existing-token\n")
    token.chmod(0o600)
    opener = responses(
        {
            "serviceAccounts": [
                {"name": "sanctuary-mcp", "id": 7, "role": "Viewer", "login": "sa-sanctuary-mcp"}
            ]
        },
        {"login": "sa-sanctuary-mcp", "isGrafanaAdmin": False},
    )
    with patch("boxie_infra.mcp.build_opener", return_value=opener):
        provision("http://grafana:3000", password, token)
    assert all(call.args[0].get_method() == "GET" for call in opener.open.call_args_list)
    assert token.read_text() == "existing-token\n"


@pytest.mark.parametrize("role", ["Admin", "Editor"])
def test_provision_refuses_elevated_account(tmp_path: Path, role: str) -> None:
    password = tmp_path / "password"
    password.write_text("private")
    opener = responses({"serviceAccounts": [{"name": "sanctuary-mcp", "id": 7, "role": role}]})
    with patch("boxie_infra.mcp.build_opener", return_value=opener):
        with pytest.raises(RuntimeError, match="enabled Viewer"):
            provision("http://grafana:3000", password, tmp_path / "token")
    assert opener.open.call_count == 1


def test_provision_refuses_orphaned_remote_token(tmp_path: Path) -> None:
    password = tmp_path / "password"
    password.write_text("private")
    opener = responses(
        {
            "serviceAccounts": [
                {"name": "sanctuary-mcp", "id": 7, "role": "Viewer", "login": "sa-sanctuary-mcp"}
            ]
        },
        [{"name": "sanctuary-mcp-read"}],
    )
    with patch("boxie_infra.mcp.build_opener", return_value=opener):
        with pytest.raises(RuntimeError, match="revoke it"):
            provision("http://grafana:3000", password, tmp_path / "token")
    assert not (tmp_path / "token").exists()


@pytest.mark.integration
def test_real_grafana_provision_and_retry(tmp_path: Path) -> None:
    config = yaml.safe_load((INFRA / "observability/compose.yml").read_text())
    image = config["services"]["grafana"]["image"]
    name = "sanctuary-mcp-test-" + uuid4().hex[:12]

    def docker(*args: str) -> str:
        return subprocess.run(
            ["docker", *args], check=True, capture_output=True, text=True, timeout=120
        ).stdout.strip()

    password = tmp_path / "password"
    password.write_text("local-mcp-test-password")
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "-p",
            "127.0.0.1::3000",
            "-e",
            "GF_SECURITY_ADMIN_PASSWORD=local-mcp-test-password",
            "-e",
            "GF_PLUGINS_PREINSTALL_DISABLED=true",
            image,
        )
        port = docker("port", name, "3000/tcp")
        url = "http://" + port
        for _ in range(60):
            try:
                with urlopen(url + "/api/health", timeout=2) as response:
                    health: dict[str, Any] = json.load(response)
                    if health["database"] == "ok":
                        break
            except OSError, URLError:
                pass
            time.sleep(1)
        else:
            pytest.fail("Grafana did not become ready")
        token = tmp_path / "token"
        provision(url, password, token)
        original = token.read_text()
        provision(url, password, token)
        assert token.read_text() == original
        mcp = yaml.safe_load((INFRA / "mcp/compose.yml").read_text())
        mcp_probe(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                f"container:{name}",
                "--user",
                "0:0",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--mount",
                f"type=bind,src={token},dst=/run/secrets/grafana-token,readonly",
                "--mount",
                f"type=bind,src={INFRA / 'mcp/start-grafana.sh'},dst=/start.sh,readonly",
                "-e",
                "GRAFANA_URL=http://127.0.0.1:3000",
                "--entrypoint",
                "/bin/sh",
                mcp["services"]["grafana"]["image"],
                "/start.sh",
            ],
            "search_dashboards",
            {"query": ""},
        )
    finally:
        docker("rm", "-f", "-v", name)


@pytest.mark.integration
def test_temporal_mcp_loads_tls_and_exposes_read_only_tools(tmp_path: Path) -> None:
    certs = tmp_path / "certs"
    subprocess.run(
        ["bash", str(INFRA / "certificates.sh"), str(certs), str(os.getuid()), str(os.getgid())],
        check=True,
        capture_output=True,
        timeout=90,
    )
    config = yaml.safe_load((INFRA / "mcp/compose.yml").read_text())
    result = mcp_probe(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--user",
            "0:0",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--mount",
            f"type=bind,src={certs / 'operator'},dst=/certs,readonly",
            "--mount",
            f"type=bind,src={INFRA / 'mcp/temporal.yaml'},dst=/config.yaml,readonly",
            "-e",
            "SSL_CERT_FILE=/certs/frontend-ca.pem",
            config["services"]["temporal"]["image"],
            "--stdio",
            "--config",
            "/config.yaml",
        ],
        "list_available_targets",
        {},
    )
    assert "production" in json.dumps(result)
