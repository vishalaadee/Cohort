"""Safe, consistent error responses for every API route."""
import logging
from collections.abc import Mapping

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("cohort.api")


def _response(status: int, code: str, message: str, *, fields: dict | None = None):
    error: dict = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JSONResponse(status_code=status, content={"error": error})


def _field_name(loc) -> str:
    parts = [str(part) for part in loc if part not in ("body", "query", "path", "header")]
    return parts[-1] if parts else "form"


def _validation_message(item: Mapping) -> str:
    kind = str(item.get("type", ""))
    ctx = item.get("ctx") or {}
    if kind == "missing":
        return "This field is required."
    if kind in {"value_error", "value_error.email"}:
        return "Enter a valid value."
    if kind == "string_too_short":
        minimum = ctx.get("min_length")
        return f"Use at least {minimum} characters." if minimum else "This value is too short."
    if kind == "string_too_long":
        maximum = ctx.get("max_length")
        return f"Use no more than {maximum} characters." if maximum else "This value is too long."
    if kind in {"int_parsing", "float_parsing"}:
        return "Enter a number."
    if kind == "bool_parsing":
        return "Choose yes or no."
    return "Enter a valid value."


async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    fields: dict[str, str] = {}
    for item in exc.errors():
        field = _field_name(item.get("loc", ()))
        # One concise message per field is easier to render than FastAPI's raw
        # validation array. Preserve the first error in input order.
        fields.setdefault(field, _validation_message(item))
    return _response(422, "validation_error", "Check the highlighted fields.", fields=fields)


async def http_exception_handler(_request: Request, exc: HTTPException):
    status = exc.status_code
    if status >= 500:
        logger.error("HTTP %s raised by application", status)
        return _response(500, "server_error", "Something went wrong on our side. Please try again.")

    detail = exc.detail if isinstance(exc.detail, str) else None
    defaults = {
        401: ("authentication_required", "Sign in to continue."),
        403: ("forbidden", "You do not have permission to do that."),
        404: ("not_found", "We could not find that item."),
        409: ("conflict", "This action conflicts with the current information."),
        422: ("validation_error", "Check the highlighted fields."),
        429: ("rate_limited", "Too many attempts. Please wait a few minutes and try again."),
    }
    code, fallback = defaults.get(status, ("request_failed", "We could not complete that request."))
    # Route handlers contain deliberately user-facing messages. Never send a
    # non-string object (database detail, a validation array, etc.) to clients.
    message = detail[:500] if detail else fallback
    return _response(status, code, message)


async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return _response(500, "server_error", "Something went wrong on our side. Please try again.")


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return _response(500, "server_error", "Something went wrong on our side. Please try again.")
