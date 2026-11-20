"""Select Cargo packages from source changes and resolved lockfile dependencies."""

import subprocess
import tomllib
from pathlib import Path

from .workspace import Package, discover, string, strings, tables

type PackageId = tuple[str, str, str]
type Closure = dict[PackageId, dict[str, object]]


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="surrogateescape",
    ).stdout


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    return git(root, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--").split(
        "\0"
    )[:-1]


def production_change(path: str, directory: str) -> bool:
    prefix = "" if directory == "." else directory + "/"
    if not path.startswith(prefix):
        return False
    relative = path.removeprefix(prefix)
    return relative in {"Cargo.toml", "build.rs"} or relative.startswith("src/")


def source_changed_packages(root: Path, members: list[Package], paths: list[str]) -> set[str]:
    root = root.resolve()
    changed: set[str] = set()
    for member in members:
        directory = member.directory.relative_to(root).as_posix()
        if any(production_change(path, directory) for path in paths):
            changed.add(member.name)
    return changed


def lock_closures(content: str) -> dict[str, Closure]:
    records: Closure = {}
    for record in tables(tomllib.loads(content).get("package", [])):
        key = (
            string(record.get("name"), "package.name"),
            string(record.get("version"), "package.version"),
            string(record["source"], "package.source") if "source" in record else "",
        )
        if key in records:
            raise ValueError(f"Duplicate locked package: {key}")
        records[key] = record
    edges: dict[PackageId, set[PackageId]] = {}
    for key, record in records.items():
        dependencies: set[PackageId] = set()
        for dependency in strings(record.get("dependencies", []), "package.dependencies"):
            parts = dependency.split(" ", 2)
            matches = [
                candidate
                for candidate in records
                if candidate[0] == parts[0]
                and (len(parts) < 2 or candidate[1] == parts[1])
                and (len(parts) < 3 or f"({candidate[2]})" == parts[2])
            ]
            if len(matches) != 1:
                raise ValueError(f"Cannot resolve locked dependency: {dependency}")
            dependencies.add(matches[0])
        edges[key] = dependencies
    normalized = {
        key: record | {"dependencies": sorted(edges[key])} for key, record in records.items()
    }
    result: dict[str, Closure] = {}
    for root in records:
        if root[2]:
            continue
        closure: Closure = {}
        pending = [root]
        while pending:
            key = pending.pop()
            if key not in closure:
                closure[key] = normalized[key]
                pending.extend(edges[key])
        if root[0] in result:
            raise ValueError(f"Ambiguous local package: {root[0]}")
        result[root[0]] = closure
    return result


def dependencies_changed(before: Closure | None, after: Closure | None, changed: set[str]) -> bool:
    return before != after or any(
        not source and name in changed for name, _, source in (after or {})
    )


def affected_packages(root: Path, base: str, head: str, paths: list[str]) -> set[str]:
    members = discover(root)
    changed = source_changed_packages(root, members, paths)
    if "Cargo.lock" not in paths and not changed:
        return changed
    merge_base = git(root, "merge-base", base, head).strip()
    before = lock_closures(git(root, "show", f"{merge_base}:Cargo.lock"))
    after = lock_closures(git(root, "show", f"{head}:Cargo.lock"))
    for member in members:
        if member.name not in after:
            raise ValueError(f"Package missing from Cargo.lock: {member.name}")
        if dependencies_changed(before.get(member.name), after[member.name], changed):
            changed.add(member.name)
    return changed


def binary_changes(
    root: Path, packages: dict[str, str], paths: list[str], base: str, head: str
) -> list[str]:
    """Return affected workspace CLIs, including consumers of changed shared code."""
    if any(
        path in {"Cargo.toml", "rust-toolchain.toml"} or path.startswith(".cargo/")
        for path in paths
    ):
        return sorted(packages)
    return sorted(packages.keys() & affected_packages(root, base, head, paths))
