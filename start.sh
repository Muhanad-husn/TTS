#!/usr/bin/env bash
set -euo pipefail

mkdir -p input output

# Copy file arguments into input/ and rewrite paths for container
args=()
for arg in "$@"; do
    if [[ -f "$arg" ]]; then
        cp "$arg" "input/$(basename "$arg")"
        args+=("/input/$(basename "$arg")")
    else
        args+=("$arg")
    fi
done

docker compose up -d pocket-tts-wyoming
docker compose run --rm read-aloud "${args[@]}"
