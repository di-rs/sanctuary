"""Exercise the production host entry points on an empty, disposable Actions VM."""

import hashlib
import json
import os
import shutil
import ssl
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml
from integration.stack import LifecycleStack

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
    shutil.copyfile(cert, "/usr/local/share/ca-certificates/playground-fixture.crt")
    subprocess.run(["update-ca-certificates"], check=True)
    return ssl.create_default_context(cafile=cert)


def prepare_boxie(tmp_path: Path) -> LifecycleStack:
    GRANTS.mkdir(mode=0o700, parents=True)
    subprocess.run(["docker", "network", "create", "--internal", "boxie-consumers"], check=True)
    overlay = tmp_path / "grants.yml"
    shared = yaml.safe_load(
        (ROOT / "infra/environments/single-host/playground-network.yml").read_text()
    )
    api_service = shared["services"]["api"]
    api_service["volumes"] = [f"{GRANTS}:/run/boxie-consumers:ro"]
    api_service["networks"]["feature"] = {"aliases": ["boxie-api"]}
    shared["networks"]["feature"] = {"external": True, "name": "boxie-consumers"}
    overlay.write_text(yaml.safe_dump(shared))
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


def remote(script: str, *args: str) -> list[str]:
    return [
        "ssh",
        "-F",
        os.environ["DOKKU_TEST_SSH_CONFIG"],
        "deployment",
        "bash",
        str(OWNER / "scripts" / script),
        *args,
    ]


def stream_image(tag: str, command: list[str]) -> None:
    subprocess.run(["docker", "tag", "cli-playground:lifecycle", tag], check=True)
    with subprocess.Popen(["docker", "save", tag], stdout=subprocess.PIPE) as archive:
        subprocess.run(command, stdin=archive.stdout, check=True)
        assert archive.wait() == 0


def feature(pr: int, sha: str, directory: Path) -> str:
    tag = f"localhost/sanctuary-playground-pr-{pr}:{sha}"
    stream_image(tag, remote("feature.sh", "deploy", str(pr), sha))
    seed = directory / f"{sha}.zip"
    subprocess.run(
        ["bash", OWNER / "scripts/seed.sh", sha, ROOT / "target/release/echor", seed], check=True
    )
    with seed.open("rb") as source:
        url = subprocess.check_output(
            remote("feature.sh", "publish", str(pr), sha), stdin=source, text=True
        )
    identifier = hashlib.sha256(f"pull-request:{pr}".encode()).hexdigest()[:32]
    assert url.strip() == f"https://app-pr-{pr}.{DOMAIN}/p/{identifier}"
    return identifier


def check_terminals(browser: subprocess.Popen[str], milestone: str) -> None:
    assert browser.stdin is not None and browser.stdout is not None
    print(milestone, file=browser.stdin, flush=True)
    assert browser.stdout.readline().strip() == milestone


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
        subprocess.run(remote("deploy.sh"), check=True)
        production_tag = "localhost/sanctuary-cli-playground:" + "c" * 40
        stream_image(production_tag, remote("deploy.sh", production_tag))
        binary = ROOT / "target/release/echor"
        archive = binary_bundle({"echor": binary.read_bytes()})
        with httpx.Client(verify=tls, timeout=60, trust_env=False) as client:
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
            config = json.loads(
                subprocess.check_output(["docker", "inspect", "playground-pr-22.web.1"])
            )[0]
            assert (
                config["HostConfig"]["Runtime"] == "runsc"
                and config["HostConfig"]["ReadonlyRootfs"]
            )
            assert config["Config"]["User"] == "65532:65532"
            assert set(config["NetworkSettings"]["Networks"]) == {
                "playground-apps",
                "dokku.postgres.playground-pr-22.playground-pr-22",
            }
            with subprocess.Popen(
                [
                    "node",
                    "e2e-native/dokku.mjs",
                    production["url"],
                    f"https://app-pr-22.{DOMAIN}/p/{second}",
                ],
                cwd=ROOT / "tools/cli-playground/frontend",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            ) as browser:
                check_terminals(browser, "open")
                feature(11, "d" * 40, tmp_path)
                check_terminals(browser, "updated")
                subprocess.run(remote("feature.sh", "remove", "11"), check=True)
                check_terminals(browser, "closed")
                assert browser.stdin
                browser.stdin.close()
                assert browser.wait(timeout=15) == 0
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
