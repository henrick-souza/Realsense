#!/usr/bin/env python3
"""
view_pointcloud.py — Visualizador 3D de nuvem de pontos para a RealSense L515

Captura frames de depth + cor alinhados e exibe uma nuvem de pontos
colorida e interativa via Open3D.

Uso (dentro do container):
    python3 /opt/view_pointcloud.py
    python3 /opt/view_pointcloud.py --save          # salva .ply ao fechar
    python3 /opt/view_pointcloud.py --max-dist 3.0  # truncar a 3m

Controles da janela Open3D:
    Arrastar       → rotacionar
    Scroll         → zoom
    Ctrl+arrastar  → pan
    R              → resetar câmera
    Q / fechar     → sair (e perguntar se salva .ply)
"""

import sys
import time
import argparse
import numpy as np
import pyrealsense2 as rs

# ── Perfis da L515 ───────────────────────────────────────────────────────────
DEPTH_W, DEPTH_H, DEPTH_FPS = 1024, 768, 30
COLOR_W, COLOR_H, COLOR_FPS = 1280, 720, 30


def check_open3d():
    try:
        import open3d as o3d
        return o3d
    except ImportError:
        print("[FAIL] open3d não está instalado.")
        print("       Instale com: pip3 install open3d")
        print("       Alternativa: use o view_streams.py (OpenCV, sem dependência extra)")
        sys.exit(1)


def build_pinhole(intrinsics) -> "o3d.camera.PinholeCameraIntrinsic":
    import open3d as o3d
    return o3d.camera.PinholeCameraIntrinsic(
        intrinsics.width,
        intrinsics.height,
        intrinsics.fx,
        intrinsics.fy,
        intrinsics.ppx,
        intrinsics.ppy,
    )


