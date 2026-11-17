"""Check Sanctuary CLIs, record demonstrations and run a worktree playground."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from cli_check.browser import Demos
from cli_check.workspace import discover

from .recording import changed_clis, check_pr_recordings


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
            raise DevError("No loopback playground port found. Run sanctuary-dev start first.")
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


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--root", type=Path, default=Path.cwd(), help="checkout or worktree path")
    sub = command.add_subparsers(dest="action", required=True)
    for name in ("up", "start"):
        start = sub.add_parser(name, help="build and start this worktree's stack")
        start.add_argument("--no-build", action="store_true", help="reuse existing images")
        if name == "up":
            start.add_argument("--detach", action="store_true", help="return after readiness")
    sub.add_parser("build", help="build images with console progress")
    logs = sub.add_parser("logs", help="follow this worktree's logs")
    logs.add_argument("--no-follow", action="store_true")
    for name, help_text in [
        ("status", "show services, health, and ports"),
        ("url", "print the currently assigned playground URL"),
        ("down", "remove this worktree's stack and disposable data"),
        ("config", "print the resolved Compose configuration"),
        ("doctor", "check Docker, context, and Compose configuration"),
    ]:
        sub.add_parser(name, help=help_text)
    check = sub.add_parser(
        "check", help="run policy, formatting, Clippy and native tests for a CLI"
    )
    check.add_argument("cli")
    record = sub.add_parser("record", help="film selected demonstrations in the local playground")
    record.add_argument("cli")
    record.add_argument("demos", nargs="*", metavar="DEMO", help="demo names in recording order")
    record.add_argument("--list", action="store_true", help="list the CLI's available demos")
    record.add_argument("--output", type=Path, help="new directory for the WebM")
    review = sub.add_parser("check-pr", help="verify the CLI demo links in a PR description")
    review.add_argument("--base", default="origin/master", help="base revision")
    review.add_argument("--head", default="HEAD", help="head revision")
    review.add_argument("--body-file", type=Path, required=True)
    return command


def package_dir(root: Path, name: str) -> Path:
    for package in discover(root):
        if package.name == name and package.is_cli:
            return package.directory
    raise DevError(f"Unknown CLI package: {name}")


def check_cli(root: Path, name: str) -> None:
    package_dir(root, name)
    for command in (
        ["uv", "run", "--locked", "cli-check", "-p", name],
        ["cargo", "fmt", "-p", name, "--", "--check"],
        [
            "cargo",
            "clippy",
            "--locked",
            "-p",
            name,
            "--all-targets",
            "--all-features",
            "--",
            "-D",
            "warnings",
            "-F",
            "unsafe_code",
        ],
        ["cargo", "nextest", "run", "--locked", "-p", name, "--all-features", "--profile", "ci"],
    ):
        print(f"+ {shlex.join(command)}", file=sys.stderr, flush=True)
        subprocess.run(command, cwd=root, check=True)


def record(root: Path, args: argparse.Namespace) -> None:
    cases = Demos.read(package_dir(root, args.cli) / "tests/browser.toml")
    if args.list:
        if args.demos:
            raise DevError("Choose --list or provide the demos to record.")
        print("\n".join(cases))
        return
    if not args.demos or any(name not in cases for name in args.demos):
        raise DevError(f"Choose one or more demos for {args.cli} from: {', '.join(cases)}")
    selected = [cases[name].model_dump(exclude_none=True) for name in args.demos]
    docker_ready(daemon=True)
    run_id = uuid4().hex[:12]
    output = (args.output or root / "target" / "cli-recordings" / run_id).resolve()
    output.mkdir(exist_ok=False, parents=True)
    stack = Stack(root, suffix="-record-" + run_id)
    try:
        stack.start(build=True, packages=[args.cli])
        subprocess.run(
            ["pnpm", "exec", "playwright", "test", "--config", "playwright.record.config.ts"],
            cwd=root / "tools/cli-playground/frontend",
            env=dict(
                os.environ,
                CLI_RECORD_URL=stack.url(),
                CLI_RECORD_OUTPUT=str(output),
                CLI_RECORD_PLAN=json.dumps({"cli": args.cli, "cases": selected}),
            ),
            check=True,
        )
        print(f"CLI recordings: {output}")
    finally:
        stack.run("down", "--volumes", "--rmi", "local")


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    try:
        root = repository(args.root)
        if args.action == "check":
            check_cli(root, args.cli)
            return 0
        if args.action == "check-pr":
            check_pr_recordings(
                changed_clis(root, args.base, args.head), args.body_file.read_text(encoding="utf-8")
            )
            return 0
        if args.action == "record":
            record(root, args)
            return 0
        stack = Stack(root)
        docker_ready(daemon=args.action != "config")
        match args.action:
            case "up" | "start":
                stack.start(build=not args.no_build)
                if args.action == "up" and not args.detach:
                    print(
                        "Following logs. Ctrl+C stops viewing; sanctuary-dev down stops services.",
                        flush=True,
                    )
                    stack.run("logs", "--follow", "--tail", "100")
            case "build":
                stack.run("--progress", "plain", "build")
            case "logs":
                stack.run("logs", *([] if args.no_follow else ["--follow"]), "--tail", "100")
            case "status":
                print(f"Worktree: {stack.root}\nCompose project: {stack.project}", flush=True)
                stack.run("ps", "--all")
            case "url":
                print(stack.url())
            case "down":
                stack.run("down", "--volumes")
            case "config":
                stack.run("config")
            case "doctor":
                subprocess.run(["docker", "context", "show"], check=True)
                subprocess.run(["docker", "version"], check=True)
                stack.run("config", "--quiet")
                print(f"Ready to start {stack.project} from {stack.root}.")
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        if args.action in {"up", "start", "logs"}:
            print("Use sanctuary-dev down to stop this worktree's stack.", file=sys.stderr)
        return 130
    except (DevError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"{cli.prog}: {error}", file=sys.stderr)
        return 1
