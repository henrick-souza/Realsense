#!/usr/bin/env python3
"""
view_streams.py — Visualizador 2D em tempo real para a RealSense L515

Mostra depth colorido + cor RGB lado a lado numa janela OpenCV.
A distância do ponto central é exibida em tempo real.

Uso (dentro do container):
    python3 /opt/view_streams.py

Controles:
    Q / Esc  → sair
    S        → salvar frame atual em /workspace/
    Space    → pausar / retomar
    C        → trocar colormap do depth (Jet, Grayscale, HSV, ...)
    F        → toggle filtro temporal (ligado por padrão)
"""

import sys
import time
import argparse
import numpy as np
import cv2
import pyrealsense2 as rs

# ── Perfis da L515 ───────────────────────────────────────────────────────────
DEPTH_W, DEPTH_H, DEPTH_FPS = 1024, 768, 30
COLOR_W, COLOR_H, COLOR_FPS = 1280, 720, 30

# Colormaps disponíveis (rs.option.color_scheme)
COLORMAPS = {0: "Jet", 1: "Classic", 2: "WhiteToBlack", 3: "BlackToWhite",
             4: "Bio", 5: "Cold", 6: "Warm", 7: "Quantized", 8: "Pattern"}


def draw_overlay(img: np.ndarray, text: str, pos=(10, 30)):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                (255, 255, 255), 1, cv2.LINE_AA)


def draw_crosshair(img: np.ndarray, color=(0, 255, 0)):
    cx, cy = img.shape[1] // 2, img.shape[0] // 2
    cv2.drawMarker(img, (cx, cy), color, cv2.MARKER_CROSS, 24, 2, cv2.LINE_AA)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-filter", action="store_true",
                        help="Desabilitar filtro temporal")
    parser.add_argument("--colormap", type=int, default=0,
                        help="Colormap inicial (0=Jet, ver lista no código)")
    args = parser.parse_args()

    # ── Pipeline ─────────────────────────────────────────────────────────────
    pipeline = rs.pipeline()
    config   = rs.config()
    config.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16,  DEPTH_FPS)
    config.enable_stream(rs.stream.color, COLOR_W, COLOR_H, rs.format.bgr8, COLOR_FPS)

    try:
        profile = pipeline.start(config)
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale  = depth_sensor.get_depth_scale()
        print(f"[OK] Pipeline iniciado — depth scale: {depth_scale:.5f} m/unit")
        print(f"     Câmera: {profile.get_device().get_info(rs.camera_info.name)}")
        print(f"     USB:    {profile.get_device().get_info(rs.camera_info.usb_type_descriptor)}")
    except Exception as e:
        print(f"[FAIL] Não foi possível iniciar o pipeline: {e}")
        print("       Câmera conectada? Execute: rs-enumerate-devices")
        sys.exit(1)

    # ── Filtros + colorizer ───────────────────────────────────────────────────
    colorizer = rs.colorizer()
    colorizer.set_option(rs.option.color_scheme, args.colormap)
    colormap_idx = args.colormap

    align    = rs.align(rs.stream.color)
    temporal = rs.temporal_filter()
    use_filter = not args.no_filter

    # ── Estado ───────────────────────────────────────────────────────────────
    frame_count  = 0
    saved_count  = 0
    paused       = False
    last_display = None
    t_start      = time.perf_counter()
    fps_display  = 0.0

    print("Aguardando câmera estabilizar...", flush=True)
    for _ in range(15):
        pipeline.wait_for_frames(timeout_ms=5000)
    print("Câmera pronta!\n")

    print("\nControles: Q/Esc=sair  S=salvar  Space=pausar  C=colormap  F=filtro")

    while True:
        if not paused:
            try:
                frames  = pipeline.wait_for_frames(timeout_ms=5000)
            except RuntimeError as e:
                print(f"[WARN] Timeout aguardando frames: {e}")
                continue

            aligned = align.process(frames)
            depth_f = aligned.get_depth_frame()
            color_f = aligned.get_color_frame()

            if not depth_f or not color_f:
                continue

            if use_filter:
                depth_f = temporal.process(depth_f).as_depth_frame()

            # Distância central
            cx = depth_f.get_width()  // 2
            cy = depth_f.get_height() // 2
            centre_dist = depth_f.get_distance(cx, cy)

            # Converter para numpy
            depth_colored = np.asanyarray(colorizer.colorize(depth_f).get_data())
            color_image   = np.asanyarray(color_f.get_data())

            # FPS a cada 30 frames
            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.perf_counter() - t_start
                fps_display = frame_count / elapsed

            # Overlay no depth
            cmap_name = COLORMAPS.get(colormap_idx, str(colormap_idx))
            filt_str  = "filtro:ON" if use_filter else "filtro:OFF"
            draw_overlay(depth_colored, f"Depth | {cmap_name} | {filt_str}")
            draw_overlay(depth_colored, f"Centro: {centre_dist:.3f} m | {fps_display:.1f} fps",
                         pos=(10, depth_colored.shape[0] - 10))
            draw_crosshair(depth_colored, color=(255, 255, 255))

            # Overlay na cor
            draw_overlay(color_image, f"Color | {COLOR_W}x{COLOR_H}@{COLOR_FPS}")
            draw_overlay(color_image, f"Centro: {centre_dist:.3f} m | {fps_display:.1f} fps",
                         pos=(10, color_image.shape[0] - 10))
            draw_crosshair(color_image, color=(0, 255, 0))

            # Redimensionar depth para mesma altura da cor e juntar
            depth_resized = cv2.resize(depth_colored,
                                       (color_image.shape[1], color_image.shape[0]))
            last_display = np.hstack([depth_resized, color_image])

        if last_display is not None:
            cv2.imshow("L515 — Depth  |  Color   (Q=sair  S=salvar  Space=pausar)",
                       last_display)

        key = cv2.waitKey(1) & 0xFF

        if key in (ord('q'), 27):       # Q ou Esc
            break
        elif key == ord('s') and last_display is not None:
            saved_count += 1
            fname = f"/workspace/l515_frame_{saved_count:04d}.png"
            cv2.imwrite(fname, last_display)
            print(f"[S] Salvo: {fname}")
        elif key == ord(' '):
            paused = not paused
            print(f"[Space] {'Pausado' if paused else 'Retomado'}")
        elif key == ord('c'):
            colormap_idx = (colormap_idx + 1) % len(COLORMAPS)
            colorizer.set_option(rs.option.color_scheme, colormap_idx)
            print(f"[C] Colormap: {COLORMAPS[colormap_idx]}")
        elif key == ord('f'):
            use_filter = not use_filter
            print(f"[F] Filtro temporal: {'ON' if use_filter else 'OFF'}")

    pipeline.stop()
    cv2.destroyAllWindows()
    print(f"\n[OK] Encerrado — {frame_count} frames capturados, {saved_count} salvos.")


if __name__ == "__main__":
    main()
