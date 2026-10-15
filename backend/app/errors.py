import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from minio.error import S3Error
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from urllib3.exceptions import HTTPError as Urllib3Error


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """Error in the contract format: {"detail": {"code": <snake_case>, "message": <ru>}}."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def forbidden(message: str = "Недостаточно прав для этого действия") -> HTTPException:
    return api_error(403, "forbidden", message)


logger = logging.getLogger(__name__)

UNIQUE_VIOLATION = "23505"


def _internal_error() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "internal_error", "message": "Внутренняя ошибка сервера"}},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(S3Error)
    @app.exception_handler(Urllib3Error)
    async def storage_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Object storage error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "storage_unavailable", "message": "Хранилище файлов временно недоступно"}},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Application errors already carry {code, message}; framework ones (404, 405) carry a plain string.
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": f"http_{exc.status_code}", "message": str(exc.detail)}
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            return JSONResponse(
                status_code=409,
                content={"detail": {"code": "conflict", "message": "Такая запись уже существует"}},
            )
        logger.exception("Integrity error on %s %s", request.method, request.url.path)
        return _internal_error()

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return _internal_error()

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: list[dict[str, Any]] = [
            {"loc": list(err["loc"]), "message": err["msg"], "type": err["type"]} for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {"detail": {"code": "validation_error", "message": "Некорректные данные запроса", "errors": errors}}
            ),
        )
