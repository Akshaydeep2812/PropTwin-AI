import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("proptwin.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        super().__init__(message)


def not_found(entity: str = "Resource") -> AppError:
    return AppError(404, f"{entity.lower().replace(' ', '_')}_not_found", f"{entity} not found.")


def forbidden(message: str = "You do not have permission to perform this action.") -> AppError:
    return AppError(403, "forbidden", message)


def conflict(code: str, message: str) -> AppError:
    return AppError(409, code, message)


def unauthorized(message: str = "Authentication is required.") -> AppError:
    return AppError(401, "unauthorized", message, {"WWW-Authenticate": "Bearer"})


def _body(request: Request, code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None), **extra}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(_body(request, exc.code, exc.message), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        return JSONResponse(_body(request, f"http_{exc.status_code}", str(exc.detail)), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(part) for part in err["loc"] if part != "body"), "message": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            _body(request, "validation_error", "The request is invalid.", fields=jsonable_encoder(fields)),
            status_code=422,
        )

    @app.exception_handler(RateLimitExceeded)
    async def handle_rate_limit(request: Request, exc: RateLimitExceeded):
        return JSONResponse(_body(request, "rate_limited", "Too many requests. Try again shortly."), status_code=429)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("unhandled_exception", extra={"path": request.url.path})
        return JSONResponse(_body(request, "internal_error", "An unexpected error occurred."), status_code=500)
