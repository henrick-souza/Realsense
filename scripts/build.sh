#!/usr/bin/env bash
# build.sh — Build the realsense-l515 Docker image
# Usage:
#   ./scripts/build.sh
#   ./scripts/build.sh --no-cache
#   ./scripts/build.sh --tag realsense-l515:v2 --librealsense 2.54.1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_TAG="realsense-l515:latest"
NO_CACHE=""
LIBREALSENSE_VERSION="2.53.1"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache)        NO_CACHE="--no-cache"; shift ;;
        --tag)             IMAGE_TAG="$2"; shift 2 ;;
        --librealsense)    LIBREALSENSE_VERSION="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

command -v docker &>/dev/null || { echo "[ERROR] docker not found"; exit 1; }

if ! docker info --format '{{.Runtimes}}' 2>/dev/null | grep -q nvidia; then
    echo "[WARN] NVIDIA runtime not in docker info — check /etc/docker/daemon.json"
fi

echo "Building ${IMAGE_TAG}  (librealsense ${LIBREALSENSE_VERSION}, $(uname -m))"

START=$(date +%s)

DOCKER_BUILDKIT=1 docker build \
    ${NO_CACHE} \
    --build-arg LIBREALSENSE_VERSION="${LIBREALSENSE_VERSION}" \
    --tag "${IMAGE_TAG}" \
    --progress=plain \
    "${PROJECT_DIR}"

ELAPSED=$(( $(date +%s) - START ))
SIZE=$(docker image inspect "${IMAGE_TAG}" --format='{{.Size}}' 2>/dev/null \
    | awk '{printf "%.1f GB", $1/1073741824}')

echo ""
echo "Done in $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s — ${IMAGE_TAG} (${SIZE})"
echo ""
echo "Next steps:"
echo "  sudo ./udev/setup_udev.sh    # first time only"
echo "  ./scripts/run.sh"
echo "  python3 /opt/validate_realsense.py --stream"
