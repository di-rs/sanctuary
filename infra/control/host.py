"""Reconcile private desired releases against one enrolled Linux host."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

from .bucket import Bucket
from .keys import key_for, lease_live, revoke, write_atomic
from .release import IMAGES, MAX_BUNDLE, MAX_IMAGE, SERVICES, Release, digest, preview_number
from .runtime import APP_UID, Site, owned, save_env, secret, sql_role


class Host:
    def __init__(self, site: Site, bucket: Bucket) -> None:
        self.site, self.bucket, self.root = site, bucket, site.state

    def blob(self, identity: str, limit: int) -> Path:
        dest = self.root / "blobs" / identity
        if not dest.is_file() or digest(dest) != identity:
            with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
                stage = Path(temp) / "download"
                self.bucket.get("blobs/" + identity, stage, limit)
                if digest(stage) != identity:
                    raise ValueError("private artifact digest mismatch")
                stage.replace(dest)
        return dest

    def load_images(self, value: Release) -> None:
        for image in IMAGES.get(value.name, ()):
            path = self.blob(value.blobs[image], MAX_IMAGE)
            subprocess.run(
                ["docker", "image", "load", "--input", str(path)], check=True, timeout=300
            )
            subprocess.run(
                ["docker", "image", "inspect", f"sanctuary/{image}:{value.commit}"],
                check=True,
                stdout=subprocess.DEVNULL,
            )

    def proxy(self) -> None:
        edge = self.site.applied("edge")
        if edge:
            self.site.compose(
                "edge",
                edge.commit,
                "exec",
                "-T",
                "proxy",
                "caddy",
                "reload",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            )

    def client_key(self, name: str, expires: int | None, *, rotate: bool = False) -> None:
        path = self.root / "instances" / name / "client/key"
        key_for(self.root / "keys", path, name, expires, rotate=rotate, uid=APP_UID)

    def key_action(self, name: str, operation: str) -> None:
        if name != "playground":
            preview_number(name)
        value = self.site.applied(name)
        if not value or (value.expires and not lease_live(value.expires)):
            raise ValueError("deployment has no active lease")
        inst = self.root / "instances" / name
        if operation == "revoke":
            write_atomic(inst / "revoked", b"1")
            revoke(self.root / "keys", inst / "client/key", name)
        elif operation in ("rotate", "issue"):
            self.client_key(name, value.expires or None, rotate=operation == "rotate")
            (inst / "revoked").unlink(missing_ok=True)
        else:
            raise ValueError("unknown key operation")

    def gateway(
        self, value: Release, web_version: str, operation: str, bundle: Path | None = None
    ) -> None:
        number = 0 if value.name == "playground" else preview_number(value.name)
        self.site.compose(
            value.name,
            web_version,
            "exec",
            "-T",
            "web",
            "python",
            "/app/gateway_request.py",
            operation,
            str(number),
            value.commit,
            str(bundle.stat().st_size if bundle else 0),
            stdin_file=bundle,
        )

    def web(self, value: Release, version: str) -> None:
        name = value.name
        previous = self.site.applied(name)
        inst = self.root / "instances" / name
        if (inst / "revoked").exists():
            raise RuntimeError("deployment key has been revoked")
        version_file = inst / "version"
        same_bundle = previous and previous.commit == value.commit and previous.blobs == value.blobs
        if same_bundle and version_file.is_file() and version_file.read_text() == version:
            self.client_key(name, value.expires or None)
            try:
                self.gateway(value, version, "renew")
                return
            except subprocess.CalledProcessError:
                pass
        host = self.site.configure_web(name)
        self.client_key(name, value.expires or None)
        # Keep enough state to tear down an interrupted first deployment.
        write_atomic(inst / "version", version.encode())
        self.site.compose(name, version, "run", "--rm", "--no-deps", "migrate")
        self.site.compose(name, version, "up", "-d", "--no-deps", "web")
        for attempt in range(15):
            try:
                self.gateway(value, version, "health")
                break
            except subprocess.CalledProcessError:
                if attempt == 14:
                    raise
                time.sleep(2)
        self.gateway(value, version, "upload", self.blob(value.blobs["bundle"], MAX_BUNDLE))
        identity = "production" if name == "playground" else f"pull-request:{preview_number(name)}"
        page = hashlib.sha256(identity.encode()).hexdigest()[:32]
        write_atomic(
            self.root / "routes" / (name + ".caddy"),
            f"http://{host} {{\n    import playground {name} /p/{page}\n}}\n".encode(),
            0o644,
        )
        self.proxy()

    def apply(self, value: Release) -> None:
        name, rev = value.name, value.commit
        if name.startswith("pr-") and (self.root / "instances" / name / "retiring").exists():
            self.remove(name)
        prior = self.site.applied(name)
        stamp = self.root / "applied" / (name + ".json")
        if value.expires and not lease_live(value.expires):
            self.remove(name)
            return
        if name.startswith("pr-"):
            production = self.site.applied("playground")
            if not production:
                raise RuntimeError("publish the production gateway first")
            version = production.commit
        else:
            version = rev
        if prior == value and stamp.is_file():
            if name != "playground" and not name.startswith("pr-"):
                return
            inst = self.root / "instances" / name
            version_file = inst / "version"
            if (
                version_file.is_file()
                and version_file.read_text() == version
                and time.time() - stamp.stat().st_mtime < 6 * 3600
            ):
                return
        if name in IMAGES and (prior is None or prior.commit != rev or prior.blobs != value.blobs):
            self.load_images(value)
        if name == "postgres":
            secret(self.root / "secrets/postgres/admin")
            os.chmod(self.root / "secrets/postgres/admin", 0o444)
            self.site.compose(name, rev, "up", "-d", "--wait", "--wait-timeout", "90")
        elif name == "temporal":
            password = self.site.database("temporal", "temporal")
            self.site.database("temporal", "temporal_visibility")
            save_env(
                self.root / "secrets/temporal/database.env",
                {"POSTGRES_USER": "temporal", "POSTGRES_PWD": password},
            )
            self.site.compose(name, rev, "run", "--rm", "--no-deps", "schema")
            self.site.compose(
                name,
                rev,
                "up",
                "-d",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "120",
                "temporal",
                "ui",
            )
        elif name == "observability":
            for service, uid in (
                ("tempo", 10001),
                ("loki", 10001),
                ("grafana", 472),
                ("prometheus", 65534),
                ("alertmanager", 65534),
            ):
                owned(self.root / "observability" / service, uid)
            secret(self.root / "secrets/grafana/password")
            os.chmod(self.root / "secrets/grafana/password", 0o444)
            self.site.compose(name, rev, "up", "-d", "--wait", "--wait-timeout", "90")
        elif name == "boxie":
            self.site.configure_boxie(rev)
            for job in ("migrate", "namespace"):
                self.site.compose(name, rev, "run", "--rm", "--no-deps", job)
            self.site.compose(
                name,
                rev,
                "up",
                "-d",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "120",
                "supervisor",
                "api",
            )
            self.check_boxie(rev)
        elif name == "edge":
            self.site.compose(name, rev, "up", "-d", "--wait", "--wait-timeout", "90")
        else:
            self.web(value, version)
        write_atomic(stamp, value.encode())

    def check_boxie(self, version: str) -> None:
        # Verify orchestrator readiness with a short-lived identity from inside the API.
        keys = self.root / "keys"
        probe = self.root / "secrets/boxie/readiness-key"
        key_for(keys, probe, "host-readiness", int(time.time()) + 150, rotate=True)
        check = (
            "import sys,urllib.request;"
            "token=sys.stdin.read().strip();"
            "req=urllib.request.Request('http://127.0.0.1:8090/readyz',headers={'Authorization':'Bearer '+token});"
            "urllib.request.urlopen(req,timeout=10).close()"
        )
        try:
            for attempt in range(15):
                try:
                    self.site.compose(
                        "boxie",
                        version,
                        "exec",
                        "-T",
                        "api",
                        "python",
                        "-c",
                        check,
                        stdin_file=probe,
                    )
                    return
                except subprocess.CalledProcessError:
                    if attempt == 14:
                        raise
                    time.sleep(2)
        finally:
            revoke(keys, probe, "host-readiness")

    def remove(self, name: str) -> None:
        number = preview_number(name)
        inst = self.root / "instances" / name
        if inst.exists():
            write_atomic(inst / "retiring", b"1")
        key = inst / "client/key"
        revoke(self.root / "keys", key, name)
        (self.root / "routes" / (name + ".caddy")).unlink(missing_ok=True)
        self.proxy()
        version = inst / "version"
        if version.exists() and not (inst / "drained").exists():
            rev = version.read_text()
            # Retire owned Boxie artifacts before discarding the gateway database.
            # A temporary replacement key is reachable only inside the retired gateway.
            self.client_key(name, int(time.time()) + 180)
            try:
                self.site.compose(name, rev, "up", "-d", "--no-deps", "web")
                self.site.compose(
                    name,
                    rev,
                    "exec",
                    "-T",
                    "web",
                    "python",
                    "/app/gateway_request.py",
                    "close",
                    str(number),
                    "retired",
                )
            finally:
                revoke(self.root / "keys", key, name)
            write_atomic(inst / "drained", b"1")
        if version.exists():
            self.site.compose(name, version.read_text(), "down")
        role = sql_role(name)
        self.site.psql(
            f'DROP DATABASE IF EXISTS "{role}" WITH (FORCE);\nDROP ROLE IF EXISTS "{role}";'
        )
        (self.root / "secrets/database" / role).unlink(missing_ok=True)
        (self.root / "applied" / (name + ".json")).unlink(missing_ok=True)
        if inst.exists():
            shutil.rmtree(inst)

    def sync(self) -> None:
        self.site.network_setup()
        subprocess.run(["sh", str(self.site.repo / "infra/control/credentials.sh")], check=True)
        for component, services in (
            ("temporal", ("temporal", "ui")),
            ("boxie", ("supervisor", "api")),
        ):
            pending = self.root / "tls/restarts" / component
            installed = self.site.applied(component)
            if pending.exists() and installed:
                self.site.compose(component, installed.commit, "restart", *services)
                pending.unlink()
        names = {Path(k).stem for k in self.bucket.names("desired/") if k.endswith(".json")}
        failures: list[str] = []
        for name in [*SERVICES, *sorted(names.difference(SERVICES))]:
            if name not in names:
                continue
            try:
                if name not in SERVICES:
                    preview_number(name)
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / "manifest"
                    self.bucket.get(f"desired/{name}.json", path, 4096)
                    self.apply(Release.decode(name, path.read_bytes()))
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                failures.append(name)
                print(f"{name}: {type(error).__name__}: reconciliation will retry", file=sys.stderr)
        for inst in (self.root / "instances").glob("pr-*"):
            if inst.name not in names:
                try:
                    self.remove(inst.name)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    failures.append(inst.name)
        for key in self.bucket.names("key-requests/"):
            name = Path(key).stem
            if name != "playground":
                preview_number(name)
            if name not in names:
                continue
            with tempfile.TemporaryDirectory() as temp:
                msg = Path(temp) / "key"
                self.bucket.get(key, msg, 1024)
                request = json.loads(msg.read_bytes())
                receipt = self.root / "key-receipts" / name
                if not receipt.exists() or receipt.read_bytes() != msg.read_bytes():
                    self.key_action(name, request["action"])
                    write_atomic(receipt, msg.read_bytes())
        if not failures:
            # Releases remain in R2. Only the artifacts in use need local cache space.
            active = {
                blob
                for stamp in (self.root / "applied").glob("*.json")
                for blob in Release.decode(stamp.stem, stamp.read_bytes()).blobs.values()
            }
            for cached in (self.root / "blobs").iterdir():
                if cached.is_file() and cached.name not in active:
                    cached.unlink()
        if failures:
            raise RuntimeError("pending deployments: " + ", ".join(failures))


def locked(site: Site) -> BinaryIO:
    lock = (site.state / "control.lock").open("a+b")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock


def stop_expired(site: Site) -> None:
    # Runs even when the object store or GitHub is unavailable.
    for stamp in (site.state / "applied").glob("pr-*.json"):
        record = Release.decode(stamp.stem, stamp.read_bytes())
        if not lease_live(record.expires):
            try:
                Host(site, Bucket()).remove(record.name)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                print(f"{record.name}: retirement pending", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sync", "issue", "rotate", "revoke"))
    parser.add_argument("consumer", nargs="?")
    args = parser.parse_args()
    site = Site()
    with locked(site):
        if args.command == "sync":
            stop_expired(site)
            Host(site, Bucket()).sync()
        else:
            Host(site, Bucket()).key_action(args.consumer or "", args.command)


if __name__ == "__main__":
    main()
