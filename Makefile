.PHONY: install format lint typecheck arch test secrets audit check

install:
	uv sync --all-extras
	uv run pre-commit install

format:
	uv run ruff format --check src/ tests/

lint:
	uv run ruff check src/ tests/

typecheck:
	uv run mypy

arch:
	uv run lint-imports

test:
	uv run pytest

secrets:
	uv run pre-commit run gitleaks-worktree --hook-stage manual
	uv run pre-commit run gitleaks-history --hook-stage manual

audit:
	uv export --format requirements-txt --no-emit-project --frozen --output-file requirements-audit.txt --all-extras
	uv run pip-audit --require-hashes --no-deps -r requirements-audit.txt

check: format lint typecheck arch test secrets audit
