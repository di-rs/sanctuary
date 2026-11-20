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
from integration.stack import LifecycleStack
from websockets.sync.client import ClientConnection, connect
from websockets.typing import Origin

from .helpers import binary_bundle

ROOT = Path(__file__).resolve().parents[3]
DOMAIN = "play.example.test"
CONFIG = Path("/etc/sanctuary")
OWNER = Path("/opt/sanctuary/cli-playground")
GRANTS = CONFIG / "consumer-grants"
FEATURES = CONFIG / "playground-apps"
DOKKU = ["docker", "exec", "sanctuary-dokku", "dokku"]


def local_tls() -> ssl.SSLContext:
    # Only the certificate issuer and DNS resolution differ from the production edge.
    proxy = OWNER / "proxy"
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
    rules["tls"] = {
        "stores": {
            "default": {
                "defaultCertificate": {
                    "certFile": "/etc/traefik/fixture.pem",
                    "keyFile": "/etc/traefik/fixture.key",
                }
            }
        }
    }
    routes.write_text(yaml.safe_dump(rules))
    manifest = OWNER / "compose.production.yml"
    compose = yaml.safe_load(manifest.read_text())
    edge = compose["services"]["proxy"]
    edge["volumes"] += [
        f"./proxy/fixture.{ext}:/etc/traefik/fixture.{ext}:ro" for ext in ("pem", "key")
    ]
    edge["command"] = [
        arg for arg in edge["command"] if not arg.startswith("--certificatesresolvers.")
    ]
    manifest.write_text(yaml.safe_dump(compose))
    with Path("/etc/hosts").open("a") as hosts:
        print(f"127.0.0.1 {DOMAIN} pr-7.{DOMAIN} app-pr-11.{DOMAIN} app-pr-22.{DOMAIN}", file=hosts)
    os.environ["CURL_CA_BUNDLE"] = str(cert)
    return ssl.create_default_context(cafile=cert)


def prepare_boxie(tmp_path: Path) -> LifecycleStack:
    GRANTS.mkdir(mode=0o700, parents=True)
    subprocess.run(["docker", "network", "create", "--internal", "boxie-consumers"], check=True)
    overlay = tmp_path / "grants.yml"
    overlay.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "api": {
                        "volumes": [f"{GRANTS}:/run/boxie-consumers:ro"],
                        "networks": {"feature": {"aliases": ["boxie-api"]}},
                    }
                },
                "networks": {"feature": {"external": True, "name": "boxie-consumers"}},
            }
        )
    )
    stack = LifecycleStack(tmp_path, runtime_overlay=overlay)
    stack.start()
    api = tmp_path / "api.json"
    api.write_text(
        json.dumps({**json.loads(api.read_text()), "consumer_grants_dir": "/run/boxie-consumers"})
    )
    stack.runtime_command("restart", "api")
    stack.wait_ready()
    (CONFIG / "boxie").mkdir()
    shutil.copy(tmp_path / "consumer.secret", CONFIG / "boxie/consumer.secret")
    return stack


def feature(pr: int, sha: str, directory: Path) -> str:
    tag = f"localhost/sanctuary-playground-pr-{pr}:{sha}"
    subprocess.run(["docker", "tag", "cli-playground:lifecycle", tag], check=True)
    command = ["bash", str(OWNER / "scripts/feature.sh")]
    with subprocess.Popen(["docker", "save", tag], stdout=subprocess.PIPE) as archive:
        subprocess.run([*command, "deploy", str(pr), sha], stdin=archive.stdout, check=True)
        assert archive.wait() == 0
    seed = directory / f"{sha}.zip"
    subprocess.run(
        ["bash", OWNER / "scripts/seed.sh", sha, ROOT / "target/release/echor", seed], check=True
    )
    with seed.open("rb") as source:
        url = subprocess.check_output([*command, "publish", str(pr), sha], stdin=source, text=True)
    identifier = hashlib.sha256(f"pull-request:{pr}".encode()).hexdigest()[:32]
    assert url.strip() == f"https://app-pr-{pr}.{DOMAIN}/p/{identifier}"
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
def test_dokku_two_prs_and_production(tmp_path: Path) -> None:
    # This acceptance fixture uses the actual /etc, /opt, network names and ports.
    if os.environ.get("SANCTUARY_DISPOSABLE_DOKKU_HOST") != "1":
        pytest.skip("requires the disposable Linux host in Sanctuary browser integration")
    assert os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and os.getuid() == 0
    assert not any(path.exists() for path in (CONFIG, OWNER, Path("/var/lib/dokku")))
    shutil.copytree(ROOT / "tools/cli-playground/infra", OWNER)
    tls = local_tls()
    stack = prepare_boxie(tmp_path)
    try:
        (CONFIG / "settings.env").write_text(
            f"CLI_PLAYGROUND_DOMAIN={DOMAIN}\nACME_EMAIL=fixture@example.test\nCLOUDFLARE_DNS_API_TOKEN=fixture\n"
        )
        (CONFIG / "cli-playground-image.env").write_text(
            "CLI_PLAYGROUND_IMAGE=cli-playground:lifecycle\n"
        )
        subprocess.run(["bash", OWNER / "scripts/install.sh"], check=True)
        subprocess.run(["bash", OWNER / "scripts/deploy.sh"], check=True)
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
                        + (CONFIG / "cli-playground/preview-token").read_text().strip()
                    },
                    content=archive,
                )
                .raise_for_status()
                .json()
            )
            feature(11, "a" * 40, tmp_path)
            second = feature(22, "b" * 40, tmp_path)
            prod = terminal(sockets, client, tls, f"pr-7.{DOMAIN}", production["id"])
            config = json.loads(
                subprocess.check_output(["docker", "inspect", "playground-pr-22.web.1"])
            )[0]
            assert (
                config["HostConfig"]["Runtime"] == "runsc"
                and config["HostConfig"]["ReadonlyRootfs"]
            )
            assert config["Config"]["User"] == "65532:65532"
            assert set(config["NetworkSettings"]["Networks"]) >= {
                "boxie-consumers",
                "playground-apps",
            }
            neighbor = terminal(sockets, client, tls, f"app-pr-22.{DOMAIN}", second)
            feature(11, "d" * 40, tmp_path)
            echo_on_terminal(prod, "updated-prod")
            echo_on_terminal(neighbor, "updated-b")
            subprocess.run(["bash", OWNER / "scripts/feature.sh", "remove", "11"], check=True)
            echo_on_terminal(prod, "closed-prod")
            echo_on_terminal(neighbor, "closed-b")
            assert client.get(f"https://app-pr-11.{DOMAIN}/healthz").status_code in (400, 404)
            for check in ("apps:exists", "postgres:exists"):
                assert subprocess.run([*DOKKU, check, "playground-pr-11"]).returncode != 0
            assert not (FEATURES / "playground-pr-11").exists()
            forbidden = client.delete(
                f"https://{DOMAIN}/api/pull-requests/7",
                headers={
                    "Authorization": "Bearer "
                    + (FEATURES / "playground-pr-22/publisher").read_text().strip()
                },
            )
            assert forbidden.status_code == 401
    finally:
        stack.close()
