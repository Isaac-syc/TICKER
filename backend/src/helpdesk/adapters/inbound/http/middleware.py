import re
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger("helpdesk.access")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
SKIP_ACCESS_LOG = ("/api/health/",)


class RequestContextMiddleware:
    """ASGI puro (compatible con streaming): asigna request_id, lo propaga a los logs y a la
    respuesta, registra el acceso con duración y agrega headers de seguridad."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                extra = [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin"),
                ]
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if not path.startswith(SKIP_ACCESS_LOG):
                client = scope.get("client")
                log.info(
                    "http_request",
                    method=scope.get("method"),
                    path=path,
                    status=status_code,
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                    client_ip=headers.get(b"x-real-ip", b"").decode("latin-1")
                    or (client[0] if client else None),
                )
            structlog.contextvars.clear_contextvars()
