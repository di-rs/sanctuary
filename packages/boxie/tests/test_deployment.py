"""Boxie release ordering at the Docker command boundary."""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, call

import pytest
from boxie_infra import readiness

INFRA = Path(__file__).resolve().parents[1] / "infra"


@pytest.mark.parametrize(
    "failure",
    ["pull", "migrate", "stop_running", "unconfirmed_container", "capacity_full", "readiness", ""],
)
def test_boxie_release_pulls_before_stopping_and_keeps_dependencies_running(
    tmp_path: Path, failure: str
) -> None:
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
        "with open(os.environ['CALLS'], 'a') as output: output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if os.environ['FAILURE'] == 'pull' and 'pull' in sys.argv: sys.exit(17)\n"
        "if os.environ['FAILURE'] == 'migrate' and 'run' in sys.argv and 'migrate' in sys.argv: sys.exit(17)\n"
        "if os.environ['FAILURE'] == 'stop_running' and 'compose' in sys.argv and 'ps' in sys.argv and 'running' in sys.argv: print('still-running')\n"
        "if os.environ['FAILURE'] == 'unconfirmed_container' and sys.argv[1:3] == ['ps', '-aq']: print('stopped-sandbox')\n"
        "if os.environ['FAILURE'] == 'capacity_full' and 'run' in sys.argv and 'smoke' in sys.argv: sys.exit(17)\n"
        "if 'exec' in sys.argv:\n"
        "    assert sys.stdin.buffer.read() == Path(os.environ['EXPECTED_PROBE']).read_bytes()\n"
        "    if os.environ['FAILURE'] == 'readiness': sys.exit(17)\n"
    )
    docker.chmod(0o755)
    config = tmp_path / "config"
    (config / "boxie").mkdir(parents=True)
    (config / "boxie.env").write_text("")
    (config / "boxie/api.json").write_text('{"release":"old"}')
    (config / "boxie/supervisor.json").write_text("{}")
    for name in ("installation-id", "host-id"):
        (config / "boxie" / name).write_text("11111111-1111-1111-1111-111111111111")
    image = tmp_path / "boxie-image.env"
    image.write_text("BOXIE_IMAGE=ghcr.io/test/boxie@sha256:" + "a" * 64 + "\n")
    owner = tmp_path / "owner"
    (owner / "boxie_infra").mkdir(parents=True)
    probe = INFRA / "boxie_infra/readiness.py"
    shutil.copyfile(probe, owner / "boxie_infra/readiness.py")
    (owner / "api.json").write_text('{"release":"old"}')
    mounted = tmp_path / "mounted-api.json"
    os.link(owner / "api.json", mounted)
    log = tmp_path / "calls"
    result = subprocess.run(
        ["bash", str(INFRA / "deploy.sh"), "a" * 40],
        env={
            **os.environ,
            "PATH": str(tmp_path) + ":" + os.environ["PATH"],
            "CALLS": str(log),
            "FAILURE": failure,
            "EXPECTED_PROBE": str(probe),
            "SANCTUARY_CONFIG_DIR": str(config),
            "SANCTUARY_BOXIE_DIR": str(owner),
            "SANCTUARY_BOXIE_IMAGE_FILE": str(image),
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    expected_status = {
        "pull": 17,
        "migrate": 17,
        "stop_running": 1,
        "unconfirmed_container": 1,
        "readiness": 17,
    }.get(failure, 0)
    assert result.returncode == expected_status, result.stderr
    assert json.loads(mounted.read_text())["release"] == "old"
    pulls = [i for i, call in enumerate(calls) if "pull" in call]
    stops = [i for i, call in enumerate(calls) if "stop" in call]
    starts = [call for call in calls if "up" in call]
    assert pulls
    assert bool(stops) == (failure != "pull")
    if stops:
        assert pulls[0] < stops[0]
        assert [call[-1] for call in calls if "stop" in call] == ["api", "supervisor"]
    assert bool(starts) == (expected_status == 0 or failure == "readiness")
    if starts:
        assert [call[-1] for call in starts] == ["supervisor", "api"]
        assert all("compose.observability.yml" in " ".join(call) for call in starts)
        assert [call[-6:] for call in calls if "exec" in call] == [
            ["exec", "-T", "api", "python", "-", "release"]
        ]
    assert not any("down" in call or "postgres" in call or "temporal" in call for call in calls)
    assert not any("smoke" in call for call in calls)
    if failure == "stop_running":
        assert "Boxie services did not stop" in result.stderr
        assert not any("run" in call and "migrate" in call for call in calls)
        assert stops[-1] < next(i for i, call in enumerate(calls) if "ps" in call)
    if failure == "unconfirmed_container":
        assert "Sandbox cleanup incomplete" in result.stderr
        assert not any("run" in call and "migrate" in call for call in calls)
    if failure not in ("pull", "migrate"):
        assert json.loads((owner / "api.json").read_text())["release"] == "a" * 40


class ProbeResponse(io.BytesIO):
    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(body)
        self.status = status


@pytest.fixture
def probe_sleep(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mock:
    credential = tmp_path / "consumer"
    credential.write_text("token\n")
    monkeypatch.setattr(readiness, "CONSUMER_CREDENTIAL", credential)
    monkeypatch.setenv("BOXIE_RELEASE", "current")
    sleep = Mock()
    monkeypatch.setattr("time.sleep", sleep)
    return sleep


@pytest.mark.parametrize(
    "check_release,replies",
    [
        (
            True,
            [
                (200, b'{"release":"old","dependencies":{"postgres":true}}'),
                (200, b'{"release":"current","dependencies":{"postgres":false}}'),
                (202, b'{"release":"current","dependencies":{"postgres":true}}'),
            ],
        ),
        (
            False,
            [
                (200, b"not json"),
                (200, b"{}"),
                (202, b'{"dependencies":{"orchestration":true}}'),
                (200, b'{"dependencies":{"orchestration":1}}'),
                (200, b'{"dependencies":{"orchestration":true,"postgres":false}}'),
            ],
        ),
    ],
)
def test_deployment_probe_applies_mode_specific_readiness(
    monkeypatch: pytest.MonkeyPatch,
    probe_sleep: Mock,
    check_release: bool,
    replies: list[tuple[int, bytes]],
) -> None:
    responses = [ProbeResponse(status, body) for status, body in replies]
    request = Mock(side_effect=[OSError("unready"), *responses])
    monkeypatch.setattr(readiness, "urlopen", request)
    readiness.wait_for_readiness(check_release=check_release)
    assert request.call_count == len(replies) + 1
    assert request.call_args.kwargs["timeout"] == 3
    assert request.call_args.args[0].full_url == "http://127.0.0.1:8090/readyz"
    assert request.call_args.args[0].get_header("Authorization") == "Bearer token"
    assert probe_sleep.call_args_list == [call(2)] * len(replies)


@pytest.mark.parametrize("check_release,target", [(True, "dependencies"), (False, "orchestration")])
def test_deployment_probe_exhaustion_fails(
    monkeypatch: pytest.MonkeyPatch, probe_sleep: Mock, check_release: bool, target: str
) -> None:
    request = Mock(side_effect=OSError("unready"))
    monkeypatch.setattr(readiness, "urlopen", request)
    with pytest.raises(SystemExit, match=f"Boxie {target} did not become ready"):
        readiness.wait_for_readiness(check_release=check_release)
    assert request.call_count == 30
    assert probe_sleep.call_args_list == [call(2)] * 30


@pytest.mark.parametrize("body,error", [(b"not json", ValueError), (b"{}", KeyError)])
def test_service_release_probe_rejects_malformed_results_immediately(
    monkeypatch: pytest.MonkeyPatch, probe_sleep: Mock, body: bytes, error: type[Exception]
) -> None:
    request = Mock(return_value=ProbeResponse(200, body))
    monkeypatch.setattr(readiness, "urlopen", request)
    with pytest.raises(error):
        readiness.wait_for_readiness(check_release=True)
    request.assert_called_once()
    probe_sleep.assert_not_called()
