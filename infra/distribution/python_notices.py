"""Collect notices from the wheels installed in a final service image."""

import argparse
import csv
import io
import re
import subprocess
import sys
import sysconfig
from importlib.metadata import Distribution
from pathlib import Path, PurePosixPath

NOTICE_NAME = re.compile(r"(?:authors|copying|copyright|licen[cs]e|notice)(?:[._-].*)?", re.I)


def copy_notice(source: Path, destination: Path) -> None:
    if not source.is_file() or not (content := source.read_bytes()).strip():
        raise ValueError(f"Missing or empty notice file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def collect_wheels(site: Path, destination: Path, project: str) -> list[str]:
    installed = sorted(
        (Distribution.at(info) for info in site.glob("*.dist-info")),
        key=lambda dist: dist.name.lower(),
    )
    if project not in {dist.name for dist in installed}:
        raise ValueError(f"Missing installed project: {project}")
    inventory = []
    for dist in installed:
        label = f"{dist.name} {dist.version}"
        inventory.append(label)
        # RECORD gives the paths actually present in the installed target wheel.
        if not (record := dist.read_text("RECORD")):
            raise ValueError(f"{label} has no wheel RECORD")
        files = {PurePosixPath(filename) for filename, _, _ in csv.reader(io.StringIO(record))}
        metadata_dirs = {
            path.parent
            for path in files
            if len(path.parts) == 2
            and path.parent.suffix == ".dist-info"
            and path.name == "METADATA"
        }
        if len(metadata_dirs) != 1:
            raise ValueError(f"{label} has no unique METADATA entry in RECORD")
        (metadata,) = metadata_dirs
        notices = {
            path
            for path in files
            if path.is_relative_to(metadata / "licenses")
            or (path.parent == metadata and NOTICE_NAME.fullmatch(path.name))
        }
        declared = {
            metadata / "licenses" / filename
            for filename in dist.metadata.get_all("License-File", [])
        }
        if missing := declared - notices:
            raise ValueError(f"{label} is missing declared notice files: {sorted(missing)}")
        if dist.name != project and not notices:
            raise ValueError(f"{label} ships without wheel license files")
        # Preserve additional upstream notice and inventory files shipped by native wheels.
        notices.update(path for path in files if path.is_relative_to(metadata / "sboms"))
        notices.update(
            path for path in files if path.name in {"LICENSE", "LICENSE.txt", "COPYRIGHT"}
        )
        for path in sorted(notices):
            source = (site / path).resolve()
            if path.is_absolute() or ".." in path.parts or not source.is_relative_to(site):
                raise ValueError(f"{label} has an invalid notice path: {path}")
            copy_notice(source, destination / metadata.stem / path)
    return inventory


def os_packages() -> list[str]:
    rows = subprocess.check_output(
        ["dpkg-query", "--show", "--showformat=${db:Status-Status}\t${Package}\t${Version}\n"],
        text=True,
    )
    inventory = []
    for row in sorted(rows.splitlines()):
        status, name, version = row.split("\t")
        if status == "installed":
            copyright_file = Path("/usr/share/doc") / name / "copyright"
            if not copyright_file.is_file() or not copyright_file.read_bytes().strip():
                raise ValueError(f"Missing or empty OS copyright file: {copyright_file}")
            inventory.append(f"{name}\t{version}\t{copyright_file}")
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("project_license", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    site = Path(sysconfig.get_path("platlib")).resolve()
    destination: Path = args.destination
    try:
        inventory = collect_wheels(site, destination / "python", args.project)
        copy_notice(args.project_license, destination / "Sanctuary.LICENSE")
        stdlib = Path(sysconfig.get_path("stdlib"))
        copy_notice(stdlib / "LICENSE.txt", destination / "CPython.LICENSE")
        if args.project == "cli-playground":
            static = site / "cli_playground/static"
            for filename in ("licenses.md", "tailwindcss.LICENSE"):
                copy_notice(static / filename, destination / "frontend" / filename)
        elif args.project == "boxie":
            capture = site / "boxie/sandbox/capture_bins"
            for filename in ("LICENSE.zig", "COPYRIGHT.musl"):
                copy_notice(capture / filename, destination / "capture" / filename)
        (destination / "python-packages.txt").write_text("\n".join(inventory) + "\n")
        (destination / "os-packages.tsv").write_text("\n".join(os_packages()) + "\n")
    except (OSError, ValueError) as exc:
        sys.exit(f"Unable to assemble distribution notices: {exc}")


if __name__ == "__main__":
    main()
