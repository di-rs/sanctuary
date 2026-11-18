"""Build Linux preview executables and assemble their revision-bound companion notices."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import IO, TypedDict, cast
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

TARGET = "x86_64-unknown-linux-gnu"
NOTICE_PREFIXES = ("license", "licence", "copying", "copyright", "notice", "unlicense")


class BuildArtifact(TypedDict):
    reason: str
    package_id: str
    target: dict[str, list[str]]
    features: list[str]
    filenames: list[str]
    executable: str | None


class CargoPackage(TypedDict):
    id: str
    name: str
    version: str
    source: str | None
    manifest_path: str
    license: str | None
    license_file: str | None
    links: str | None


def cargo_artifacts(
    messages: IO[str],
    release: Path,
    names: list[str],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    executables: dict[str, str] = {}
    features: dict[str, set[str]] = {}
    for line in messages:
        artifact = cast(BuildArtifact, json.loads(line))
        if artifact["reason"] != "compiler-artifact":
            continue
        # Explicit --target puts target libraries in a different directory from
        # host build scripts, their dependencies, and proc macros.
        kinds = artifact["target"]["kind"]
        if "custom-build" in kinds or "proc-macro" in kinds:
            continue
        if binary := artifact["executable"]:
            path = Path(binary)
            if path.parent == release and path.name in names:
                executables[path.name] = binary
        if any(Path(file).is_relative_to(release) for file in artifact["filenames"]):
            features.setdefault(artifact["package_id"], set()).update(artifact["features"])
    if sorted(executables) != sorted(names) or not features:
        raise ValueError("Cargo did not report the selected target executables and libraries")
    return executables, features


def notice_files(package: CargoPackage, root: Path, checksum: str | None) -> dict[str, bytes]:
    directory = Path(package["manifest_path"]).parent
    label = f"{package['name']}@{package['version']}"
    paths = {
        path
        for path in directory.iterdir()
        if path.is_file() and path.name.lower().startswith(NOTICE_PREFIXES)
    }
    if filename := package["license_file"]:
        declared = directory / filename
        if not declared.is_file() or not declared.read_bytes().strip():
            raise ValueError(f"missing declared license file for {label}: {filename}")
        paths.add(declared)
    if not paths and package["source"] is None and directory.is_relative_to(root):
        manifest = tomllib.loads(Path(package["manifest_path"]).read_text())
        inherited = manifest["package"].get("license") == {"workspace": True}
        if inherited and "vendor" not in directory.relative_to(root).parts:
            paths.add(root / "LICENSE")
    if not paths and checksum:
        supplement = root / "tools/cli-playground/vendor/rust-notices" / label.replace("@", "-")
        provenance = supplement / "SOURCE.json"
        if provenance.is_file():
            review = json.loads(provenance.read_bytes())
            if review["crate_sha256"] != checksum:
                raise ValueError(f"reviewed notice checksum does not match Cargo.lock for {label}")
            paths = {supplement / filename for filename in review["notices"]}
            paths.add(provenance)
    texts = {path.name: path.read_bytes() for path in sorted(paths)}
    if not texts or any(not content.strip() for content in texts.values()):
        raise ValueError(f"missing license notice text for {label}")
    if package["links"]:
        raise ValueError(f"review the native code and its notices for {label}")
    return texts


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_notice_bundle(
    root: Path,
    output: Path,
    revision: str,
    executables: dict[str, str],
    features: dict[str, set[str]],
    packages: list[CargoPackage],
    sysroot: Path,
) -> None:
    entries = {}
    inventory = []
    lockfile = root / "Cargo.lock"
    checksums = {
        (item["name"], item["version"], item.get("source")): item.get("checksum")
        for item in tomllib.loads(lockfile.read_text()).get("package", [])
    }
    for package in sorted(packages, key=lambda item: item["id"]):
        if package["id"] not in features:
            continue
        origin = package["source"] or Path(package["manifest_path"]).relative_to(root).as_posix()
        key = hashlib.sha256(origin.encode()).hexdigest()[:16]
        prefix = f"crates/{package['name']}-{package['version']}-{key}"
        checksum = checksums.get((package["name"], package["version"], package["source"]))
        texts = notice_files(package, root, checksum)
        files = [f"{prefix}/{name}" for name in sorted(texts)]
        entries.update({f"{prefix}/{name}": content for name, content in texts.items()})
        inventory.append(
            {
                "name": package["name"],
                "version": package["version"],
                "source": origin,
                "source_checksum": checksum,
                "features": sorted(features[package["id"]]),
                "license": package["license"],
                "notices": files,
            }
        )
    if len(inventory) != len(features):
        raise ValueError("Cargo metadata is missing packages compiled for the preview target")
    docs = sysroot / "share/doc/rust"
    for file in (docs / "COPYRIGHT-library.html", *sorted((docs / "licenses").glob("*"))):
        if file.is_file():
            entries[f"rust/{file.relative_to(docs)}"] = file.read_bytes()
    if not entries.get("rust/COPYRIGHT-library.html"):
        raise ValueError("missing the pinned Rust standard library copyright notices")
    manifest = {
        "revision": revision,
        "target": TARGET,
        "cargo_lock_sha256": sha256(lockfile),
        "executables": {name: sha256(Path(path)) for name, path in sorted(executables.items())},
        "crates": sorted(inventory, key=lambda item: (str(item["name"]), str(item["source"]))),
    }
    entries["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    with ZipFile(output, "x") as bundle:
        for name, content in sorted(entries.items()):
            bundle.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)


def build(root: Path, names: list[str], binaries: Path, companion: Path, revision: str) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if revision != head:
        raise ValueError("preview notices must match the checked-out revision")
    metadata = json.loads(
        subprocess.check_output(
            ["cargo", "metadata", "--format-version", "1", "--locked", "--filter-platform", TARGET],
            cwd=root,
        )
    )
    release = Path(metadata["target_directory"]) / TARGET / "release"
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as messages:
        subprocess.run(
            [
                "cargo",
                "build",
                "--locked",
                "--release",
                "--bins",
                "--target",
                TARGET,
                "--message-format=json-render-diagnostics",
                *(arg for name in names for arg in ("--package", name)),
            ],
            cwd=root,
            stdout=messages,
            check=True,
        )
        messages.seek(0)
        executables, features = cargo_artifacts(messages, release, names)
    sysroot = subprocess.check_output(["rustc", "--print", "sysroot"], cwd=root, text=True).strip()
    write_notice_bundle(
        root, companion, revision, executables, features, metadata["packages"], Path(sysroot)
    )
    binaries.mkdir()
    for name, source in sorted(executables.items()):
        shutil.copy2(source, binaries / name)
