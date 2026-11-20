"""Boxie sandbox updates at the command boundary."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1] / "infra"


@pytest.mark.parametrize("readiness_status", [0, 17])
def test_sandbox_update_preserves_boxie_image_and_custom_profile(
    tmp_path: Path, readiness_status: int
) -> None:
    config = tmp_path / "config"
    boxie = config / "boxie"
    boxie.mkdir(parents=True)
    profile = {
        "default": {
            "image_digest": "old",
            "commands": [["custom"]],
            "env": {"TERM": ["custom"]},
        }
    }
    (boxie / "profiles.json").write_text(json.dumps(profile))
    (config / "boxie.env").write_text("")
    boxie_image = "ghcr.io/test/boxie@sha256:" + "b" * 64
    (config / "boxie-image.env").write_text("BOXIE_IMAGE=" + boxie_image + "\n")
    owner = tmp_path / "owner"
    (owner / "profiles").mkdir(parents=True)
    (owner / "boxie_infra").mkdir()
    for name in ("installation.py", "readiness.py"):
        shutil.copyfile(INFRA / "boxie_infra" / name, owner / "boxie_infra" / name)
    (owner / "profiles/default.json").write_text(json.dumps(profile))
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
        "with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if 'exec' in sys.argv:\n"
        "    assert sys.stdin.buffer.read() == Path(os.environ['EXPECTED_PROBE']).read_bytes()\n"
        "    sys.exit(int(os.environ['READINESS_STATUS']))\n"
    )
    docker.chmod(0o755)
    log = tmp_path / "calls"
    digest = "ghcr.io/test/sandbox@sha256:" + "c" * 64
    result = subprocess.run(
        ["bash", str(INFRA / "sandbox-release.sh"), digest],
        env={
            **os.environ,
            "PATH": str(tmp_path) + ":" + os.environ["PATH"],
            "CALLS": str(log),
            "EXPECTED_PROBE": str(INFRA / "boxie_infra/readiness.py"),
            "READINESS_STATUS": str(readiness_status),
            "SANCTUARY_CONFIG_DIR": str(config),
            "SANCTUARY_BOXIE_DIR": str(owner),
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    assert result.returncode == readiness_status, result.stderr
    profile["default"]["image_digest"] = digest
    assert json.loads((boxie / "profiles.json").read_text()) == profile
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert any("pull" in call and digest in call for call in calls)
    stops = [index for index, call in enumerate(calls) if "stop" in call]
    updates = [call for call in calls if "up" in call]
    assert len(stops) == 1
    assert calls[stops[0]][-3:] == ["--timeout", "60", "supervisor"]
    assert stops[0] < next(index for index, call in enumerate(calls) if "up" in call)
    assert len(updates) == 1
    assert updates[0][-1] == "supervisor"
    assert "--force-recreate" in updates[0]
    assert not any("backend" in call for call in calls)
    assert [call[-6:] for call in calls if "exec" in call] == [
        ["exec", "-T", "api", "python", "-", "sandbox"]
    ]
    assert not any("api" in call for call in calls if "stop" in call or "up" in call)
    assert (config / "boxie-image.env").read_text() == "BOXIE_IMAGE=" + boxie_image + "\n"
