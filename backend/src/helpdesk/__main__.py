"""CLI de operación: `python -m helpdesk <comando>`.

Comandos:
  seed      Crea permisos, roles base, categorías, usuarios demo y (opcional) datos de ejemplo.
  openapi   Imprime el esquema OpenAPI en JSON (para generar los tipos del front).
"""

import asyncio
import json
import sys


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "seed":
        from helpdesk.adapters.inbound.cli.seed import run_seed
        from helpdesk.adapters.outbound.logging import configure_logging
        from helpdesk.config import get_settings

        settings = get_settings()
        configure_logging(settings.log_level, settings.log_json)
        asyncio.run(run_seed(settings))
    elif command == "openapi":
        from pydantic import SecretStr

        from helpdesk.adapters.inbound.http.app import create_app
        from helpdesk.config import Settings

        # El esquema no necesita BD ni secretos reales: no se ejecuta el lifespan.
        settings = Settings(jwt_secret=SecretStr("x" * 32), app_env="dev")
        app = create_app(lambda: None, settings)  # type: ignore[arg-type,return-value]
        sys.stdout.write(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stderr.write(__doc__ or "")
        sys.exit(2)


if __name__ == "__main__":
    main()
