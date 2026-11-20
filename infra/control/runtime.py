"""Trusted host paths, Docker Compose projects and private service credentials."""

import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from .keys import write_atomic
from .release import Release, preview_number, sha

APP_UID = 10001
DNS = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def secret(path: Path) -> str:
    if not path.exists():
        write_atomic(path, (secrets.token_hex(32) + "\n").encode())
    return path.read_text().strip()


def save_env(path: Path, values: dict[str, str]) -> None:
    if any("\n" in v or "\r" in v or "'" in v for v in values.values()):
        raise ValueError("invalid multiline or quoted deployment value")
    write_atomic(path, "".join(f"{k}='{v}'\n" for k, v in values.items()).encode())


def owned(path: Path, uid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, -1)
    path.chmod(0o750)


def sql_role(name: str) -> str:
    if name == "playground":
        return "playground"
    return "playground_pr_" + str(preview_number(name))


class Site:
    def __init__(self) -> None:
        self.repo = Path(__file__).resolve().parents[2]
        self.state = Path(os.environ.get("SANCTUARY_STATE", "/var/lib/sanctuary"))
        self.site = os.environ.get("SANCTUARY_SITE", "sanctuary")
        if not self.state.is_absolute() or not re.fullmatch(r"[a-z][a-z0-9-]{0,29}", self.site):
            raise ValueError("invalid installation path or project name")
        for setting in ("PLAYGROUND_HOST", "PREVIEW_ZONE", "TEMPORAL_HOST", "GRAFANA_HOST"):
            if not DNS.fullmatch(os.environ[setting]):
                raise ValueError(f"invalid {setting}")
        self.state.mkdir(exist_ok=True, parents=True, mode=0o700)
        self.state.chmod(0o700)

    def applied(self, name: str) -> Release | None:
        path = self.state / "applied" / (name + ".json")
        return Release.decode(name, path.read_bytes()) if path.is_file() else None

    def config(self, commit: str) -> Path:
        sha(commit, 40)
        dest = self.state / "versions" / commit
        if not dest.is_dir():
            # Only protected-branch code can supply host configuration. PR commit IDs
            # are used solely as application metadata and never enter this method.
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, "origin/master"],
                cwd=self.repo,
                check=True,
            )
            dest.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
                root = Path(tmp)
                archive = root / "config.tar"
                subprocess.run(
                    ["git", "archive", "-o", str(archive), commit, "infra/services"],
                    cwd=self.repo,
                    check=True,
                )
                subprocess.run(["tar", "-xf", str(archive), "-C", tmp], check=True)
                (root / "infra/services").rename(dest)
        return dest

    def compose(
        self,
        name: str,
        version: str,
        *args: str,
        input_data: bytes | None = None,
        stdin_file: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        component = "playground" if name.startswith("pr-") else name
        values = (
            os.environ
            | {
                "SITE": self.site,
                "STATE": str(self.state),
                "INSTANCE": str(self.state / "instances" / name),
                "WEB_ALIAS": name,
                "DOCKER_GID": str(os.stat("/var/run/docker.sock").st_gid),
                "BOXIE_IMAGE": f"sanctuary/boxie:{version}",
                "PLAYGROUND_IMAGE": f"sanctuary/playground:{version}",
                "TEMPORAL_ADDRESS": os.getenv("BOXIE_TEMPORAL_ADDRESS", "temporal:7233"),
                "TEMPORAL_NAMESPACE": os.getenv("BOXIE_TEMPORAL_NAMESPACE", "boxie"),
                "TEMPORAL_SERVER_NAME": os.getenv("BOXIE_TEMPORAL_SERVER_NAME", "temporal"),
            }
            | (env or {})
        )
        cmd = [
            "docker",
            "compose",
            "--project-name",
            f"{self.site}-{name}",
            "-f",
            str(self.config(version) / ("compose." + component + ".yml")),
            *args,
        ]
        if stdin_file is None:
            subprocess.run(cmd, env=values, input=input_data, check=True, timeout=240)
        else:
            with stdin_file.open("rb") as stream:
                subprocess.run(cmd, env=values, stdin=stream, check=True, timeout=240)

    def network_setup(self) -> None:
        names = subprocess.check_output(
            ["docker", "network", "ls", "--format", "{{.Name}}"], text=True
        ).splitlines()
        for suffix in ("database", "temporal", "clients", "telemetry", "web", "admin"):
            name = self.site + "-" + suffix
            if name not in names:
                subprocess.run(["docker", "network", "create", "--internal", name], check=True)
        for sub in ("applied", "instances", "keys", "routes", "metrics", "blobs", "secrets"):
            (self.state / sub).mkdir(exist_ok=True)
        (self.state / "keys").chmod(0o755)
        (self.state / "metrics").chmod(0o755)
        (self.state / "routes").chmod(0o755)
        disk = shutil.disk_usage(self.state)
        write_atomic(
            self.state / "metrics/disk.prom",
            f"sanctuary_data_free_ratio {disk.free / disk.total}\n".encode(),
            0o644,
        )

    def psql(self, sql: str) -> None:
        pg = self.applied("postgres")
        if pg is None:
            raise RuntimeError("Postgres has no successful deployment yet")
        self.compose(
            "postgres",
            pg.commit,
            "exec",
            "-T",
            "db",
            "psql",
            "-Xq",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "postgres",
            input_data=sql.encode(),
        )

    def database(self, role: str, name: str) -> str:
        if not all(re.fullmatch(r"[a-z][a-z0-9_]{0,62}", v) for v in (role, name)):
            raise ValueError("invalid database identity")
        password = secret(self.state / "secrets/database" / role)
        if not re.fullmatch(r"[0-9a-f]{64}", password):
            raise ValueError("invalid stored database secret")
        self.psql(rf"""SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', '{role}', '{password}')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{role}') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', '{name}', '{role}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='{name}') \gexec
REVOKE ALL ON DATABASE "{name}" FROM PUBLIC;
""")
        return password

    def configure_boxie(self, version: str) -> None:
        state = self.state
        cfg = state / "secrets/boxie"
        dsn = f"postgresql://boxie:{self.database('boxie', 'boxie')}@sanctuary-postgres/boxie"
        installation = state / "installation-id"
        if not installation.exists():
            from uuid import uuid4

            write_atomic(installation, str(uuid4()).encode())
        identity = {"installation_id": installation.read_text().strip(), "host_id": self.site}
        shared = secret(cfg / "supervisor-token")
        lifecycle = {
            "postgres_dsn_file": "/config/dsn",
            "temporal_ca_file": "/tls/ca.pem",
            "temporal_cert_file": "/tls/cert.pem",
            "temporal_key_file": "/tls/key.pem",
        }
        endpoints = {
            "BOXIE_TEMPORAL_ADDRESS": os.getenv("BOXIE_TEMPORAL_ADDRESS", "temporal:7233"),
            "BOXIE_TEMPORAL_SERVER_NAME": os.getenv("BOXIE_TEMPORAL_SERVER_NAME", "temporal"),
            "BOXIE_TEMPORAL_NAMESPACE": os.getenv("BOXIE_TEMPORAL_NAMESPACE", "boxie"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4318"
            ),
        }
        save_env(cfg / "endpoints.env", endpoints)
        for role in ("api", "worker"):
            directory = cfg / role
            owned(directory, APP_UID)
            write_atomic(directory / "dsn", dsn.encode(), uid=APP_UID)
            write_atomic(directory / "supervisor-token", shared.encode(), uid=APP_UID)
        owned(state / "boxie", APP_UID)
        api = {
            "release": version,
            "consumer_credential_files": {},
            "consumer_key_directory": "/consumer-keys",
            "supervisor_credential_file": "/config/supervisor-token",
            "supervisor_url": "http://supervisor:8091",
            "bind_host": "0.0.0.0",
            "identity": identity,
            "lifecycle": lifecycle,
            "job_policy": {
                "priority_consumers": ["playground"],
                "reserved_slots": 2,
                "per_consumer_slots": 1,
            },
        }
        worker = {
            "data_dir": str(state / "boxie"),
            "credential_file": "/config/supervisor-token",
            "profiles_file": "/config/profiles.json",
            "bind_host": "0.0.0.0",
            "identity": identity,
            "postgres_dsn_file": "/config/dsn",
            "lifecycle": lifecycle,
        }
        for role, config in (("api", api), ("worker", worker)):
            write_atomic(cfg / role / "process.json", json.dumps(config).encode(), uid=APP_UID)
        image = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", f"sanctuary/sandbox:{version}"],
            text=True,
        ).strip()
        if not image.startswith("sha256:"):
            raise ValueError("invalid sandbox image")
        sha(image[7:], 64)
        profile = {
            "default": {
                "image_digest": image,
                "commands": [["/opt/boxie/shell.sh"]],
                "env": {"TERM": ["xterm-256color"]},
            }
        }
        write_atomic(cfg / "worker/profiles.json", json.dumps(profile).encode(), uid=APP_UID)

    def configure_web(self, name: str) -> str:
        number = preview_number(name) if name != "playground" else 0
        host = (
            f"pr-{number}." + os.environ["PREVIEW_ZONE"]
            if number
            else os.environ["PLAYGROUND_HOST"]
        )
        if number and host in {
            os.environ[k] for k in ("PLAYGROUND_HOST", "GRAFANA_HOST", "TEMPORAL_HOST")
        }:
            raise ValueError("preview hostname collides with a service")
        inst = self.state / "instances" / name
        owned(inst / "client", APP_UID)
        owned(inst / "data", APP_UID)
        role = sql_role(name)
        password = self.database(role, role)
        save_env(
            inst / "web.env",
            {
                "CLI_PLAYGROUND_DATABASE_URL": f"postgresql+psycopg://{role}:{password}@sanctuary-postgres/{role}",
                "CLI_PLAYGROUND_PUBLIC_URL": f"https://{host}",
                "CLI_PLAYGROUND_DATA_DIR": "/data",
                "CLI_PLAYGROUND_DEPLOY_TOKEN": secret(inst / "deploy-token"),
                "CLI_PLAYGROUND_BOXIE_URL": os.getenv("BOXIE_URL", "http://boxie-api:8090"),
                "CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE": "/client/key",
                "CLI_PLAYGROUND_METRICS_HOST": "0.0.0.0",
                "OTEL_SERVICE_NAME": "playground" if not number else "playground-preview",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
                "OTEL_METRICS_EXPORTER": "none",
                "OTEL_EXPORTER_OTLP_ENDPOINT": os.getenv(
                    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4318"
                ),
                "OTEL_LOGS_EXPORTER": "otlp",
            },
        )
        return host
