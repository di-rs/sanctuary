import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from boxie_test_support.supervisor import configuration


@pytest.mark.parametrize("service", ["consumer", "supervisor"])
def test_private_app_bounds_post_bodies_after_authentication(service: str) -> None:
    import httpx
    from boxie.api.app import ApiConfig, create_app
    from boxie.sandbox.transport.server import create_supervisor_app
    from fastapi import Request

    if service == "consumer":
        app = create_app(
            ApiConfig(release="test", consumers={"one": b"secret"}),
            AsyncMock(),
            AsyncMock(),
            AsyncMock(),
        )
    else:
        app = create_supervisor_app(
            Mock(),
            AsyncMock(),
            credential=b"secret",
            readiness=AsyncMock(),
            lifespan=lambda _: nullcontext(),
        )

    @app.api_route("/body", methods=["POST", "PUT"])
    async def chunk_sizes(request: Request) -> list[int]:
        return [len(chunk) async for chunk in request.stream() if chunk]

    body_read_started = False

    async def chunks(last_chunk_size: int) -> AsyncIterator[bytes]:
        nonlocal body_read_started
        body_read_started = True
        yield b"a" * 32_768
        yield b"b" * last_chunk_size

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            denied = await client.post("/body", content=chunks(32_769))
            assert denied.status_code == 401
            assert not body_read_started

            headers = {"Authorization": "Bearer secret"}
            accepted = await client.post("/body", headers=headers, content=chunks(32_768))
            assert accepted.status_code == 200 and accepted.json() == [65_536]
            oversized = await client.post("/body", headers=headers, content=chunks(32_769))
            assert oversized.status_code == 413
            assert oversized.json() == {"detail": "request too large"}
            streamed = await client.put("/body", headers=headers, content=chunks(32_769))
            assert streamed.status_code == 200 and streamed.json() == [32_768, 32_769]

    asyncio.run(exercise())


def test_standalone_api_requires_lifecycle_configuration(tmp_path: Path) -> None:
    from boxie.bootstrap.api import load_configuration

    config = configuration(tmp_path)
    consumer = tmp_path / "consumer.secret"
    consumer.write_text("consumer-one-secret")
    consumer.chmod(0o600)
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps(
            {
                "supervisor_url": "http://127.0.0.1:8091",
                "supervisor_credential_file": str(config.credential_file),
                "consumer_credential_files": {"one": str(consumer)},
                "release": "process-release",
            }
        )
    )
    with pytest.raises(ValueError, match="lifecycle"):
        load_configuration(path)


def test_api_configuration_rejects_reused_or_public_secret_files(tmp_path: Path) -> None:
    from boxie.bootstrap.api import load_configuration

    secret = tmp_path / "secret"
    secret.write_text("supervisor-test-secret")
    secret.chmod(0o600)
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps(
            {
                "supervisor_url": "http://127.0.0.1:8091",
                "supervisor_credential_file": str(secret),
                "consumer_credential_files": {"one": str(secret)},
                "release": "test",
            }
        )
    )
    with pytest.raises(ValueError, match="distinct"):
        load_configuration(path)
    secret.chmod(0o644)
    with pytest.raises(ValueError, match="private regular"):
        load_configuration(path)


