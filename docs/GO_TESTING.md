## Go Tests

[![Go Tests](https://github.com/javimosch/a2a-skill/actions/workflows/go-test.yml/badge.svg)](https://github.com/javimosch/a2a-skill/actions/workflows/go-test.yml)

### Unit Tests

```bash
go test -count=1 -timeout 60s ./...
```

### Smoke Test

```bash
go build -tags fts5 -o a2a ./cmd/a2a/
./smoke_test_go.sh ./a2a
```

### JSON Cross-Verification

```bash
go build -tags fts5 -o a2a ./cmd/a2a/
./verify_json_parity.sh ./a2a
```

### Coverage

```bash
make test-cover
```

## Go Binary

The a2a CLI is available as a Go binary (companion to the Python CLI):

```bash
# Build from source
go build -tags fts5 -o a2a ./cmd/a2a/
./a2a version
```

See [GO_CLI_REFERENCE.md](docs/GO_CLI_REFERENCE.md) for full documentation.
