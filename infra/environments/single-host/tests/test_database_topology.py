"""Shared-host PostgreSQL topology."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.integration
def test_postgres_exposes_only_database_on_playground_network() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-f",
            str(ROOT / "packages/boxie/infra/postgres/compose.yml"),
            "config",
            "--format",
            "json",
        ],
        env={
            **{key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")},
            "BOXIE_CONTROL_NETWORK": "test-control",
            "POSTGRES_PASSWORD": "test",
            "BOXIE_DB_PASSWORD": "test",
            "TEMPORAL_DB_PASSWORD": "test",
            "VISIBILITY_DB_PASSWORD": "test",
        },
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    assert config["networks"]["playground"]["internal"] is True
    assert set(config["services"]) == {"postgres"}
    assert set(config["services"]["postgres"]["networks"]) == {"control", "playground"}
