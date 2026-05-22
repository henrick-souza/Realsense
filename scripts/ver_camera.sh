#!/usr/bin/env bash
set -e

docker rm -f realsense-l515 2>/dev/null || true

# Copia fontes para o Qt do OpenCV
mkdir -p /tmp/cv2fonts
find /usr/share/fonts -name '*.ttf' -exec cp {} /tmp/cv2fonts/ \; 2>/dev/null || true

xhost +local:docker 2>/dev/null || true

docker run --name realsense-l515 --runtime nvidia -it --rm \
  --env DISPLAY="${DISPLAY:-:1}" \
  --env QT_X11_NO_MITSHM=1 \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
  --volume /tmp/cv2fonts:/usr/local/lib/python3.10/dist-packages/cv2/qt/fonts:ro \
  --volume "$(dirname "$0"):/opt/scripts:ro" \
  --device /dev/bus/usb:/dev/bus/usb \
  --device /dev/hidraw0 --device /dev/hidraw1 --device /dev/hidraw2 \
  --device-cgroup-rule 'c 189:* rmw' \
  --device-cgroup-rule 'c 13:* rmw' \
  realsense-l515:latest python3 /opt/scripts/camera_live.py
