.PHONY: install test check test-llm agent

install:
	uv sync
	uv run pre-commit install

test:            ## offline tests (free)
	uv run pytest

check: test      ## lint, format check, type check, offline tests
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run pyright

test-llm:        ## agent behaviour tests against a real LLM (costs ~1p)
	uv run pytest -m llm

agent:           ## run the voice agent worker locally
	uv run phoneai agent dev
