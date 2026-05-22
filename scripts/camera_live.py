import pyrealsense2 as rs, numpy as np, cv2

pipeline = rs.pipeline()
config   = rs.config()
config.enable_stream(rs.stream.depth, 1024, 768, rs.format.z16,  30)
config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
profile = pipeline.start(config)
colorizer = rs.colorizer()
colorizer.set_option(rs.option.min_distance, 0.1)
colorizer.set_option(rs.option.max_distance, 3.0)
align     = rs.align(rs.stream.color)

print("Aquecendo camera (aguarde)...", flush=True)
for _ in range(15):
    pipeline.wait_for_frames()
print("Janela aberta! Use Q para sair.", flush=True)

while True:
    frames  = pipeline.wait_for_frames(5000)
    aligned = align.process(frames)
    depth_f = aligned.get_depth_frame()
    color_f = aligned.get_color_frame()
    if not depth_f or not color_f:
        continue
    depth_img = np.asanyarray(colorizer.colorize(depth_f).get_data())
    color_img = np.asanyarray(color_f.get_data())
    depth_r   = cv2.resize(depth_img, (color_img.shape[1], color_img.shape[0]))
    combined  = np.hstack([depth_r, color_img])
    cv2.imshow("L515 - Depth | Color  (Q=sair)", combined)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

pipeline.stop()
cv2.destroyAllWindows()
