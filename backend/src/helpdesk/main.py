"""Punto de entrada ASGI: `uvicorn helpdesk.main:app`."""

from helpdesk.adapters.inbound.http.app import create_app
from helpdesk.adapters.outbound.logging import configure_logging
from helpdesk.config import get_settings
from helpdesk.container import Container

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
app = create_app(lambda: Container(settings), settings)
