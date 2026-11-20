"""Exercise the production host entry points on an empty, disposable Actions VM."""

import hashlib
import json
import os
import shutil
import ssl
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
import pytest
import yaml
from cli_playground_infra import dokku, installation
from integration.stack import LifecycleStack
from websockets.sync.client import ClientConnection, connect
from websockets.typing import Origin

from .helpers import binary_bundle

ROOT = Path(__file__).resolve().parents[3]
DOMAIN = "play.example.test"


def local_tls() -> ssl.SSLContext:
    # Only the certificate issuer and DNS resolution differ from the production edge.
    proxy = dokku.OWNER / "proxy"
    cert = proxy / "fixture.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={DOMAIN}",
            "-addext",
            f"subjectAltName=DNS:{DOMAIN},DNS:*.{DOMAIN}",
            "-keyout",
            proxy / "fixture.key",
            "-out",
            cert,
        ],
        check=True,
    )
    routes = proxy / "routes.yml"
    rules = yaml.safe_load(routes.read_text())
    rules["http"]["routers"]["cli-playground"]["tls"] = {}
    routes.write_text(yaml.safe_dump(rules))
    (proxy / "tls.yml").write_text(
        yaml.safe_dump(
            {
                "tls": {
                    "stores": {
                        "default": {
                            "defaultCertificate": {
                                "certFile": "/etc/traefik/routes/fixture.pem",
                                "keyFile": "/etc/traefik/routes/fixture.key",
                            }
                        }
                    }
                }
            }
        )
    )
    manifest = dokku.OWNER / "compose.production.yml"
    compose = yaml.safe_load(manifest.read_text())
    edge = compose["services"]["proxy"]
    edge["command"] = [
        arg for arg in edge["command"] if not arg.startswith("--certificatesresolvers.")
    ]
    manifest.write_text(yaml.safe_dump(compose))
    with Path("/etc/hosts").open("a") as hosts:
        print(f"127.0.0.1 {DOMAIN} pr-7.{DOMAIN} app-pr-11.{DOMAIN} app-pr-22.{DOMAIN}", file=hosts)
    os.environ["CURL_CA_BUNDLE"] = str(cert)
    return ssl.create_default_context(cafile=cert)


def prepare_boxie(tmp_path: Path) -> LifecycleStack:
    dokku.GRANTS.mkdir(mode=0o700, parents=True)
    dokku.run("docker", "network", "create", "--internal", "boxie-consumers")
    overlay = tmp_path / "grants.yml"
    overlay.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "api": {
                        "volumes": [f"{dokku.GRANTS}:/run/boxie-consumers:ro"],
                        "networks": {"feature": {"aliases": ["boxie-api"]}},
                    }
                },
                "networks": {"feature": {"external": True, "name": "boxie-consumers"}},
            }
        )
    )
    stack = LifecycleStack(tmp_path, runtime_overlay=overlay)
    stack.postgres = "boxie-postgres"
    stack.start()
    api = tmp_path / "api.json"
    api.write_text(
        json.dumps({**json.loads(api.read_text()), "consumer_grants_dir": "/run/boxie-consumers"})
    )
    stack.runtime_command("restart", "api")
    stack.wait_ready()
    (dokku.CONFIG / "boxie").mkdir()
    shutil.copy(tmp_path / "consumer.secret", dokku.CONFIG / "boxie/consumer.secret")
    return stack


def local_image(app: str, sha: str) -> str:
    # A new label makes an observable second revision without rebuilding the application.
    name = "localhost/sanctuary-" + app
    subprocess.run(
        [
            "docker",
            "build",
            "--tag",
            name,
            "--label",
            f"org.opencontainers.image.revision={sha}",
            "-",
        ],
        input=b"FROM cli-playground:lifecycle\n",
        check=True,
    )
    identifier = dokku.output("docker", "image", "inspect", "--format", "{{.Id}}", name)
    reference = name + ":" + identifier.removeprefix("sha256:")
    dokku.run("docker", "tag", name, reference)
    return reference


def feature(pr: int, sha: str, archive: bytes) -> str:
    command = ["bash", str(dokku.OWNER / "scripts/feature.sh")]
    subprocess.run([*command, "reserve", str(pr)], check=True)
    reference = local_image(f"playground-pr-{pr}", sha)
    url = (
        subprocess.check_output([*command, "deploy", str(pr), sha, reference], input=archive)
        .decode()
        .strip()
    )
    identifier = hashlib.sha256(f"pull-request:{pr}".encode()).hexdigest()[:32]
    assert url == f"https://app-pr-{pr}.{DOMAIN}/p/{identifier}"
    return identifier


