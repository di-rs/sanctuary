import hashlib
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from boxie.api.auth import ConsumerAuth
from boxie.domain.errors import BoxieError
from cli_playground.app import read_boxie_key

from infra.control.bucket import Bucket
from infra.control.host import Host
from infra.control.keys import key_for, revoke
from infra.control.preview import changed_cli, eligible
from infra.control.release import Release
from infra.control.runtime import Site, sql_role

SHA = "a" * 40
BLOB = "b" * 64


def test_key_rotation_revocation_and_expiry_are_live(tmp_path: Path) -> None:
    directory, key = tmp_path / "records", tmp_path / "client/key"
    backend = ConsumerAuth({}, directory)
    key_for(directory, key, "pr-9", int(time.time()) + 60)
    first = read_boxie_key(key)
    assert backend.resolve("Bearer " + first).consumer_id == "pr-9"
    assert (directory / hashlib.sha256(first.encode()).hexdigest()).is_file()
    key_for(directory, key, "pr-9", None, rotate=True)
    assert not backend.accepts("Bearer " + first)
    second = read_boxie_key(key)
    assert second != first and backend.accepts("Bearer " + second)
    key_for(directory, key, "pr-9", 1)
    with pytest.raises(BoxieError):
        backend.resolve("Bearer " + second)
    key_for(directory, tmp_path / "persistent", "playground", None)
    revoke(directory, key, "pr-9")
    assert not key.exists()
    assert backend.accepts("Bearer " + read_boxie_key(tmp_path / "persistent"))


def test_release_schema_keeps_preview_bytes_out_of_the_host_config() -> None:
    release = Release("pr-42", SHA, {"bundle": BLOB}, 42)
    assert Release.decode(release.name, release.encode()) == release
    for changes in (
        {"name": "../postgres"},
        {"expires": True},
        {"expires": 0},
        {"blobs": {"boxie": BLOB}},
        {"commit": "main"},
        {"extra": "data"},
    ):
        with pytest.raises(ValueError):
            Release.decode(
                release.name, json.dumps(json.loads(release.encode()) | changes).encode()
            )
    for data in (b"[]", b"null", b"x" * 5000):
        with pytest.raises(ValueError):
            Release.decode("pr-42", data)
    assert sql_role("pr-42") != sql_role("playground")
    with pytest.raises(ValueError):
        sql_role("postgres")


def test_complete_cli_diff_and_non_cli_paths() -> None:
    roots = {"buildins/echor", "packages/kara"}
    for path in (
        "Cargo.lock",
        "utils/cli-schema/src/lib.rs",
        "buildins/echor/README.md",
        "packages/kara/tests/options.toml",
    ):
        assert changed_cli(["notes.md"] * 350 + [path], roots)
    assert not changed_cli(["infra/services/boxie.yml", "packages/boxie/src/x.py"], roots)
    assert not changed_cli([], roots)


@pytest.mark.parametrize(
    "state,draft,repo",
    [
        ("closed", False, "org/app"),
        ("open", True, "org/app"),
        ("open", False, "fork/app"),
        ("open", False, None),
    ],
)
def test_ineligible_pull_request_never_fetches_source(
    state: str, draft: bool, repo: str | None
) -> None:
    pr = {
        "state": state,
        "draft": draft,
        "head": {"sha": SHA, "repo": {"full_name": repo}},
        "base": {"sha": SHA, "ref": "master"},
    }
    with (
        patch("infra.control.preview.subprocess.check_output", return_value=json.dumps(pr)),
        patch("infra.control.preview.subprocess.run") as fetch,
    ):
        assert eligible("org/app", 42) == (False, SHA, SHA)
        fetch.assert_not_called()


def test_preview_activates_only_with_protected_gateway(tmp_path: Path) -> None:
    site = Mock(spec=Site)
    site.state = tmp_path
    prod = Release("playground", "c" * 40, {"bundle": BLOB, "playground": "d" * 64})
    site.applied.side_effect = lambda name: prod if name == "playground" else None
    host = Host(site, Mock(spec=Bucket))
    preview = Release("pr-42", SHA, {"bundle": BLOB}, int(time.time()) + 3600)
    with patch.object(host, "web") as web, patch.object(host, "load_images") as load:
        host.apply(preview)
    web.assert_called_once_with(preview, prod.commit)
    load.assert_not_called()
    assert Release.decode("pr-42", (tmp_path / "applied/pr-42.json").read_bytes()) == preview


def test_partial_retirement_revokes_before_attempting_proxy(tmp_path: Path) -> None:
    site = Mock(spec=Site)
    site.state = tmp_path
    host = Host(site, Mock(spec=Bucket))
    key = tmp_path / "instances/pr-2/client/key"
    key_for(tmp_path / "keys", key, "pr-2", None)
    auth = ConsumerAuth({}, tmp_path / "keys")
    bearer = "Bearer " + read_boxie_key(key)
    with (
        patch.object(host, "proxy", side_effect=RuntimeError("edge unavailable")),
        pytest.raises(RuntimeError),
    ):
        host.remove("pr-2")
    assert not auth.accepts(bearer)
    site.psql.assert_not_called()


def test_blob_integrity_failure_leaves_no_local_artifact(tmp_path: Path) -> None:
    (tmp_path / "blobs").mkdir()
    site, bucket = Mock(spec=Site), Mock(spec=Bucket)
    site.state = tmp_path
    bucket.get.side_effect = lambda _, destination, __: destination.write_bytes(b"different")
    with pytest.raises(ValueError, match="digest mismatch"):
        Host(site, bucket).blob(BLOB, 1024)
    assert not list((tmp_path / "blobs").iterdir())


def test_unprotected_config_is_rejected_before_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCTUARY_STATE", str(tmp_path))
    for key in ("PLAYGROUND_HOST", "PREVIEW_ZONE", "TEMPORAL_HOST", "GRAFANA_HOST"):
        monkeypatch.setenv(key, "example.net")
    site = Site()
    with patch(
        "infra.control.runtime.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")
    ) as git:
        with pytest.raises(subprocess.CalledProcessError):
            site.config(SHA)
    assert git.call_count == 1
    assert git.call_args.args[0] == ["git", "merge-base", "--is-ancestor", SHA, "origin/master"]
