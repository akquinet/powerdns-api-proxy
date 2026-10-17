PROJECT_NAME := "powerdns_api_proxy"

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

all: setup run ## run everything

setup: ## install required modules
	uv sync
	uv run prek install

lint: ## run linters via prek
	uv run prek run --all-files $(PREK_SKIP)

fmt: ## format the code
	uv run ruff check --fix .
	uv run ruff format .

test: lint unit integration ## Run all tests

unit: ## run unit tests
	uv run pytest -vvl tests/unit/ --showlocals

integration: ## run integration tests
	uv run pytest -vvl --setup-show -vvl tests/integration/ --showlocals || test $$? -eq 5

LISTEN_HOST ?= ::

run: ## run project
	LISTEN_HOST=$(LISTEN_HOST) uv run python -m powerdns_api_proxy --reload

clean: ## clean cache and temp dirs
	rm -rf ./.mypy_cache ./.pytest_cache
	rm -f .coverage

build-docker: ## build docker image
	docker build -t $(PROJECT_NAME):test .

run-docker: build-docker ## run docker image
	docker run --rm $(PROJECT_NAME):test

run-docker-debug: build-docker ## run debug with docker on port 8000
	docker run --rm -it -v "${PWD}:/app" -p 8000:8000 -e "PROXY_CONFIG_PATH=${PROXY_CONFIG_PATH}" --rm $(PROJECT_NAME):test python -m powerdns_api_proxy --reload
