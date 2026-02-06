# hana — Hands Are Not APIs
# Development Makefile

.PHONY: help build up down logs shell setup health run dry-run test clean

# Default target
help:
	@echo "hana — Development Commands"
	@echo ""
	@echo "Docker Environment:"
	@echo "  make build     Build Docker images"
	@echo "  make up        Start all services (WordPress + MariaDB)"
	@echo "  make down      Stop all services"
	@echo "  make logs      Show logs from all services"
	@echo "  make setup     Run WordPress initial setup"
	@echo ""
	@echo "hana Commands:"
	@echo "  make health    Run health check against WordPress"
	@echo "  make run       Run ingestion engine"
	@echo "  make dry-run   Run ingestion in dry-run mode"
	@echo "  make shell     Open shell in hana container"
	@echo ""
	@echo "Development:"
	@echo "  make test      Run tests locally"
	@echo "  make clean     Remove all containers and volumes"
	@echo ""

# =============================================================================
# Docker Environment
# =============================================================================

build:
	docker compose build

up:
	docker compose up -d wordpress mariadb
	@echo ""
	@echo "WordPress starting at http://localhost:8080"
	@echo "Run 'make setup' to initialize WordPress"

down:
	docker compose down

logs:
	docker compose logs -f

setup:
	docker compose --profile setup run --rm wpcli

# =============================================================================
# hana Commands
# =============================================================================

health:
	docker compose run --rm --no-deps --entrypoint hana hana health -c /app/hana.yaml

run:
	docker compose run --rm --no-deps --entrypoint hana hana run -c /app/hana.yaml

dry-run:
	docker compose run --rm --no-deps --entrypoint hana hana run -c /app/hana.yaml --dry-run

shell:
	docker compose run --rm --entrypoint /bin/bash hana

# =============================================================================
# Development (all inside Docker)
# =============================================================================

test:
	docker compose --profile test build test
	docker compose --profile test run --rm test

test-verbose:
	docker compose --profile test run --rm test python -m pytest tests/ -v --tb=long

lint:
	docker compose --profile test run --rm test ruff check hana/ tests/

typecheck:
	docker compose --profile test run --rm test mypy hana/

format:
	docker compose --profile test run --rm test ruff format hana/ tests/

# =============================================================================
# Cleanup
# =============================================================================

clean:
	docker compose down -v --remove-orphans
	rm -rf .hana/ __pycache__/ .pytest_cache/ *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

reset: clean
	docker compose up -d wordpress mariadb
	sleep 10
	$(MAKE) setup
