"""Playground wheel, frontend assets and gateway Compose contracts."""

from pathlib import Path

import pytest
from boxie_test_support.packaging import (
    check_installed_wheel,
    export_docker_context,
    resolve_compose,
)

ROOT = Path(__file__).resolve().parents[3]
PLAYGROUND = ROOT / "tools/cli-playground"


@pytest.mark.integration
def test_docker_context_excludes_generated_frontend_assets(tmp_path: Path) -> None:
    context = tmp_path / "context"
    source = Path("tools/cli-playground/src/cli_playground")
    assets = context / source / "static"
    assets.mkdir(parents=True)
    (assets / "stale.js").write_text("stale local frontend")
    (context / source / "__init__.py").write_text("# backend source\n")

    output = export_docker_context(
        PLAYGROUND / "infra/docker/CliPlayground.Dockerfile", context, tmp_path / "output"
    )
    assert (output / source / "__init__.py").read_text() == "# backend source\n"
    assert not (output / source / "static").exists()


@pytest.mark.integration
def test_real_isolated_installation(tmp_path: Path) -> None:
    assert (PLAYGROUND / "src/cli_playground/static/index.html").is_file(), (
        "Build the real frontend first"
    )
    check_installed_wheel(
        tmp_path,
        ROOT,
        "cli-playground",
        """
import asyncio
import importlib.util
import re
import sys
from io import StringIO
from pathlib import Path

import cli_playground
from alembic import command
from alembic.config import Config
from cli_playground.app import STATIC_DIR, create_app
from cli_playground.config import Settings

assert Path(cli_playground.__file__).is_relative_to(sys.prefix)
for name in (
    "boxie", "boxie_infra", "cli_playground_infra", "boxie_test_support", "pulumi", "pytest",
):
    assert importlib.util.find_spec(name) is None, name

config = Config()
config.set_main_option("script_location", "cli_playground:alembic")
config.set_main_option("sqlalchemy.url", "postgresql+psycopg://localhost/cli_playground")
config.output_buffer = StringIO()
command.upgrade(config, "head", sql=True)
assert "CREATE TABLE preview" in config.output_buffer.getvalue()

secret = Path("consumer.secret")
secret.write_text("isolated-consumer-secret")
secret.chmod(0o600)
app = create_app(Settings(
    database_url="postgresql+psycopg://localhost/cli_playground",
    data_dir=Path.cwd() / "data",
    public_url="http://localhost",
    deploy_token="local-token",
    boxie_url="http://127.0.0.1:1",
    boxie_credential_file=secret.absolute(),
))


async def request(path):
    sent = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message):
        sent.append(message)

    await app({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"host", b"localhost")],
        "server": ("localhost", 80),
        "client": ("127.0.0.1", 123),
    }, receive, send)
    assert sent[0]["status"] == 200, sent
    return b"".join(message.get("body", b"") for message in sent)


async def run():
    html = await request("/p/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert html == (STATIC_DIR / "index.html").read_bytes()
    paths = re.findall(rb'(?:src|href)="(/static/[^"]+)"', html)
    assert paths
    for path in paths:
        body = await request(path.decode())
        assert len(body) > 1000
    assert (STATIC_DIR / "licenses.md").stat().st_size > 1000
    await app.state.service.boxie.close()


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
        "CLI_PLAYGROUND_IMAGE": "cli-playground:test",
        "CLI_PLAYGROUND_DATABASE_URL_FILE": str(tmp_path / "playground-dsn.secret"),
        "CLI_PLAYGROUND_DATABASE_NETWORK": "test-database",
        "CLI_PLAYGROUND_BOXIE_URL": "http://independent-boxie:8090",
        "CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE": str(tmp_path / "consumer.secret"),
        "CLI_PLAYGROUND_CONSUMER_NETWORK": "test-consumers",
        "CLI_PLAYGROUND_PROXY_NETWORK": "test-proxy",
        "CLI_PLAYGROUND_DATA_VOLUME": "test-product-data",
        "CLI_PLAYGROUND_CERTIFICATES_VOLUME": "test-certificates",
        "CLI_PLAYGROUND_DEPLOY_TOKEN": "test-token",
        "CLI_PLAYGROUND_DOMAIN": "play.example.com",
        "ACME_EMAIL": "test@example.com",
        "CLOUDFLARE_DNS_API_TOKEN": "test-dns-token",
    }
    if project_override:
        values["CLI_PLAYGROUND_PROJECT_NAME"] = "operator-cli-playground"
    config = resolve_compose(
        PLAYGROUND / "infra" / manifest,
        values,
        exclude_prefixes=("COMPOSE_", "CLI_PLAYGROUND_", "BOXIE_"),
    )
    production = manifest == "compose.production.yml"
    assert config["name"] == values.get("CLI_PLAYGROUND_PROJECT_NAME", "cli-playground")
    assert set(config["services"]) == ({"backend", "proxy"} if production else {"backend"})
    for service in config["services"].values():
        assert all(v["target"] != "/var/run/docker.sock" for v in service.get("volumes", []))
    backend = config["services"]["backend"]
    assert set(backend["networks"]) == (
        {"consumer", "database", "proxy"} if production else {"consumer", "database"}
    )
    assert config["networks"]["database"]["name"] == "test-database"
    assert not backend.get("depends_on")
    assert backend["environment"]["CLI_PLAYGROUND_BOXIE_URL"] == values["CLI_PLAYGROUND_BOXIE_URL"]
    assert {v["target"] for v in backend["volumes"]} == {
        "/run/secrets/CLI_PLAYGROUND_DATABASE_URL",
        "/run/secrets/consumer",
        "/var/lib/cli-playground",
    }
    assert all(net["external"] for net in config["networks"].values())
    assert all(volume["external"] for volume in config["volumes"].values())
