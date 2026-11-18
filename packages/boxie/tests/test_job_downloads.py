"""Downloads hold their budget until a slow or disconnected client's send ends."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from boxie.api.app import ApiConfig, create_app
from boxie.application.admission import JobPolicy
from boxie.application.ports import JobAccess
from boxie.contracts.jobs import JobResultView
from starlette.types import Message, Receive, Scope, Send


def test_result_capacity_covers_slow_clients_and_frees_cancelled_requests() -> None:
    async def exercise() -> None:
        users = ("one", "two", "three")
        config = ApiConfig(
            release="test",
            consumers={user: user.encode() for user in users},
            job_policy=JobPolicy(consumer_downloads=1, total_downloads=2),
        )
        jobs = AsyncMock(spec=JobAccess)
        jobs.get_result.return_value = JobResultView(
            exit_code=0, stdout_base64="YQ==", stderr_base64="", truncated=False
        )
        app = create_app(config, AsyncMock(), AsyncMock(), AsyncMock(), jobs=jobs)
        sending = {user: asyncio.Event() for user in users}
        resume = asyncio.Event()

        async def slow_transport(scope: Scope, receive: Receive, send: Send) -> None:
            headers = dict(scope["headers"])

            async def backpressure(message: Message) -> None:
                if (
                    b"x-slow" in headers
                    and message["type"] == "http.response.body"
                    and message.get("body")
                ):
                    sending[headers[b"authorization"].decode().split()[1]].set()
                    await resume.wait()
                await send(message)

            await app(scope, receive, backpressure)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=slow_transport), base_url="http://test"
        ) as client:
            route = f"/v1/jobs/{uuid4()}/result"

            async def get(user: str, *, slow: bool = False) -> httpx.Response:
                headers = {"Authorization": f"Bearer {user}"}
                if slow:
                    headers["x-slow"] = "yes"
                return await client.get(route, headers=headers)

            async with asyncio.timeout(5):
                first = asyncio.create_task(get("one", slow=True))
                await sending["one"].wait()
                assert (await get("one")).status_code == 429
                second = asyncio.create_task(get("two", slow=True))
                await sending["two"].wait()
                assert (await get("three")).status_code == 429
                assert jobs.get_result.await_count == 2
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)
                assert (await get("one")).status_code == 200
                resume.set()
                assert (await second).status_code == 200
                assert (await get("two")).status_code == 200

    asyncio.run(exercise())
