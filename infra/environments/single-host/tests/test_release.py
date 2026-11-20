"""Run the release transport with fake SSH/SCP boundaries, without a host."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
IMAGE_ID = "sha256:" + "a" * 64
RETAINED = {
    "BOXIE_IMAGE": "ghcr.io/test/boxie@sha256:" + "b" * 64,
    "BOXIE_SANDBOX_IMAGE": "ghcr.io/test/sandbox@sha256:" + "c" * 64,
    "OBS_COLLECTOR_IMAGE": "ghcr.io/test/collector@sha256:" + "d" * 64,
}


@pytest.fixture
def release_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in subprocess.check_output(
        ["git", "rev-parse", "--local-env-vars"], text=True
    ).split():
        env.pop(name, None)
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, env=env, text=True
    ).strip()
    env.update(
        SOURCE_SHA=sha,
        IMAGE_ID=IMAGE_ID,
        DEPLOY_HOST="example.com",
        DEPLOY_SSH_KEY="private-key",
        DEPLOY_KNOWN_HOSTS="host-key",
        GITHUB_RUN_ID="123",
        GITHUB_RUN_ATTEMPT="1",
        CALLS=str(tmp_path / "calls"),
        RETAINED=json.dumps(RETAINED),
        FAIL="",
        PATH=str(tmp_path) + os.pathsep + env["PATH"],
    )
    boundary = (
        f"#!{sys.executable}\n"
        + """import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if name == "docker":
    if args[:2] == ["image", "inspect"]:
        print(os.environ["IMAGE_ID"])
    sys.exit(0)
config = pathlib.Path(args[1])
record = {"name": name, "args": args, "private": str(config.parent)}
assert "StrictHostKeyChecking yes" in config.read_text()
assert all(p.stat().st_mode & 0o077 == 0 for p in config.parent.rglob("*") if p.is_file())
if name == "scp" and args[-1].endswith("/image.env"):
    record["image_env"] = pathlib.Path(args[-2]).read_text()
with open(os.environ["CALLS"], "a") as log:
    log.write(json.dumps(record) + "\\n")
if name == "ssh" and "docker image inspect" in args[-1]:
    print("mismatch" if os.environ["FAIL"] == "image" else "sha256:" + "b" * 64)
if name == "ssh" and "sed -n" in args[-1]:
    key = args[-1].split("s/^")[1].split("=")[0]
    print(json.loads(os.environ["RETAINED"])[key])
if os.environ["FAIL"] == "copy" and name == "scp":
    sys.exit(23)
if os.environ["FAIL"] == "deploy" and name == "ssh" and "install -m 0600" in args[-1]:
    sys.exit(24)
"""
    )
    for name in ("ssh", "scp", "docker"):
        path = tmp_path / name
        path.write_text(boundary)
        path.chmod(0o755)
    return env


def run_release(component: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / "infra/environments/single-host/release.sh"), component],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "component,key,retained_keys,command",
    [
        (
            "boxie",
            "BOXIE_IMAGE",
            ("BOXIE_SANDBOX_IMAGE", "OBS_COLLECTOR_IMAGE"),
            "deploy.sh",
        ),
        (
            "boxie-sandbox",
            "BOXIE_SANDBOX_IMAGE",
            ("BOXIE_IMAGE", "OBS_COLLECTOR_IMAGE"),
            "sandbox-release.sh",
        ),
    ],
)
def test_release_preserves_other_image_and_cleans_credentials(
    release_env: dict[str, str],
    component: str,
    key: str,
    retained_keys: tuple[str, ...],
    command: str,
) -> None:
    result = run_release(component, release_env)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in Path(release_env["CALLS"]).read_text().splitlines()]
    image_env = next(call["image_env"] for call in calls if "image_env" in call)
    image = (
        "sha256:" + "b" * 64
        if component == "boxie-sandbox"
        else f"localhost/sanctuary-{component}:{IMAGE_ID[7:]}"
    )
    assert set(image_env.splitlines()) == {
        f"{key}={image}",
        *(f"{name}={RETAINED[name]}" for name in retained_keys),
    }
    deployment = next(call["args"][-1] for call in calls if "install -m 0600" in call["args"][-1])
    assert f"/opt/sanctuary/boxie/{command}" in deployment
    assert "/etc/sanctuary/boxie-image.env" in deployment
    assert "install -m 0600" in deployment
    assert (image if component == "boxie-sandbox" else release_env["SOURCE_SHA"]) in deployment
    assert calls[-1]["args"][-1].startswith("rm -rf /run/sanctuary-")
    assert not Path(calls[0]["private"]).exists()
    assert "private-key" not in result.stdout + result.stderr
    assert "private-token" not in result.stdout + result.stderr


@pytest.mark.parametrize("failure,code", [("copy", 23), ("deploy", 24), ("image", 1)])
def test_release_failure_cleans_credentials_and_preserves_exit_status(
    release_env: dict[str, str], failure: str, code: int
) -> None:
    release_env["FAIL"] = failure
    result = run_release("boxie", release_env)
    assert result.returncode == code
    calls = [json.loads(line) for line in Path(release_env["CALLS"]).read_text().splitlines()]
    assert calls[-1]["args"][-1].startswith("rm -rf /run/sanctuary-")
    assert not Path(calls[0]["private"]).exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("SOURCE_SHA", "0" * 40),
        ("DEPLOY_HOST", "host;touch /tmp/bad"),
        ("GITHUB_RUN_ID", "1;false"),
    ],
)
def test_release_rejects_invalid_inputs_before_ssh(
    release_env: dict[str, str], field: str, value: str
) -> None:
    release_env[field] = value
    assert run_release("boxie", release_env).returncode != 0
    assert not Path(release_env["CALLS"]).exists()


def test_release_rejects_unknown_component(release_env: dict[str, str]) -> None:
    assert run_release("unknown", release_env).returncode != 0
    assert not Path(release_env["CALLS"]).exists()
