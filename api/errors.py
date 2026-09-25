"""RFC 7807 error envelope (docs/05-API-SPEC.md section 0)."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_ERROR_BASE = "https://sentineltrace.dev/errors"

_TITLES = {
    400: "Malformed request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    422: "Unprocessable entity",
    429: "Too many requests",
    503: "Service unavailable",
}


def _slug(detail: object) -> str:
    text = str(detail).lower()
    keep = [c if c.isalnum() else "-" for c in text]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60] or "error"


def _problem_response(status: int, detail: object, instance: str) -> JSONResponse:
    title = _TITLES.get(status, "Error")
    body = {
        "type": f"{_ERROR_BASE}/{_slug(title)}",
        "title": title,
        "status": status,
        "detail": str(detail),
        "instance": instance,
        "trace_id": uuid.uuid4().hex[:10].upper(),
    }
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem_response(exc.status_code, exc.detail, str(request.url.path))

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem_response(422, exc.errors(), str(request.url.path))
