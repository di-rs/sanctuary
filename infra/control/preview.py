"""Trusted preview eligibility. Git reads objects without checking out PR source."""

import json
import re
import subprocess
from pathlib import PurePosixPath
from typing import Any

from .release import sha


def changed_cli(names: list[str], package_roots: set[str]) -> bool:
    for name in names:
        path = PurePosixPath(name)
        if name in {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml"} or path.parts[:1] == (
            ".cargo",
        ):
            return True
        if len(path.parts) >= 3 and (
            path.parts[0] == "utils" or "/".join(path.parts[:2]) in package_roots
        ):
            return True
    return False


def git_paths(*args: str) -> list[str]:
    output = subprocess.check_output(["git", *args])
    return [p.decode("utf-8", "surrogateescape") for p in output.split(b"\0") if p]


def eligible(repository: str, number: int) -> tuple[bool, str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or number < 1:
        raise ValueError("invalid repository or pull request")
    pr: dict[str, Any] = json.loads(
        subprocess.check_output(["gh", "api", f"repos/{repository}/pulls/{number}"])
    )
    base, head = sha(pr["base"]["sha"], 40), sha(pr["head"]["sha"], 40)
    if (
        pr["state"] != "open"
        or pr["draft"]
        or (pr["head"]["repo"] or {}).get("full_name") != repository
    ):
        return False, base, head
    subprocess.run(["git", "fetch", "--no-tags", "origin", base, head], check=True)
    ancestor = subprocess.check_output(["git", "merge-base", base, head], text=True).strip()
    names = git_paths(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--name-only",
        "-z",
        ancestor,
        head,
    )
    roots: set[str] = set()
    for rev in (head, ancestor):
        paths = git_paths(
            "ls-tree", "-rz", "--name-only", rev, "--", "buildins", "packages", "tools", "utils"
        )
        roots.update(
            p.removesuffix("/src/main.rs")
            for p in paths
            if re.fullmatch(r"(?:buildins|packages|tools|utils)/[^/]+/src/main\.rs", p)
        )
    return changed_cli(names, roots), base, head
