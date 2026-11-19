"""Shared HTTP handling for Boxie's private services."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.types import Lifespan

from boxie.domain.errors import BoxieError


def boxie_error_response(error: BoxieError) -> JSONResponse:
    return JSONResponse({"detail": error.public_detail}, status_code=error.status)


def create_private_app(*, lifespan: Lifespan[FastAPI] | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, _error: Exception) -> PlainTextResponse:
        return PlainTextResponse(
            "Internal Server Error",
            status_code=500,
            headers={"X-Request-ID": request.state.request_id},
        )

    @app.exception_handler(BoxieError)
    async def application_error(_request: Request, error: BoxieError) -> JSONResponse:
        return boxie_error_response(error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "invalid request"}, status_code=422)

    return app


async def buffer_post_body(request: Request) -> JSONResponse | None:
    if request.method != "POST":
        return None

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 65_536:
            return JSONResponse({"detail": "request too large"}, status_code=413)
        body.extend(chunk)
    # Starlette replays the cached body for route handlers.
    request._body = bytes(body)
    return None
