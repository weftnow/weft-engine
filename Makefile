POETRY ?= poetry

.PHONY: install dev start worker check-docs lint format format-check typecheck test verify-fast verify

install:
	$(POETRY) sync

dev:
	$(POETRY) run uvicorn src.main:create_app --factory --reload --host 127.0.0.1 --port 8000

start:
	$(POETRY) run uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000

worker:
	$(POETRY) run python -m src.matching.worker

check-docs:
	$(POETRY) run python scripts/check_harness.py

lint:
	$(POETRY) run ruff check .

format:
	$(POETRY) run ruff format .

format-check:
	$(POETRY) run ruff format --check .

typecheck:
	$(POETRY) run mypy

test:
	$(POETRY) run pytest --cov=src --cov-report=term-missing

verify-fast: check-docs lint format-check typecheck

verify: verify-fast test