def terminal(
    resources: ExitStack, client: httpx.Client, tls: ssl.SSLContext, host: str, identifier: str
) -> tuple[ClientConnection, int]:
    origin = f"https://{host}"
    url = f"{origin}/api/environments/{identifier}"
    metadata = client.get(url).raise_for_status().json()
    session = (
        client.post(
            f"{url}/sessions", json={"revision": metadata["revision"]}, headers={"Origin": origin}
        )
        .raise_for_status()
        .json()
    )
    ws = resources.enter_context(
        connect(
            f"wss://{host}/ws/{identifier}?session_id={session['id']}&revision={metadata['revision']}",
            origin=Origin(origin),
            ssl=tls,
            proxy=None,
        )
    )
    ws.send(json.dumps({"type": "auth", "credential": session["credential"]}))
    assert json.loads(ws.recv(timeout=55))["type"] == "authenticated"
    ws.send(json.dumps({"type": "attach", "resume_after": 0, "cols": 80, "rows": 24}))
    while True:
        message = ws.recv(timeout=10)
        if isinstance(message, str) and (reply := json.loads(message))["type"] == "attached":
            return ws, int(reply["epoch"])


def echo_on_terminal(connection: tuple[ClientConnection, int], marker: str) -> None:
    ws, epoch = connection
    ws.send(
        json.dumps(
            {
                "type": "input",
                "epoch": epoch,
                "source": "user",
                "data": f"echor '{marker}-'\"ok\"\n",
            }
        )
    )
    deadline = time.monotonic() + 20
    output = b""
    while (marker + "-ok").encode() not in output:
        packet = ws.recv(timeout=max(0, deadline - time.monotonic()))
        if isinstance(packet, bytes):
            output += packet[8:]


@pytest.mark.integration
def test_dokku_two_prs_and_production(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # This acceptance fixture uses the actual /etc, /opt, network names and ports.
    if os.environ.get("SANCTUARY_DISPOSABLE_DOKKU_HOST") != "1":
        pytest.skip("requires the disposable Linux host in Sanctuary browser integration")
    assert os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and os.getuid() == 0
    assert not any(path.exists() for path in (dokku.CONFIG, dokku.OWNER, Path("/var/lib/dokku")))
    shutil.copytree(ROOT / "tools/cli-playground/infra", dokku.OWNER)
    tls = local_tls()
    stack = prepare_boxie(tmp_path)
    try:
        image = local_image("cli-playground", "c" * 40)
        monkeypatch.setenv("CLI_PLAYGROUND_IMAGE", image)
        monkeypatch.setenv("CLI_PLAYGROUND_DOMAIN", DOMAIN)
        monkeypatch.setenv("ACME_EMAIL", "fixture@example.test")
        monkeypatch.setenv("CLOUDFLARE_DNS_API_TOKEN", "fixture")
        installation.render(dokku.CONFIG)
        (dokku.CONFIG / "cli-playground-image.env").write_text(f"CLI_PLAYGROUND_IMAGE={image}\n")
        password = (dokku.CONFIG / "cli-playground/postgres-password").read_text().strip()
        pg = stack.compose("postgres", "ps", "-q", "postgres")
        dokku.run(
            "docker",
            "exec",
            "-i",
            pg,
            "psql",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            stdin=f"\\set playground_password '{password}'\n"
            + (dokku.OWNER / "postgres/postgres.sql").read_text(),
        )
        dokku.run("bash", str(dokku.OWNER / "scripts/deploy.sh"))
        binary = ROOT / "target/release/echor"
        archive = binary_bundle({"echor": binary.read_bytes()})
        with (
            httpx.Client(verify=tls, timeout=60, trust_env=False) as client,
            ExitStack() as sockets,
        ):
            production = (
                client.post(
                    f"https://{DOMAIN}/api/environments?pr=7&sha=" + "c" * 40,
                    headers={
                        "Authorization": "Bearer "
                        + (dokku.CONFIG / "cli-playground/preview-token").read_text().strip()
                    },
                    content=archive,
                )
                .raise_for_status()
                .json()
            )
            prod = terminal(sockets, client, tls, f"pr-7.{DOMAIN}", production["id"])
            feature(11, "a" * 40, archive)
            second = feature(22, "b" * 40, archive)
            neighbor = terminal(sockets, client, tls, f"app-pr-22.{DOMAIN}", second)
            feature(11, "d" * 40, archive)
            echo_on_terminal(prod, "updated-prod")
            echo_on_terminal(neighbor, "updated-b")
            dokku.run("bash", str(dokku.OWNER / "scripts/feature.sh"), "remove", "11")
            echo_on_terminal(prod, "closed-prod")
            echo_on_terminal(neighbor, "closed-b")
            assert client.get(f"https://app-pr-11.{DOMAIN}/healthz").status_code == 404
            assert not dokku.exists(*dokku.DOKKU, "apps:exists", "playground-pr-11")
            assert not dokku.exists("docker", "network", "inspect", "playground-pr-11-data")
            assert not (dokku.FEATURES / "playground-pr-11").exists()
            forbidden = client.delete(
                f"https://{DOMAIN}/api/pull-requests/7",
                headers={
                    "Authorization": "Bearer "
                    + (dokku.FEATURES / "playground-pr-22/deploy-token").read_text().strip()
                },
            )
            assert forbidden.status_code == 401
    finally:
        stack.close()
