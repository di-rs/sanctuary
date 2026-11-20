"""Build and probe installed artifacts from disposable test directories."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_compose(
    manifest: Path, values: dict[str, str], *, exclude_prefixes: tuple[str, ...]
) -> dict[str, Any]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(exclude_prefixes)
    }
    result = subprocess.check_output(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-f",
            str(manifest),
            "config",
            "--format",
            "json",
        ],
        env={**environment, **values},
        text=True,
    )
    config: dict[str, Any] = json.loads(result)
    return config


def export_docker_context(dockerfile: Path, context: Path, output: Path) -> Path:
    recipe = context / dockerfile.name
    recipe.write_text("FROM scratch\nCOPY . /\n")
    recipe.with_suffix(".Dockerfile.dockerignore").write_bytes(
        dockerfile.with_suffix(".Dockerfile.dockerignore").read_bytes()
    )
    subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(recipe),
            "--output",
            f"type=local,dest={output}",
            str(context),
        ],
        check=True,
        timeout=60,
    )
    return output


def check_installed_wheel(tmp_path: Path, checkout: Path, package: str, probe: str) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}
    }
    wheels = tmp_path / "wheels"
    subprocess.run(
        ["uv", "build", "--package", package, "--out-dir", str(wheels)],
        cwd=checkout,
        env=env,
        check=True,
    )
    (wheel,) = wheels.glob("*.whl")
    constraints = tmp_path / "constraints.txt"
    subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--package",
            package,
            "--no-dev",
            "--no-emit-workspace",
            "--no-hashes",
            "--output-file",
            str(constraints),
            "--quiet",
        ],
        cwd=checkout,
        env=env,
        check=True,
    )
    venv = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "--no-project", "--python", sys.executable, str(venv)],
        cwd=tmp_path,
        env=env,
        check=True,
    )
    python = venv / "bin/python"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--constraint",
            str(constraints),
            str(wheel),
        ],
        cwd=tmp_path,
        env=env,
        check=True,
    )
    subprocess.run([str(python), "-I", "-c", probe], cwd=tmp_path, env=env, check=True)
