"""Worktree scoping, port discovery, and failure recovery contracts."""

import subprocess
from pathlib import Path

import pytest
from local_dev.command import DevError, Stack, project_name, repository
from local_dev.recording import check_pr_recordings


def test_local_video_evidence_is_per_affected_cli() -> None:
    url = "https://github.com/user-attachments/assets/18d04903-90f8-4b10-83aa-99c9755a6735"
    body = f"#### `catr`\r\n\r\n{url}\r\n"
    check_pr_recordings(["catr"], body)
    check_pr_recordings([], "")
    with pytest.raises(ValueError, match="echor"):
        check_pr_recordings(["catr", "echor"], body)
    with pytest.raises(ValueError, match="catr"):
        check_pr_recordings(["catr"], body.replace("github.com", "example.org"))
    with pytest.raises(ValueError, match="different"):
        check_pr_recordings(["catr", "echor"], body + f"#### `echor`\n\n{url}\n")


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


def test_repository_from_subdirectory(tmp_path: Path) -> None:
    manifest = tmp_path / "tools/cli-playground/compose.dev.yml"
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
        ("up", "-d", "--wait", "--wait-timeout", "180"),
        ("ps", "--all"),
        ("logs", "--tail", "100"),
    ]
