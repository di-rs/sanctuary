"""Record named CLI demonstrations in a disposable local browser terminal."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from cli_check.browser import Demos
from cli_check.workspace import cli_package
from local_dev.stack import DevError, Stack, docker_ready, repository


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--root", type=Path, default=Path.cwd(), help="checkout or worktree path")
    command.add_argument("cli")
    command.add_argument("demos", nargs="*", metavar="DEMO", help="demo names in recording order")
    command.add_argument("--list", action="store_true", help="list the CLI's available demos")
    command.add_argument("--output", type=Path, help="new directory for the WebM")
    return command


def record(root: Path, args: argparse.Namespace) -> None:
    cases = Demos.read(cli_package(root, args.cli).directory / "tests/browser.toml")
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
        print(f"CLI recordings: {output}", flush=True)
    finally:
        stack.run("down", "--volumes", "--rmi", "local")


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    try:
        record(repository(args.root), args)
    except KeyboardInterrupt:
        return 130
    except (DevError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"{cli.prog}: {error}", file=sys.stderr)
        return 1
    return 0
