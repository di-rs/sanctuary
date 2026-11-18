"""A new private client rejoins a job after SIGKILL at a chosen execution boundary."""

import asyncio
import base64
import json
import multiprocessing
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from multiprocessing.process import BaseProcess
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from boxie.api.app import ApiConfig, create_app
from boxie.bootstrap.config import SupervisorConfig
from boxie.persistence.database import database
from boxie.persistence.migrate import migrate
from boxie.persistence.models import JobResult, Outbox, Sandbox
from boxie.persistence.outbox import PostgresOutbox
from boxie.persistence.postgres import PostgresLifecycle
from boxie.sandbox.transport.client import SupervisorClient
from boxie.temporal.contracts import lifecycle_queue
from boxie.temporal.dispatcher import CommandDelivery
from boxie_test_support.api import CONSUMER_AUTH, FOREIGN_AUTH, artifact, serve
from boxie_test_support.dependencies import POSTGRES_IMAGE, docker
from boxie_test_support.supervisor import configuration
from database_support import counts
from sqlalchemy import func, update
from sqlmodel import col
from temporal_test_server import test_server_path as pinned_server
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from integration.job_supervisor import run_supervisor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def supervisor_process(
    config: SupervisorConfig,
    dsn: str,
    address: str,
    listener: socket.socket,
    root: Path,
    interrupt: str | None,
) -> AsyncIterator[BaseProcess]:
    process = multiprocessing.get_context("spawn").Process(
        target=run_supervisor,
        args=(
            config,
            dsn,
            address,
            listener,
            root,
            interrupt,
            os.environ.get("BOXIE_JOB_TEST_RUNTIME", "runc"),
        ),
    )
    process.start()
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": "Bearer supervisor-test-secret"}
        ) as client:
            async with asyncio.timeout(30):
                while True:
                    assert process.exitcode is None, process.exitcode
                    try:
                        response = await client.get(
                            f"http://127.0.0.1:{listener.getsockname()[1]}/readyz", timeout=0.5
                        )
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.05)
        yield process
    finally:
        if process.is_alive():
            process.kill()
        await asyncio.to_thread(process.join, 10)
        assert process.exitcode is not None
        process.close()


@asynccontextmanager
async def job_api(
    config: SupervisorConfig, dsn: str, listener: socket.socket
) -> AsyncIterator[tuple[str, WorkflowEnvironment, PostgresLifecycle]]:
    async with (
        await WorkflowEnvironment.start_time_skipping(
            test_server_existing_path=str(pinned_server()),
            data_converter=pydantic_data_converter,
        ) as env,
        database(dsn) as sessions,
        SupervisorClient(
            f"http://127.0.0.1:{listener.getsockname()[1]}", b"supervisor-test-secret"
        ) as control,
    ):
        life = PostgresLifecycle(sessions, control, config.identity, control.ready)
        delivery = CommandDelivery(
            PostgresOutbox(sessions, config.identity),
            env.client,
            lifecycle_queue(config.identity),
        )
        app = create_app(
            ApiConfig(
                release="test",
                consumers={"one": b"consumer-one-secret", "two": b"consumer-two-secret"},
            ),
            life,
            control,
            control,
            jobs=life,
            deliver=delivery.deliver_pending,
        )
        async with serve(app) as url:
            yield url, env, life


async def wait_for_cleanup(
    client: httpx.AsyncClient, route: str, life: PostgresLifecycle, expected: str
) -> None:
    try:
        async with asyncio.timeout(95):
            while (await counts(life.sessions))[1:3] != (0, 0):
                await asyncio.sleep(0.1)
    except TimeoutError:
        status = await client.get(route)
        pytest.fail(f"capacity and artifact still reserved, job status {status.text}")
    status = await client.get(route)
    assert status.status_code == 200 and status.json()["state"] == expected


async def wait_for_provision_ack(env: WorkflowEnvironment, identifier: UUID) -> None:
    handle = env.client.get_workflow_handle(f"boxie/sandbox/{identifier}")
    async with asyncio.timeout(20):
        while True:
            scheduled = None
            completed = False
            for event in (await handle.fetch_history()).events:
                activity = event.activity_task_scheduled_event_attributes
                if activity.activity_type.name == "ensure_sandbox":
                    scheduled = event.event_id
                if event.activity_task_completed_event_attributes.scheduled_event_id == scheduled:
                    completed = True
                if completed and event.HasField("timer_started_event_attributes"):
                    return
            await asyncio.sleep(0.1)


def assert_result(result: httpx.Response, state: str, exit_code: int, truncated: bool) -> None:
    if state == "outcome_unknown":
        assert result.status_code == 409
        return
    assert result.status_code == 200
    payload = result.json()
    assert payload["exit_code"] == exit_code
    assert base64.b64decode(payload["stdout_base64"]) == (
        b"out\xffEXT" if truncated else b"out\xff"
    )
    assert base64.b64decode(payload["stderr_base64"]) == (b"" if truncated else b"err")
    assert payload["truncated"] is truncated


