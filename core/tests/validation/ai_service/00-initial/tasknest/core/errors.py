from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class TasknestError(Exception):
    status = 400


class NotFound(TasknestError):
    status = 404


class Unauthorized(TasknestError):
    status = 401


class Forbidden(TasknestError):
    status = 403


class ValidationFailed(TasknestError):
    status = 422


def install_error_handlers(api: FastAPI) -> None:
    @api.exception_handler(TasknestError)
    def handle(request: Request, exc: TasknestError) -> JSONResponse:
        return error_response(exc)


def error_response(exc: TasknestError) -> JSONResponse:
    return JSONResponse({"error": type(exc).__name__, "detail": str(exc)}, status_code=exc.status)
