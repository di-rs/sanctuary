"""Run a disposable Boxie installation using its service-owned Compose definitions."""

import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import NAMESPACE_URL, uuid5

from .stack import DevError, Stack

INFRA = Path("packages/boxie/infra")
PASSWORDS = (
    "POSTGRES_PASSWORD",
    "BOXIE_DB_PASSWORD",
    "TEMPORAL_DB_PASSWORD",
    "VISIBILITY_DB_PASSWORD",
)


class Boxie(Stack):
    def __init__(self, root: Path) -> None:
        super().__init__(root, suffix="-boxie", files=(INFRA / "compose.dev.yml",))
        self.installation = uuid5(NAMESPACE_URL, f"sanctuary-local:{root}")
        self.state = root / ".local-dev" / "boxie"
        self.credential = self.state / "consumer.secret"
        tls = self.state / "tls"
        self.sandbox_image = f"{self.project}-sandbox:local"
        self.env.update(
            BOXIE_IMAGE=f"{self.project}:local",
            BOXIE_RELEASE="local-dev",
            BOXIE_DATA_DIR=str(self.state / "data"),
            BOXIE_API_CONFIG=str(self.state / "api.json"),
            BOXIE_SUPERVISOR_CONFIG=str(self.state / "supervisor.json"),
            BOXIE_SUPERVISOR_CREDENTIAL_FILE=str(self.state / "supervisor.secret"),
            BOXIE_CONSUMER_CREDENTIAL_FILE=str(self.credential),
            BOXIE_POSTGRES_DSN_FILE=str(self.state / "postgres-dsn.secret"),
            BOXIE_PROFILES_FILE=str(self.state / "profiles.json"),
            BOXIE_TEMPORAL_CA_FILE=str(tls / "server/frontend-ca.pem"),
            BOXIE_API_TEMPORAL_CERT_FILE=str(tls / "api/boxie-api.pem"),
            BOXIE_API_TEMPORAL_KEY_FILE=str(tls / "api/boxie-api.key"),
            BOXIE_SUPERVISOR_TEMPORAL_CERT_FILE=str(tls / "supervisor/boxie-supervisor.pem"),
            BOXIE_SUPERVISOR_TEMPORAL_KEY_FILE=str(tls / "supervisor/boxie-supervisor.key"),
            TEMPORAL_CERTS_DIR=str(tls / "server"),
            TEMPORAL_OPERATOR_CERTS_DIR=str(tls / "operator"),
            LOCAL_DEV_USER=f"{os.getuid()}:{os.getgid()}",
            BOXIE_API_ALIAS="boxie-api",
            BOXIE_CONSUMER_NETWORK=f"{self.project}_consumer",
            BOXIE_CONTROL_NETWORK=f"{self.project}_control",
            TEMPORAL_UI_CERTS_DIR=str(tls / "ui"),
        )
        self.env.update(dict.fromkeys(PASSWORDS, "local-dev-placeholder"))

    @property
    def network(self) -> str:
        return f"{self.project}_consumer"

    def docker(self, *args: str, capture: bool = False) -> str:
        result = subprocess.run(
            ["docker", *args],
            cwd=self.root,
            env=self.env,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout.strip() if capture else ""

    def local_engine(self) -> dict[str, object]:
        if sys.platform != "linux":
            raise DevError("Local Boxie requires native Linux/amd64 with Docker Engine and runsc.")
        host = self.env.get("DOCKER_HOST") if not self.env.get("DOCKER_CONTEXT") else None
        if host is None:
            host = self.docker(
                "context", "inspect", "--format", "{{.Endpoints.docker.Host}}", capture=True
            )
        if host != "unix:///var/run/docker.sock":
            raise DevError("Local Boxie requires the local /var/run/docker.sock Docker endpoint.")
        # Pin commands to the checked endpoint even if the active context changes.
        self.env.pop("DOCKER_CONTEXT", None)
        self.env["DOCKER_HOST"] = host
        info: dict[str, object] = json.loads(
            self.docker("info", "--format", "{{json .}}", capture=True)
        )
        engine = info.get("ID")
        if not isinstance(engine, str) or not engine:
            raise DevError("Could not establish the local Docker engine identity.")
        if self.state.exists():
            try:
                saved = (self.state / "docker-engine").read_text().strip()
            except OSError:
                raise DevError(
                    "Could not read the saved Docker engine identity. Local Boxie state was kept."
                ) from None
            if saved != engine:
                raise DevError(
                    "This Boxie project belongs to a different Docker engine. Local state was kept."
                )
        return info

    def require_native(self) -> str:
        info = self.local_engine()
        runtimes = info.get("Runtimes")
        options = info.get("SecurityOptions")
        if (
            info["OSType"] != "linux"
            or info["Architecture"] != "x86_64"
            or not isinstance(runtimes, dict)
            or "runsc" not in runtimes
            or not isinstance(options, list)
            or any("rootless" in option or "userns" in option for option in options)
        ):
            raise DevError(
                "Local Boxie requires rootful Linux/amd64 Docker with runsc and host UIDs."
            )
        socket = Path("/var/run/docker.sock").stat()
        if not stat.S_ISSOCK(socket.st_mode):
            raise DevError("Expected /var/run/docker.sock to be a Unix socket.")
        self.env["LOCAL_DEV_DOCKER_GID"] = str(socket.st_gid)
        return str(info["ID"])

    def build(self) -> None:
        self.run("--progress", "plain", "build", "api")
        self.docker(
            "build",
            "--tag",
            self.sandbox_image,
            "--file",
            "packages/boxie/sandbox/Dockerfile",
            ".",
        )

    def prepare(self, engine: str) -> None:
        if not self.state.exists():
            self.state.mkdir(mode=0o700)
            (self.state / "docker-engine").write_text(engine + "\n")
        if self.state.is_symlink() or self.state.stat().st_mode & 0o077:
            raise DevError(f"Expected a private local Boxie state directory at {self.state}.")
        (self.state / "data" / "profiles").mkdir(parents=True, exist_ok=True)
        for key in (*PASSWORDS, "consumer", "supervisor"):
            path = self.state / f"{key}.secret"
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as target:
                    target.write(secrets.token_hex(24))
            except FileExistsError:
                pass
            if key in PASSWORDS:
                self.env[key] = path.read_text()
        dsn = f"host=postgres dbname=boxie user=boxie password={self.env['BOXIE_DB_PASSWORD']}"
        descriptor = os.open(
            self.state / "postgres-dsn.secret", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        with os.fdopen(descriptor, "w") as target:
            target.write(dsn)
        subprocess.run(
            [
                "bash",
                str(self.root / INFRA / "certificates.sh"),
                str(self.state / "tls"),
                str(os.getuid()),
                str(os.getgid()),
            ],
            check=True,
        )
        profiles = json.loads((self.root / INFRA / "profiles/default.json").read_text())
        profiles["default"]["image_digest"] = self.docker(
            "image", "inspect", self.sandbox_image, "--format", "{{.Id}}", capture=True
        )
        (self.state / "profiles.json").write_text(json.dumps(profiles))
        subprocess.run(
            [
                sys.executable,
                str(self.root / INFRA / "boxie_infra/config.py"),
                "--output",
                str(self.state),
                "--data-dir",
                self.env["BOXIE_DATA_DIR"],
                "--installation-id",
                str(self.installation),
                "--host-id",
                self.project,
                "--consumer-id",
                "local-playground",
            ],
            check=True,
        )

    def url(self) -> str:
        return self.loopback_url("api", "8090")

    def start(
        self, *, build: bool, packages: list[str] | None = None, credential: str | None = None
    ) -> None:
        self.identify()
        engine = self.require_native()
        if build:
            self.build()
        self.prepare(engine)
        self.run("up", "-d", "--wait", "--wait-timeout", "90", "postgres")
        for store, database in (("temporal", "temporal"), ("visibility", "temporal_visibility")):
            present = self.run(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-Atc",
                "SELECT to_regclass('public.schema_version') IS NOT NULL",
                capture=True,
            ).strip()
            self.run(
                "run", "--rm", "--no-deps", "schema", "update" if present == "t" else "setup", store
            )
        self.run("run", "--rm", "--no-deps", "migrate")
        self.run("up", "-d", "--no-build", "temporal")
        for attempt in range(6):
            try:
                self.run("run", "--rm", "--no-deps", "bootstrap")
                break
            except subprocess.CalledProcessError:
                if attempt == 5:
                    raise
                time.sleep(1)
        self.run("up", "-d", "--no-build", "supervisor", "api")
        url = self.url()
        request = Request(
            url + "readyz", headers={"Authorization": "Bearer " + self.credential.read_text()}
        )
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 120
        while True:
            try:
                with opener.open(request, timeout=5):
                    break
            except URLError, TimeoutError:
                if time.monotonic() >= deadline:
                    raise DevError(
                        f"Boxie did not become ready at {url}. See local-dev logs --mode boxie."
                    ) from None
                time.sleep(1)
        print(
            f"Ready: {url} (Boxie · gVisor/runsc)\nConsumer credential: {self.credential}",
            flush=True,
        )

    def down(self, *, playground: Stack | None = None) -> None:
        self.local_engine()
        if playground is not None:
            playground.env.pop("DOCKER_CONTEXT", None)
            playground.env["DOCKER_HOST"] = self.env["DOCKER_HOST"]
            playground.run("down", "--volumes")
        self.run("down", "--volumes")
        # Compose never creates these containers. Stop the supervisor first,
        # then remove any residual children of this exact local installation.
        owned = re.compile(rf"boxie-{self.installation.hex}-[0-9a-f]{{32}}-[1-9][0-9]*")
        children = self.docker(
            "ps",
            "-a",
            "--filter",
            f"label=boxie.installation={self.installation}",
            "--filter",
            f"label=boxie.host={self.project}",
            "--filter",
            "label=boxie.consumer=local-playground",
            "--format",
            "{{.Names}}",
            capture=True,
        ).splitlines()
        for name in children:
            if owned.fullmatch(name):
                self.docker("rm", "--force", name)
        if self.state.is_dir():
            shutil.rmtree(self.state)
