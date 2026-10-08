"""Translate application and unexpected errors into JSON responses."""

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class UnexpectedErrorMiddleware:
    """Turn unhandled exceptions into a JSON body.

    ``AppError`` and FastAPI validation errors are handled inside the application
    and never reach this middleware, so they keep their own status codes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            await self._app(scope, receive, send)
        except Exception:
            logger.exception("Unhandled error on %s", scope.get("path"))
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                },
            )
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_middleware(UnexpectedErrorMiddleware)

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        payload: dict[str, str] = {"error": exc.code, "message": exc.message}
        if exc.file_id is not None:
            payload["file_id"] = exc.file_id
        return JSONResponse(status_code=exc.status_code, content=payload)