def test_api_file_errors_hide_credentials_and_copy_consumers(tmp_path: Path) -> None:
    from boxie.api.app import ApiConfig
    from boxie.bootstrap.api import load_configuration

    config = configuration(tmp_path)
    consumer = tmp_path / "consumer.secret"
    consumer.write_text("consumer-one-secret")
    consumer.chmod(0o600)
    values = {
        "supervisor_url": "http://127.0.0.1:8091",
        "supervisor_credential_file": str(config.credential_file),
        "consumer_credential_files": {"one": str(consumer)},
        "release": "process-release",
        "lifecycle": {
            "postgres_dsn_file": str(tmp_path / "db"),
            "temporal_address": "temporal:7233",
            "temporal_server_name": "temporal",
            "temporal_ca_file": str(tmp_path / "ca"),
            "temporal_cert_file": str(tmp_path / "cert"),
            "temporal_key_file": str(tmp_path / "key"),
        },
        "identity": {
            "installation_id": str(config.identity.installation_id),
            "host_id": config.identity.host_id,
        },
    }
    path = tmp_path / "api.json"
    path.write_text(json.dumps({**values, "consumer-one-secret": "consumer-one-secret"}))
    with pytest.raises(ValueError) as raised:
        load_configuration(path)
    assert "consumer-one-secret" not in str(raised.value)
    assert "consumer-one-secret" not in repr(raised.value.args)
    assert config.credential_file.read_text().strip() not in str(raised.value)
    assert config.credential_file.read_text().strip() not in repr(raised.value.args)
    assert raised.value.__context__ is None
    assert "<unknown field>: extra_forbidden" in str(raised.value)

    path.write_text(json.dumps(values))
    loaded = load_configuration(path)
    assert loaded.api.consumers["one"] == b"consumer-one-secret"
    assert not loaded.api.job_policy.profile_grants
    path.write_text(json.dumps({**values, "job_policy": {"profile_grants": {"two": ["batch"]}}}))
    with pytest.raises(ValueError, match="invalid configuration"):
        load_configuration(path)
    path.write_text(
        json.dumps(
            {
                **values,
                "job_policy": {"profile_grants": {"one": ["batch"]}, "consumer_downloads": 1},
            }
        )
    )
    loaded = load_configuration(path)
    assert loaded.api.job_policy.profile_grants == {"one": {"batch"}}
    assert loaded.api.job_policy.consumer_downloads == 1
    original = {"one": b"consumer-one-secret"}
    api = ApiConfig(release="process-release", consumers=original)
    original["one"] = b"changed"
    assert api.consumers["one"] == b"consumer-one-secret"


@pytest.mark.parametrize(
    "frame",
    [
        '{"type":"status","reason":"supervisor-test-secret"}',
        '{"type":"status","reason":"requested","secret":"supervisor-test-secret"}',
        "not json",
    ],
)
def test_supervisor_client_rejects_malformed_status_without_leaking_payload(frame: str) -> None:
    from boxie.domain.errors import BoxieError
    from boxie.domain.models import Principal
    from boxie.sandbox.transport.client import SupervisorClient
    from boxie_test_support.api import serve
    from fastapi import FastAPI, WebSocket

    async def exercise() -> None:
        # A deliberately malformed peer characterizes the network adapter, while
        # the E2E suite above always runs the real supervisor and replaces Docker only.
        peer = FastAPI()

        @peer.websocket("/v1/sandboxes/{identifier}/terminal")
        async def malformed(websocket: WebSocket, identifier: str) -> None:
            await websocket.accept()
            await websocket.send_text(frame)
            await websocket.close()

        async with serve(peer) as url:
            async with SupervisorClient(url, b"supervisor-test-secret") as client:
                with pytest.raises(BoxieError) as error:
                    async with client.attach(Principal("one"), uuid4()) as terminal:
                        await terminal.receive()
                assert error.value.status == 503 and "supervisor-test-secret" not in str(
                    error.value
                )

    asyncio.run(exercise())


def test_pooled_supervisor_client_isolates_concurrent_contexts() -> None:
    import httpx
    from boxie.observability.telemetry.context import request_context
    from boxie.sandbox.transport.client import SupervisorClient

    async def exercise() -> None:
        async def peer(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0)
            assert request.headers["authorization"] == "Bearer secret"
            assert request.headers.get("x-request-id") == request.url.params.get("expected")
            assert request.headers["x-content-sha256"] == "digest"
            return httpx.Response(204)

        async with SupervisorClient(
            "http://supervisor", b"secret", transport=httpx.MockTransport(peer)
        ) as client:

            async def call(identity: str | None) -> None:
                with request_context(identity):
                    await client._request(
                        "PUT",
                        "/artifact",
                        params={"expected": identity} if identity else {},
                        headers={"X-Content-SHA256": "digest"},
                    )

            await asyncio.gather(
                call("11111111-1111-1111-1111-111111111111"),
                call("22222222-2222-2222-2222-222222222222"),
            )
            await call(None)

    asyncio.run(exercise())
