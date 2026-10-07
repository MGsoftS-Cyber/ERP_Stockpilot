.PHONY: install backend-dev frontend-dev migrate seed test lint check docker-up docker-down

install:
	uv --project services/erp-core sync
	pnpm install
	cd services/api-gateway && npm ci --ignore-scripts

backend-dev:
	uv --project services/erp-core run python services/erp-core/manage.py runserver

frontend-dev:
	pnpm --filter @stockpilot/web dev

migrate:
	uv --project services/erp-core run python services/erp-core/manage.py migrate

seed:
	uv --project services/erp-core run python services/erp-core/manage.py seed_week8

test:
	cd services/api-gateway && npm test
	cd services/identity && mvn -B verify
	uv --project services/erp-core run pytest services/erp-core
	cd services/ai-service && uv run pytest
	pnpm --filter @stockpilot/web test

lint:
	uv --project services/erp-core run ruff check services/erp-core
	uv --project services/ai-service run ruff check services/ai-service
	pnpm --filter @stockpilot/web lint

check: lint test
	uv --project services/erp-core run python services/erp-core/manage.py check
	uv --project services/erp-core run python services/erp-core/manage.py makemigrations --check --dry-run
	uv --project services/erp-core run python scripts/verify_static.py
	pnpm --filter @stockpilot/web build

docker-up:
	docker compose up --build

docker-down:
	docker compose down
