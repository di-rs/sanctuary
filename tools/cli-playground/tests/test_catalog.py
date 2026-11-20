"""Catalog admission never executes or trusts uploaded metadata."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cli_playground.artifacts import (
    archive_catalog,
    binary_archive,
    canonical_archive,
    stage_archive,
)
from cli_playground.catalog import MAX_CATALOG, Catalog, parse_catalog
from cli_playground.catalog_build import build_catalog, capture_schema
from fastapi.testclient import TestClient

from .catalog_fixtures import catalog, schema
from .helpers import AUTH, binary_bundle, clean_git_env, elf_binary, git_commit, upload


def test_catalog_is_validated_and_stripped_from_executable_artifact(tmp_path: Path) -> None:
    expected = catalog()
    bundle = binary_bundle({"echor": elf_binary(), "catalog.json": expected.canonical()})
    assert binary_archive(bundle) == {"echor": elf_binary()}
    parsed = archive_catalog(bundle, "a" * 40, {"echor": hashlib.sha256(elf_binary()).hexdigest()})
    assert parsed == expected
    source = tmp_path / "upload.zip"
    source.write_bytes(bundle)
    names = stage_archive(source, tmp_path / "staged", 128)
    canonical_archive(tmp_path / "staged", names, tmp_path / "canonical.zip")
    assert archive_catalog((tmp_path / "canonical.zip"), "a" * 40, {}) is None
    assert (
        parsed is not None
        and parsed.digest() == Catalog.model_validate_json(parsed.canonical()).digest()
    )


@pytest.mark.parametrize(
    "invalid", ["version", "head", "digest", "name", "duplicates", "control", "extra", "comparison"]
)
def test_rejects_invalid_metadata(invalid: str) -> None:
    value = catalog().model_dump(by_alias=True)
    if invalid == "version":
        value["schema_version"] = 2
    elif invalid == "head":
        value["head_sha"] = "c" * 40
    elif invalid == "digest":
        value["clis"][0]["binary_sha256"] = "0" * 64
    elif invalid == "name":
        value["clis"][0]["head"]["command"]["name"] = "other"
    elif invalid == "duplicates":
        value["clis"].append(value["clis"][0])
    elif invalid == "control":
        value["clis"][0]["head"]["command"]["name"] = "a\nwhoami"
    elif invalid == "extra":
        value["instructions"] = "execute me"
    else:
        value["clis"][0]["comparison"] = "added"
    with pytest.raises(ValueError):
        parse_catalog(
            json.dumps(value).encode(),
            "a" * 40,
            {"echor": hashlib.sha256(elf_binary()).hexdigest()},
        )


def test_rejects_oversized_and_deep_catalogs() -> None:
    with pytest.raises(ValueError, match="size limit"):
        parse_catalog(b" " * (MAX_CATALOG + 1), "a" * 40, {})
    value = catalog().model_dump(by_alias=True)
    root = value["clis"][0]["head"]["command"]
    for _ in range(18):
        child = schema("nested").command.model_dump()
        root["subcommands"] = [child]
        root = child
    with pytest.raises(ValueError, match="tree exceeds"):
        Catalog.model_validate(value)


def test_catalog_route_is_revision_scoped_and_upload_identity_is_immutable(
    api_client: TestClient,
) -> None:
    original = catalog()
    saved = upload(api_client, clis={"echor": elf_binary(), "catalog.json": original.canonical()})
    url = f"/api/environments/{saved['id']}/revisions/{'a' * 40}/catalog"
    assert api_client.get(url).json() == original.model_dump(by_alias=True)
    upload(api_client, sha="c" * 40)
    assert api_client.get(url).json() == original.model_dump(by_alias=True)
    assert api_client.get(url.replace("a" * 40, "c" * 40)).json() is None
    assert api_client.get(url.replace("a" * 40, "d" * 40)).status_code == 404
    changed = catalog(about="Changed metadata, identical binary")
    response = api_client.post(
        "/api/environments?sha=" + "a" * 40 + "&pr=123",
        headers=AUTH,
        content=binary_bundle({"echor": elf_binary(), "catalog.json": changed.canonical()}),
    )
    assert response.status_code == 409
    assert api_client.get(url).json() == original.model_dump(by_alias=True)
    api_client.delete("/api/pull-requests/123", headers=AUTH)
    assert api_client.get(url).status_code == 404


def test_invalid_catalog_never_reaches_boxie(api_client: TestClient) -> None:
    value = catalog().model_dump(by_alias=True)
    value["head_sha"] = "c" * 40
    response = api_client.post(
        "/api/environments?sha=" + "a" * 40 + "&pr=123",
        headers=AUTH,
        content=binary_bundle({"echor": elf_binary(), "catalog.json": json.dumps(value).encode()}),
    )
    assert response.status_code == 422


def executable(path: Path, script: str) -> Path:
    path.write_text(f"#!{sys.executable}\n" + script)
    path.chmod(0o755)
    return path


def test_capture_uses_export_mode_with_isolated_cwd_and_no_ambient_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRIVATE_TOKEN", "must-not-inherit")
    payload = schema().model_dump_json(by_alias=True)
    binary = executable(
        tmp_path / "cli",
        f"import os,sys\nassert sys.argv[1:] == ['--help']\nassert os.environ['SANCTUARY_CLI_SCHEMA'] == '1'\nassert 'PRIVATE_TOKEN' not in os.environ\nassert os.getcwd() != {str(tmp_path)!r}\nprint({payload!r})\n",
    )
    assert capture_schema(binary) == schema()


@pytest.mark.parametrize(
    "script, message",
    [("import time\ntime.sleep(5)\n", "timed out"), ("print('x' * 8192)\n", "output limit")],
)
def test_capture_bounds_time_and_output(tmp_path: Path, script: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        capture_schema(executable(tmp_path / "cli", script), timeout=0.2, limit=128)


@pytest.mark.parametrize("baseline", ["supported", "legacy", "failed", "unreadable"])
def test_catalog_build_uses_merge_base_and_exact_head_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, baseline: str
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    env = clean_git_env()
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("CARGO_HOME", str(tmp_path / "cargo-home"))

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, env=env, text=True).strip()

    def write_workspace(*members: str) -> None:
        (root / "Cargo.toml").write_text(
            f'[workspace]\nresolver = "2"\nmembers = {json.dumps(members)}\n'
            'exclude = ["buildins/fresh"]\n'
        )
        subprocess.run(["cargo", "generate-lockfile", "--offline"], cwd=root, check=True)

    def write_cli(path: str, about: str) -> Path:
        package = root / path
        (package / "src").mkdir(parents=True, exist_ok=True)
        (package / "Cargo.toml").write_text(
            f'[package]\nname = "{package.name}"\nversion = "0.1.0"\n'
        )
        source = package / "src/main.rs"
        payload = schema(package.name, about).model_dump_json(by_alias=True)
        source.write_text(f'fn main() {{ println!("{{}}", r#"{payload}"#); }}\n')
        return source

    git("init", "-q")
    write_cli("tools/cli-testing", "Unchanged interface")
    moved = write_cli("tools/moved", "Ancestor interface")
    write_cli("buildins/fresh", "Excluded from the workspace")
    members = ["tools/cli-testing", "tools/moved"]
    if baseline != "legacy":
        exporter = root / "utils/cli-schema"
        (exporter / "src").mkdir(parents=True)
        (exporter / "Cargo.toml").write_text('[package]\nname = "cli-schema"\nversion = "0.1.0"\n')
        (exporter / "src/lib.rs").touch()
        members.append("utils/cli-schema")
    write_workspace(*members)
    if baseline == "failed":
        moved.write_text('compile_error!("baseline build fixture");\n')
    if baseline == "unreadable":
        (root / "Cargo.toml").write_text("[workspace\n")
    git("add", ".")
    git_commit(root)
    ancestor = git("rev-parse", "HEAD")
    # The base branch moves after the fork. It must not become the comparison.
    write_cli("tools/moved", "Base tip interface")
    write_cli("tools/fresh", "Base tip addition")
    write_workspace(*members, "tools/fresh")
    git("add", ".")
    git_commit(root)
    base = git("rev-parse", "HEAD")
    git("checkout", "--detach", ancestor)
    (root / "packages").mkdir()
    (root / "tools/moved").rename(root / "packages/moved")
    write_cli("packages/moved", "Head interface")
    write_cli("tools/fresh", "Head addition")
    members[members.index("tools/moved")] = "packages/moved"
    write_workspace(*members, "tools/fresh")
    git("add", ".")
    git_commit(root)
    head = git("rev-parse", "HEAD")
    target = tmp_path / "head-target"
    subprocess.run(
        ["cargo", "build", "--locked", "--release", "--bins", "--target-dir", str(target)],
        cwd=root,
        check=True,
    )
    binaries = target / "release"
    names = ["cli-testing", "moved", "fresh"]
    build_catalog(root, base, head, names, binaries)
    hashes = {name: hashlib.sha256((binaries / name).read_bytes()).hexdigest() for name in names}
    result = parse_catalog((binaries / "catalog.json").read_bytes(), head, hashes)
    assert result.base_sha == ancestor
    unchanged, moved_entry, fresh = result.clis
    assert moved_entry.head.command.about == "Head interface"
    assert fresh.comparison == ("unavailable" if baseline == "unreadable" else "added")
    if baseline == "supported":
        assert unchanged.comparison == moved_entry.comparison == "available"
        assert unchanged.base == unchanged.head
        assert moved_entry.base == schema("moved", "Ancestor interface")
    else:
        assert unchanged.comparison == moved_entry.comparison == "unavailable"
        assert unchanged.base is moved_entry.base is None
