"""Serve a local checkout preview using portable PTYs or a real Boxie consumer."""

import asyncio
import fcntl
import hashlib
import os
import pty
import re
import secrets
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request as ClientRequest
from urllib.request import urlopen
from uuid import uuid4

import psycopg
import uvicorn
from boxie_test_support.supervisor import FakeTerminal
from boxie_test_support.terminal_network import EchoDaemon
from cli_playground.app import create_app
from cli_playground.boxie_client import HttpBoxieClient
from cli_playground.catalog import Catalog, CliCatalog
from cli_playground.catalog_build import capture_schema
from cli_playground.config import Settings
from cli_playground.database import connection
from cli_playground.service import CliPlaygroundService
from cli_playground.storage import EnvironmentStore
from cli_playground.tables import Preview
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import URL
from sqlmodel import col, select
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from .boxie_network import boxie_network
from .helpers import binary_bundle, migrate

DRAIN_PATH = "/_local/drain"


class PreviewDrain:
    """Close the previews listed in this gateway's own disposable database."""

    def __init__(self) -> None:
        self.closing = False
        self.complete = False
        self.writers = 0
        self.idle = asyncio.Event()
        self.idle.set()
        self.lock = asyncio.Lock()

    async def close(
        self, service: CliPlaygroundService, store: EnvironmentStore, *, seconds: float = 30
    ) -> str | None:
        async with self.lock:
            if self.complete:
                return None
            self.closing = True
            pending = "preview cleanup has not been acknowledged"
            try:
                async with asyncio.timeout(seconds):
                    await self.idle.wait()
                    async with service.uploads:
                        async with connection(store.sessions) as session:
                            previews = list(
                                await session.exec(
                                    select(Preview.pr).where(col(Preview.closed).is_(False))
                                )
                            )
                        for pr in previews:
                            await service.store.close_pull_request(pr)
                        while True:
                            await service.recover()
                            counts = {
                                "stop acknowledgements": len(
                                    await service.sessions.pending_stops()
                                ),
                                "artifact retirements": len(await service.sessions.retirements()),
                                "sandbox admissions": len(await service.sessions.creates()),
                                "artifact uploads": len(await service.sessions.uploads()),
                            }
                            outstanding = ", ".join(
                                f"{count} {operation}"
                                for operation, count in counts.items()
                                if count
                            )
                            if not outstanding:
                                self.complete = True
                                return None
                            pending = f"Boxie cleanup remains pending ({outstanding})"
                            await asyncio.sleep(0.5)
            except TimeoutError:
                return pending


class LocalPublishedPort:
    """Translate Docker's loopback authority only in the disposable dev runtime."""

    def __init__(self, app: ASGIApp, drain: PreviewDrain | None = None) -> None:
        self.app = app
        self.drain = drain

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
        drain = self.drain
        writer = scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if drain is None or scope["path"] == DRAIN_PATH:
            await self.app(scope, receive, send)
        elif drain.closing and scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1013})
        elif drain.closing and writer:
            await PlainTextResponse("Playground is shutting down", status_code=503)(
                scope, receive, send
            )
        elif writer:
            drain.writers += 1
            drain.idle.clear()
            try:
                await self.app(scope, receive, send)
            finally:
                drain.writers -= 1
                if not drain.writers:
                    drain.idle.set()
        else:
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


def catalog_bundle(binaries: Path, generation: str = "") -> tuple[str, bytes, int]:
    files = {path.name: path.read_bytes() for path in sorted(binaries.iterdir()) if path.is_file()}
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    revision = hashlib.sha256((generation + repr(digests)).encode()).hexdigest()[:40]
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


