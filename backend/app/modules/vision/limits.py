"""Early rejection of oversized uploads.

FastAPI parses the multipart body before any dependency of the endpoint runs, and Starlette spools the whole file
to disk while doing so; a size check inside the endpoint therefore comes after the bytes have been received. This
middleware refuses a request by its `Content-Length` before the body is read at all.

Remaining limits: a request without `Content-Length` (chunked) is not caught here and is still refused by the
check after spooling, and nginx caps bodies at 1100 MB on `/api/v1/vision/`. The exact per-kind limit (photo or
video) is enforced by the endpoint once the file type is known.
"""

import json
import re
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

UPLOAD_PATH = re.compile(r"^/api/v1/vision/sessions/\d+/assets$")
# Multipart framing and the other form fields.
SLACK_BYTES = 1024 * 1024


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and UPLOAD_PATH.match(scope["path"]):
            settings = get_settings()
            limit_mb = max(settings.vision_max_photo_mb, settings.vision_max_video_mb)
            declared = dict(scope["headers"]).get(b"content-length")
            if declared is not None and declared.isdigit() and int(declared) > limit_mb * 1024 * 1024 + SLACK_BYTES:
                await _too_large(send, limit_mb)
                return
        await self.app(scope, receive, send)


async def _too_large(send: Send, limit_mb: int) -> None:
    body: dict[str, Any] = {"detail": {"code": "file_too_large", "message": f"Файл больше {limit_mb} МБ"}}
    payload = json.dumps(body, ensure_ascii=False).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": payload})
