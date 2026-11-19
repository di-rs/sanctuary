"""Run the playground and Boxie independently or together for one worktree."""

import argparse
import fcntl
import os
import stat
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlsplit

from .boxie import Boxie
from .stack import DevError, Stack, docker_ready, repository

PLAYGROUND = Path("tools/cli-playground")


def playground(root: Path, mode: str, boxie: Boxie | None) -> Stack:
    files = [PLAYGROUND / "compose.dev.yml"]
    if mode in {"external", "full"}:
        files.append(PLAYGROUND / "compose.boxie.dev.yml")
    if mode == "full":
        files.append(PLAYGROUND / "compose.full.dev.yml")
    stack = Stack(root, files=tuple(files))
    stack.env["LOCAL_DEV_PLAYGROUND_IMAGE"] = f"{stack.project}-playground"
    stack.env["LOCAL_DEV_BOXIE_ORIGIN"] = "http://boxie-api:8090"
    if boxie is not None:
        stack.env["LOCAL_DEV_BOXIE_NETWORK"] = boxie.network
    return stack


def connect(stack: Stack, source: Path, origin: str) -> str:
    try:
        url = urlsplit(origin)
        _ = url.port
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or any(char.isspace() for char in origin)
        ):
            raise ValueError
    except ValueError:
        raise DevError(
            "LOCAL_DEV_BOXIE_URL must be an HTTP(S) origin without credentials or a path."
        ) from None
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as file:
        mode = os.fstat(file.fileno()).st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise DevError("Boxie credential must be a private regular file (mode 0600).")
        credential = file.read(4097).strip()
    if not 16 <= len(credential) <= 4096 or any(not 33 <= char <= 126 for char in credential):
        raise DevError("Boxie credential must contain a printable token of 16–4096 characters.")
    stack.env["LOCAL_DEV_BOXIE_ORIGIN"] = origin.rstrip("/")
    return credential.decode("ascii")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--root", type=Path, default=Path.cwd(), help="checkout or worktree path")
    sub = command.add_subparsers(dest="action", required=True)
    for name in ("up", "start"):
        start = sub.add_parser(name, help="build and start this worktree's stack")
        start.add_argument("--no-build", action="store_true", help="reuse existing images")
        if name == "up":
            start.add_argument("--detach", action="store_true", help="return after readiness")
    build = sub.add_parser("build", help="build images with console progress")
    logs = sub.add_parser("logs", help="follow this worktree's logs")
    logs.add_argument("--no-follow", action="store_true")
    actions = [sub.choices["up"], sub.choices["start"], build, logs]
    for name, help_text in [
        ("status", "show services, health, and ports"),
        ("url", "print the currently assigned playground or Boxie URL"),
        ("down", "remove this worktree's stack and disposable data"),
        ("config", "print the resolved Compose configuration"),
        ("doctor", "check Docker, context, and Compose configuration"),
    ]:
        actions.append(sub.add_parser(name, help=help_text))
    for action in actions:
        action.add_argument(
            "--mode",
            choices=("portable", "external", "boxie", "full"),
            default="portable",
            help="portable Bash (default), external Boxie, standalone Boxie, or both projects",
        )
    return command


def run_action(args: argparse.Namespace, stack: Stack, boxie: Boxie | None) -> None:
    stacks = (boxie, stack) if boxie is not None and boxie is not stack else (stack,)
    match args.action:
        case "up" | "start":
            token = None
            if args.mode == "external":
                origin = os.environ.get("LOCAL_DEV_BOXIE_URL")
                credential = os.environ.get("LOCAL_DEV_BOXIE_CREDENTIAL_FILE")
                if not origin or not credential:
                    raise DevError("Set LOCAL_DEV_BOXIE_URL and LOCAL_DEV_BOXIE_CREDENTIAL_FILE.")
                token = connect(stack, Path(credential), origin)
            if args.mode == "full" and boxie is not None:
                boxie.start(build=not args.no_build)
                stack.env.pop("DOCKER_CONTEXT", None)
                stack.env["DOCKER_HOST"] = boxie.env["DOCKER_HOST"]
                token = connect(stack, boxie.credential, "http://boxie-api:8090")
            if args.mode != "boxie":
                backend = "portable Bash PTYs" if args.mode == "portable" else "Boxie API"
                print(f"Terminal backend: {backend}", flush=True)
            stack.start(build=not args.no_build, credential=token)
        case "build":
            if boxie is not None:
                boxie.require_native()
                boxie.build()
            if stack is not boxie:
                stack.run("--progress", "plain", "build")
        case "logs":
            for project in stacks if args.no_follow else (stack,):
                project.run("logs", *([] if args.no_follow else ["--follow"]), "--tail", "100")
        case "status":
            for project in stacks:
                project.identify()
                project.run("ps", "--all")
        case "url":
            print(stack.url())
        case "down":
            # The external manifest includes the credential volume and resolves
            # even when the full deployment's Boxie network no longer exists.
            target = None
            if stack is not boxie:
                target = (
                    playground(stack.root, "external", None)
                    if (stack.root / PLAYGROUND / "compose.boxie.dev.yml").is_file()
                    else Stack(stack.root)
                )
            if boxie is not None:
                boxie.down(playground=target)
            elif target is not None:
                target.down_playground()
        case "config" | "doctor":
            if args.action == "doctor":
                subprocess.run(["docker", "context", "show"], check=True)
                subprocess.run(["docker", "version"], check=True)
                if boxie is not None:
                    boxie.require_native()
            for project in stacks:
                project.run("config", *([] if args.action == "config" else ["--quiet"]))


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    try:
        root = repository(args.root)
        boxie = Boxie(root) if args.mode in {"boxie", "full"} else None
        stack = (
            boxie
            if args.mode == "boxie" and boxie is not None
            else playground(root, args.mode, boxie)
        )
        docker_ready(daemon=args.action != "config")
        mutation = args.action in {"up", "start", "build", "down"}
        state = root / ".local-dev"
        if mutation:
            state.mkdir(mode=0o700, exist_ok=True)
            if state.is_symlink() or state.stat().st_mode & 0o077:
                raise DevError(f"Expected a private local state directory at {state}.")
        with (state / "lock").open("a") if mutation else nullcontext() as lock:
            if lock is not None:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise DevError(
                        "Another local-dev command is operating on this worktree."
                    ) from None
            run_action(args, stack, boxie)
        if args.action == "up" and not args.detach:
            print(
                f"Following logs. Ctrl+C stops viewing. Use local-dev down --mode {args.mode} to stop services.",
                flush=True,
            )
            stack.run("logs", "--follow", "--tail", "100")
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        if args.action in {"up", "start", "logs"}:
            print(
                f"Use local-dev down --mode {args.mode} to stop this worktree's stack.",
                file=sys.stderr,
            )
        return 130
    except (DevError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"{cli.prog}: {error}", file=sys.stderr)
        return 1
