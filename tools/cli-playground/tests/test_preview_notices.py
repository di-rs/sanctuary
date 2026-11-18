"""Verify the recipient archive and its association to the target binaries."""

import io
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

import preview_notices
import pytest
from cli_playground.artifacts import binary_archive

from .helpers import clean_git_env, git_commit

ROOT = Path(__file__).resolve().parents[3]


def test_cargo_output_separates_target_features_from_host_libraries(tmp_path: Path) -> None:
    release = tmp_path / preview_notices.TARGET / "release"
    binary = str(release / "echor")
    messages = io.StringIO(
        "\n".join(
            json.dumps(
                {
                    "reason": "compiler-artifact",
                    "package_id": name,
                    "target": {"kind": [kind]},
                    "features": features,
                    "filenames": [filename],
                    "executable": executable,
                }
            )
            for name, kind, features, filename, executable in (
                ("echor", "bin", [], binary, binary),
                ("runtime", "lib", ["actual"], str(release / "deps/libruntime.rlib"), None),
                ("host", "lib", ["build-only"], str(tmp_path / "release/deps/libhost.rlib"), None),
                ("derive", "proc-macro", [], str(release / "deps/libderive.so"), None),
            )
        )
    )
    assert preview_notices.cargo_artifacts(messages, release, ["echor"]) == (
        {"echor": binary},
        {"echor": set(), "runtime": {"actual"}},
    )
    messages.seek(0)
    with pytest.raises(ValueError, match="selected target executables"):
        preview_notices.cargo_artifacts(messages, release, ["uniqr"])


def test_missing_crate_notice_stops_companion_creation(tmp_path: Path) -> None:
    package: preview_notices.CargoPackage = {
        "id": "registry+example#demo@1.0.0",
        "name": "demo",
        "version": "1.0.0",
        "source": "registry+example",
        "manifest_path": str(tmp_path / "Cargo.toml"),
        "license": "MIT",
        "license_file": None,
        "links": None,
    }
    output = tmp_path / "notices.zip"
    (tmp_path / "Cargo.lock").write_text("version = 4\n")
    with pytest.raises(ValueError, match="missing license notice text for demo@1.0.0"):
        preview_notices.write_notice_bundle(
            tmp_path,
            output,
            "a" * 40,
            {},
            {package["id"]: {"default"}},
            [package],
            tmp_path,
        )
    assert not output.exists()


@pytest.mark.integration
@pytest.mark.parametrize("name", ["echor", "uniqr"])
def test_linux_preview_companion_matches_real_executables(name: str, tmp_path: Path) -> None:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    reference = tmp_path / "reference"
    reference.mkdir()
    companion = reference / f"{name}-third-party-notices.zip"
    binaries = tmp_path / "binaries"
    preview_notices.build(ROOT, [name], binaries, companion, revision)
    repeated = tmp_path / "repeated.zip"
    preview_notices.build(ROOT, [name], tmp_path / "repeated-binaries", repeated, revision)
    assert companion.read_bytes() == repeated.read_bytes()
    assert {member.name for member in binaries.iterdir()} == {name}
    artifact = io.BytesIO()
    with ZipFile(artifact, "w") as bundle:
        bundle.write(binaries / name, name)
    assert set(binary_archive(artifact.getvalue())) == {name}

    with ZipFile(companion) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["revision"] == revision
        assert manifest["target"] == preview_notices.TARGET
        assert manifest["executables"] == {name: preview_notices.sha256(binaries / name)}
        assert bundle.read("rust/COPYRIGHT-library.html").strip()
        crates = {crate["name"]: crate for crate in manifest["crates"]}
        assert name in crates
        assert "derive" in crates["clap"]["features"]
        assert "clap_derive" not in crates
        assert "cli-testing" not in crates
        assert ("exitcode" in crates) == (name == "uniqr")
        assert all(
            bundle.read(file).strip() for crate in crates.values() for file in crate["notices"]
        )
    print(name, preview_notices.sha256(companion), len(crates), "target crates")


@pytest.mark.integration
def test_local_vendored_path_keeps_its_own_attribution(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    vendor = root / "vendor/brush-core"
    app = root / "app"
    for crate in (vendor, app):
        (crate / "src").mkdir(parents=True)
    (root / "rust-toolchain.toml").write_bytes((ROOT / "rust-toolchain.toml").read_bytes())
    (root / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["app"]\nexclude = ["vendor/brush-core"]\nresolver = "3"\n'
        '[workspace.package]\nlicense = "Apache-2.0"\n'
    )
    (root / "LICENSE").write_text("Fixture workspace license\n")
    (vendor / "Cargo.toml").write_text(
        '[package]\nname = "brush-core"\nversion = "0.5.0"\nedition = "2024"\nlicense = "MIT"\n'
    )
    (vendor / "src/lib.rs").write_text("pub fn upstream_value() -> u32 { 42 }\n")
    notice = vendor / "LICENSE"
    notice.write_text("Fixture upstream copyright and license\n")
    (app / "Cargo.toml").write_text(
        '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2024"\nlicense.workspace = true\n'
        '[dependencies]\nbrush-core = { path = "../vendor/brush-core" }\n'
    )
    (app / "src/main.rs").write_text(
        'fn main() { println!("{}", brush_core::upstream_value()); }\n'
    )
    subprocess.run(["cargo", "generate-lockfile", "--offline"], cwd=root, check=True)
    subprocess.run(["git", "init", "-q"], cwd=root, env=clean_git_env(), check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=clean_git_env(), check=True)
    git_commit(root)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, env=clean_git_env(), text=True
    ).strip()

    companion = tmp_path / "notice.zip"
    binaries = tmp_path / "binaries"
    preview_notices.build(root, ["fixture"], binaries, companion, revision)
    assert subprocess.check_output([str(binaries / "fixture")]) == b"42\n"
    with ZipFile(companion) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        crates = {crate["name"]: crate for crate in manifest["crates"]}
        assert crates["brush-core"]["source"] == "vendor/brush-core/Cargo.toml"
        [upstream_license] = crates["brush-core"]["notices"]
        assert bundle.read(upstream_license) == notice.read_bytes()
        [workspace_license] = crates["fixture"]["notices"]
        assert bundle.read(workspace_license) == (root / "LICENSE").read_bytes()

    notice.unlink()
    with pytest.raises(ValueError, match="missing license notice text for brush-core@0.5.0"):
        preview_notices.build(
            root, ["fixture"], tmp_path / "missing", tmp_path / "missing.zip", revision
        )
    assert not (tmp_path / "missing.zip").exists()
