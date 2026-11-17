"""Choose real browser exercises from the same workspace graph as preview builds."""

import re
from collections.abc import Iterable
from pathlib import Path

from cli_check.affected import binary_changes, changed_paths
from cli_check.workspace import discover


def recording_packages(
    root: Path, requested: list[str] | None, base: str | None, head: str
) -> dict[str, str]:
    packages = {
        p.name: p.directory.relative_to(root).as_posix() for p in discover(root) if p.is_cli
    }
    names = set(packages)
    if requested:
        if unknown := set(requested) - names:
            raise ValueError(f"Unknown CLI packages: {', '.join(sorted(unknown))}")
        names = set(requested)
    elif base:
        paths = changed_paths(root, base, head)
        recorder_changed = any(
            path.startswith(
                (
                    "tools/cli-playground/dev/",
                    "tools/cli-playground/frontend/e2e-record/",
                    "tools/local-dev/src/",
                )
            )
            or path
            in {
                "tools/cli-playground/compose.dev.yml",
                "tools/cli-playground/frontend/playwright.record.config.ts",
                "tools/cli-playground/tests/dev_server.py",
            }
            for path in paths
        )
        if not recorder_changed:
            names = set(binary_changes(root, packages, paths, base, head))
            names.update(
                name
                for name, directory in packages.items()
                if f"{directory}/tests/browser.json" in paths
            )
    return {name: str(root / packages[name] / "tests/browser.json") for name in sorted(names)}


def check_pr_recordings(packages: Iterable[str], body: str) -> None:
    """Require a separately labelled GitHub media attachment for each selected CLI."""
    uuid = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
    videos = dict(
        re.findall(
            rf"^#### `([\w-]+)`[ \t]*\n\s*^(https://github\.com/user-attachments/assets/{uuid})[ \t]*$",
            body.replace("\r\n", "\n"),
            re.MULTILINE,
        )
    )
    selected = set(packages)
    if missing := sorted(selected - videos.keys()):
        raise ValueError(
            f"Attach local recordings for {', '.join(missing)}. "
            "Use the PR format in docs/cli-development.md."
        )
    if len({videos[name] for name in selected}) != len(selected):
        raise ValueError("Attach a different local recording for each selected CLI.")
