PROJECT_NAME := powerdns-api-proxy
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS := -X main.version=$(VERSION)

.PHONY: help all build run unit test integration lint fmt vet tidy clean build-docker run-docker run-docker-debug

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

all: build ## build everything

build: ## build the binary into bin/
	go build -trimpath -ldflags "$(LDFLAGS)" -o bin/$(PROJECT_NAME) ./cmd/powerdns-api-proxy

run: ## run the proxy (needs PROXY_CONFIG_PATH)
	PROXY_CONFIG_PATH=$(PROXY_CONFIG_PATH) LOG_FILE=false go run ./cmd/powerdns-api-proxy

unit: ## run unit tests
	go test ./... -v

test: lint unit ## run linters and tests

lint: ## run linters (golangci-lint if available, else go vet)
	@command -v golangci-lint >/dev/null 2>&1 && golangci-lint run || \
		(echo "golangci-lint not found, falling back to go vet" && go vet ./...)

fmt: ## format the code
	gofmt -l -w .

vet: ## run go vet
	go vet ./...

tidy: ## tidy go.mod/go.sum
	go mod tidy

clean: ## remove build artifacts
	rm -rf ./bin

build-docker: ## build the docker image
	docker build -t $(PROJECT_NAME):test .

run-docker: build-docker ## run the docker image
	docker run --rm -p 8000:8000 $(PROJECT_NAME):test

run-docker-debug: build-docker ## run with a mounted config on port 8000
	docker run --rm -it -v "${PWD}:/app" -p 8000:8000 -e "PROXY_CONFIG_PATH=/app/config.yml" $(PROJECT_NAME):test
