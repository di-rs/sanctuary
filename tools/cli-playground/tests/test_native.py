"""Application-owned browser proof against the independently usable Boxie stack."""

import json
import os
import secrets
import select
import socket
import subprocess
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from socketserver import BaseRequestHandler, ThreadingTCPServer
from threading import Event, Thread
from urllib.parse import urlsplit

import httpx
import pytest
from integration.stack import LifecycleStack
from local_dev.boxie import Boxie
from local_dev.command import playground

from .helpers import binary_bundle, clean_git_env

ROOT = Path(__file__).resolve().parents[3]


def wait_for_playground(
    public: httpx.Client,
    runtime_command: Callable[[str, str, str, str], str],
    *,
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    last = "no response"
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            response = public.get("/healthz", timeout=min(2, remaining))
            if response.status_code == 200:
                return
            last = f"HTTP {response.status_code}"
        except httpx.TransportError as error:
            last = type(error).__name__
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    logs = runtime_command("logs", "--no-color", "--tail=40", "cli-playground")
    raise AssertionError(f"Playground /healthz did not become ready ({last})\n{logs}")


def wait_for_request_log(
    runtime_command: Callable[[str, str, str, str], str],
    service: str,
    request_id: str,
    *,
    timeout: float = 10,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        logs = runtime_command("logs", "--no-color", "--no-log-prefix", service)
        events = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
        if any(event.get("request_id") == request_id for event in events):
            return
        assert time.monotonic() < deadline, service
        time.sleep(0.2)


def test_readiness_retries_the_health_probe_after_a_connection_reset() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if len(calls) == 1:
            raise httpx.ReadError("connection reset", request=request)
        return httpx.Response(200, json={"status": "ok"})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handle)) as public:
        wait_for_playground(public, lambda *args: pytest.fail("unexpected log request"))
    assert calls == ["GET /healthz", "GET /healthz"]


def test_readiness_timeout_reports_the_gateway_status_and_logs() -> None:
    def logs(*args: str) -> str:
        assert args == ("logs", "--no-color", "--tail=40", "cli-playground")
        return "fixture startup diagnostic"

    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    with (
        httpx.Client(base_url="http://localhost", transport=transport) as public,
        pytest.raises(AssertionError, match=r"HTTP 503\)\nfixture startup diagnostic"),
    ):
        wait_for_playground(public, logs, timeout=0.05)


@pytest.mark.integration
def test_native_application_and_browser(tmp_path: Path) -> None:
    binary = Path(os.environ.get("BOXIE_NATIVE_BINARY", ROOT / "target/release/echor"))
    if not binary.is_file():
        raise RuntimeError("native echor binary is required (BOXIE_NATIVE_BINARY)")
    token = secrets.token_hex(24)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    stack = LifecycleStack(
        tmp_path,
        runtime_overlay=ROOT / "tools/cli-playground/infra/compose.test.yml",
        runtime_services=("faults", "supervisor", "api"),
    )
    stack.env.update(
        CLI_PLAYGROUND_DATABASE_NETWORK=stack.postgres + "_playground",
        CLI_PLAYGROUND_IMAGE=os.environ.get("CLI_PLAYGROUND_IMAGE", "cli-playground:lifecycle"),
        BOXIE_TEST_PRODUCT_PORT=str(port),
        CLI_PLAYGROUND_PUBLIC_URL=origin,
        CLI_PLAYGROUND_DEPLOY_TOKEN=token,
    )
    try:
        stack.start()
        # Provision the application's database separately from Boxie's lifecycle schema.
        import psycopg

        from .helpers import migrate

        password = secrets.token_hex(32)
        with psycopg.connect(
            f"host=127.0.0.1 port={stack.pg_port} user=postgres dbname=postgres password={stack.env['POSTGRES_PASSWORD']}",
            autocommit=True,
        ) as connection:
            from psycopg import sql

            connection.execute(
                sql.SQL("CREATE ROLE cli_playground LOGIN PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
            connection.execute("CREATE DATABASE cli_playground OWNER cli_playground")
            connection.execute("REVOKE CONNECT ON DATABASE cli_playground FROM PUBLIC")
        migrate(
            f"postgresql+psycopg://cli_playground:{password}@127.0.0.1:{stack.pg_port}/cli_playground"
        )
        secret = stack.root / "playground-dsn"
        secret.write_text(f"postgresql+psycopg://cli_playground:{password}@postgres/cli_playground")
        secret.chmod(0o600)
        stack.runtime_command("up", "--detach", "cli-playground")
        with httpx.Client(base_url=origin, timeout=30, trust_env=False) as public:
            wait_for_playground(public, stack.runtime_command)
            response = public.post(
                "/api/environments",
                params={"sha": "c" * 40, "pr": 987654},
                headers={"Authorization": "Bearer " + token},
                content=binary_bundle({binary.name: binary.read_bytes()}),
            )
            assert response.status_code == 201, response.text
            request_id = response.headers["x-request-id"]
        for service in ("cli-playground", "api", "supervisor"):
            wait_for_request_log(stack.runtime_command, service, request_id)
        subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "cli_playground_infra.smoke",
                "--boxie-url",
                stack.api_url,
                "--credential-file",
                str(stack.root / "consumer.secret"),
                "--binary",
                str(binary),
            ],
            check=True,
            timeout=180,
        )
        subprocess.run(
            ["pnpm", "exec", "playwright", "test", "--config", "playwright.native.config.ts"],
            cwd=ROOT / "tools/cli-playground/frontend",
            env={
                **os.environ,
                "BOXIE_NATIVE_ORIGIN": origin,
                "BOXIE_NATIVE_BINARY": str(binary),
                "BOXIE_NATIVE_DEPLOY_TOKEN": token,
            },
            check=True,
            timeout=180,
        )
        for _ in range(120):
            if not stack.children():
                break
            time.sleep(0.5)
        assert not stack.children()
    finally:
        stack.close()


