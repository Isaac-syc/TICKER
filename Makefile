# Atajos de desarrollo. En Windows: Git Bash / WSL con `make`, o copia los comandos.
DEV := docker compose -f compose.yaml -f compose.dev.yaml

.PHONY: env up down dev logs ps test test-unit test-api lint e2e migrate seed openapi clean

env: ## Crea .env a partir del ejemplo si no existe
	@test -f .env || cp .env.example .env

up: env ## Stack tipo producción → http://localhost:8080
	docker compose up --build -d --wait

down: ## Detiene el stack (conserva datos)
	docker compose down

dev: env ## Stack de desarrollo con recarga en caliente
	$(DEV) up --build

logs: ## Logs de todos los servicios
	docker compose logs -f --tail=100

ps:
	docker compose ps

test: test-unit test-api ## Todas las pruebas del backend (en contenedor)

test-unit:
	$(DEV) run --rm --no-deps api pytest tests/unit -q

test-api: ## Pruebas de API contra Postgres/Redis del stack de desarrollo
	$(DEV) run --rm api pytest tests/api -q

lint: ## Lint + tipos + contratos de arquitectura (back) y lint + tipos (front)
	$(DEV) run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy && lint-imports"
	cd frontend && npm run lint && npm run typecheck

e2e: up ## Pruebas end-to-end con Playwright contra el stack
	cd frontend && npx playwright test

migrate: ## Aplica migraciones y seed
	docker compose run --rm migrate

openapi: ## Regenera los tipos TypeScript a partir del OpenAPI del backend
	cd backend && uv run python -m helpdesk openapi > ../frontend/src/lib/api/openapi.json
	cd frontend && npm run gen:api

clean: ## Borra contenedores y volúmenes (¡borra la BD!)
	docker compose down -v