def depth_to_pcd(depth_img, color_img, pinhole, depth_scale_m, max_dist, o3d):
    """
    Converte arrays numpy (depth uint16, color BGR uint8) em PointCloud Open3D.

    depth_scale_m: metros por unit (ex: 0.00025 para L515 padrão)
    max_dist:      distância máxima em metros para incluir na nuvem
    """
    # Open3D espera profundidade como uint16 e cor como RGB uint8
    depth_o3d = o3d.geometry.Image(depth_img.astype(np.uint16))
    color_o3d = o3d.geometry.Image(color_img[:, :, ::-1].astype(np.uint8))  # BGR→RGB

    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        color_o3d,
        depth_o3d,
        depth_scale=1.0 / depth_scale_m,   # unidades por metro
        depth_trunc=max_dist,
        convert_rgb_to_intensity=False,
    )

    return o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, pinhole)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true",
                        help="Salvar nuvem de pontos em /workspace/ ao fechar")
    parser.add_argument("--max-dist", type=float, default=5.0,
                        help="Distância máxima em metros (padrão: 5.0)")
    parser.add_argument("--update-hz", type=float, default=10.0,
                        help="Taxa de atualização da nuvem (padrão: 10 Hz)")
    args = parser.parse_args()

    o3d = check_open3d()

    # ── Pipeline ─────────────────────────────────────────────────────────────
    pipeline = rs.pipeline()
    config   = rs.config()
    config.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16,  DEPTH_FPS)
    config.enable_stream(rs.stream.color, COLOR_W, COLOR_H, rs.format.bgr8, COLOR_FPS)

    try:
        profile = pipeline.start(config)
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale  = depth_sensor.get_depth_scale()   # metros/unit (ex: 0.00025)
        print(f"[OK] Pipeline iniciado")
        print(f"     Câmera:      {profile.get_device().get_info(rs.camera_info.name)}")
        print(f"     Depth scale: {depth_scale:.5f} m/unit ({1/depth_scale:.0f} units/m)")
        print(f"     Max dist:    {args.max_dist} m")
    except Exception as e:
        print(f"[FAIL] Não foi possível iniciar o pipeline: {e}")
        sys.exit(1)

    align     = rs.align(rs.stream.color)
    temporal  = rs.temporal_filter()
    spatial   = rs.spatial_filter()

    # Após rs.align(color), o depth fica reprojetado no espaço da câmera de cor.
    # Usar os intrínsecos do COLOR (não do depth) para a nuvem de pontos.
    color_intrinsics = (
        profile.get_stream(rs.stream.color)
        .as_video_stream_profile()
        .get_intrinsics()
    )
    pinhole = build_pinhole(color_intrinsics)

    # ── Open3D visualizer ────────────────────────────────────────────────────
    vis = o3d.visualization.Visualizer()
    vis.create_window("L515 — Point Cloud 3D  (Q=sair  R=reset câmera)",
                      width=1280, height=720)

    opt = vis.get_render_option()
    opt.background_color = np.array([0.05, 0.05, 0.05])  # fundo quase preto
    opt.point_size = 1.5

    pcd         = o3d.geometry.PointCloud()
    first_frame = True
    frame_count = 0
    update_interval = 1.0 / args.update_hz
    last_update     = 0.0

    print("\n[OK] Janela Open3D aberta.")
    print("     Arrastar=rotacionar  Scroll=zoom  Ctrl+arrastar=pan  R=reset  Q=sair")

    try:
        while True:
            now = time.perf_counter()

            # Capturar frames na frequência full (30 fps) mas atualizar a nuvem em update_hz
            try:
                frames  = pipeline.wait_for_frames(timeout_ms=200)
            except RuntimeError:
                # Sem frame novo — só atualizar a janela
                if not vis.poll_events():
                    break
                vis.update_renderer()
                continue

            aligned = align.process(frames)
            depth_f = aligned.get_depth_frame()
            color_f = aligned.get_color_frame()

            if not depth_f or not color_f:
                continue

            # Só recalcular a nuvem na taxa desejada
            if now - last_update < update_interval:
                if not vis.poll_events():
                    break
                vis.update_renderer()
                continue

            last_update = now

            # Aplicar filtros
            depth_f = temporal.process(depth_f)
            depth_f = spatial.process(depth_f)

            # Converter para numpy
            depth_img = np.asanyarray(depth_f.get_data())
            color_img = np.asanyarray(color_f.get_data())

            # Gerar nuvem de pontos
            new_pcd = depth_to_pcd(depth_img, color_img, pinhole,
                                   depth_scale, args.max_dist, o3d)

            pcd.points = new_pcd.points
            pcd.colors = new_pcd.colors

            frame_count += 1

            if first_frame:
                vis.add_geometry(pcd)
                # Posicionar câmera inicial olhando de cima e de frente
                vc = vis.get_view_control()
                vc.set_zoom(0.5)
                first_frame = False
            else:
                vis.update_geometry(pcd)

            if frame_count % 10 == 0:
                n_points = len(pcd.points)
                print(f"  Frame {frame_count:4d} | Pontos: {n_points:>7,} | "
                      f"Update: {args.update_hz:.0f} Hz")

            if not vis.poll_events():
                break
            vis.update_renderer()

    except KeyboardInterrupt:
        print("\n[Ctrl+C] Interrompido pelo usuário.")
    finally:
        pipeline.stop()
        vis.destroy_window()
        print(f"\n[OK] Encerrado — {frame_count} nuvens geradas.")

    # ── Salvar ────────────────────────────────────────────────────────────────
    if len(pcd.points) > 0:
        do_save = args.save
        if not do_save:
            resp = input("Salvar última nuvem de pontos? (s/N): ").strip().lower()
            do_save = resp == 's'

        if do_save:
            ts    = time.strftime("%Y%m%d_%H%M%S")
            fname = f"/workspace/l515_pointcloud_{ts}.ply"
            o3d.io.write_point_cloud(fname, pcd)
            print(f"[OK] Salvo: {fname}  ({len(pcd.points):,} pontos)")


if __name__ == "__main__":
    main()
