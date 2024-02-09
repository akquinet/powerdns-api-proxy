PROJECT_NAME := "powerdns_api_proxy"

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

all: setup run ## run everything

test: unit pre-commit-all integration ## Run all tests

setup: ## install required modules
	python -m pip install -U -r requirements.txt
	python -m pip install -U -r requirements-dev.txt
	pre-commit install

unit: ## run unit tests
	python -m pytest -vvl tests/unit/ --showlocals

integration: ## run integration tests
	python -m pytest -vvl --setup-show -vvl tests/integration/ --showlocals

run: ## run project
	uvicorn --host 0.0.0.0 --port 8000 --reload powerdns_api_proxy.proxy:app

clean: ## clean cache and temp dirs
	rm -rf ./.mypy_cache ./.pytest_cache
	rm -f .coverage

build-docker: ## build docker image
	docker build -t $(PROJECT_NAME):test .

run-docker: build-docker ## run docker image
	docker run --rm $(PROJECT_NAME):test

pre-commit-all: ## run pre-commit on all files
	pre-commit run --all-files

pre-commit: ## run pre-commit
	pre-commit run

run-docker-debug: build-docker ## run debug with docker on port 8000
	docker run --rm -it -v "${PWD}:/app" -p 8000:8000 -e "PROXY_CONFIG_PATH=${PROXY_CONFIG_PATH}" --rm $(PROJECT_NAME):test uvicorn --host 0.0.0.0 --port 8000 --reload powerdns_api_proxy.proxy:app
