#!/usr/bin/env bash
# setup_udev.sh — Install RealSense udev rules on the HOST (run once, as root)
# Usage: sudo ./udev/setup_udev.sh
set -euo pipefail

IMAGE="realsense-l515:latest"
RULES_DEST="/etc/udev/rules.d/99-realsense-libusb.rules"
CALLING_USER="${SUDO_USER:-${USER}}"

[ "${EUID:-$(id -u)}" -eq 0 ] || { echo "[ERROR] Run with sudo."; exit 1; }

echo "[1/4] Checking image exists..."
docker image inspect "${IMAGE}" &>/dev/null \
    || { echo "[ERROR] Image '${IMAGE}' not found. Run ./scripts/build.sh first."; exit 1; }

echo "[2/4] Extracting udev rules from image..."
# Rules are copied into /opt/ during the runtime stage build
docker run --rm "${IMAGE}" cat /opt/99-realsense-libusb.rules > /tmp/99-realsense-libusb.rules

echo "[3/4] Installing to ${RULES_DEST}..."
cp /tmp/99-realsense-libusb.rules "${RULES_DEST}"
chmod 644 "${RULES_DEST}"
udevadm control --reload-rules && udevadm trigger
echo "      Done. Unplug and re-plug the L515."

echo "[4/4] Checking groups for user '${CALLING_USER}'..."
for grp in plugdev video; do
    if id -nG "${CALLING_USER}" | grep -q "\b${grp}\b"; then
        echo "      Already in ${grp}."
    else
        usermod -aG "${grp}" "${CALLING_USER}"
        echo "      Added to ${grp} — re-login or run: newgrp ${grp}"
    fi
done

echo ""
echo "Setup complete."
echo "  Verify: lsusb | grep 8086"
echo "  Run:    ./scripts/run.sh"
