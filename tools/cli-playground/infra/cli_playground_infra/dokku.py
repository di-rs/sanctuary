"""Host operations for the production gateway and individually owned feature apps."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

DOKKU = ("docker", "exec", "sanctuary-dokku", "dokku")
CONFIG = Path("/etc/sanctuary")
OWNER = Path("/opt/sanctuary/cli-playground")
GRANTS = CONFIG / "consumer-grants"
FEATURES = CONFIG / "playground-apps"
PRODUCTION_LOGGING = (
    "--log-driver=journald",
    "--log-opt=tag=cli-playground-api",
    "--log-opt=mode=non-blocking",
    "--log-opt=max-buffer-size=4m",
)


def run(*args: str, stdin: str | None = None) -> None:
    subprocess.run(args, input=stdin, text=True, check=True)


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def exists(*args: str) -> bool:
    return (
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    )


def write(path: Path, value: str, *, uid: int = 0) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(value + "\n")
            target.flush()
            os.fchown(target.fileno(), uid, uid)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def secret(path: Path, *, prefix: str = "", uid: int = 0) -> str:
    if not path.exists():
        write(path, prefix + secrets.token_hex(32), uid=uid)
    return path.read_text().strip()


def clean_images(app: str, keep: str = "") -> None:
    repository = f"localhost/sanctuary-{app}"
    tags = output(
        "docker",
        "image",
        "ls",
        "--filter",
        f"reference={repository}:*",
        "--format",
        "{{.Repository}}:{{.Tag}}",
    )
    for tag in tags.splitlines():
        if tag != keep and re.fullmatch(rf"{repository}:[0-9a-f]{{64}}", tag):
            run("docker", "image", "rm", tag)


def reserve(app: str) -> None:
    FEATURES.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = FEATURES / app
    with (FEATURES / ".capacity").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        limit = FEATURES / "limit"
        capacity = int(limit.read_text()) if limit.exists() else 3
        if not directory.exists() and len(list(FEATURES.glob("playground-pr-*"))) >= capacity:
            raise ValueError(f"All {capacity} Playground feature slots are in use")
        directory.mkdir(mode=0o700, exist_ok=True)
    current = directory / "current-image"
    clean_images(app, current.read_text().strip() if current.exists() else "")


def feature_database(app: str, directory: Path) -> str:
    network = f"{app}-data"
    if not exists("docker", "network", "inspect", network):
        run("docker", "network", "create", "--internal", network)
    assert_internal(network)
    database = f"{app}-postgres"
    password = secret(directory / "pg-password")
    if not exists("docker", "container", "inspect", database):
        # Use exactly the already installed production engine version with a new
        # instance, independent RAM-backed data, role, password and network.
        server = output(
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=boxie-postgres",
            "--filter",
            "label=com.docker.compose.service=postgres",
        )
        image = output("docker", "inspect", "--format", "{{.Image}}", server)
        admin = directory / "pg-admin"
        secret(admin)
        run(
            "docker",
            "run",
            "--detach",
            "--name",
            database,
            "--restart=unless-stopped",
            "--network",
            network,
            "--network-alias",
            "postgres",
            "--memory=320m",
            "--cpus=0.5",
            "--pids-limit=128",
            "--tmpfs",
            "/var/lib/postgresql:rw,size=160m",
            "--mount",
            f"type=bind,src={admin},dst=/run/secrets/admin,readonly",
            "--env",
            "POSTGRES_PASSWORD_FILE=/run/secrets/admin",
            "--env",
            "POSTGRES_DB=playground",
            image,
        )
    run("docker", "start", database)
    for _ in range(60):
        if exists("docker", "exec", database, "pg_isready", "-h", "127.0.0.1"):
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"PostgreSQL did not become ready for {app}")
    if not re.fullmatch("[0-9a-f]{64}", password):
        raise ValueError("invalid feature database credential")
    run(
        "docker",
        "exec",
        "-i",
        database,
        "psql",
        "-U",
        "postgres",
        "-d",
        "playground",
        "-v",
        "ON_ERROR_STOP=1",
        stdin="SELECT 'CREATE ROLE playground LOGIN' WHERE NOT EXISTS "
        "(SELECT FROM pg_roles WHERE rolname = 'playground') \\gexec\n"
        f"ALTER ROLE playground PASSWORD '{password}';\nALTER DATABASE playground OWNER TO playground;\n",
    )
    write(
        directory / "database-url",
        f"postgresql+psycopg://playground:{password}@postgres/playground",
        uid=65532,
    )
    return network


def assert_internal(network: str) -> None:
    if output("docker", "network", "inspect", "--format", "{{.Internal}}", network) != "true":
        raise ValueError(f"expected an internal network: {network}")


def feature_route(app: str, hostname: str) -> Path:
    path = OWNER / "proxy" / f"{app}.yml"
    route = {
        "http": {
            "routers": {
                app: {
                    "rule": f"Host(`{hostname}`)",
                    "entryPoints": ["websecure"],
                    "tls": {},
                    "service": app,
                }
            },
            "services": {app: {"loadBalancer": {"servers": [{"url": f"http://{app}.web:8000"}]}}},
        }
    }
    write(path, json.dumps(route))
    # The proxy can read routes. They contain hostnames only.
    path.chmod(0o644)
    return path


def deploy(app: str, domain: str, image: str, pr: int | None) -> None:
    if pr is None:
        directory = CONFIG / "cli-playground"
        database_url = directory / "database-url.secret"
        token = directory / "preview-token"
        consumer = CONFIG / "boxie" / "consumer.secret"
        database_network = os.environ["CLI_PLAYGROUND_DATABASE_NETWORK"]
        hostname = domain
        options = [
            "--volume=cli-playground-data:/var/lib/cli-playground",
            *PRODUCTION_LOGGING,
        ]
    else:
        directory = FEATURES / app
        if not directory.is_dir():
            raise ValueError(f"No reserved feature slot for {app}")
        token = directory / "deploy-token"
        secret(token, uid=65532)
        consumer = directory / "consumer"
        bearer = secret(consumer, prefix="scoped.", uid=65532)
        grant = GRANTS / hashlib.sha256(bearer.encode()).hexdigest()
        write(grant, app)
        database_network = feature_database(app, directory)
        database_url = directory / "database-url"
        hostname = f"app-pr-{pr}.{domain}"
        options = [
            "--runtime=runsc",
            "--user=65532:65532",
            "--memory=384m",
            "--cpus=0.75",
            "--pids-limit=128",
            "--tmpfs=/var/lib/cli-playground:rw,noexec,nosuid,size=96m,uid=65532",
            "--log-driver=local",
            "--log-opt=max-size=5m",
            "--log-opt=max-file=2",
        ]
    assert_internal(database_network)
    assert_internal("boxie-consumers")
    assert_internal("playground-apps")
    # No registry lookup or branch-provided Dokku configuration.
    run("docker", "image", "inspect", "--format", "{{.Id}}", image)
    if not exists(*DOKKU, "apps:exists", app):
        run(*DOKKU, "apps:create", app)
    run(*DOKKU, "proxy:disable", app)
    run(*DOKKU, "checks:disable", app, "web")
    run(*DOKKU, "network:set", app, "bind-all-interfaces", "false")
    run(*DOKKU, "network:set", app, "initial-network", database_network)
    run(*DOKKU, "network:set", app, "attach-post-create", "playground-apps", "boxie-consumers")
    run(
        *DOKKU,
        "config:set",
        "--no-restart",
        app,
        f"CLI_PLAYGROUND_PUBLIC_URL=https://{hostname}",
        f"CLI_PLAYGROUND_PREVIEW_DOMAIN={'' if pr else domain}",
        "CLI_PLAYGROUND_DATA_DIR=/var/lib/cli-playground",
        "CLI_PLAYGROUND_BOXIE_URL=http://boxie-api:8090",
        "CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE=/run/secrets/consumer",
    )
    db = f"--volume={database_url}:/run/secrets/CLI_PLAYGROUND_DATABASE_URL:ro"
    sandbox_options = [
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs=/tmp:rw,nosuid,size=48m",
    ]
    run(
        *DOKKU,
        "docker-options:add",
        app,
        "deploy,run",
        *sandbox_options,
        *options,
        db,
        f"--volume={token}:/run/secrets/CLI_PLAYGROUND_DEPLOY_TOKEN:ro",
        f"--volume={consumer}:/run/secrets/consumer:ro",
    )
    # Run schema changes in the candidate's isolation boundary, with only its database credential.
    run(
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network",
        database_network,
        db,
        *sandbox_options,
        *(
            [
                o
                for o in options
                if o.startswith(("--runtime=", "--user=", "--memory=", "--cpus=", "--pids-limit="))
            ]
        ),
        "--entrypoint",
        "/app/.venv/bin/alembic",
        image,
        "-c",
        "/app/alembic.ini",
        "upgrade",
        "head",
    )
    if pr is None:
        # Both gateways would otherwise reconcile the same database on the first Dokku release.
        legacy = output(
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=cli-playground",
            "--filter",
            "label=com.docker.compose.service=backend",
        )
        for container in legacy.splitlines():
            run("docker", "stop", container)
    run(*DOKKU, "git:from-image", app, image)
    if pr is not None:
        feature_route(app, hostname)
    run(
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "100",
        "--retry-all-errors",
        "--retry-delay",
        "3",
        "--retry-max-time",
        "300",
        "--max-time",
        "10",
        "--output",
        "/dev/null",
        f"https://{hostname}/healthz",
    )
    if pr is not None:
        write(directory / "current-image", image)
        clean_images(app, keep=image)


def remove(app: str, domain: str, pr: int) -> None:
    directory = FEATURES / app
    route = OWNER / "proxy" / f"{app}.yml"
    token = directory / "deploy-token"
    if token.exists() and route.exists():
        # Ask a functioning gateway to stop its own sessions and retire its artifact.
        # The remote service sees only its own credential. Cleanup also works after a bad build.
        subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--max-time",
                "20",
                "--output",
                "/dev/null",
                "--request",
                "DELETE",
                "--header",
                "@-",
                f"https://app-pr-{pr}.{domain}/api/pull-requests/{pr}",
            ],
            input=f"Authorization: Bearer {token.read_text().strip()}\n",
            text=True,
        )
    route.unlink(missing_ok=True)
    consumer = directory / "consumer"
    if consumer.exists():
        digest = hashlib.sha256(consumer.read_bytes().strip()).hexdigest()
        (GRANTS / digest).unlink(missing_ok=True)
    if exists(*DOKKU, "apps:exists", app):
        run(*DOKKU, "apps:destroy", app, "--force")
    if exists("docker", "container", "inspect", f"{app}-postgres"):
        run("docker", "rm", "-fv", f"{app}-postgres")
    if exists("docker", "network", "inspect", f"{app}-data"):
        run("docker", "network", "rm", f"{app}-data")
    clean_images(app)
    if directory.exists():
        shutil.rmtree(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("reserve", "deploy", "remove"))
    parser.add_argument("--pr", type=int)
    parser.add_argument("--image")
    args = parser.parse_args()
    if args.pr is not None and not 1 <= args.pr < 10**10:
        parser.error("invalid pull request")
    app = f"playground-pr-{args.pr}" if args.pr else "cli-playground"
    domain = os.environ["CLI_PLAYGROUND_DOMAIN"]
    if not re.fullmatch(r"[a-z0-9.-]+", domain):
        parser.error("invalid configured domain")
    run(*DOKKU, "version")
    with (Path("/run") / f"sanctuary-{app}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.operation == "reserve" and args.pr:
            reserve(app)
        elif args.operation == "remove" and args.pr:
            remove(app, domain, args.pr)
        elif (
            args.operation == "deploy"
            and args.image
            and re.fullmatch(rf"localhost/sanctuary-{app}:[a-f0-9]{{64}}", args.image)
        ):
            deploy(app, domain, args.image, args.pr)
        else:
            parser.error("deploy requires an image, remove requires a PR")


if __name__ == "__main__":
    main()
