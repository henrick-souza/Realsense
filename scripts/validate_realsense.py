#!/usr/bin/env python3
"""
validate_realsense.py — In-container validation for Intel RealSense L515

Run inside the Docker container:
    python3 /opt/validate_realsense.py           # device check only
    python3 /opt/validate_realsense.py --stream  # + 30-frame capture test
    python3 /opt/validate_realsense.py --cuda    # + CUDA filter test

Exit codes:
    0  all selected checks passed
    1  at least one check failed
    2  no RealSense device found (not a build failure, camera may be unplugged)
"""

import sys
import time
import argparse

# ── ANSI colours (safe to use — terminal is always tty inside the container) ──
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}[OK]{RESET}   {msg}")
def warn(msg): print(f"  {YELLOW}[WARN]{RESET} {msg}")
def fail(msg): print(f"  {RED}[FAIL]{RESET} {msg}")
def section(title): print(f"\n{BOLD}── {title} {'─' * (50 - len(title))}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. pyrealsense2 import
# ─────────────────────────────────────────────────────────────────────────────
def check_import():
    section("pyrealsense2 import")
    try:
        import pyrealsense2 as rs
        ok(f"pyrealsense2 imported — version {rs.__version__}")
        return rs
    except ImportError as e:
        fail(f"Cannot import pyrealsense2: {e}")
        print("\n  Likely causes:")
        print("    • Container not built successfully (CMake/make error)")
        print("    • pyrealsense2 not in sys.path")
        print(f"    • sys.path = {sys.path}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. CUDA availability (optional)
# ─────────────────────────────────────────────────────────────────────────────
def check_cuda(rs):
    section("CUDA availability")
    try:
        # pyrealsense2 exposes rs.cuda_context on CUDA-enabled builds
        if hasattr(rs, "cuda_context"):
            ctx = rs.cuda_context()
            ok("rs.cuda_context() created — CUDA support compiled in")
            return True
        else:
            warn("rs.cuda_context not found. librealsense may have been built without CUDA.")
            warn("This is OK — CPU fallback will be used for post-processing filters.")
            return False
    except Exception as e:
        warn(f"CUDA context check raised: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Device enumeration
# ─────────────────────────────────────────────────────────────────────────────
def check_devices(rs):
    section("Connected RealSense devices")

    ctx = rs.context()
    devices = ctx.query_devices()

    if len(devices) == 0:
        warn("No RealSense devices found.")
        print("\n  Likely causes:")
        print("    • Camera not plugged in")
        print("    • udev rules not installed on HOST (run: sudo ./udev/setup_udev.sh)")
        print("    • USB bus not passed to container (/dev/bus/usb missing in --device)")
        print("    • Container running without --privileged or device-cgroup-rule")
        return None

    l515_device = None
    for i, dev in enumerate(devices):
        name    = dev.get_info(rs.camera_info.name)
        serial  = dev.get_info(rs.camera_info.serial_number)
        fw      = dev.get_info(rs.camera_info.firmware_version)
        usb     = dev.get_info(rs.camera_info.usb_type_descriptor)

        ok(f"Device {i}: {name}")
        print(f"         Serial:   {serial}")
        print(f"         Firmware: {fw}")
        print(f"         USB:      {usb}")

        if "L515" in name:
            l515_device = dev
            ok("→ Intel RealSense LiDAR Camera L515 identified ✓")

    if l515_device is None:
        warn("L515 not found in device list (other RealSense device(s) present)")
        return None

    # Verificar firmware mínimo compatível com librealsense 2.53.1
    # Firmware muito antigo causa falhas silenciosas no stream de depth
    MIN_FW = (1, 5, 8, 0)
    fw_str = l515_device.get_info(rs.camera_info.firmware_version)
    try:
        fw_parts = tuple(int(x) for x in fw_str.split("."))
        if fw_parts >= MIN_FW:
            ok(f"Firmware {fw_str} ≥ {'.'.join(str(x) for x in MIN_FW)} ✓")
        else:
            warn(f"Firmware {fw_str} pode ser antigo demais para librealsense 2.53.1.")
            warn(f"  Mínimo recomendado: {'.'.join(str(x) for x in MIN_FW)}")
            warn(f"  Atualizar via realsense-viewer → More → Update Firmware")
    except ValueError:
        warn(f"Não foi possível parsear versão de firmware: {fw_str}")

    return l515_device


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stream test (depth + colour, 30 frames)
# ─────────────────────────────────────────────────────────────────────────────
def check_streaming(rs, n_frames=30):
    section(f"Streaming test ({n_frames} frames)")

    # L515 native resolutions:
    #   Depth:  1024×768 @ 30 fps  (Z16)
    #   Color:  1920×1080 @ 30 fps (BGR8) or 1280×720
    pipeline = rs.pipeline()
    config   = rs.config()
    config.enable_stream(rs.stream.depth, 1024, 768,  rs.format.z16,  30)
    config.enable_stream(rs.stream.color, 1280, 720,  rs.format.bgr8, 30)

    try:
        profile = pipeline.start(config)
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale  = depth_sensor.get_depth_scale()
        ok(f"Pipeline started (depth scale = {depth_scale:.4f} m/unit)")

        ok(f"Capturing {n_frames} frames...")
        frame_times = []
        t0 = time.perf_counter()

        for i in range(n_frames):
            frames = pipeline.wait_for_frames(timeout_ms=5000)
            depth  = frames.get_depth_frame()
            color  = frames.get_color_frame()

            if not depth or not color:
                fail(f"Frame {i+1}: missing depth or color")
                pipeline.stop()
                return False

            frame_times.append(time.perf_counter())

            if i == 0 or (i + 1) % 10 == 0:
                centre_dist = depth.get_distance(depth.get_width() // 2,
                                                  depth.get_height() // 2)
                print(f"         Frame {i+1:3d}/{n_frames} — "
                      f"depth {depth.get_width()}×{depth.get_height()} | "
                      f"color {color.get_width()}×{color.get_height()} | "
                      f"centre {centre_dist:.3f} m")

        elapsed = frame_times[-1] - t0
        fps = (n_frames - 1) / elapsed if elapsed > 0 else 0
        ok(f"Stream stable — measured {fps:.1f} fps over {n_frames} frames")

        pipeline.stop()
        return True

    except Exception as e:
        fail(f"Streaming error: {e}")
        try:
            pipeline.stop()
        except Exception:
            pass
        print("\n  Likely causes:")
        print("    • Camera firmware/driver mismatch (try firmware update)")
        print("    • Another process has the camera open (rs-enumerate-devices -S)")
        print("    • USB 2.0 connection (L515 requires USB 3.0 SuperSpeed)")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. CUDA post-processing filter test
# ─────────────────────────────────────────────────────────────────────────────
def check_cuda_filters(rs):
    section("CUDA post-processing filters")

    pipeline = rs.pipeline()
    config   = rs.config()
    config.enable_stream(rs.stream.depth, 1024, 768, rs.format.z16, 30)

    temporal = rs.temporal_filter()
    align    = rs.align(rs.stream.color)

    try:
        pipeline.start(config)

        # Grab a few frames and apply the temporal filter (uses CUDA if compiled in)
        for _ in range(5):
            frames = pipeline.wait_for_frames(timeout_ms=5000)

        depth = frames.get_depth_frame()
        filtered = temporal.process(depth)
        ok(f"Temporal filter applied: {depth.get_width()}×{depth.get_height()} → "
           f"{filtered.get_width()}×{filtered.get_height()}")

        pipeline.stop()
        return True

    except Exception as e:
        fail(f"Filter test error: {e}")
        try:
            pipeline.stop()
        except Exception:
            pass
        return False


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Validate RealSense L515 environment inside Docker"
    )
    parser.add_argument("--stream", action="store_true",
                        help="Run the 30-frame streaming test (requires camera)")
    parser.add_argument("--cuda",   action="store_true",
                        help="Run CUDA filter test (requires camera)")
    parser.add_argument("--frames", type=int, default=30,
                        help="Number of frames to capture in --stream test (default: 30)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 60}")
    print(" RealSense L515 Environment Validation")
    print(f"{'═' * 60}{RESET}")
    print(f" Python  : {sys.version}")
    print(f" Platform: {sys.platform}")

    failures = 0

    # Step 1: import (always runs, exits on failure)
    rs = check_import()

    # Step 2: CUDA (always runs, non-fatal)
    check_cuda(rs)

    # Step 3: device enumeration (always runs)
    device = check_devices(rs)
    if device is None:
        print(f"\n{YELLOW}Camera not found — skipping streaming/filter tests.{RESET}")
        print("Connect the L515 and re-run with --stream to test capture.")
        sys.exit(2)

    # Step 4: streaming (opt-in)
    if args.stream or args.cuda:
        if not check_streaming(rs, n_frames=args.frames):
            failures += 1

    # Step 5: CUDA filters (opt-in)
    if args.cuda:
        if not check_cuda_filters(rs):
            failures += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    if failures == 0:
        print(f"{GREEN}{BOLD} All checks passed ✓{RESET}")
    else:
        print(f"{RED}{BOLD} {failures} check(s) failed ✗{RESET}")
    print(f"{'═' * 60}\n")

    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