async def serve_preview(
    root: Path, data: Path, api_url: str, boxie: HttpBoxieClient | None
) -> None:
    revision, bundle, count = catalog_bundle(
        Path("/opt/artifact"), uuid4().hex if boxie is None else ""
    )
    token = secrets.token_hex(24)
    # The native test can read this via Compose exec. It is never in a public
    # response, a Compose environment variable, or the Docker build context.
    token_file = root / "deploy.secret"
    with os.fdopen(os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        file.write(token)
    settings = Settings(
        data_dir=data,
        public_url="http://127.0.0.1:8765",
        deploy_token=token,
        boxie_url=api_url,
        boxie_credential_file=Path("/run/boxie/consumer"),
    )
    app = create_app(settings, boxie=boxie)
    drain = PreviewDrain()
    app.add_middleware(LocalPublishedPort, drain=drain if boxie is None else None)
    service: CliPlaygroundService = app.state.service
    store: EnvironmentStore = app.state.store
    product_lifespan = app.router.lifespan_context

    async def chunks() -> AsyncIterator[bytes]:
        yield bundle

    @app.post(DRAIN_PATH)
    async def close_previews(request: Request) -> PlainTextResponse:
        if (
            boxie is not None
            or request.client is None
            or request.client.host != "127.0.0.1"
            or not secrets.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {token}"
            )
        ):
            return PlainTextResponse("Not found", status_code=404)
        pending = await drain.close(service, store)
        return PlainTextResponse(pending or "", status_code=503 if pending else 200)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with product_lifespan(app):
            await service.reopen_pull_request(1)
            preview = await service.deploy(chunks(), revision, 1)

            @app.get("/")
            async def home() -> RedirectResponse:
                return RedirectResponse(f"/p/{preview.id}")

            backend = "Boxie API" if boxie is None else "portable Bash PTYs"
            print(f"[dev] Preview ready ({count} CLIs). Terminal backend: {backend}.", flush=True)
            try:
                yield
            finally:
                if boxie is None and (pending := await drain.close(service, store, seconds=8)):
                    print(f"[dev] {pending}", flush=True)

    app.router.lifespan_context = lifespan
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8765,
            proxy_headers=False,
            ws="websockets-sansio",
            access_log=False,
            timeout_graceful_shutdown=5,
        )
    )
    loop = asyncio.get_running_loop()
    # Uvicorn restores and replays the signal after its graceful shutdown.
    # Let asyncio consume the replay so the outer database cleanup can run.
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, setattr, server, "should_exit", True)
    try:
        await server.serve()
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
    if not server.started:
        raise RuntimeError("Could not start the local playground preview")


async def serve(root: Path, workspaces: Path) -> None:
    external = os.environ.get("DEV_BOXIE_URL")
    if external:
        await serve_preview(root, Path("/var/lib/playground-sessions/product"), external, None)
    else:
        daemon = LocalDaemon(workspaces, Path("/opt/artifact"), Path("/opt/fixtures"))
        async with boxie_network(root / "supervisor", daemon=daemon) as network:
            api_url = str(network.api.base_url)
            await serve_preview(
                root, root / "product", api_url, HttpBoxieClient(api_url, "consumer-one-secret")
            )


def main() -> None:
    if not Path("/.dockerenv").is_file():
        raise SystemExit("Use docker compose -f tools/cli-playground/compose.dev.yml up --build")
    admin = os.environ["DEV_DATABASE_URL"]
    external = bool(os.environ.get("DEV_BOXIE_URL"))
    name = "playground_dev" if external else "playground_dev_" + uuid4().hex
    print("[dev] Creating a temporary playground database", flush=True)
    with psycopg.connect(admin, autocommit=True) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone():
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
        with (
            tempfile.TemporaryDirectory(prefix="playground-dev-", dir="/tmp") as directory,
            tempfile.TemporaryDirectory(dir="/var/lib/playground-sessions") as sessions,
        ):
            with suppress(KeyboardInterrupt):
                asyncio.run(serve(Path(directory), Path(sessions)))
    finally:
        if not external:
            with psycopg.connect(admin, autocommit=True) as connection:
                connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
                )


def drain_from_container() -> None:
    (token_path,) = Path("/tmp").glob("playground-dev-*/deploy.secret")
    request = ClientRequest(
        "http://127.0.0.1:8765" + DRAIN_PATH,
        headers={"Authorization": "Bearer " + token_path.read_text()},
        method="POST",
    )
    try:
        with urlopen(request, timeout=35):
            pass
    except HTTPError as error:
        raise SystemExit(error.read(4096).decode("utf-8", errors="replace")) from None


if __name__ == "__main__":
    if sys.argv[1:] == ["drain"]:
        drain_from_container()
    else:
        main()
