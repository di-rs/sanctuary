"""Runs inside a disposable Linux builder, including all Cargo build scripts."""

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def main() -> None:
    # Copy into the container's disposable filesystem. The checkout on the runner is read-only.
    work = Path("/work")
    root = work / "source"
    shutil.copytree("/source", root, symlinks=True)
    os.chdir(root)
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    (work / "temp").mkdir()
    os.environ.update(
        CARGO_TARGET_DIR=str(work / "target"),
        CARGO_HOME=str(work / "cargo"),
        RUSTUP_HOME=str(work / "rustup"),
        HOME=str(work),
        TMPDIR=str(work / "temp"),
    )

    # Keep build output away from the binary ZIP stream.
    def run(*args: str) -> None:
        subprocess.run(args, check=True, stdout=sys.stderr)

    import tomllib

    channel = tomllib.loads(Path("rust-toolchain.toml").read_text())["toolchain"]["channel"]
    if not re.fullmatch(r"nightly-\d{4}-\d{2}-\d{2}|\d+\.\d+\.\d+", channel):
        raise ValueError("invalid toolchain")
    run("rustup", "toolchain", "install", channel, "--profile", "minimal", "--no-self-update")
    metadata = json.loads(
        subprocess.check_output(
            ["cargo", "metadata", "--locked", "--no-deps", "--format-version=1"]
        )
    )
    packages: list[str] = []
    bins: list[str] = []
    for pkg in metadata["packages"]:
        if pkg["id"] not in metadata["workspace_members"]:
            continue
        for target in pkg["targets"]:
            if "bin" in target["kind"] and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", target["name"]):
                packages += ["--package", pkg["name"]]
                bins.append(target["name"])
    if not bins:
        raise ValueError("no CLI binary targets")
    run("cargo", "build", "--locked", "--release", "--bins", *packages)
    out = work / "bin"
    out.mkdir()
    for name in bins:
        shutil.copyfile(work / "target/release" / name, out / name)
        (out / name).chmod(0o755)
    # The catalog is optional at the gateway, but is part of the Playground UI.
    python = sys.executable
    env = os.environ | {
        "PYTHONPATH": os.pathsep.join(
            str(root / path) for path in ("tools/cli-playground/src", "tools/cli-check/src")
        )
    }
    subprocess.run(
        [
            python,
            "-c",
            "from cli_playground.catalog_build import build_catalog; import sys; from pathlib import Path;"
            " build_catalog(Path.cwd(),sys.argv[1],sys.argv[2],sys.argv[3:],Path('/work/bin'))",
            sys.argv[1],
            sys.argv[2],
            *sorted(bins),
        ],
        check=True,
        stdout=sys.stderr,
        env=env,
    )
    archive = work / "bundle.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
        for path in sorted(out.iterdir()):
            bundle.write(path, path.name)
    with archive.open("rb") as stream:
        shutil.copyfileobj(stream, sys.stdout.buffer)


if __name__ == "__main__":
    main()
