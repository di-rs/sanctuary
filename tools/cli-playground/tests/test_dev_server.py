"""Real local PTY behavior for the Compose-only terminal adapter."""

import asyncio
import os
from pathlib import Path

from .dev_server import LocalTerminal


def test_terminal_executes_preserves_input_resizes_and_cleans_up(tmp_path: Path) -> None:
    async def exercise() -> None:
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        (fixtures / "sample.txt").write_text("fixture contents\n")
        terminal = LocalTerminal(tmp_path / "session", Path("/bin"), fixtures)
        terminal.start()

        async def until(expected: bytes) -> bytes:
            output = b""
            async with asyncio.timeout(10):
                while expected not in output:
                    chunk = await terminal.read()
                    assert chunk, output
                    output += chunk
            return output

        try:
            await until(b"133;B")
            await terminal.write(b"this-must-not-execute")
            await terminal.write(b"\x1b[99~printf 'replacement-ok\\n'\n")
            replaced = await until(b"replacement-ok\r\n")
            assert b"command not found" not in replaced
            if b"133;B" not in replaced.split(b"replacement-ok\r\n", 1)[1]:
                await until(b"133;B")
            await terminal.write(b"stty -echo\n")
            await until(b"dev ")
            await terminal.write(b"printf 'part")
            await terminal.resize(101, 37)
            await terminal.write(b"ial-output\\n'; cat sample.txt; stty size\n")
            output = await until(b"dev ")
            assert b"partial-output\r\nfixture contents\r\n37 101\r\n" in output
            await terminal.write(b"false; printf 'status=%s\\n' \"$?\"\n")
            assert b"status=1\r\n" in await until(b"dev ")
        finally:
            await terminal.close()
            await terminal.close()
        assert terminal.process is not None and terminal.process.poll() is not None
        try:
            os.fstat(terminal.master)
        except OSError:
            pass
        else:
            raise AssertionError("PTY descriptor survived cleanup")

    asyncio.run(exercise())


def test_published_port_preserves_host_and_origin_boundary() -> None:
    from fastapi import FastAPI, Request, WebSocket
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from .dev_server import LocalPublishedPort

    app = FastAPI()
    app.add_middleware(LocalPublishedPort)

    @app.get("/")
    def echo(request: Request) -> dict[str, str]:
        return {"host": request.headers["host"]}

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        await socket.accept()
        await socket.send_text(socket.headers["origin"])
        await socket.close()

    with TestClient(app, base_url="http://127.0.0.1:53064") as client:
        assert client.get("/").json() == {"host": "127.0.0.1:8765"}
        for host in ["evil.example:53064", "127.0.0.1:65536", "127.0.0.1:0"]:
            assert client.get("/", headers={"host": host}).status_code == 403
        assert client.get("/", headers=[("host", "127.0.0.1:53064")] * 2).status_code == 403
        for origin in ["https://evil.example", "http://127.0.0.1:8765"]:
            assert client.get("/", headers={"origin": origin}).status_code == 403
        with client.websocket_connect(
            "ws://127.0.0.1:53064/ws", headers={"origin": "http://127.0.0.1:53064"}
        ) as ws:
            assert ws.receive_text() == "http://127.0.0.1:8765"
        try:
            with client.websocket_connect(
                "ws://127.0.0.1:53064/ws", headers={"origin": "https://evil.example"}
            ):
                raise AssertionError("cross-origin socket accepted")
        except WebSocketDisconnect as error:
            assert error.code == 1008
