.PHONY: all up down test test-unit test-curl lint clean

all: up

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test: test-unit test-curl

test-unit:
	bash scripts/test.sh

test-curl:
	bash scripts/test_curl.sh

lint:
	cd agent-service && ruff check . && cd ../mcp-servers && ruff check . && cd ..

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf agent-service/*.egg-info mcp-servers/*.egg-info
