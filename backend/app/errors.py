import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from minio.error import S3Error
from urllib3.exceptions import HTTPError as Urllib3Error


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    """Error in the contract format: {"detail": {"code": <snake_case>, "message": <ru>}}."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def forbidden(message: str = "Недостаточно прав для этого действия") -> HTTPException:
    return api_error(403, "forbidden", message)


logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(S3Error)
    @app.exception_handler(Urllib3Error)
    async def storage_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Object storage error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "storage_unavailable", "message": "Хранилище файлов временно недоступно"}},
        )

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
