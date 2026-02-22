.PHONY: up down logs shell test

# Copy env if not present
.env:
	cp .env.example .env
	@echo "Created .env from .env.example — fill in AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, etc."

up: .env
	docker compose up -d --build
	@echo "RubricOps running at http://localhost:$$(grep WEB_PORT .env | cut -d= -f2 || echo 5000)"
	@echo "(migrations + seed run automatically on startup)"

down:
	docker compose down

logs:
	docker compose logs -f web

shell:
	docker compose exec web bash

test:
	docker compose exec web pytest tests/ -v
