"""Worktree scoping, port discovery, and failure recovery contracts."""

import os
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest
from local_dev.boxie import Boxie
from local_dev.command import connect, playground, run_action
from local_dev.stack import DevError, Stack, project_name, repository


def test_worktree_identity(tmp_path: Path) -> None:
    first = tmp_path / "first" / "sanctuary"
    second = tmp_path / "second" / "sanctuary"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(first, target_is_directory=True)
    assert project_name(first) != project_name(second)
    # repository resolution ensures aliases use the same canonical identity.
    assert project_name(first.resolve()) == project_name(alias.resolve())


@pytest.mark.parametrize(
    "relative", ["tools/cli-playground/compose.dev.yml", "packages/boxie/infra/compose.dev.yml"]
)
def test_repository_from_subdirectory(tmp_path: Path, relative: str) -> None:
    manifest = tmp_path / relative
    manifest.parent.mkdir(parents=True)
    manifest.touch()
    (tmp_path / "Cargo.toml").touch()
    assert repository(manifest.parent) == tmp_path.resolve()
    with pytest.raises(DevError, match="checkout"):
        repository(tmp_path / "..")


def test_compose_paths_and_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "a worktree"
    stack = Stack(root)

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "--project-name",
            project_name(root),
            "--project-directory",
            str(root / "tools/cli-playground"),
            "-f",
            str(root / "tools/cli-playground/compose.dev.yml"),
            "port",
            "playground",
            "8765",
        ]
        assert kwargs["cwd"] == root
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0, "127.0.0.1:49123\n")

    monkeypatch.setattr(subprocess, "run", run)
    assert stack.url() == "http://127.0.0.1:49123/"


@pytest.mark.parametrize("address", ["", "0.0.0.0:1234", "127.0.0.1:0", "127.0.0.1:65536"])
def test_invalid_port(address: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Stack, "run", lambda *args, **kwargs: address)
    with pytest.raises(DevError, match="port"):
        Stack(tmp_path).url()


def test_start_failure_preserves_services_and_prints_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []

    def run(self: Stack, *args: str, capture: bool = False) -> str:
        commands.append(args)
        if args[0] == "up":
            raise subprocess.CalledProcessError(1, args)
        return ""

    monkeypatch.setattr(Stack, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        Stack(tmp_path).start(build=False)
    assert commands == [
        ("up", "-d", "--no-build", "--wait", "--wait-timeout", "180"),
        ("ps", "--all"),
        ("logs", "--tail", "100"),
    ]


@pytest.mark.parametrize("mode", ["boxie", "full"])
@pytest.mark.parametrize(
    ("context", "identity", "message"),
    [
        ("ssh://different-engine", "saved", "local /var/run/docker.sock"),
        ("unix:///var/run/docker.sock", "different", "different Docker engine"),
        ("unix:///var/run/docker.sock", "", "establish the local Docker engine identity"),
    ],
)
def test_down_checks_engine_before_touching_either_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    context: str,
    identity: str,
    message: str,
) -> None:
    monkeypatch.setattr("local_dev.boxie.sys.platform", "linux")
    monkeypatch.setenv("DOCKER_CONTEXT", "switched")
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    boxie = Boxie(tmp_path)
    boxie.state.mkdir(parents=True)
    (boxie.state / "docker-engine").write_text("saved\n")
    boxie.credential.write_text("disposable-fixture-secret")

    def docker(self: Boxie, *args: str, capture: bool = False) -> str:
        if args[0] == "context":
            return context
        if args[0] == "info":
            return '{"ID": "' + identity + '"}'
        pytest.fail("teardown reached Docker")

    def compose(self: Stack, *args: str, **kwargs: object) -> str:
        pytest.fail("teardown reached either Compose project")

    monkeypatch.setattr(Boxie, "docker", docker)
    monkeypatch.setattr(Stack, "run", compose)
    stack = boxie if mode == "boxie" else playground(tmp_path, mode, boxie)
    with pytest.raises(DevError, match=message):
        run_action(Namespace(action="down", mode=mode), stack, boxie)
    assert boxie.credential.read_text() == "disposable-fixture-secret"


def test_external_credential_is_private_and_absent_from_compose_env(tmp_path: Path) -> None:
    secret = tmp_path / "consumer"
    secret.write_text("synthetic-consumer-token\n")
    stack = playground(tmp_path, "external", None)
    secret.chmod(0o644)
    with pytest.raises(DevError, match="private regular file"):
        connect(stack, secret, "https://boxie.example")
    secret.chmod(0o600)
    assert connect(stack, secret, "https://boxie.example/") == "synthetic-consumer-token"
    assert stack.env["LOCAL_DEV_BOXIE_ORIGIN"] == "https://boxie.example"
    assert "synthetic-consumer-token" not in stack.env.values()
    with pytest.raises(DevError, match="without credentials"):
        connect(stack, secret, "https://user:password@boxie.example")


@pytest.mark.parametrize("backend", ["", "boxie"])
def test_down_executes_remote_drain_only_for_boxie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    commands: list[tuple[str, ...]] = []

    def compose(self: Stack, *args: str, capture: bool = False) -> str:
        commands.append(args)
        return "stopped-container" if args[0] == "ps" else ""

    def docker(self: Stack, *args: str, capture: bool = False) -> str:
        if args[0] == "inspect":
            assert args[-1] == "stopped-container"
            return backend
        assert args == (
            "exec",
            "-i",
            "stopped-container",
            "python",
            "-m",
            "tests.dev_server",
            "drain",
        )
        if not backend:
            pytest.fail("portable container received a drain invocation")
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(Stack, "run", compose)
    monkeypatch.setattr(Stack, "docker", docker)
    stack = playground(tmp_path, "external", None)
    if backend:
        with pytest.raises(DevError, match="database and volumes were kept"):
            stack.down_playground()
        assert commands == [("ps", "--all", "-q", "playground")]
    else:
        stack.down_playground()
        assert commands == [("ps", "--all", "-q", "playground"), ("down", "--volumes")]
