# Convenience targets for Unix-like shells and CI.
# On Windows use scripts\bootstrap.ps1 and scripts\verify.ps1.

PYTHON ?= python

.PHONY: help bootstrap format lint layers typecheck test verify clean

help:
	@echo "bootstrap  - create .venv and install dev dependencies"
	@echo "format     - auto-format the codebase"
	@echo "lint       - ruff format check + lint"
	@echo "layers     - enforce modules -> integrations -> core"
	@echo "typecheck  - mypy strict over src/"
	@echo "test       - pytest with coverage (integration tests excluded)"
	@echo "verify     - SDLC Step 7: every quality gate (CI parity)"

bootstrap:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check . --fix

lint:
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .

layers:
	lint-imports

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest --cov=src --cov-report=term-missing -m "not integration"

verify: lint layers typecheck test
	@echo "All gates passed. Next: SDLC Step 8 - documentation drift audit."

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .import_linter_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -exec rm -rf {} +