async def assert_expired_receipt(
    life: PostgresLifecycle,
    client: httpx.AsyncClient,
    identifier: UUID,
    body: dict[str, object],
    key: dict[str, str],
) -> None:
    expired = func.clock_timestamp() - timedelta(days=8)
    route = f"/v1/jobs/{identifier}"
    async with life.sessions.begin() as session:
        await session.exec(
            update(Sandbox).where(col(Sandbox.id) == identifier).values(cleaned_at=expired)
        )
    assert (await client.get(route + "/result")).status_code == 410
    await life.purge_retained()
    async with life.sessions.begin() as session:
        assert await session.get(JobResult, identifier) is None
        assert await session.get(Sandbox, identifier) is not None
        await session.exec(
            update(Outbox).where(col(Outbox.sandbox_id) == identifier).values(delivered_at=expired)
        )
    assert await life.purge_retained() == 1
    assert (await client.post("/v1/jobs", json=body, headers=key)).json() == {
        "id": str(identifier),
        "state": "failed",
    }
    assert (await counts(life.sessions)) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("boundary", "expected", "effects"),
    [
        ("before_authorization", "succeeded", 1),
        ("before_start_journal", "outcome_unknown", 0),
        ("after_authorization", "outcome_unknown", 0),
        ("after_effect", "outcome_unknown", 1),
        ("after_result", "failed", 1),
    ],
)
def test_private_job_recovery(
    postgres_dsn: str, tmp_path: Path, boundary: str, expected: str, effects: int
) -> None:
    migrate(postgres_dsn)
    config = configuration(tmp_path)
    counter = tmp_path / "counter"
    counter.mkdir()
    counter.chmod(0o777)
    exit_code = 7 if boundary == "after_result" else 0
    output = (
        "printf 'out\\377EXTRA'"
        if boundary == "before_authorization"
        else "printf 'out\\377'; printf 'err' >&2"
    )
    command = [
        "/bin/sh",
        "-c",
        f"printf 'effect\\n' >> /evidence/effects; {output}; exit {exit_code}",
    ]
    config.profiles_file.write_text(
        json.dumps(
            {
                "batch": {
                    "image_digest": docker(
                        "image", "inspect", "--format", "{{.Id}}", POSTGRES_IMAGE
                    ),
                    "commands": [command, ["/bin/true"]],
                    "limits": {"output_bytes": 7},
                }
            }
        )
    )

    async def exercise(listener: socket.socket) -> None:
        key = {"Idempotency-Key": "one-operation"}
        async with job_api(config, postgres_dsn, listener) as (url, env, life):
            address = env.client.service_client.config.target_host
            async with (
                supervisor_process(
                    config, postgres_dsn, address, listener, tmp_path, boundary
                ) as original,
                httpx.AsyncClient(base_url=url, headers=CONSUMER_AUTH) as first,
            ):
                body: dict[str, object] = {
                    "artifact_id": await artifact(first),
                    "profile_id": "batch",
                    "command": command,
                }
                rejected = await first.post(
                    "/v1/jobs", json={**body, "command": ["/bin/false"]}, headers=key
                )
                assert rejected.status_code == 422
                submitted = await first.post("/v1/jobs", json=body, headers=key)
                assert submitted.status_code == 202, submitted.text
                identifier = UUID(submitted.json()["id"])
                route = f"/v1/jobs/{identifier}"
                deadline = (await life.load_request(identifier)).absolute_deadline
                async with asyncio.timeout(35):
                    while not (tmp_path / "barrier").exists():
                        assert original.exitcode is None
                        await asyncio.sleep(0.05)
                assert (tmp_path / "barrier").read_text() == boundary
                assert (counter / "effects").exists() == (
                    boundary in ("after_effect", "after_result")
                )
                if boundary == "after_effect":
                    # No provisioning activity remains to drive boot handover on redelivery.
                    await wait_for_provision_ack(env, identifier)
            async with (
                supervisor_process(config, postgres_dsn, address, listener, tmp_path, None),
                httpx.AsyncClient(base_url=url, headers=CONSUMER_AUTH) as fresh,
            ):
                replay = await fresh.post("/v1/jobs", json=body, headers=key)
                assert replay.status_code == 202 and replay.json()["id"] == str(identifier)
                if expected == "outcome_unknown":
                    assert replay.json()["state"] == "outcome_unknown"
                assert (
                    await fresh.post(
                        "/v1/jobs", headers=key, json={**body, "command": ["/bin/true"]}
                    )
                ).status_code == 409
                assert (await fresh.get(route, headers=FOREIGN_AUTH)).status_code == 404
                assert (await fresh.get(route + "/result", headers=FOREIGN_AUTH)).status_code == 404
                assert (await fresh.get(f"/v1/sandboxes/{identifier}")).status_code == 404
                await wait_for_cleanup(fresh, route, life, expected)
                assert_result(
                    await fresh.get(route + "/result"),
                    expected,
                    exit_code,
                    boundary == "before_authorization",
                )
                history = await env.client.get_workflow_handle(
                    f"boxie/sandbox/{identifier}"
                ).fetch_history()
                assert (await life.load_request(identifier)).absolute_deadline == deadline
                provision_deadlines = []
                for event in history.events:
                    payload = event.SerializeToString()
                    assert all(
                        value not in payload
                        for value in (b"/evidence/effects", b"out\xff", b"b3V0/w==")
                    )
                    activity = event.activity_task_scheduled_event_attributes
                    if activity.activity_type.name == "ensure_sandbox":
                        provision_deadlines.append(
                            event.event_time.ToMilliseconds() / 1000
                            + activity.schedule_to_close_timeout.ToTimedelta().total_seconds()
                        )
                # Temporal can redeliver provisioning throughout the original admission window.
                assert provision_deadlines == [pytest.approx(deadline.timestamp(), abs=2, rel=0)]
                if boundary == "after_result":
                    await assert_expired_receipt(life, fresh, identifier, body, key)
                observed = (
                    (counter / "effects").read_bytes() if (counter / "effects").exists() else b""
                )
                assert observed == b"effect\n" * effects

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        try:
            asyncio.run(exercise(listener))
        finally:
            # Only this test's randomly generated installation owns these containers.
            ids = docker(
                "ps",
                "-aq",
                "--filter",
                f"label=boxie.installation={config.identity.installation_id}",
            ).splitlines()
            if ids:
                docker("rm", "--force", *ids)
