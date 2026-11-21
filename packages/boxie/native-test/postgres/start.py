"""Check the cluster on disk before Compose can replace the production database."""

import json
import re
import subprocess
import sys
from pathlib import Path


def check_cluster(image: str, volume: str, installed: bool) -> None:
    probe = """
postgres --version
if [ -f /cluster/PG_VERSION ]; then
    version=$(cat /cluster/PG_VERSION)
    test -n "$version" || { echo "Empty PostgreSQL version marker" >&2; exit 1; }
    echo "$version"
else
    entries=$(ls -A /cluster)
    test -z "$entries" || { echo "Nonempty PostgreSQL volume has no PG_VERSION" >&2; exit 1; }
fi
"""
    output = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "postgres",
            "--mount",
            f"type=volume,source={volume},target=/cluster,readonly,volume-nocopy",
            "--entrypoint",
            "sh",
            image,
            "-ec",
            probe,
        ],
        text=True,
    ).splitlines()
    version = re.fullmatch(r"postgres \(PostgreSQL\) (\d+)\..+", output[0]) if output else None
    if not version or len(output) > 2:
        raise SystemExit("Cannot determine PostgreSQL image or cluster major version")
    if len(output) == 2 and output[1] != version[1]:
        raise SystemExit(
            f"Volume {volume} contains PostgreSQL {output[1]}. The image runs PostgreSQL "
            f"{version[1]}. Complete a tested major-version migration before setup."
        )
    if installed and len(output) == 1:
        raise SystemExit(f"Existing installation has an empty PostgreSQL volume: {volume}")


def start(config: Path) -> None:
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(config / "boxie.env"),
        "-f",
        str(Path(__file__).with_name("compose.yml")),
    ]
    selector = config / "boxie/postgres-volume"
    override = ""
    if selector.exists():
        name = selector.read_text().strip()
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", name):
            raise SystemExit(f"Invalid Docker volume name in {selector}")
        override = json.dumps({"volumes": {"postgres-data": {"name": name, "external": True}}})
        compose.extend(["-f", "-"])

    def run_compose(*args: str) -> str:
        return subprocess.check_output([*compose, *args], input=override, text=True).strip()

    spec = json.loads(run_compose("config", "--format", "json"))
    service = spec["services"]["postgres"]
    if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", service["image"]):
        raise SystemExit("Production PostgreSQL requires a digest-pinned image")
    volume = spec["volumes"]["postgres-data"]["name"]
    target = service["environment"].get("PGDATA")
    mounts = [m for m in service["volumes"] if m.get("source") == "postgres-data"]
    if (
        len(mounts) != 1
        or mounts[0]["type"] != "volume"
        or mounts[0]["target"] != target
        or mounts[0].get("volume", {}).get("subpath")
    ):
        raise SystemExit("PostgreSQL PGDATA must be the root of the postgres-data volume")

    current = run_compose("ps", "--all", "--quiet", "postgres")
    if current:
        attached = json.loads(
            subprocess.check_output(["docker", "inspect", "--format", "{{json .Mounts}}", current])
        )
        if not any(m["Destination"] == target and m.get("Name") == volume for m in attached):
            raise SystemExit(
                f"PostgreSQL is attached to different storage. Refusing to switch to {volume}"
            )
    installed = bool(current) or (config / "temporal-schema-ready").exists()
    volumes = subprocess.check_output(
        ["docker", "volume", "ls", "--format", "{{.Name}}"], text=True
    )
    if volume in volumes.splitlines():
        check_cluster(service["image"], volume, installed)
    elif installed or selector.exists():
        raise SystemExit(f"Expected PostgreSQL volume is missing: {volume}")
    subprocess.run(
        [*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "150", "postgres"],
        input=override,
        text=True,
        check=True,
    )


if __name__ == "__main__":
    start(Path(sys.argv[1]))
