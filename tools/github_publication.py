"""GitHub requests shared by the trusted CI publishers."""

import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import cast

import anyio
import httpx
from githubkit import BaseAuthStrategy, GitHub, TokenAuthStrategy
from githubkit.exception import GitHubException

MAX_JSON = 2 * 1024 * 1024
MAX_PAGES = 20


class PaginationLimit(ValueError):
    """A complete listing cannot be established within the repository's limit."""


def table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return cast(dict[str, object], value)


def array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected JSON array")
    return cast(list[object], value)


def github_client() -> GitHub[TokenAuthStrategy]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Set GH_TOKEN or GITHUB_TOKEN for GitHub publication")
    return GitHub(token, auto_retry=False, http_cache=False, timeout=60)


def github_request[A: BaseAuthStrategy](
    api: GitHub[A],
    path: str,
    *,
    method: str = "GET",
    body: object = None,
    limit: int = MAX_JSON,
    timeout: float = 60,
) -> bytes:
    # SDK error and redirect handling also reads bodies. Bound the underlying
    # stream before that handling, as well as the decoded successful response.
    async def bound_response(response: httpx.Response) -> None:
        # GitHubKit buffers error bodies before returning them. Request identity
        # encoding and reject compressed responses before its decoder can inflate
        # an otherwise small wire body beyond the repository's byte budget.
        if response.headers.get("content-encoding", "identity").strip().lower() not in {
            "",
            "identity",
        }:
            raise ValueError("GitHub response uses unexpected HTTP compression")
        upstream = response.stream
        if not isinstance(upstream, httpx.AsyncByteStream):
            raise ValueError("expected an asynchronous GitHub response")
        stream: httpx.AsyncByteStream = upstream

        class LimitedBody(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                size = 0
                try:
                    async for chunk in stream:
                        size += len(chunk)
                        if size > limit:
                            raise ValueError("GitHub response exceeds size limit")
                        yield chunk
                finally:
                    with anyio.CancelScope(shield=True):
                        await stream.aclose()

            async def aclose(self) -> None:
                with anyio.CancelScope(shield=True):
                    await stream.aclose()

        response.stream = LimitedBody()

    async def fetch() -> bytes:
        config = replace(
            api.config,
            http_cache=False,
            auto_retry=None,
            timeout=httpx.Timeout(timeout),
            async_event_hooks={"response": [bound_response]},
        )
        async with GitHub(api.auth, config=config) as client:
            with anyio.fail_after(timeout):
                response = await client.arequest(
                    method, path, json=body, stream=True, headers={"Accept-Encoding": "identity"}
                )
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > limit:
                        raise ValueError("GitHub response exceeds size limit")
                    data.extend(chunk)
                return bytes(data)

    try:
        return anyio.run(fetch)
    except (GitHubException, httpx.HTTPError, TimeoutError) as error:
        # SDK error strings can contain response bodies or signed artifact URLs.
        raise ValueError(
            "GitHub request failed or exceeded its response limit or deadline"
        ) from error


def github_json[A: BaseAuthStrategy](
    api: GitHub[A],
    path: str,
    *,
    method: str = "GET",
    body: object = None,
) -> object:
    return cast(object, json.loads(github_request(api, path, method=method, body=body)))


def github_pages[A: BaseAuthStrategy](
    api: GitHub[A],
    path: str,
    key: str | None = None,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, MAX_PAGES + 1):
        response = github_json(api, f"{path}{separator}per_page=100&page={page}")
        values = array(table(response)[key] if key else response)
        result.extend(table(value) for value in values)
        if len(values) < 100:
            return result
    raise PaginationLimit("GitHub pagination limit exceeded")
