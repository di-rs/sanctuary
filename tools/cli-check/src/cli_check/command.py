"""Check CLI package standards, verify one binary or inspect PR recording evidence."""

import argparse
import shlex
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from cli_check import index
from cli_check.checks import benches, docs, layout, tests
from cli_check.diagnostics import Diagnostic
from cli_check.output import ArgumentParser, emit, failure
from cli_check.recordings import changed_clis, check_pr_recordings
from cli_check.workspace import discover, find_root, select_cli

CHECKS = {
    "layout": layout.check,
    "tests": tests.check,
    "docs": docs.check,
    "benches": benches.check,
}


def arguments() -> argparse.Namespace:
    # Existing callers use shared options on either side of a check group.
    common = ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument("--root", type=Path, help="explicit Cargo workspace root")
    common.add_argument(
        "-p", "--package", action="append", help="select a package for policy checks"
    )
    common.add_argument("--json", action="store_true", help="emit structured results and errors")
    common.add_argument(
        "--list-packages", action="store_true", help="discover packages without checking them"
    )
    options, rest = common.parse_known_args()
    parser = ArgumentParser(parents=[common], description=__doc__)
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    sub = parser.add_subparsers(dest="group")
    for group in CHECKS:
        sub.add_parser(group, help=f"run the {group} policy checks")
    shared_help = "Use --root PATH to select a workspace and --json for structured output."
    sub.add_parser("index", help="refresh the root README command index", epilog=shared_help)
    verify = sub.add_parser(
        "verify",
        help="run policy, formatting, Clippy and native tests for one CLI",
        epilog=shared_help,
    )
    verify.add_argument("cli")
    review = sub.add_parser(
        "check-pr", help="verify the CLI evidence in a PR description", epilog=shared_help
    )
    review.add_argument("--base", default="origin/master", help="base revision")
    review.add_argument("--head", default="HEAD", help="head revision")
    review.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args(rest, namespace=options)
    if args.group in {"verify", "check-pr", "index"} and (args.package or args.list_packages):
        parser.error("--package and --list-packages select workspace policy checks")
    return args


def native_checks(root: Path, name: str, *, json_output: bool) -> None:
    for command in (
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
        subprocess.run(command, cwd=root, check=True, stdout=sys.stderr if json_output else None)


def main() -> int:
    args = arguments()
    try:
        root = args.root.resolve() if args.root else find_root(Path.cwd())
        if args.group == "check-pr":
            names = changed_clis(root, args.base, args.head)
            check_pr_recordings(names, args.body_file.read_text(encoding="utf-8"))
            if args.json:
                emit({"packages": names})
            return 0
        inventory = discover(root)
        if args.group == "index":
            updated = index.refresh(root, inventory, write=True)
            if args.json:
                emit({"path": "README.md", "updated": updated})
            else:
                print("Updated README.md" if updated else "README.md is current")
            return 0
        verifying = args.group == "verify"
        packages = [select_cli(inventory, args.cli)] if verifying else inventory
        if args.package:
            unknown = set(args.package) - {package.name for package in packages}
            if unknown:
                raise ValueError(f"Unknown packages: {', '.join(sorted(unknown))}")
            packages = [package for package in packages if package.name in args.package]
        if args.list_packages:
            records = [
                {"name": p.name, "path": str(p.directory), "cli": p.is_cli} for p in packages
            ]
            if args.json:
                emit({"packages": records})
            else:
                print("\n".join(p.name for p in packages))
            return 0
        selected = [CHECKS[args.group]] if args.group in CHECKS else list(CHECKS.values())
        errors = [error for check in selected for error in check(root, packages)]
        if docs.check in selected:
            if (root / "README.md").is_file() and index.refresh(root, inventory, write=False):
                errors.append(
                    Diagnostic(
                        "README.md",
                        "docs",
                        "index",
                        f"run {index.REFRESH} to refresh the stale root README command index",
                    )
                )
            if not args.package and not verifying:
                errors.extend(docs.component_docs(root, packages))
        errors.sort()
        if verifying and not errors:
            native_checks(root, args.cli, json_output=args.json)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        if args.json:
            failure("operation", str(error))
        else:
            print(f"Cannot check CLI standards: {error}", file=sys.stderr)
        return 1
    if args.json:
        emit(
            {
                "root": str(root),
                "packages": [p.name for p in packages],
                "checks": [args.group] if args.group else list(CHECKS),
                "diagnostics": [asdict(error) for error in errors],
            },
            ok=not errors,
        )
        return int(bool(errors))
    if errors:
        print("\n".join(map(str, errors)), file=sys.stderr)
        return 1
    print("CLI checks passed" + (f" ({args.group})" if args.group else ""))
    return 0
