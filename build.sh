#!/bin/bash
set -eu

# Build the a2a Go CLI binary.
# Usage: ./build.sh [local|release]
#   local (default): build for current platform
#   release: build all 4 platforms (requires cross-compilers or native runners)

VERSION="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo 'dev')}"
MODE="${1:-local}"

case "$MODE" in
  local)
    echo "Building a2a v$VERSION for current platform..."
    go build -ldflags "-s -w -X main.Version=$VERSION" -tags fts5 -o a2a ./cmd/a2a/
    echo "Built a2a ($(ls -lh a2a | awk '{print $5}'))"
    ;;
  release)
    echo "Building a2a v$VERSION for all platforms..."
    mkdir -p dist
    for target in "linux/amd64" "linux/arm64" "darwin/amd64" "darwin/arm64"; do
      os="${target%%/*}"
      arch="${target##*/}"
      out="dist/a2a-${os}-${arch}"
      echo "  Building $os/$arch..."
      GOOS="$os" GOARCH="$arch" CGO_ENABLED=1 \
        go build -ldflags "-s -w -X main.Version=$VERSION" -tags fts5 -o "$out" ./cmd/a2a/
      sha256sum "$out" > "${out}.sha256" 2>/dev/null || shasum -a256 "$out" > "${out}.sha256"
      echo "    $(ls -lh "$out" | awk '{print $5}')"
    done
    echo "Done. Release binaries in dist/:"
    ls -lh dist/
    ;;
  *)
    echo "Usage: $0 [local|release]"
    exit 1
    ;;
esac
