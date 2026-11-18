"""Authenticated SQL-admitted execution transport. No consumer admission routes."""

import hmac
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, Query, Request, Response, WebSocket
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import Lifespan

from boxie.application.ports import ArtifactAccess
from boxie.contracts.common import ConsumerId
from boxie.contracts.consumer import PolicyWire
from boxie.contracts.execution import (
    AdmissionProfileRequest,
    JobProfileApproval,
    ProfileMetadata,
    SnapshotWire,
)
from boxie.contracts.jobs import JobProfileRequest
from boxie.domain.errors import BoxieError
from boxie.domain.models import Principal
from boxie.domain.policy import validate_policy
from boxie.http import boxie_error_response, buffer_post_body, create_private_app
from boxie.observability.logging import RequestLogging
from boxie.sandbox.execution.supervisor import Supervisor
from boxie.sandbox.terminal.session import serve_terminal


def create_supervisor_app(
    supervisor: Supervisor,
    artifacts: ArtifactAccess,
    *,
    credential: bytes,
    readiness: Callable[[], Awaitable[dict[str, bool]]],
    lifespan: Lifespan[FastAPI],
    request_completed: Callable[[str, str, str, float], None] | None = None,
) -> FastAPI:
    app = create_private_app(lifespan=lifespan)
    app.state.supervisor = supervisor

    def authorized(value: str) -> bool:
        return hmac.compare_digest(value.encode(), b"Bearer " + credential)

    @app.middleware("http")
    async def authenticate(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not authorized(request.headers.get("Authorization", "")):
            return JSONResponse({"detail": "invalid supervisor credential"}, status_code=401)
        rejection = await buffer_post_body(request)
        if rejection is not None:
            return rejection
        return await call_next(request)

    @app.get("/v1/identity")
    async def identity() -> dict[str, object]:
        return {"identity": asdict(supervisor.config.identity), "boot_id": supervisor.boot_id}

    @app.get("/readyz")
    async def ready() -> JSONResponse:
        dependencies = await readiness()
        return JSONResponse(
            {
                "identity": {
                    "installation_id": str(supervisor.config.identity.installation_id),
                    "host_id": supervisor.config.identity.host_id,
                },
                "dependencies": dependencies,
            },
            status_code=200 if all(dependencies.values()) else 503,
        )

    @app.post("/v1/profiles/resolve")
    async def profile(body: AdmissionProfileRequest) -> SnapshotWire:
        validate_policy(body.policy.domain(), supervisor.config.policy_maximum)
        return SnapshotWire.from_domain(
            supervisor.profiles.resolve_profile(body.profile_id, body.command, body.env)
        )

    @app.post("/v1/profiles/resolve-job")
    async def job_profile(body: JobProfileRequest) -> JobProfileApproval:
        snapshot = supervisor.profiles.resolve_profile(body.profile_id, body.command, {}, job=True)
        return JobProfileApproval(
            profile=ProfileMetadata.model_validate(snapshot, from_attributes=True),
            policy=PolicyWire(**asdict(supervisor.config.policy_maximum)),
        )

    @app.put("/v1/artifacts/{artifact_id}")
    async def put_artifact(
        artifact_id: UUID,
        request: Request,
        response: Response,
        consumer_id: Annotated[ConsumerId, Query()],
        x_content_sha256: Annotated[str, Header()],
    ) -> dict[str, object]:
        result = await artifacts.put(
            Principal(consumer_id), artifact_id, x_content_sha256, request.stream()
        )
        response.status_code = 201 if result.created else 200
        return asdict(result.artifact)

    @app.delete("/v1/artifacts/{artifact_id}", status_code=204)
    async def retire(artifact_id: UUID, consumer_id: Annotated[ConsumerId, Query()]) -> Response:
        await artifacts.retire(Principal(consumer_id), artifact_id)
        return Response(status_code=204)

    @app.websocket("/v1/sandboxes/{identifier}/terminal")
    async def terminal(
        websocket: WebSocket, identifier: UUID, consumer_id: Annotated[ConsumerId, Query()]
    ) -> None:
        if not authorized(websocket.headers.get("Authorization", "")):
            await websocket.send_denial_response(
                JSONResponse({"detail": "invalid supervisor credential"}, status_code=401)
            )
            return
        try:
            ref = supervisor.terminal_ref(Principal(consumer_id), identifier)
        except BoxieError as error:
            await websocket.send_denial_response(boxie_error_response(error))
            return
        await serve_terminal(websocket, supervisor, ref)

    app.add_middleware(
        RequestLogging,
        completed=request_completed,
        accept_incoming=lambda scope: authorized(Headers(scope=scope).get("authorization", "")),
    )
    return app
