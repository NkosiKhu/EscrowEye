.PHONY: lint format typecheck test coverage fix install setup

lint:
	ruff check app/ tests/

format:
	ruff format --check app/ tests/

typecheck:
	npx pyright app/

test:
	pytest -v

coverage:
	pytest --cov --cov-report=term-missing -v

fix:
	ruff check --fix app/ tests/
	ruff format app/ tests/

install:
	pip install -r requirements.txt

setup: install
	pre-commit install
