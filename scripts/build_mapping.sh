#!/usr/bin/env bash
# build_mapping.sh — Builda a imagem realsense-mapping:latest (Step 2)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_TAG="realsense-mapping:latest"
NO_CACHE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        --tag)      IMAGE_TAG="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

command -v docker &>/dev/null || { echo "[ERROR] docker not found"; exit 1; }

# Verificar que a imagem base existe
docker image inspect realsense-l515:latest &>/dev/null \
    || { echo "[ERROR] realsense-l515:latest não encontrada. Execute ./scripts/build.sh primeiro."; exit 1; }

echo "Building ${IMAGE_TAG}"
echo "Base: realsense-l515:latest"
echo ""

START=$(date +%s)

DOCKER_BUILDKIT=1 docker build \
    ${NO_CACHE} \
    --file "${PROJECT_DIR}/Dockerfile.mapping" \
    --tag "${IMAGE_TAG}" \
    --progress=plain \
    "${PROJECT_DIR}"

ELAPSED=$(( $(date +%s) - START ))
SIZE=$(docker image inspect "${IMAGE_TAG}" --format='{{.Size}}' 2>/dev/null \
    | awk '{printf "%.1f GB", $1/1073741824}')

echo ""
echo "Done em $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s — ${IMAGE_TAG} (${SIZE})"
echo ""
echo "Para rodar:"
echo "  bash ./scripts/run_mapping.sh"
