.PHONY: up down migrate seed test logs shell

# Copy env if not present
.env:
	cp .env.example .env
	@echo "Created .env from .env.example — edit secrets before production use."

up: .env
	docker compose up -d --build
	@echo "RubricOps running at http://localhost:$$(grep WEB_PORT .env | cut -d= -f2 || echo 8000)"

down:
	docker compose down

migrate:
	docker compose exec web alembic upgrade head

seed:
	docker compose exec web python scripts/seed.py

test:
	docker compose exec web pytest tests/ -v

logs:
	docker compose logs -f web

shell:
	docker compose exec web bash

# Run migrations + seed in one step (first-time setup)
bootstrap: up
	@echo "Waiting for web to be healthy…"
	@sleep 5
	$(MAKE) migrate
	$(MAKE) seed
	@echo "Bootstrap complete. Login: $$(grep SEED_ADMIN_EMAIL .env | cut -d= -f2)"
