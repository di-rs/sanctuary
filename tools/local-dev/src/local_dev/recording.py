"""Check for review evidence on CLI implementation changes."""

import re
from collections.abc import Iterable
from pathlib import Path

from cli_check.affected import changed_paths
from cli_check.workspace import discover


def changed_clis(root: Path, base: str, head: str) -> list[str]:
    """Direct CLI code changes need a demo or a short internal-change explanation."""
    paths = changed_paths(root, base, head)
    names = []
    for package in discover(root):
        if package.is_cli:
            directory = package.directory.relative_to(root).as_posix()
            prefix = "" if directory == "." else directory + "/"
            if any(
                path == prefix + "build.rs" or path.startswith(prefix + "src/") for path in paths
            ):
                names.append(package.name)
    return sorted(names)


def check_pr_recordings(packages: Iterable[str], body: str) -> None:
    """Read the per-CLI video links or internal-change explanations in a PR."""
    uuid = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
    body = body.replace("\r\n", "\n")
    videos = dict(
        re.findall(
            rf"^#### `([\w-]+)`[ \t]*\n\s*^(https://github\.com/user-attachments/assets/{uuid})[ \t]*$",
            body,
            re.MULTILINE,
        )
    )
    selected = set(packages)
    internal = set(
        re.findall(r"^#### `([\w-]+)`[ \t]*\n\s*^Internal change — \S[^\n]*$", body, re.MULTILINE)
    )
    if missing := sorted(selected - videos.keys() - internal):
        raise ValueError(
            f"Attach a demo or explain the internal change for {', '.join(missing)}. "
            "Use the PR format in docs/cli-development.md."
        )
    if len(set(videos.values())) != len(videos):
        raise ValueError("Attach a different local recording for each selected CLI.")
