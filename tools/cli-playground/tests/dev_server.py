"""Disposable Compose UI development runtime; never part of service composition.

Real CLI binaries and PTYs run inside the development container. The test network
supplies Boxie's transport, but this is not a gVisor or Temporal lifecycle test.
"""

import asyncio
import fcntl
import hashlib
import os
import pty
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import psycopg
from boxie_test_support.supervisor import FakeTerminal
from boxie_test_support.terminal_network import EchoDaemon
from cli_playground.catalog import Catalog, CliCatalog
from cli_playground.catalog_build import capture_schema
from fastapi.responses import PlainTextResponse, RedirectResponse
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import URL
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from .boxie_network import boxie_network, product_server
from .helpers import binary_bundle, migrate


class LocalPublishedPort:
    """Translate Docker's loopback authority only in the disposable dev runtime."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        hosts = headers.getlist("host")
        origins = headers.getlist("origin")
        match = re.fullmatch(r"127\.0\.0\.1:([0-9]+)", hosts[0]) if len(hosts) == 1 else None
        if (
            match is None
            or not 1 <= int(match[1]) <= 65535
            or (origins and origins != [f"http://{hosts[0]}"])
        ):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await PlainTextResponse("Invalid local host or origin", status_code=403)(
                    scope, receive, send
                )
            return
        scope = dict(scope)
        scope["headers"] = [
            (key, b"127.0.0.1:8765" if key == b"host" else b"http://127.0.0.1:8765")
            if key in {b"host", b"origin"}
            else (key, value)
            for key, value in scope["headers"]
        ]
        await self.app(scope, receive, send)


def controlling_terminal() -> None:
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


class LocalTerminal(FakeTerminal):
    """One PTY per browser session; reconnects retain its process and workspace."""

    def __init__(self, root: Path, binaries: Path, fixtures: Path) -> None:
        super().__init__()
        self.root = root
        self.binaries = binaries
        shutil.copytree(fixtures, root)
        self.master, self.slave = pty.openpty()
        os.set_blocking(self.master, False)
        self.process: subprocess.Popen[bytes] | None = None
        self.loop = asyncio.get_running_loop()

    def start(self) -> None:
        rc = self.root / ".bashrc"
        rc.write_text(
            "export PS1='\\[\\e]133;A\\a\\]dev \\w $ \\[\\e]133;B\\a\\]'\n"
            "export PS0=$'\\e]133;C\\a'\n"
            "export PS2='\\[\\e]133;C\\a\\]> '\n"
            "_sanctuary_clear_line() { READLINE_LINE=; READLINE_POINT=0; }\n"
            "bind -x '\"\\e[99~\":_sanctuary_clear_line'\n"
            "enable -n true false\n"
            "printf 'Local Compose development terminal; sessions share this container.\\n'\n"
        )
        self.process = subprocess.Popen(
            [shutil.which("bash") or "/bin/bash", "--noprofile", "--rcfile", str(rc), "-i"],
            cwd=self.root,
            env={
                "HOME": str(self.root),
                "PATH": f"{self.binaries}:/usr/local/bin:/usr/bin:/bin",
                "TERM": "xterm-256color",
                "LANG": "C.UTF-8",
                "SANCTUARY_LOG_LEVEL": "off",
            },
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            preexec_fn=controlling_terminal,
        )
        os.close(self.slave)
        self.slave = -1
        self.loop.add_reader(self.master, self.readable)

    def readable(self) -> None:
        try:
            data = os.read(self.master, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self.loop.remove_reader(self.master)
        # Bound the staging queue independently of the supervisor's replay limit.
        if self.queue.qsize() >= 256:
            asyncio.create_task(self.close())
        else:
            self.queue.put_nowait(data)

    async def write(self, data: bytes) -> None:
        while data and not self.closed:
            try:
                written = os.write(self.master, data)
            except BlockingIOError:
                await asyncio.sleep(0.01)
            else:
                data = data[written:]

    async def resize(self, columns: int, rows: int) -> None:
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.loop.remove_reader(self.master)
        os.close(self.master)
        if self.slave >= 0:
            os.close(self.slave)
        if self.process is not None:
            with suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
            await asyncio.to_thread(self.process.wait)
        self.queue.put_nowait(b"")


class LocalDaemon(EchoDaemon):
    def __init__(self, root: Path, binaries: Path, fixtures: Path) -> None:
        super().__init__()
        self.root, self.binaries, self.fixtures = root, binaries, fixtures
        self.local: dict[str, LocalTerminal] = {}

    async def attach(self, identifier: str) -> LocalTerminal:
        stream = LocalTerminal(self.root / identifier, self.binaries, self.fixtures)
        self.local[identifier] = stream
        self.streams[identifier] = stream
        return stream

    async def start(self, identifier: str) -> None:
        self.started.append(identifier)
        self.local[identifier].start()

    async def delete(self, identifier: str) -> None:
        stream = self.local.pop(identifier, None)
        if stream is not None:
            await stream.close()
            shutil.rmtree(stream.root)
        await super().delete(identifier)

    async def close(self) -> None:
        for stream in self.local.values():
            await stream.close()


def catalog_bundle(binaries: Path) -> tuple[str, bytes, int]:
    files = {path.name: path.read_bytes() for path in sorted(binaries.iterdir()) if path.is_file()}
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    revision = hashlib.sha256(repr(digests).encode()).hexdigest()[:40]
    print(f"[dev] Exporting command catalogs from {len(files)} CLI binaries", flush=True)
    catalog = Catalog(
        schema_version=1,
        head_sha=revision,
        base_sha=revision,
        clis=[
            CliCatalog(
                name=name,
                binary_sha256=digest,
                head=capture_schema(binaries / name),
                base=None,
                comparison="unavailable",
            )
            for name, digest in digests.items()
        ],
    )
    return revision, binary_bundle(files | {"catalog.json": catalog.canonical()}), len(files)


async def serve(root: Path) -> None:
    binaries = Path("/opt/artifact")
    revision, bundle, count = catalog_bundle(binaries)
    daemon = LocalDaemon(root / "workspaces", binaries, Path("/opt/fixtures"))
    print("[dev] Starting development Boxie transport and playground API", flush=True)
    async with boxie_network(root / "supervisor", daemon=daemon) as network:
        async with product_server(
            root / "product",
            str(network.api.base_url),
            port=8765,
            bind_host="0.0.0.0",
            clock=time.time,
            configure_app=lambda app: app.add_middleware(LocalPublishedPort),
        ) as product:
            print("[dev] Publishing the local binary bundle and catalog as PR 1", flush=True)
            result = await product.http.post(
                "/api/environments",
                params={"sha": revision, "pr": 1},
                headers={"Authorization": "Bearer test-deployment-token"},
                content=bundle,
                timeout=60,
            )
            result.raise_for_status()
            identifier = result.json()["id"]

            @product.app.get("/")
            async def home() -> RedirectResponse:
                return RedirectResponse(f"/p/{identifier}")

            print(
                f"\nPlayground ready on container port 8765; use local-dev url for the host URL ({count} CLIs)\n",
                flush=True,
            )
            stopped = asyncio.Event()
            loop = asyncio.get_running_loop()
            for event in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(event, stopped.set)
            await stopped.wait()


def main() -> None:
    if not Path("/.dockerenv").is_file():
        raise SystemExit("Use docker compose -f tools/cli-playground/compose.dev.yml up --build")
    admin = os.environ["DEV_DATABASE_URL"]
    name = "playground_dev_" + uuid4().hex
    print("[dev] Creating a temporary playground database", flush=True)
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        connection_values = {
            key: str(value)
            for key, value in conninfo_to_dict(make_conninfo(admin, dbname=name)).items()
            if value is not None
        }
        url = URL.create(
            "postgresql+psycopg",
            username=connection_values["user"],
            password=connection_values["password"],
            host=connection_values["host"],
            port=int(connection_values.get("port", "5432")),
            database=name,
        ).render_as_string(hide_password=False)
        os.environ["CLI_PLAYGROUND_DATABASE_URL"] = url
        print("[dev] Applying playground database migrations", flush=True)
        migrate(url)
        with tempfile.TemporaryDirectory(prefix="playground-dev-") as directory:
            with suppress(KeyboardInterrupt):
                asyncio.run(serve(Path(directory)))
    finally:
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


if __name__ == "__main__":
    main()
