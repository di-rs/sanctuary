"""Production and feature app operations at the Docker and Dokku command boundaries."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest
from boxie.api.auth import ConsumerAuth
from cli_playground_infra import dokku

INFRA = Path(__file__).resolve().parents[1] / "infra"


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    owner = tmp_path / "owner"
    (owner / "proxy").mkdir(parents=True)
    (tmp_path / "grants").mkdir()
    monkeypatch.setattr(dokku, "OWNER", owner)
    monkeypatch.setattr(dokku, "CONFIG", tmp_path)
    monkeypatch.setattr(dokku, "FEATURES", tmp_path / "features")
    monkeypatch.setattr(dokku, "GRANTS", tmp_path / "grants")
    monkeypatch.setattr(os, "fchown", lambda *args: None)
    monkeypatch.setenv("CLI_PLAYGROUND_DATABASE_NETWORK", "production-database")
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(dokku, "run", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(dokku, "exists", lambda *args: "pg_isready" in args)
    monkeypatch.setattr(dokku, "output", lambda *args: "true" if "{{.Internal}}" in args else "")
    return calls


def test_backend_release_targets_one_writer_and_checks_public_tls(
    host: list[tuple[str, ...]],
) -> None:
    dokku.deploy("cli-playground", "play.example.test", "image", None)
    assert (*dokku.DOKKU, "checks:disable", "cli-playground", "web") in host
    assert (*dokku.DOKKU, "git:from-image", "cli-playground", "image") in host
    assert host[-1][-1] == "https://play.example.test/healthz"
    assert "--retry-all-errors" in host[-1] and "--retry-max-time" in host[-1]
    options = next(call for call in host if "docker-options:add" in call)
    assert "--volume=cli-playground-data:/var/lib/cli-playground" in options
    assert not any("apps:destroy" in call for call in host)


def test_migration_failure_leaves_current_gateway_running(
    host: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(*args: str) -> None:
        host.append(args)
        if "upgrade" in args:
            raise subprocess.CalledProcessError(17, args)

    monkeypatch.setattr(dokku, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        dokku.deploy("cli-playground", "play.example.test", "image", None)
    assert not any("stop" in call or "git:from-image" in call for call in host)


def test_updating_and_closing_a_feature_preserves_its_neighbors(
    host: list[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", MagicMock())
    auth = ConsumerAuth({"cli-playground": b"production"}, dokku.GRANTS)
    for pr in (11, 22):
        app = f"playground-pr-{pr}"
        dokku.reserve(app)
        dokku.deploy(app, "play.example.test", app, pr)
    first = dokku.FEATURES / "playground-pr-11"
    second = dokku.FEATURES / "playground-pr-22"
    first_auth = "Bearer " + (first / "consumer").read_text().strip()
    second_auth = "Bearer " + (second / "consumer").read_text().strip()
    assert auth.resolve(first_auth).consumer_id == first.name
    assert auth.resolve(second_auth).consumer_id == second.name
    assert (first / "database-url").read_text() != (second / "database-url").read_text()
    assert (first / "deploy-token").read_text() != (second / "deploy-token").read_text()
    route = dokku.OWNER / "proxy" / f"{second.name}.yml"
    b = route.read_bytes()
    assert (
        json.loads(b)["http"]["routers"][second.name]["rule"]
        == "Host(`app-pr-22.play.example.test`)"
    )
    host.clear()
    dokku.reserve(first.name)
    dokku.deploy(first.name, "play.example.test", "new-image", 11)
    options = next(call for call in host if "docker-options:add" in call)
    assert "--runtime=runsc" in options and "--user=65532:65532" in options
    assert all(
        "docker.sock" not in value and "boxie/consumer.secret" not in value for value in options
    )
    assert (
        *dokku.DOKKU,
        "network:set",
        first.name,
        "initial-network",
        first.name + "-data",
    ) in host
    assert auth.resolve(first_auth).consumer_id == first.name
    dokku.remove(first.name, "play.example.test", 11)
    dokku.remove(first.name, "play.example.test", 11)
    assert not first.exists() and not auth.accepts(first_auth)
    assert route.read_bytes() == b and auth.resolve(second_auth).consumer_id == second.name
    assert auth.resolve("Bearer production").consumer_id == "cli-playground"
    assert all(second.name not in call and "cli-playground" not in call for call in host)


def test_scoped_grants_cannot_alias_static_principals(host: list[tuple[str, ...]]) -> None:
    token = "scoped." + "a" * 64
    path = dokku.GRANTS / hashlib.sha256(token.encode()).hexdigest()
    for principal in ("cli-playground", "../other", ""):
        path.write_text(principal)
        assert not ConsumerAuth({"cli-playground": b"production"}, dokku.GRANTS).accepts(
            "Bearer " + token
        )
    path.write_text("pr-1")
    assert not ConsumerAuth({}).accepts("Bearer " + token)


@pytest.mark.parametrize("recovers", [True, False])
def test_release_probes_authenticated_boxie(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, recovers: bool
) -> None:
    credential = tmp_path / "credential"
    credential.write_text("production-token")
    monkeypatch.setenv("CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE", str(credential))
    monkeypatch.setenv("CLI_PLAYGROUND_BOXIE_URL", "http://boxie")
    response = MagicMock()
    response.__enter__.return_value.status = 200
    request = MagicMock(side_effect=[URLError("starting"), response])
    monkeypatch.setattr("urllib.request.urlopen", request)
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr("time.monotonic", MagicMock(side_effect=[0, 1 if recovers else 301]))
    script = (INFRA / "scripts/deploy.sh").read_text().split("<<'PY'\n")[1].split("\nPY")[0]
    if recovers:
        exec(script, {})
    else:
        with pytest.raises(SystemExit, match="authenticated Boxie readiness failed"):
            exec(script, {})
    probe = request.call_args.args[0]
    assert probe.full_url == "http://boxie/readyz"
    assert probe.get_header("Authorization") == "Bearer production-token"
