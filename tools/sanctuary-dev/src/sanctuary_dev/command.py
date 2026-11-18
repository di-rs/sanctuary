"""Run a checkout's CLI checks, fixture tools, benchmarks and playground."""

import argparse
import os
import sys
from pathlib import Path

ROUTES = {
    "check": ("cli-check", "verify"),
    "test": ("cli-testing",),
    "bench": ("cli-bench",),
    "record": ("cli-record",),
    "local": ("local-dev",),
    "check-pr": ("cli-check", "check-pr"),
}


def checkout(start: Path) -> Path:
    directory = start.resolve(strict=True)
    if directory.is_dir():
        for root in (directory, *directory.parents):
            if (root / "uv.lock").is_file() and (
                root / "tools/sanctuary-dev/pyproject.toml"
            ).is_file():
                return root
    raise ValueError("Run inside a Sanctuary checkout or use sdev --root PATH COMMAND.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        usage="%(prog)s [--root PATH] COMMAND [ARG ...]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Commands\n"
        + "\n".join(f"  {name:<11}{' '.join(route)}" for name, route in ROUTES.items()),
        allow_abbrev=False,
    )
    parser.add_argument("--root", type=Path, help="run from this Sanctuary checkout")
    # One remainder preserves every token after the command, including a leading --.
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="use COMMAND --help for its options",
    )
    args = parser.parse_args()
    if not args.args or args.args[0] not in ROUTES:
        parser.error("choose a command from " + ", ".join(ROUTES))
    tool, *prefix = ROUTES[args.args[0]]
    try:
        root = checkout(args.root or Path.cwd())
        if args.root is not None:
            os.chdir(root)
        if tool == "cli-testing":
            command = [
                "cargo",
                "run",
                "--quiet",
                "--locked",
                "--manifest-path",
                str(root / "Cargo.toml"),
                "-p",
                tool,
                "--",
            ]
        else:
            command = [
                "uv",
                "run",
                "--locked",
                "--no-dev",
                "--project",
                str(root),
                "--package",
                tool,
                "--",
                tool,
            ]
        os.execvp(command[0], [*command, *prefix, *args.args[1:]])
    except (ValueError, OSError) as error:
        print(f"sdev: {error}", file=sys.stderr)
        return 1
