"""Native verification stops when the first tool fails."""

import subprocess
from pathlib import Path

import pytest
from cli_check.command import native_checks


def test_format_failure_stops_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> None:
        assert kwargs["cwd"] == tmp_path and kwargs["check"]
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        native_checks(tmp_path, "echor", json_output=False)
    assert calls == [["cargo", "fmt", "-p", "echor", "--", "--check"]]
