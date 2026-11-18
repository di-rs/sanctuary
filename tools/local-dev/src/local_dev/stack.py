"""Compose lifecycle and port discovery for a Sanctuary worktree."""

import hashlib
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen


class DevError(Exception):
    """An actionable local setup failure."""


def repository(start: Path) -> Path:
    """Resolve a checkout from cwd or --root, including invocation from a subdirectory."""
    start = start.resolve()
    for root in (start, *start.parents):
        if (root / "tools/cli-playground/compose.dev.yml").is_file() and (
            root / "Cargo.toml"
        ).is_file():
            return root
    raise DevError("Run inside a Sanctuary checkout or pass --root /path/to/worktree.")


def project_name(root: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")[:24] or "worktree"
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return f"sanctuary-dev-{slug}-{digest}"


class Stack:
    def __init__(self, root: Path, *, suffix: str = "") -> None:
        self.root = root
        self.project = project_name(root) + suffix
        self.base = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(root / "tools/cli-playground"),
            "-f",
            str(root / "tools/cli-playground/compose.dev.yml"),
        ]

    def run(self, *args: str, capture: bool = False) -> str:
        command = [*self.base, *args]
        print(f"+ {shlex.join(command)}", file=sys.stderr, flush=True)
        result = subprocess.run(
            command,
            cwd=self.root,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout if capture else ""

    def url(self) -> str:
        address = self.run("port", "playground", "8765", capture=True).strip()
        match = re.fullmatch(r"127\.0\.0\.1:([0-9]+)", address)
        if not match or not 1 <= int(match[1]) <= 65535:
            raise DevError("No loopback playground port found. Run local-dev start first.")
        return f"http://127.0.0.1:{match[1]}/"

    def start(self, *, build: bool, packages: list[str] | None = None) -> None:
        print(f"Worktree: {self.root}\nCompose project: {self.project}", flush=True)
        if build:
            options = ["--build-arg", "CLI_PACKAGES=" + " ".join(packages)] if packages else []
            self.run("--progress", "plain", "build", *options)
        try:
            self.run("up", "-d", "--wait", "--wait-timeout", "180")
        except subprocess.CalledProcessError:
            for command in [("ps", "--all"), ("logs", "--tail", "100")]:
                try:
                    self.run(*command)
                except subprocess.CalledProcessError:
                    pass
            raise
        url = self.url()
        # Container health cannot validate the published authority or host mapping.
        with urlopen(url, timeout=10) as response:
            if response.status != 200 or "/p/" not in response.url:
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
