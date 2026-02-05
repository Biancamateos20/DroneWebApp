import cv2
import time
from aiohttp import web
import aiohttp_cors
from ultralytics import YOLO
# import mediapipe as mp
import asyncio

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    RTCConfiguration,
    RTCIceServer,
)
from av import VideoFrame

# ===============================
# MediaPipe (GLOBAL) - reservado para uso futuro
# ===============================
# mp_face_mesh = mp.solutions.face_mesh
# mp_drawing = mp.solutions.drawing_utils
#
# face_mesh = mp_face_mesh.FaceMesh(
#     static_image_mode=False,
#     max_num_faces=1,
#     refine_landmarks=True,
#     min_detection_confidence=0.5,
#     min_tracking_confidence=0.5
# )
#
# soft_green = mp_drawing.DrawingSpec(
#     color=(0, 255, 0),
#     thickness=1,
#     circle_radius=1
# )

# ===============================
# YOLO (GLOBAL) - COCO "person" = class 0
# ===============================
model = YOLO("yolov8n.pt")

pcs = set()
latest_jpeg = None
latest_ts = 0.0
latest_lock = asyncio.Lock()
snapshot_interval = 0.4  # seconds

# ===============================
# Video Track Optimizado
# ===============================
class ProcessedVideoTrack(VideoStreamTrack):

    def __init__(self, source):
        super().__init__()
        self.source = source
        self.last_process_time = 0
        self.process_interval = 1 / 24  # 24 FPS (equilibrado)
        self.last_boxes = None        # 🔑 persistencia
        # self.last_landmarks = None  # 🔑 reservado para MediaPipe

    async def recv(self):
        frame = await self.source.recv()

        # 🔑 descartar frames antiguos
        try:
            while self.source._queue.qsize() > 1:
                frame = await self.source.recv()
        except:
            pass

        img = frame.to_ndarray(format="bgr24")

        now = time.time()
        do_process = (now - self.last_process_time) > self.process_interval

        if do_process:
            self.last_process_time = now
            results = model.predict(
                img,
                imgsz=640,
                conf=0.25,
                classes=[0],  # person
                verbose=False
            )
            if results and len(results) > 0:
                self.last_boxes = results[0].boxes
            # img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # results = face_mesh.process(img_rgb)
            # if results.multi_face_landmarks:
            #     self.last_landmarks = results.multi_face_landmarks

        # ===============================
        # Dibujado de cajas
        # ===============================
        if self.last_boxes is not None:
            for box in self.last_boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0]) if box.conf is not None else 0.0
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    img,
                    f"person {conf:.2f}",
                    (x1, max(0, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )
        # if self.last_landmarks:
        #     overlay = img.copy()
        #
        #     for face_landmarks in self.last_landmarks:
        #         mp_drawing.draw_landmarks(
        #             image=overlay,
        #             landmark_list=face_landmarks,
        #             connections=mp_face_mesh.FACEMESH_LEFT_EYE,
        #             landmark_drawing_spec=soft_green,
        #             connection_drawing_spec=soft_green
        #         )
        #
        #         mp_drawing.draw_landmarks(
        #             image=overlay,
        #             landmark_list=face_landmarks,
        #             connections=mp_face_mesh.FACEMESH_RIGHT_EYE,
        #             landmark_drawing_spec=soft_green,
        #             connection_drawing_spec=soft_green
        #         )
        #
        #         mp_drawing.draw_landmarks(
        #             image=overlay,
        #             landmark_list=face_landmarks,
        #             connections=mp_face_mesh.FACEMESH_LIPS,
        #             landmark_drawing_spec=soft_green,
        #             connection_drawing_spec=soft_green
        #         )
        #
        #     img = cv2.addWeighted(overlay, 0.4, img, 0.6, 0)

        cv2.putText(
            img,
            "Person Detection (COCO)",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        # Guarda un snapshot JPEG cada cierto tiempo para /snapshot
        global latest_jpeg, latest_ts
        now2 = time.time()
        if now2 - latest_ts > snapshot_interval:
            ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok:
                async with latest_lock:
                    latest_jpeg = buf.tobytes()
                    latest_ts = now2

        new_frame = VideoFrame.from_ndarray(img, format="bgr24")
        pts, time_base = await self.next_timestamp()
        new_frame.pts = pts
        new_frame.time_base = time_base

        return new_frame

# ===============================
# Offer
# ===============================
async def offer(request):
    params = await request.json()

    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"]
    )

    pc = RTCPeerConnection(
        RTCConfiguration(
            iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
        )
    )

    pcs.add(pc)

    @pc.on("track")
    def on_track(track):
        if track.kind == "video":
            sender = pc.addTrack(ProcessedVideoTrack(track))
            try:
                params = sender.getParameters()
                if not params.encodings:
                    params.encodings = [{}]
                params.encodings[0]["maxBitrate"] = 2_500_000  # 2.5 Mbps
                params.encodings[0]["maxFramerate"] = 30
                sender.setParameters(params)
            except Exception as e:
                print("⚠️ No se pudo ajustar bitrate:", e)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# ===============================
# Snapshot
# ===============================
async def snapshot(request):
    async with latest_lock:
        if latest_jpeg is None:
            return web.json_response({"error": "No hay frames aún"}, status=503)
        return web.Response(body=latest_jpeg, content_type="image/jpeg")

# ===============================
# Cleanup
# ===============================
async def cleanup(app):
    for pc in pcs:
        await pc.close()
    pcs.clear()
    # face_mesh.close()

# ===============================
# App
# ===============================
app = web.Application()
app.router.add_post("/offer", offer)
app.router.add_get("/snapshot", snapshot)
app.on_shutdown.append(cleanup)

cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})

for route in list(app.router.routes()):
    cors.add(route)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
