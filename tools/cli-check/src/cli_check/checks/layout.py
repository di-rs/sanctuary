"""Enforce one matching binary per CLI package."""

from pathlib import Path

from cli_check.diagnostics import Diagnostic
from cli_check.workspace import Package, load_toml, table


def check(root: Path, packages: list[Package]) -> list[Diagnostic]:
    errors: list[Diagnostic] = []
    workspace = table(load_toml(root / "Cargo.toml").get("workspace", {}))
    for package in packages:
        manifest = (package.directory / "Cargo.toml").relative_to(root).as_posix()
        if (
            "lints" in workspace
            and table(package.manifest.get("lints", {})).get("workspace") is not True
        ):
            errors.append(
                Diagnostic(manifest, "layout", "lints", "inherit [lints] workspace = true")
            )
        if not package.is_cli:
            continue
        if len(package.binaries) != 1:
            errors.append(
                Diagnostic(manifest, "layout", "single-binary", "must define exactly one binary")
            )
        if package.name != package.directory.name:
            errors.append(
                Diagnostic(
                    manifest, "layout", "package-name", "package name must match directory name"
                )
            )
        for binary in package.binaries:
            if binary.name != package.name:
                errors.append(
                    Diagnostic(
                        manifest, "layout", "binary-name", "binary name must match package name"
                    )
                )
            if (
                binary.source != (package.directory / "src/main.rs").resolve()
                or not binary.source.is_file()
            ):
                errors.append(
                    Diagnostic(
                        manifest,
                        "layout",
                        "binary-source",
                        "binary must use an existing src/main.rs",
                    )
                )
        for source in sorted((package.directory / "src/bin").rglob("*.rs")):
            errors.append(
                Diagnostic(
                    source.relative_to(root).as_posix(),
                    "layout",
                    "bin-directory",
                    "use src/main.rs instead of src/bin/ for CLI sources",
                )
            )
    return errors
