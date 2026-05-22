#!/usr/bin/env bash
# run_mapping.sh — Inicia mapeamento 3D em tempo real com RTAB-Map + L515
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE="realsense-mapping:latest"
CONTAINER_NAME="realsense-mapping"
XAUTH_FILE="/tmp/.docker.xauth"

# X11
if command -v xhost &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    xhost +local:docker >/dev/null 2>&1 || true
fi
if command -v xauth &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    touch "${XAUTH_FILE}" && chmod 600 "${XAUTH_FILE}"
    xauth nlist "${DISPLAY}" 2>/dev/null | sed 's/^..../ffff/' | \
        xauth -f "${XAUTH_FILE}" nmerge - 2>/dev/null || true
fi

# Coletar hidraw para IMU da L515
DEVICE_ARGS=(--device /dev/bus/usb:/dev/bus/usb)
for hr in /dev/hidraw*; do
    [ -e "$hr" ] && DEVICE_ARGS+=(--device "${hr}:${hr}")
done

docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo "Iniciando mapeamento 3D..."
echo "  DISPLAY=${DISPLAY:-:1}"
echo "  Dispositivos: ${DEVICE_ARGS[*]}"
echo ""
echo "Abrindo RViz2 + RTAB-Map. Mova a câmera devagar para mapear o ambiente."
echo "O mapa 3D aparece em tempo real no RViz2."
echo ""

docker run \
    --name "${CONTAINER_NAME}" \
    --runtime nvidia -it --rm \
    --env NVIDIA_VISIBLE_DEVICES=all \
    --env NVIDIA_DRIVER_CAPABILITIES=all \
    --env DISPLAY="${DISPLAY:-:1}" \
    --env XAUTHORITY=/root/.Xauthority \
    --env QT_X11_NO_MITSHM=1 \
    --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
    --volume "${XAUTH_FILE}:/root/.Xauthority:ro" \
    --volume "${PROJECT_DIR}/workspace:/workspace" \
    "${DEVICE_ARGS[@]}" \
    --device-cgroup-rule 'c 189:* rmw' \
    --device-cgroup-rule 'c 13:* rmw' \
    --group-add video \
    --group-add plugdev \
    --network host \
    --ipc host \
    "${IMAGE}" \
    ros2 launch /opt/mapping/l515_rtabmap.launch.py
