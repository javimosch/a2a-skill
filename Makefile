.PHONY: build test test-cover clean release lint

VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")

build:
	go build -ldflags "-s -w -X main.Version=$(VERSION)" -tags fts5 -o a2a ./cmd/a2a/

test:
	CGO_ENABLED=1 go test -count=1 -timeout 60s ./...

test-cover:
	CGO_ENABLED=1 go test -count=1 -timeout 60s -coverprofile=coverage.out ./...
	go tool cover -func=coverage.out | tail -1
	go tool cover -html=coverage.out -o coverage.html

test-race:
	CGO_ENABLED=1 go test -count=1 -race -timeout 120s ./...

release:
	./build.sh release

clean:
	rm -f a2a
	rm -rf dist/
	rm -f coverage.out coverage.html
