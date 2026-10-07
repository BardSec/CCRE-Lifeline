.PHONY: up dev down logs shell test migrate upgrade

COMPOSE_DEV = docker compose -f docker-compose.yml -f docker-compose.dev.yml

# Copy env if not present
.env:
	cp .env.example .env
	@echo "Created .env from .env.example — set SECRET_KEY, ADMIN_EMAILS, and the AZURE_* values."

up: .env
	docker compose up -d --build
	@echo "RubricOps running at http://localhost:$$(grep '^WEB_PORT=' .env | cut -d= -f2 || echo 5000)"
	@echo "(migrations + seed run automatically on startup)"

dev: .env
	$(COMPOSE_DEV) up --build

down:
	docker compose down

logs:
	docker compose logs -f web

shell:
	docker compose exec web bash

test:
	docker compose exec web pytest tests/ -v

# Generate a migration after changing app/models.py: make migrate m="add foo"
migrate:
	docker compose exec web flask db migrate -m "$(m)"

upgrade:
	docker compose exec web flask db upgrade
