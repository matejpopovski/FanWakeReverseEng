.PHONY: setup dev backend frontend build start test test-backend test-frontend e2e lint migrate seed backup keys hash-password pause

setup:            ## install all dependencies
	cd backend && uv sync
	cd frontend && npm install
	@test -f .env || (cp .env.example .env && echo "Created .env - edit it (make keys, set ADMIN_PASSWORD)")

backend:          ## API + worker with auto-reload on :8000
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:         ## Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev:              ## run backend and frontend together
	$(MAKE) -j2 backend frontend

build:            ## build the SPA into backend/app/static
	cd frontend && npm run build

start: build      ## production-like single process on :8000
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.cli seed

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest -q

test-frontend:
	cd frontend && npm test

e2e:              ## browser end-to-end tests (starts its own server on :8765 with a temp DB)
	cd frontend && npm run e2e

lint:
	cd backend && uv run ruff check app tests && uv run mypy app
	cd frontend && npx tsc -b

backup:
	cd backend && uv run python -m app.cli backup

keys:
	cd backend && uv run python -m app.cli gen-keys

hash-password:
	cd backend && uv run python -m app.cli hash-password

pause:            ## emergency stop for all automation
	cd backend && uv run python -m app.cli pause
