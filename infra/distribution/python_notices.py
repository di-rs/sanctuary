"""Collect notices from the wheels installed in a final service image."""

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import sysconfig
from importlib.metadata import Distribution
from pathlib import Path, PurePosixPath

NOTICE_NAME = re.compile(r"(?:authors|copying|copyright|licen[cs]e|notice)(?:[._-].*)?", re.I)
NATIVE_NAME = re.compile(r"\.so(?:\.|$)")
REVIEW_ROOT = Path(__file__).resolve().parent / "vendor/native"


def copy_notice(source: Path, destination: Path) -> None:
    if not source.is_file() or not (content := source.read_bytes()).strip():
        raise ValueError(f"Missing or empty notice file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def record_native_inputs(
    site: Path,
    files: set[PurePosixPath],
    sboms: set[PurePosixPath],
    wheel: str,
    destination: Path,
) -> dict[str, object]:
    native = {}
    for path in sorted(files):
        if path.is_absolute() or ".." in path.parts or not NATIVE_NAME.search(path.name):
            continue
        source = (site / path).resolve()
        if not source.is_relative_to(site):
            raise ValueError(f"invalid embedded library path: {path}")
        with source.open("rb") as stream:
            native[str(path)] = hashlib.file_digest(stream, "sha256").hexdigest()
    if not native:
        return {}
    verified = {}
    unresolved = set(native)
    review_directory = REVIEW_ROOT / wheel
    review_source = review_directory / "SOURCE.json"
    if review_source.is_file():
        for component, review in sorted(json.loads(review_source.read_bytes()).items()):
            objects = review["objects"]
            if not objects or any(native.get(name) != digest for name, digest in objects.items()):
                continue
            notices = []
            for name, checksum in sorted(review["notices"].items()):
                if hashlib.sha256((review_directory / name).read_bytes()).hexdigest() != checksum:
                    raise ValueError(f"reviewed native notice differs from its checksum: {name}")
                relative = Path("reviewed") / name
                copy_notice(review_directory / name, destination / relative)
                notices.append(relative.as_posix())
            verified[component] = {
                "objects": sorted(objects),
                "sources": review["sources"],
                "notices": notices,
            }
            unresolved.difference_update(objects)
    supplied = {}
    missing = []
    for sbom in sorted(sboms):
        data = json.loads((site / sbom).read_bytes())
        for component in sorted(data.get("components", []), key=lambda item: item["bom-ref"]):
            identity = component.get("purl", component["bom-ref"])
            texts = []
            for license_info in component.get("licenses", []):
                if text := license_info.get("license", {}).get("text", {}):
                    content = text["content"].encode()
                    if text.get("encoding") == "base64":
                        content = base64.b64decode(content, validate=True)
                    if content.strip():
                        key = hashlib.sha256(content).hexdigest()
                        destination.mkdir(parents=True, exist_ok=True)
                        (destination / f"{key}.txt").write_bytes(content)
                        texts.append(f"{key}.txt")
            if texts:
                supplied[identity] = sorted(set(texts))
            elif component["bom-ref"] != data.get("metadata", {}).get("component", {}).get(
                "bom-ref"
            ):
                missing.append(identity)
    return {
        "shared_objects": native,
        "upstream_sboms": sorted(map(str, sboms)),
        "embedded_license_texts": supplied,
        "sbom_entries_without_embedded_text": sorted(set(missing)),
        "verified_inputs": verified,
        "unresolved_objects": sorted(unresolved),
    }


def collect_wheels(
    site: Path,
    destination: Path,
    project: str | None = None,
    native_review: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    installed = sorted(
        (Distribution.at(info) for info in site.glob("*.dist-info")),
        key=lambda dist: dist.name.lower(),
    )
    if project is not None and project not in {dist.name for dist in installed}:
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
        sboms = {path for path in files if path.is_relative_to(metadata / "sboms")}
        notices.update(sboms)
        notices.update(
            path
            for path in files
            if (
                NOTICE_NAME.fullmatch(path.name)
                and path.suffix not in {".py", ".pyc"}
                or path.as_posix() == "pip/_vendor/vendor.txt"
            )
        )
        for path in sorted(notices):
            source = (site / path).resolve()
            if path.is_absolute() or ".." in path.parts or not source.is_relative_to(site):
                raise ValueError(f"{label} has an invalid notice path: {path}")
            copy_notice(source, destination / metadata.stem / path)
        if native_review is not None and (
            review := record_native_inputs(
                site, files, sboms, metadata.stem, destination / metadata.stem / "native"
            )
        ):
            native_review[label] = review
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
    parser.add_argument("--native-policy", choices=("report", "require-complete"), default="report")
    args = parser.parse_args()
    site = Path(sysconfig.get_path("platlib")).resolve()
    destination: Path = args.destination
    try:
        native_review: dict[str, dict[str, object]] = {}
        inventory = collect_wheels(site, destination / "python", args.project, native_review)
        copy_notice(args.project_license, destination / "Sanctuary.LICENSE")
        stdlib = Path(sysconfig.get_path("stdlib"))
        copy_notice(stdlib / "LICENSE.txt", destination / "CPython.LICENSE")
        base_site = stdlib / "site-packages"
        base_inventory = collect_wheels(
            base_site, destination / "python-base", native_review=native_review
        )
        if args.project == "cli-playground":
            static = site / "cli_playground/static"
            for filename in ("licenses.md", "tailwindcss.LICENSE"):
                copy_notice(static / filename, destination / "frontend" / filename)
        elif args.project == "boxie":
            capture = site / "boxie/sandbox/capture_bins"
            for filename in ("LICENSE.zig", "COPYRIGHT.musl"):
                copy_notice(capture / filename, destination / "capture" / filename)
        (destination / "python-packages.txt").write_text("\n".join(inventory) + "\n")
        (destination / "python-base-packages.txt").write_text("\n".join(base_inventory) + "\n")
        (destination / "os-packages.tsv").write_text("\n".join(os_packages()) + "\n")
        unresolved = sorted(
            label for label, review in native_review.items() if review["unresolved_objects"]
        )
        (destination / "native-wheel-review.json").write_text(
            json.dumps(
                {"complete": not unresolved, "wheels": native_review}, sort_keys=True, indent=2
            )
            + "\n"
        )
        if unresolved:
            message = "Native wheel notices require verification: " + ", ".join(unresolved)
            if args.native_policy == "require-complete":
                raise ValueError(message)
            print(message, file=sys.stderr)
    except (OSError, ValueError) as exc:
        sys.exit(f"Unable to assemble distribution notices: {exc}")


if __name__ == "__main__":
    main()
