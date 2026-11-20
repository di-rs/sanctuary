"""The production publisher keeps its private credential across repeated setup."""

import os
import subprocess
from pathlib import Path

import pytest

INSTALL = Path(__file__).resolve().parents[1] / "infra/scripts/install.sh"


def setup(config: Path) -> subprocess.CompletedProcess[str]:
    (config / "settings.env").write_text("CLI_PLAYGROUND_DOMAIN=play.example.test\n")
    docker = config / "docker"
    docker.write_text('#!/bin/sh\nif [ "$3" = --format ]; then echo true; fi\n')
    docker.chmod(0o755)
    return subprocess.run(
        ["bash", INSTALL],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SANCTUARY_CONFIG_DIR": str(config),
            "PATH": f"{config}:{os.environ['PATH']}",
        },
    )


def test_setup_preserves_publisher_token(tmp_path: Path) -> None:
    setup(tmp_path).check_returncode()
    token = tmp_path / "cli-playground/preview-token"
    first = token.read_text()
    assert len(first.strip()) == 64 and token.stat().st_mode & 0o777 == 0o600
    setup(tmp_path).check_returncode()
    assert token.read_text() == first


@pytest.mark.parametrize("invalid", ["empty", "public", "symlink", "directory"])
def test_setup_rejects_invalid_existing_token(tmp_path: Path, invalid: str) -> None:
    token = tmp_path / "cli-playground/preview-token"
    token.parent.mkdir()
    if invalid == "directory":
        token.mkdir()
    elif invalid == "symlink":
        token.symlink_to(tmp_path / "other")
    else:
        token.write_text("" if invalid == "empty" else "secret")
        token.chmod(0o600 if invalid == "empty" else 0o644)
    result = setup(tmp_path)
    assert result.returncode != 0 and "private, nonempty" in result.stderr
    assert not (tmp_path / "other").exists()
