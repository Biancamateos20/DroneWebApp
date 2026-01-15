import cv2
import time
import mediapipe as mp
from aiohttp import web
import aiohttp_cors

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    RTCConfiguration,
    RTCIceServer,
)
from av import VideoFrame

# ===============================
# MediaPipe (GLOBAL)
# ===============================
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils

face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Drawing spec suave
soft_green = mp_drawing.DrawingSpec(
    color=(0, 255, 0),
    thickness=1,
    circle_radius=1
)

pcs = set()

# ===============================
# Video Track Optimizado
# ===============================
class ProcessedVideoTrack(VideoStreamTrack):

    def __init__(self, source):
        super().__init__()
        self.source = source
        self.last_process_time = 0
        self.process_interval = 1 / 12  # 12 FPS
        self.last_landmarks = None     # 🔑 persistencia

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
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(img_rgb)
            if results.multi_face_landmarks:
                self.last_landmarks = results.multi_face_landmarks

        # ===============================
        # Dibujado con transparencia
        # ===============================
        if self.last_landmarks:
            overlay = img.copy()

            for face_landmarks in self.last_landmarks:

                # OJO IZQUIERDO
                mp_drawing.draw_landmarks(
                    image=overlay,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_LEFT_EYE,
                    landmark_drawing_spec=soft_green,
                    connection_drawing_spec=soft_green
                )

                # OJO DERECHO
                mp_drawing.draw_landmarks(
                    image=overlay,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_RIGHT_EYE,
                    landmark_drawing_spec=soft_green,
                    connection_drawing_spec=soft_green
                )

                # BOCA
                mp_drawing.draw_landmarks(
                    image=overlay,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_LIPS,
                    landmark_drawing_spec=soft_green,
                    connection_drawing_spec=soft_green
                )

            # 🔑 alpha para “transparencia”
            img = cv2.addWeighted(overlay, 0.4, img, 0.6, 0)

        cv2.putText(
            img,
            "Low Latency Face Tracking",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

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
            pc.addTrack(ProcessedVideoTrack(track))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# ===============================
# Cleanup
# ===============================
async def cleanup(app):
    for pc in pcs:
        await pc.close()
    pcs.clear()
    face_mesh.close()

# ===============================
# App
# ===============================
app = web.Application()
app.router.add_post("/offer", offer)
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
