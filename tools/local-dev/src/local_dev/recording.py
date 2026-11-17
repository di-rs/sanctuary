"""Choose real browser exercises from the same workspace graph as preview builds."""

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
            path.startswith(("tools/cli-playground/frontend/e2e-record/", "tools/local-dev/src/"))
            or path == "tools/cli-playground/frontend/playwright.record.config.ts"
            or path == "tools/cli-playground/dev/Dockerfile"
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
