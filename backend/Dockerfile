# syntax=docker/dockerfile:1.7
# ---------- base ----------
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# ---------- builder: resuelve dependencias con uv (capa cacheable) ----------
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY pyproject.toml uv.lock alembic.ini ./
COPY src ./src
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------- dev: incluye herramientas de prueba y recarga en caliente ----------
FROM builder AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked
COPY tests ./tests
COPY .importlinter ./
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["api-dev"]

# ---------- runtime: imagen final mínima, usuario sin privilegios ----------
FROM base AS runtime
# Parches de seguridad del SO y sin pip: el venv de uv no lo necesita y su código vendorizado
# (msgpack, pkg_resources) es lo único que Trivy marcaba en la imagen.
RUN apt-get update && apt-get upgrade -y --no-install-recommends     && rm -rf /var/lib/apt/lists/*     && rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/bin/pip*     && groupadd --system app && useradd --system --gid app --no-create-home app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /app/migrations /app/migrations
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["api"]
