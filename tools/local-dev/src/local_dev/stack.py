"""Compose lifecycle and port discovery for a Sanctuary worktree."""

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener


class DevError(Exception):
    """An actionable local setup failure."""


def wait_for_http(request: Request, ready: Callable[[int, str], bool], *, seconds: float) -> bool:
    """Wait for a published loopback service, which can reset early connections."""
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            with opener.open(request, timeout=min(5, remaining)) as response:
                if ready(response.status, response.url):
                    return True
        except OSError:
            pass
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return False


def repository(start: Path) -> Path:
    """Resolve a checkout from cwd or --root, including invocation from a subdirectory."""
    start = start.resolve()
    for root in (start, *start.parents):
        if (root / "Cargo.toml").is_file() and any(
            (root / manifest).is_file()
            for manifest in (
                "tools/cli-playground/compose.dev.yml",
                "packages/boxie/infra/compose.dev.yml",
            )
        ):
            return root
    raise DevError("Run inside a Sanctuary checkout or pass --root /path/to/worktree.")


def project_name(root: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")[:24] or "worktree"
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return f"sanctuary-dev-{slug}-{digest}"


class Stack:
    def __init__(
        self,
        root: Path,
        *,
        suffix: str = "",
        files: tuple[Path, ...] = (Path("tools/cli-playground/compose.dev.yml"),),
    ) -> None:
        self.root = root
        self.project = project_name(root) + suffix
        self.env = {
            key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")
        }
        self.base = [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "--project-name",
            self.project,
            "--project-directory",
            str(root / files[0].parent),
        ]
        for manifest in files:
            self.base.extend(("-f", str(root / manifest)))

    def run(self, *args: str, capture: bool = False, data: str | None = None) -> str:
        command = [*self.base, *args]
        print(f"+ {shlex.join(command)}", file=sys.stderr, flush=True)
        result = subprocess.run(
            command,
            cwd=self.root,
            env=self.env,
            check=True,
            text=True,
            input=data,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout if capture else ""

    def url(self) -> str:
        return self.loopback_url("playground", "8765")

    def docker(self, *args: str, capture: bool = False) -> str:
        result = subprocess.run(
            ["docker", *args],
            cwd=self.root,
            env=self.env,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout.strip() if capture else ""

    def loopback_url(self, service: str, port: str) -> str:
        address = self.run("port", service, port, capture=True).strip()
        match = re.fullmatch(r"127\.0\.0\.1:([0-9]+)", address)
        if not match or not 1 <= int(match[1]) <= 65535:
            raise DevError(f"No loopback port found for {service}. Run local-dev start first.")
        return f"http://127.0.0.1:{match[1]}/"

    def identify(self) -> None:
        print(f"Worktree: {self.root}\nCompose project: {self.project}", flush=True)

    def down_playground(self) -> None:
        for container in self.run("ps", "--all", "-q", "playground", capture=True).split():
            backend = self.docker(
                "inspect",
                "--format",
                '{{index .Config.Labels "sanctuary.local.terminal"}}',
                container,
                capture=True,
            )
            if backend != "boxie":
                continue
            try:
                self.docker("exec", "-i", container, "python", "-m", "tests.dev_server", "drain")
            except subprocess.CalledProcessError:
                raise DevError(
                    "Playground cleanup is unconfirmed. Its local database and volumes were kept. "
                    "Restore the Boxie API connection and retry down."
                ) from None
        self.run("down", "--volumes")

    def start(
        self, *, build: bool, packages: list[str] | None = None, credential: str | None = None
    ) -> None:
        self.identify()
        if build:
            options = ["--build-arg", "CLI_PACKAGES=" + " ".join(packages)] if packages else []
            self.run("--progress", "plain", "build", *options)
        if credential is not None:
            self.run(
                "run", "--rm", "--no-deps", "--pull", "never", "-T", "credential", data=credential
            )
        try:
            wait = ("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
            if credential is None:
                self.run(*wait)
            else:
                self.run(*wait, "postgres")
                self.run(*wait, "--no-deps", "--force-recreate", "playground")
        except subprocess.CalledProcessError:
            for command in [("ps", "--all"), ("logs", "--tail", "100")]:
                try:
                    self.run(*command)
                except subprocess.CalledProcessError:
                    pass
            raise
        url = self.url()
        # Container health cannot validate the published authority or host mapping.
        if not wait_for_http(
            Request(url),
            lambda status, final: status == 200 and final.startswith(url + "p/"),
            seconds=20,
        ):
            raise DevError(f"Playground preview is not ready at {url}")
        print(f"Ready: {url}", flush=True)


def docker_ready(*, daemon: bool) -> None:
    if not shutil.which("docker"):
        raise DevError("Docker is missing. Install Docker with the Compose plugin.")
    subprocess.run(["docker", "compose", "version"], check=True, stdout=subprocess.DEVNULL)
    if daemon:
        result = subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        if result.returncode:
            raise DevError(
                "Docker is not reachable. Start the daemon and check docker context show."
            )
