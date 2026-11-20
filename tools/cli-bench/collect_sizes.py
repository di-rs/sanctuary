#!/usr/bin/env python3.15
"""Build affected Cargo binaries at the merge base and head; record executable bytes."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from cli_check.affected import dependencies_changed, git, lock_closures, source_changed_packages
from cli_check.workspace import Package, discover, string, strings, table
from size_data import BinarySize, Build, SizeReport

ROOT = Path(__file__).resolve().parents[2]


def selected_packages(
    before: Path,
    after: Path,
    paths: list[str],
    *,
    before_members: list[Package],
    after_members: list[Package],
) -> set[str]:
    binaries = {member.name for member in [*before_members, *after_members] if member.binaries}
    global_files = {"Cargo.toml", "rust-toolchain", "rust-toolchain.toml"}
    if any(path in global_files or path.startswith(".cargo/") for path in paths):
        return binaries
    changed = source_changed_packages(before, before_members, paths) | source_changed_packages(
        after, after_members, paths
    )
    if not changed and "Cargo.lock" not in paths:
        return set()
    old = lock_closures((before / "Cargo.lock").read_text())
    new = lock_closures((after / "Cargo.lock").read_text())
    return {
        name
        for name in binaries
        if name in changed or dependencies_changed(old.get(name), new.get(name), changed)
    }


def selected_binaries(members: list[Package], selected: set[str]) -> set[tuple[str, str]]:
    return {
        (member.name, binary.name)
        for member in members
        if member.name in selected
        for binary in member.binaries
    }


def build_sizes(
    root: Path, members: list[Package], selected: set[str], target: Path
) -> dict[tuple[str, str], Build]:
    results: dict[tuple[str, str], Build] = {}
    for member in members:
        if member.name not in selected or not member.binaries:
            continue
        expected = {binary.name for binary in member.binaries}
        # One package per invocation keeps feature unification independent of the selected set.
        command = [
            "cargo",
            "build",
            "--locked",
            "--release",
            "--bins",
            "-p",
            member.name,
            "--target-dir",
            str(target),
            "--message-format=json-render-diagnostics",
        ]
        result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, check=False)
        found: dict[str, int] = {}
        for line in result.stdout.splitlines():
            message = table(json.loads(line))
            if message.get("reason") != "compiler-artifact" or not message.get("executable"):
                continue
            artifact = table(message["target"])
            name = string(artifact.get("name"), "target name")
            if name not in expected or "bin" not in strings(
                artifact.get("kind", []), "target kind"
            ):
                continue
            executable = Path(string(message["executable"], "executable")).resolve()
            if not executable.is_relative_to(target.resolve()):
                raise ValueError("executable outside build directory")
            found[name] = executable.stat().st_size
        for name in expected:
            results[member.name, name] = (
                Build(status="complete", bytes=found[name])
                if result.returncode == 0 and name in found
                else Build(status="failed")
            )
    return results


def collect(root: Path, base: str, head: str, attempt: int, output: Path) -> SizeReport:
    base_sha = git(root, "merge-base", base, head).strip()
    head_sha = git(root, "rev-parse", head).strip()
    # Validate revisions before passing them to checkout commands.
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base_sha, head_sha)):
        raise ValueError("invalid revision")
    paths = git(root, "diff", "--name-only", "--no-renames", "-z", base_sha, head_sha).split("\0")[
        :-1
    ]
    toolchain = string(
        table(tomllib.loads(git(root, "show", f"{head_sha}:rust-toolchain.toml"))["toolchain"])[
            "channel"
        ],
        "toolchain channel",
    )
    # Both snapshots use the PR's compiler, even if the base pins another compiler.
    os.environ["RUSTUP_TOOLCHAIN"] = toolchain
    compiler = subprocess.run(["rustc", "-vV"], check=True, capture_output=True, text=True).stdout
    host = next(
        line.removeprefix("host: ") for line in compiler.splitlines() if line.startswith("host: ")
    )
    os.environ["CARGO_BUILD_TARGET"] = host
    with tempfile.TemporaryDirectory(prefix="cli-sizes-") as directory:
        work = Path(directory)
        before, after = work / "base", work / "head"
        added: list[Path] = []
        try:
            for path, sha in ((before, base_sha), (after, head_sha)):
                git(root, "worktree", "add", "--detach", str(path), sha)
                added.append(path)
            before_members, after_members = discover(before), discover(after)
            selected = selected_packages(
                before, after, paths, before_members=before_members, after_members=after_members
            )
            before_binaries = selected_binaries(before_members, selected)
            after_binaries = selected_binaries(after_members, selected)
            report = SizeReport(
                base_sha=base_sha,
                head_sha=head_sha,
                run_attempt=attempt,
                toolchain=toolchain,
                target=host,
                rows=[
                    BinarySize(
                        package=package,
                        binary=binary,
                        base=Build(
                            status="failed" if (package, binary) in before_binaries else "absent"
                        ),
                        head=Build(
                            status="failed" if (package, binary) in after_binaries else "absent"
                        ),
                    )
                    for package, binary in sorted(before_binaries | after_binaries)
                ],
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report.model_dump_json(indent=2) + "\n")
            if not selected:
                print("No affected binary packages; skipping all builds.")
                return report
            print("Selected binary packages: " + ", ".join(sorted(selected)), flush=True)
            for label, snapshot, members in (
                ("base", before, before_members),
                ("head", after, after_members),
            ):
                results = build_sizes(snapshot, members, selected, work / f"target-{label}")
                for row in report.rows:
                    if (build := results.get((row.package, row.binary))) is not None:
                        setattr(row, label, build)
                output.write_text(report.model_dump_json(indent=2) + "\n")
            return report
        finally:
            for path in reversed(added):
                git(root, "worktree", "remove", "--force", str(path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    try:
        report = collect(
            args.root.resolve(), args.base, args.head, args.attempt, args.output.resolve()
        )
        failed = any(row.status == "failed" for row in report.rows)
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            from size_report import render_size

            run: dict[str, object] = {
                "run_number": int(os.environ["GITHUB_RUN_NUMBER"]),
                "id": int(os.environ["GITHUB_RUN_ID"]),
                "run_attempt": args.attempt,
                "conclusion": "failure" if failed else "success",
            }
            with Path(summary).open("a", encoding="utf-8") as destination:
                destination.write(render_size(os.environ["GITHUB_REPOSITORY"], run, report))
        if failed:
            sys.exit("Some binary builds failed; see the size report and build logs.")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f"Cannot collect sizes: {error}")


if __name__ == "__main__":
    main()
