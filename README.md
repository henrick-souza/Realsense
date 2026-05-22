# RealSense L515 — Docker on Jetson AGX Orin

Step 1 of the real-time 3D mapping pipeline (→ Nvblox + Isaac ROS).

## Stack

| Component | Value |
|-----------|-------|
| Hardware | NVIDIA Jetson AGX Orin |
| L4T | R36.4.x (JetPack 6.1) |
| CUDA | 12.6 · SM 8.7 (Orin Ampere) |
| Camera | Intel RealSense L515 (LiDAR) |
| librealsense | 2.53.1 — last release with full L515 support |
| Python | 3.10 |
| Build | multi-stage: builder (~8 GB) → runtime (~2.5 GB) |
| Backend | RSUSB (libusb) — no V4L2 kernel modules needed |

## Structure

```
Realsense/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── README.md
├── scripts/
│   ├── build.sh                # build the image
│   ├── run.sh                  # run with X11, CUDA, USB devices
│   ├── validate.sh             # pre-flight host checks
│   ├── validate_realsense.py   # in-container validation
│   ├── view_streams.py         # real-time depth + color viewer (OpenCV)
│   └── view_pointcloud.py      # 3D point cloud viewer (Open3D)
├── udev/
│   └── setup_udev.sh           # install udev rules on host (sudo, once)
└── workspace/                  # bind-mounted into /workspace
```

## Quick start

```bash
# 1. Pre-flight — check host prerequisites
./scripts/validate.sh

# 2. Install udev rules (once, requires sudo)
sudo ./udev/setup_udev.sh
# Unplug and re-plug the L515 after this step

# 3. Build (~35-50 min first time, ~5 min after ccache is warm)
./scripts/build.sh

# 4. Run
./scripts/run.sh
```

Inside the container:
```bash
python3 /opt/validate_realsense.py           # import + device check
python3 /opt/validate_realsense.py --stream  # 30-frame capture test
python3 /opt/validate_realsense.py --cuda    # + CUDA filter test

python3 /opt/view_streams.py                 # depth + color side-by-side (OpenCV)
python3 /opt/view_pointcloud.py              # 3D point cloud (Open3D)
python3 /opt/view_pointcloud.py --save       # save .ply on exit

realsense-viewer                             # official Intel GUI
rs-enumerate-devices                         # list camera profiles
```

### Docker Compose (alternative)

```bash
export DISPLAY=:0
xhost +local:docker
docker compose up -d
docker compose exec realsense bash
docker compose down
```

## Visualizer controls

**view_streams.py**

| Key | Action |
|-----|--------|
| `Q` / `Esc` | Quit |
| `S` | Save frame to `/workspace/` |
| `Space` | Pause / resume |
| `C` | Cycle depth colormap |
| `F` | Toggle temporal filter |

**view_pointcloud.py** — drag to rotate, scroll to zoom, `R` to reset camera.

## L515 stream profiles

| Stream | Resolution | Format | FPS |
|--------|-----------|--------|-----|
| Depth | 1024×768 | Z16 | 30 |
| Depth | 640×480 | Z16 | 30 |
| Color | 1920×1080 | BGR8 | 30 |
| Color | 1280×720 | BGR8 | 30 |
| IMU gyro | — | — | 400 Hz |
| IMU accel | — | — | 100 Hz |

Depth unit: 0.25 mm (value × 0.00025 = meters).

## Kernel module (L515 IMU)

The IMU requires `hid-sensor-hub` on the host:

```bash
sudo modprobe hid-sensor-hub

# Persist across reboots:
echo 'hid-sensor-hub' | sudo tee /etc/modules-load.d/realsense-imu.conf
```

## Troubleshooting

**Camera not found inside container**
```bash
lsusb | grep 8086                          # verify camera visible on host
ls /etc/udev/rules.d/99-realsense-libusb.rules  # verify udev rules
# Quick diagnostic with full access:
docker run --rm --privileged --runtime nvidia realsense-l515:latest \
    python3 /opt/validate_realsense.py
```

**pyrealsense2 import error**
```bash
find /usr/local/lib -name "pyrealsense2*.so"
python3 -c "import sys; print('\n'.join(sys.path))"
```

**realsense-viewer blank screen**
```bash
xhost +local:docker          # on host
glxgears                     # inside container — tests OpenGL/X11
```

**L515 on USB 2.0**
The L515 requires USB 3.0 SuperSpeed. A 2.0 connection causes dropped frames.
Verify inside container:
```python
import pyrealsense2 as rs
for dev in rs.context().query_devices():
    print(dev.get_info(rs.camera_info.usb_type_descriptor))  # expect 3.1 or 3.2
```

## Design decisions

**librealsense 2.53.1** — Intel announced L515 End-of-Life in 2.54.1. This is the last version where the L515 was actively tested. Hardware still works in newer versions but camera-specific bugs won't be fixed.
Override: `./scripts/build.sh --librealsense 2.54.1`

**RSUSB backend** — The V4L2 backend requires `uvcvideo` kernel module and `/dev/video*` access inside the container. RSUSB uses libusb directly — only needs `/dev/bus/usb` and udev rules.

**nvidia/cuda:12.6.0-devel as builder base** — `docker build` does not use the NVIDIA runtime, so CUDA headers and nvcc must be embedded in the image. The runtime stage uses the smaller `cuda:runtime` variant; at runtime `--runtime=nvidia` overlays the Jetson GPU libraries from the host.

**ccache + ninja** — First build populates the ccache (~5 GB). Subsequent builds recompile only changed files (~5 min instead of ~50 min).

## Next step: Nvblox + Isaac ROS

Step 2 will build on this image:
```dockerfile
FROM realsense-l515:latest
# + ROS 2 Humble + Isaac ROS + Nvblox
```
The L515 depth + color aligned frames feed directly into Nvblox as input.
Note: Nvblox was tuned for stereo cameras (D435/D455). With the L515 LiDAR,
adjust `voxel_size` and `truncation_distance` to match the L515's noise profile.
