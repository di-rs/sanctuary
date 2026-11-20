"""Exercise the setup and streamed release paths at the Docker and HTTP boundaries."""

import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "infra/scripts/deploy.sh"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("fail_release", [False, True])
def test_production_release(tmp_path: Path, stream: bool, fail_release: bool) -> None:
    tag = "localhost/sanctuary-cli-playground:" + "a" * 40
    (tmp_path / "settings.env").write_text("CLI_PLAYGROUND_DOMAIN=play.example.test\n")
    (tmp_path / "cli-playground-image.env").write_text(f"CLI_PLAYGROUND_IMAGE={tag}\n")
    log = tmp_path / "calls"
    for name in ("docker", "curl"):
        stub = tmp_path / name
        stub.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
            'case "$*" in *git:load-image*) cat > "$ARCHIVE";; esac\n'
            'case "$*" in *git:*) exit "$STATUS";; esac\n'
        )
        stub.chmod(0o755)
    archive = tmp_path / "image"
    result = subprocess.run(
        ["bash", DEPLOY, *([tag] if stream else [])],
        input=b"archive",
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "SANCTUARY_CONFIG_DIR": str(tmp_path),
            "CALLS": str(log),
            "ARCHIVE": str(archive),
            "STATUS": str(int(fail_release)),
        },
    )
    calls = log.read_text()
    method = "load-image" if stream else "from-image"
    assert f"dokku git:{method} cli-playground {tag}" in calls
    if stream:
        assert archive.read_bytes() == b"archive"
    assert (result.returncode != 0) == fail_release
    assert ("/readyz" in calls and "Bearer " in calls) == (not fail_release)
    assert ("https://play.example.test/healthz" in calls) == (not fail_release)
