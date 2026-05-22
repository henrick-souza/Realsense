# RealSense L515 · CUDA 12.6 · Python 3.10 · Jetson AGX Orin (SM 8.7)
# builder (~8 GB) → runtime (~2.5 GB) | ccache + ninja | BuildKit cache mounts

ARG LIBREALSENSE_VERSION=2.53.1
ARG CUDA_IMAGE=nvidia/cuda:12.6.0

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM ${CUDA_IMAGE}-devel-ubuntu22.04 AS builder

ARG LIBREALSENSE_VERSION
ENV LIBREALSENSE_VERSION=${LIBREALSENSE_VERSION} \
    DEBIAN_FRONTEND=noninteractive \
    CCACHE_DIR=/root/.ccache \
    CCACHE_MAXSIZE=5G \
    CMAKE_C_COMPILER_LAUNCHER=ccache \
    CMAKE_CXX_COMPILER_LAUNCHER=ccache \
    CMAKE_CUDA_COMPILER_LAUNCHER=ccache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git pkg-config ninja-build ccache \
        libusb-1.0-0-dev libudev-dev libv4l-dev \
        libglfw3-dev libgl1-mesa-dev libglu1-mesa-dev libgtk-3-dev freeglut3-dev \
        libx11-dev libxcb-dri3-0 \
        python3 python3-dev python3-pip \
        libssl-dev zlib1g-dev liblz4-dev ca-certificates

RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --upgrade pip

RUN git clone --depth 1 --branch v${LIBREALSENSE_VERSION} \
    https://github.com/IntelRealSense/librealsense.git /opt/librealsense

RUN mkdir -p /opt/librealsense/build && cd /opt/librealsense/build && cmake .. \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/rs_install \
        -DBUILD_PYTHON_BINDINGS=true \
        -DPYTHON_EXECUTABLE=$(which python3) \
        -DPYTHON_INSTALL_DIR=/opt/rs_install/lib/python3.10/dist-packages \
        -DBUILD_WITH_CUDA=true \
        -DCMAKE_CUDA_ARCHITECTURES=87 \
        -DCUDA_ARCH_BIN="8.7" \
        -DFORCE_RSUSB_BACKEND=true \
        -DBUILD_EXAMPLES=false \
        -DBUILD_GRAPHICAL_EXAMPLES=false \
        -DBUILD_UNIT_TESTS=false \
        -DBUILD_CV_EXAMPLES=false \
        -DBUILD_PCL_EXAMPLES=false \
        -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda

RUN --mount=type=cache,target=/root/.ccache \
    cd /opt/librealsense/build && ninja -j$(nproc) && ninja install && ccache --show-stats

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM ${CUDA_IMAGE}-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    LD_LIBRARY_PATH=/usr/local/lib:/usr/local/cuda/lib64 \
    MPLBACKEND=TkAgg \
    DISPLAY=:0

LABEL librealsense.version="2.53.1" jetpack.version="6.1" cuda.sm="8.7"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libusb-1.0-0 libudev1 libv4l-0 v4l-utils usbutils \
        libglfw3 libgl1-mesa-glx libglu1-mesa libgtk-3-0 freeglut3 \
        mesa-utils x11-apps x11-utils libxcb-dri3-0 \
        python3 python3-pip python3-tk ca-certificates

COPY --from=builder /opt/rs_install /usr/local
RUN ldconfig

RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --upgrade pip && \
    pip3 install numpy opencv-python matplotlib && \
    pip3 install open3d || echo "[WARN] open3d não instalado"

COPY scripts/validate_realsense.py scripts/view_streams.py scripts/view_pointcloud.py /opt/
# udev rules: copiadas do builder pois o source (/opt/librealsense) não existe no runtime
COPY --from=builder /opt/librealsense/config/99-realsense-libusb.rules /opt/

RUN python3 -c "import pyrealsense2 as rs; print('[OK] pyrealsense2', rs.__version__)"

WORKDIR /workspace

HEALTHCHECK --interval=60s --timeout=15s --start-period=10s --retries=3 \
    CMD python3 -c "import pyrealsense2 as rs; print(rs.__version__)" || exit 1

CMD ["/bin/bash"]
