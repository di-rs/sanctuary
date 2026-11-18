"""Bound result materialization and transmission in the private API process."""

from collections import Counter

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from boxie.application.admission import JobPolicy
from boxie.domain.errors import BoxieError


class JobDownloads:
    def __init__(self, policy: JobPolicy) -> None:
        self.policy = policy
        self.active: Counter[str] = Counter()

    def acquire(self, request: Request, consumer: str) -> None:
        if (
            self.active[consumer] >= self.policy.consumer_downloads
            or self.active.total() >= self.policy.total_downloads
        ):
            raise BoxieError(429, "job result download capacity reached")
        self.active[consumer] += 1
        request.state.job_download_owner = consumer

    def middleware(self, app: ASGIApp) -> ASGIApp:
        async def serve(scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await app(scope, receive, send)
            finally:
                # Hold the slot through the outer response send, including cancellation.
                if owner := scope.get("state", {}).pop("job_download_owner", None):
                    self.active[owner] -= 1
                    if not self.active[owner]:
                        del self.active[owner]

        return serve