@pytest.mark.integration
def test_local_deploy_browser_and_worktree_teardown(tmp_path: Path) -> None:
    """Use the public launcher for both projects and exercise an external URL."""
    binary = Path(os.environ.get("BOXIE_NATIVE_BINARY", ROOT / "target/release/echor"))
    assert binary.is_file(), "native echor binary is required (BOXIE_NATIVE_BINARY)"

    def command(args: list[str], *, env: dict[str, str] | None = None) -> str:
        return subprocess.run(
            args, cwd=ROOT, env=env, check=True, text=True, stdout=subprocess.PIPE, timeout=480
        ).stdout.strip()

    def local(root: Path, action: str, mode: str, env: dict[str, str] | None = None) -> str:
        return command(
            [
                "uv",
                "run",
                "--locked",
                "sdev",
                "--root",
                str(root),
                "local",
                action,
                "--mode",
                mode,
                *(["--no-build"] if action == "start" else []),
            ],
            env=env,
        )

    def children(boxie: Boxie) -> list[str]:
        return boxie.docker(
            "ps",
            "-aq",
            "--filter",
            f"label=boxie.installation={boxie.installation}",
            "--filter",
            f"label=boxie.host={boxie.project}",
            capture=True,
        ).split()

    with ExitStack() as cleanup:
        first = tmp_path / "first"
        second = tmp_path / "second"
        for worktree in (first, second):
            command(
                ["git", "worktree", "add", "--detach", str(worktree), "HEAD"], env=clean_git_env()
            )
            cleanup.callback(
                command,
                ["git", "worktree", "remove", "--force", str(worktree)],
                env=clean_git_env(),
            )
        boxie = Boxie(second)
        full = playground(second, "full", boxie)
        external = playground(first, "external", None)
        # Reuse the workflow's shipped-image builds and build the local preview
        # image once with only the test CLI. Every tag is owned by this test.
        for source, target in (
            (os.environ.get("BOXIE_IMAGE", "boxie:lifecycle"), boxie.env["BOXIE_IMAGE"]),
            (os.environ.get("BOXIE_SANDBOX_IMAGE", "boxie-sandbox:lifecycle"), boxie.sandbox_image),
        ):
            boxie.docker("image", "tag", source, target)
            cleanup.callback(boxie.docker, "image", "rm", target)
        full.run("--progress", "plain", "build", "--build-arg", "CLI_PACKAGES=echor")
        cleanup.callback(boxie.docker, "image", "rm", full.env["LOCAL_DEV_PLAYGROUND_IMAGE"])
        boxie.docker(
            "image",
            "tag",
            full.env["LOCAL_DEV_PLAYGROUND_IMAGE"],
            external.env["LOCAL_DEV_PLAYGROUND_IMAGE"],
        )
        cleanup.callback(boxie.docker, "image", "rm", external.env["LOCAL_DEV_PLAYGROUND_IMAGE"])

        cleanup.callback(local, second, "down", "full")
        standalone = local(second, "start", "boxie")
        assert "gVisor/runsc" in standalone
        assert not full.run("ps", "-q", capture=True).strip()
        assert "Terminal backend: Boxie API" in local(second, "start", "full")
        api = local(second, "url", "boxie")
        full_url = local(second, "url", "full")

        # Make the loopback-only development API reachable from the other
        # container through a test-only TCP relay on this Boxie's bridge.
        gateway = boxie.docker(
            "network",
            "inspect",
            boxie.network,
            "--format",
            "{{(index .IPAM.Config 0).Gateway}}",
            capture=True,
        )
        api_port = urlsplit(api).port
        assert api_port is not None

        connected = Event()
        connected.set()

        class Relay(BaseRequestHandler):
            def handle(self) -> None:
                with socket.create_connection(("127.0.0.1", api_port), timeout=10) as upstream:
                    for_socket = self.request
                    for_socket.settimeout(10)
                    while True:
                        readable, _, _ = select.select([upstream, for_socket], [], [], 60)
                        if not readable or not connected.is_set():
                            return
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            (for_socket if source is upstream else upstream).sendall(data)

        relay = cleanup.enter_context(ThreadingTCPServer((gateway, 0), Relay))
        relay.daemon_threads = True
        Thread(target=relay.serve_forever, daemon=True).start()
        cleanup.callback(relay.shutdown)
        relay_origin = f"http://{gateway}:{relay.server_address[1]}"
        cleanup.callback(local, first, "down", "external")
        assert "Terminal backend: Boxie API" in local(
            first,
            "start",
            "external",
            os.environ
            | {
                "LOCAL_DEV_BOXIE_URL": relay_origin,
                "LOCAL_DEV_BOXIE_CREDENTIAL_FILE": str(boxie.credential),
            },
        )
        origin = local(first, "url", "external")
        assert origin != full_url
        token = external.run(
            "exec",
            "-T",
            "playground",
            "sh",
            "-c",
            "cat /tmp/playground-dev-*/deploy.secret",
            capture=True,
        ).strip()
        with subprocess.Popen(
            ["pnpm", "exec", "playwright", "test", "--config", "playwright.native.config.ts"],
            cwd=ROOT / "tools/cli-playground/frontend",
            env=os.environ
            | {
                "BOXIE_NATIVE_ORIGIN": origin,
                "BOXIE_NATIVE_BINARY": str(binary),
                "BOXIE_NATIVE_DEPLOY_TOKEN": token,
            },
        ) as browser:
            runtime = ""
            try:
                deadline = time.monotonic() + 150
                while not runtime and browser.poll() is None and time.monotonic() < deadline:
                    for child in children(boxie):
                        inspected = subprocess.run(
                            ["docker", "inspect", "--format", "{{.HostConfig.Runtime}}", child],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=10,
                        )
                        if inspected.returncode == 0:
                            runtime = inspected.stdout.strip()
                    time.sleep(0.2)
                assert browser.wait(timeout=max(1, deadline - time.monotonic())) == 0
                assert runtime == "runsc"
            finally:
                if browser.poll() is None:
                    browser.kill()
        deadline = time.monotonic() + 60
        while children(boxie) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert not children(boxie), "Boxie left the browser session's sandbox behind"

        def publish_open_preview(url: str, token: str) -> str:
            origin = url.rstrip("/")
            response = httpx.post(
                origin + "/api/environments",
                params={"pr": 43211, "sha": "d" * 40},
                headers={"Authorization": "Bearer " + token},
                content=binary_bundle({"echor": binary.read_bytes()}),
                timeout=30,
            )
            assert response.status_code == 201, response.text
            identifier = str(response.json()["id"])
            metadata = httpx.get(origin + f"/api/environments/{identifier}", timeout=10)
            metadata.raise_for_status()
            admitted = httpx.post(
                origin + f"/api/environments/{identifier}/sessions",
                headers={"Origin": origin},
                json={"revision": metadata.json()["revision"]},
                timeout=30,
            )
            assert admitted.status_code == 201, admitted.text
            return identifier

        own_preview = publish_open_preview(origin, token)
        sibling_token = full.run(
            "exec",
            "-T",
            "playground",
            "sh",
            "-c",
            "cat /tmp/playground-dev-*/deploy.secret",
            capture=True,
        ).strip()
        sibling_preview = publish_open_preview(full_url, sibling_token)
        assert (
            own_preview == sibling_preview
        )  # Identical PR numbers still refer to separate records.
        gateway_id = external.run("ps", "-q", "playground", capture=True).strip()
        assert gateway_id

        def credential_digest() -> str:
            return external.run(
                "exec", "-T", "playground", "sha256sum", "/run/boxie/consumer", capture=True
            ).split()[0]

        original_digest = credential_digest()
        other_credential = tmp_path / "other-consumer"
        other_credential.touch(mode=0o600)
        other_credential.write_text(secrets.token_hex(24))
        connected.clear()
        try:
            with pytest.raises(subprocess.CalledProcessError):
                local(first, "start", "portable")
            with pytest.raises(subprocess.CalledProcessError):
                local(
                    first,
                    "start",
                    "external",
                    os.environ
                    | {
                        "LOCAL_DEV_BOXIE_URL": "http://127.0.0.1:1",
                        "LOCAL_DEV_BOXIE_CREDENTIAL_FILE": str(other_credential),
                    },
                )
            assert external.run("ps", "-q", "playground", capture=True).strip() == gateway_id
            assert credential_digest() == original_digest
            with pytest.raises(subprocess.CalledProcessError):
                local(first, "down", "external")
            assert external.run("ps", "--status", "running", "-q", "postgres", capture=True).strip()
        finally:
            connected.set()
        local(first, "down", "external")
        assert not external.run("ps", "-a", "-q", capture=True).strip()
        assert not boxie.docker(
            "volume",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={external.project}",
            capture=True,
        )
        assert httpx.get(full_url, follow_redirects=True, timeout=10).status_code == 200
        assert (
            httpx.get(full_url + f"api/environments/{sibling_preview}", timeout=10).status_code
            == 200
        )
        assert (
            httpx.get(
                api + "readyz",
                headers={"Authorization": "Bearer " + boxie.credential.read_text()},
                timeout=10,
            ).status_code
            == 200
        )
        local(second, "down", "full")
        assert not boxie.run("ps", "-a", "-q", capture=True).strip()
        assert not children(boxie)
