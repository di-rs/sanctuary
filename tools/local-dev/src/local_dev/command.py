"""Manage the playground and PostgreSQL for one Sanctuary worktree."""

import argparse
import subprocess
import sys
from pathlib import Path

from .stack import DevError, Stack, docker_ready, repository


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
    return command


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    try:
        root = repository(args.root)
        stack = Stack(root)
        docker_ready(daemon=args.action != "config")
        match args.action:
            case "up" | "start":
                stack.start(build=not args.no_build)
                if args.action == "up" and not args.detach:
                    print(
                        "Following logs. Ctrl+C stops viewing; local-dev down stops services.",
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
            print("Use local-dev down to stop this worktree's stack.", file=sys.stderr)
        return 130
    except (DevError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"{cli.prog}: {error}", file=sys.stderr)
        return 1
