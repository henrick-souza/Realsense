#!/usr/bin/env bash
# validate.sh — Pre-flight host checks before building/running the container
# Usage: ./scripts/validate.sh
set -euo pipefail

PASS=0; FAIL=0; WARN=0
ok()   { echo "  [OK]   $*"; (( PASS++ )) || true; }
warn() { echo "  [WARN] $*"; (( WARN++ )) || true; }
fail() { echo "  [FAIL] $*"; (( FAIL++ )) || true; }

# ── Docker ────────────────────────────────────────────────────────────────────
echo "── Docker ───────────────────────────────────────────────────"
command -v docker &>/dev/null \
    && ok "Docker: $(docker --version | head -1)" \
    || fail "Docker not found. Install Docker Engine."

docker info --format '{{.Runtimes}}' 2>/dev/null | grep -q nvidia \
    && ok "NVIDIA runtime registered" \
    || fail "NVIDIA runtime missing. Add to /etc/docker/daemon.json and restart Docker."

command -v nvidia-ctk &>/dev/null \
    && ok "nvidia-ctk: $(nvidia-ctk --version 2>/dev/null | head -1)" \
    || warn "nvidia-ctk not found: sudo apt install nvidia-container-toolkit"

# GPU smoke test inside Docker
if docker run --rm --runtime nvidia \
       -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
       nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi -L 2>/dev/null | grep -q "GPU"; then
    ok "GPU visible inside Docker"
else
    warn "GPU not confirmed inside Docker — run manually: docker run --rm --runtime nvidia -e NVIDIA_VISIBLE_DEVICES=all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi"
fi

# ── CUDA (host) ───────────────────────────────────────────────────────────────
echo ""
echo "── CUDA (host) ──────────────────────────────────────────────"
command -v nvcc &>/dev/null \
    && ok "nvcc: $(nvcc --version | grep release | awk '{print $6}' | tr -d ',')" \
    || warn "nvcc not in PATH — ensure /usr/local/cuda/bin is in PATH"

[ -f /usr/local/cuda/include/cuda.h ] \
    && ok "CUDA headers at /usr/local/cuda/include/" \
    || warn "CUDA headers not found"

# ── udev rules ────────────────────────────────────────────────────────────────
echo ""
echo "── udev + camera ────────────────────────────────────────────"
[ -f /etc/udev/rules.d/99-realsense-libusb.rules ] \
    && ok "udev rules installed" \
    || fail "udev rules missing — run: sudo ./udev/setup_udev.sh"

# ── Camera devices ────────────────────────────────────────────────────────────
[ -d /dev/bus/usb ] && ok "/dev/bus/usb exists" || fail "/dev/bus/usb not found"

if command -v lsusb &>/dev/null; then
    RS=$(lsusb | grep "8086" | grep -iE "L515|0b3a|0b64|0b68" || true)
    [ -n "$RS" ] && ok "L515 detected: $RS" || warn "L515 not found via lsusb (camera connected?)"
fi

HIDRAW_COUNT=$(ls /dev/hidraw* 2>/dev/null | wc -l)
[ "$HIDRAW_COUNT" -gt 0 ] \
    && ok "$HIDRAW_COUNT hidraw device(s): $(ls /dev/hidraw* 2>/dev/null | tr '\n' ' ')" \
    || warn "No /dev/hidraw* — L515 IMU may not be accessible"

lsmod 2>/dev/null | grep -q "hid_sensor_hub" \
    && ok "hid_sensor_hub kernel module loaded (L515 IMU ok)" \
    || warn "hid_sensor_hub not loaded — sudo modprobe hid-sensor-hub"

# ── Permissions ───────────────────────────────────────────────────────────────
echo ""
echo "── Permissions ──────────────────────────────────────────────"
USER=$(whoami)
id -nG "$USER" | grep -q '\bplugdev\b' \
    && ok "$USER in plugdev" \
    || warn "$USER not in plugdev — sudo usermod -aG plugdev $USER"

id -nG "$USER" | grep -q '\bvideo\b' \
    && ok "$USER in video" \
    || warn "$USER not in video — sudo usermod -aG video $USER"

# ── X11 ───────────────────────────────────────────────────────────────────────
echo ""
echo "── X11 ──────────────────────────────────────────────────────"
[ -n "${DISPLAY:-}" ] \
    && ok "DISPLAY=${DISPLAY}" \
    || warn "DISPLAY not set — GUI (realsense-viewer) will not work"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "  ${PASS} passed | ${WARN} warnings | ${FAIL} failed"
[ "$FAIL" -gt 0 ] && { echo "  Fix FAIL items before proceeding."; exit 1; }
[ "$WARN" -gt 0 ] && { echo "  Warnings found — review above."; exit 0; }
echo "  All checks passed — ready to build: ./scripts/build.sh"
