#!/usr/bin/env bash
# run.sh — Run the realsense-l515 container
# Usage:
#   ./scripts/run.sh                                          # interactive bash
#   ./scripts/run.sh realsense-viewer
#   ./scripts/run.sh python3 /opt/validate_realsense.py --stream
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE="realsense-l515:latest"
CONTAINER_NAME="realsense-l515"
XAUTH_FILE="/tmp/.docker.xauth"

# X11: allow local Docker containers and generate a scoped Xauthority cookie
if command -v xhost &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    xhost +local:docker >/dev/null 2>&1 || true
fi
if command -v xauth &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    touch "${XAUTH_FILE}" && chmod 600 "${XAUTH_FILE}"
    xauth nlist "${DISPLAY}" 2>/dev/null | sed 's/^..../ffff/' | \
        xauth -f "${XAUTH_FILE}" nmerge - 2>/dev/null || true
fi

# Collect hidraw devices for L515 IMU
DEVICE_ARGS=(--device /dev/bus/usb:/dev/bus/usb)
for hr in /dev/hidraw*; do
    [ -e "$hr" ] && DEVICE_ARGS+=(--device "${hr}:${hr}")
done

docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo "Starting ${CONTAINER_NAME}  DISPLAY=${DISPLAY:-not set}  devices=${DEVICE_ARGS[*]}"

TTY_FLAGS=$([ -t 0 ] && echo "-it" || echo "-i")

docker run \
    --name "${CONTAINER_NAME}" --runtime nvidia ${TTY_FLAGS} --rm \
    --env NVIDIA_VISIBLE_DEVICES=all \
    --env NVIDIA_DRIVER_CAPABILITIES=all \
    --env DISPLAY="${DISPLAY:-:0}" \
    --env XAUTHORITY=/root/.Xauthority \
    --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
    --volume "${XAUTH_FILE}:/root/.Xauthority:ro" \
    --volume "${PROJECT_DIR}/workspace:/workspace" \
    "${DEVICE_ARGS[@]}" \
    --device-cgroup-rule 'c 189:* rmw' \
    --device-cgroup-rule 'c 13:* rmw' \
    --group-add video \
    --group-add plugdev \
    --network host \
    "${IMAGE}" "${@:-/bin/bash}"
