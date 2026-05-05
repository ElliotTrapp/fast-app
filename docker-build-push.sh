#!/bin/bash
set -euo pipefail
VERSION=${1:-latest}
echo "Building and pushing trapper137/fast-app:${VERSION}..."
docker buildx build --platform linux/amd64,linux/arm64 -t "trapper137/fast-app:${VERSION}" --push .
echo "Done! Pushed trapper137/fast-app:${VERSION}"