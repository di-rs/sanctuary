"""Run a dependency scanner and check its coverage against the locked input."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from typing import Any


def json_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {label}")
    return value


def scan(
    command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> dict[str, Any]:
    result = subprocess.run(
        command, cwd=cwd, env=env, timeout=300, text=True, stdout=subprocess.PIPE
    )
    if result.returncode not in (0, 1):
        raise ValueError(f"Scanner exited with status {result.returncode}")
    try:
        report = json_object(json.loads(result.stdout), "scanner report")
    except json.JSONDecodeError as error:
        raise ValueError(f"Scanner returned invalid JSON (status {result.returncode})") from error
    if result.returncode == 1 and not report.get("error"):
        # Exit 1 may carry advisories. It cannot establish a clean result.
        report["error"] = "Scanner exited with status 1"
    return report


def audit_python() -> tuple[str, str]:
    # Run under pip-audit's interpreter so both sides evaluate markers identically.
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    export = subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--all-packages",
            "--all-groups",
            "--all-extras",
            "--no-emit-workspace",
            "--no-hashes",
            "--no-annotate",
            "--no-header",
        ],
        check=True,
        timeout=90,
        text=True,
        stdout=subprocess.PIPE,
    )
    expected: set[tuple[str, Version]] = set()
    for line in export.stdout.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==":
            raise ValueError(f"Applicable requirement {requirement.name} has no exact version")
        expected.add((canonicalize_name(requirement.name), Version(pins[0].version)))
    if not expected:
        raise ValueError("uv exported zero applicable dependencies")

    with TemporaryDirectory() as directory:
        requirements = Path(directory) / "requirements.txt"
        requirements.write_text(export.stdout, encoding="utf-8")
        report = scan(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--disable-pip",
                "--no-deps",
                "--progress-spinner",
                "off",
                "--format",
                "json",
                "--requirement",
                str(requirements),
            ]
        )
    rows = report.get("dependencies")
    if not isinstance(rows, list):
        raise ValueError("pip-audit report has no dependency list")
    audited: set[tuple[str, Version]] = set()
    affected = []
    for row in rows:
        dependency = json_object(row, "pip-audit dependency")
        vulnerabilities = dependency.get("vulns")
        if dependency.get("skip_reason") is not None or not isinstance(vulnerabilities, list):
            continue
        name, version = dependency.get("name"), dependency.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        if vulnerabilities:
            affected.append(dependency)
        else:
            audited.add((canonicalize_name(name), Version(version)))
    if affected:
        print(json.dumps(affected))
        return "Affected", "pip-audit reported known vulnerabilities"
    if report.get("error") is not None or audited != expected or len(audited) != len(rows):
        raise ValueError(
            f"pip-audit coverage could not be verified ({len(audited)} reported, {len(expected)} expected)"
        )
    return (
        "Clean",
        f"pip-audit found no known vulnerabilities in {len(audited)} applicable locked packages",
    )


def frontend_package_count(frontend: Path) -> int:
    import yaml

    manifest = json_object(
        json.loads((frontend / "package.json").read_text(encoding="utf-8")), "frontend manifest"
    )
    with (frontend / "pnpm-lock.yaml").open(encoding="utf-8") as lockfile:
        try:
            documents = [
                json_object(doc, "pnpm lockfile document") for doc in yaml.safe_load_all(lockfile)
            ]
        except yaml.YAMLError as error:
            raise ValueError("Invalid pnpm lockfile YAML") from error
    if not documents:
        raise ValueError("Empty pnpm lockfile")
    # pnpm v12 can put its own packages in a boot document before the project document.
    importers = json_object(documents[-1].get("importers"), "frontend lockfile importers")
    importer = json_object(importers.get("."), "frontend lockfile importer")
    direct_count = 0
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        direct = json_object(manifest.get(section, {}), f"frontend manifest {section}")
        locked = json_object(importer.get(section, {}), f"frontend lockfile {section}")
        if direct != {
            name: json_object(entry, "lockfile dependency").get("specifier")
            for name, entry in locked.items()
        }:
            raise ValueError(f"Frontend manifest and lockfile disagree on {section}")
        direct_count += len(direct)
    project_packages = json_object(documents[-1].get("packages"), "frontend project packages")
    if not direct_count or not project_packages:
        raise ValueError("pnpm lockfile contains no frontend application dependencies")
    return len(
        {
            package
            for doc in documents
            for package in json_object(doc.get("packages", {}), "locked packages")
        }
    )


def audit_frontend(frontend: Path) -> tuple[str, str]:
    with TemporaryDirectory() as directory:
        audit_dir = Path(directory)
        for name in ("package.json", "pnpm-lock.yaml"):
            copyfile(frontend / name, audit_dir / name)
        expected = frontend_package_count(audit_dir)
        # Omit repository audit exceptions, configuration, and lifecycle scripts.
        (audit_dir / "pnpm-workspace.yaml").write_text("packages: []\n", encoding="utf-8")
        report = scan(
            ["pnpm", "audit", "--json", "--audit-level", "info", "--ignore-registry-errors=false"],
            cwd=audit_dir,
            env={
                **os.environ,
                "NPM_CONFIG_USERCONFIG": os.devnull,
                "NPM_CONFIG_GLOBALCONFIG": os.devnull,
            },
        )
    metadata = json_object(report.get("metadata"), "pnpm audit metadata")
    counts = json_object(metadata.get("vulnerabilities"), "pnpm vulnerability counts")
    if report.get("advisories") or any(
        type(count) is int and count > 0 for count in counts.values()
    ):
        print(json.dumps(report))
        return "Affected", "pnpm reported known vulnerabilities"
    if (
        report.get("error") is not None
        or report.get("advisories") != {}
        or counts.keys() != {"info", "low", "moderate", "high", "critical"}
        or any(type(count) is not int or count != 0 for count in counts.values())
    ):
        raise ValueError("pnpm did not return a complete advisory result")
    total = metadata.get("totalDependencies")
    if type(total) is not int or total != expected:
        raise ValueError(
            f"pnpm coverage could not be verified ({total!r} reported, {expected} expected)"
        )
    return "Clean", f"pnpm found no known vulnerabilities in {total} locked package versions"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ecosystem", choices=("python", "frontend"))
    ecosystem = parser.parse_args().ecosystem
    try:
        if ecosystem == "python":
            outcome, detail = audit_python()
        else:
            outcome, detail = audit_frontend(Path("tools/cli-playground/frontend"))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        outcome, detail = "Incomplete", str(error)
    summary = f"{ecosystem.title()} dependency audit — {outcome}. {detail}."
    print(summary)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        print(summary, file=output)
    return {"Clean": 0, "Affected": 1, "Incomplete": 2}[outcome]


if __name__ == "__main__":
    sys.exit(main())
