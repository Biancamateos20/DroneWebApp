import cv2
import time
from aiohttp import web
import aiohttp_cors
from ultralytics import YOLO
import asyncio

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    RTCConfiguration,
    RTCIceServer,
)
from av import VideoFrame

model = YOLO("yolov8n.pt")

pcs = set()
latest_jpeg = None
latest_ts = 0.0
latest_lock = asyncio.Lock()
snapshot_interval = 0.4

class ProcessedVideoTrack(VideoStreamTrack):

    def __init__(self, source):
        # Inicializa el track con el stream de video de entrada.
        super().__init__()
        self.source = source
        self.last_process_time = 0
        self.process_interval = 1 / 24
        self.last_boxes = None

    async def recv(self):
        # Recibe frames, aplica deteccion de personas y actualiza snapshots.
        frame = await self.source.recv()

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
                classes=[0],
                verbose=False
            )
            if results and len(results) > 0:
                self.last_boxes = results[0].boxes
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

        cv2.putText(
            img,
            "Person Detection (COCO)",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

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

async def offer(request):
    # Gestiona la oferta WebRTC y responde con el SDP de respuesta.
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
                params.encodings[0]["maxBitrate"] = 2_500_000
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

async def snapshot(request):
    # Devuelve el ultimo frame JPEG disponible.
    async with latest_lock:
        if latest_jpeg is None:
            return web.json_response({"error": "No hay frames aún"}, status=503)
        return web.Response(body=latest_jpeg, content_type="image/jpeg")

async def cleanup(app):
    # Cierra conexiones WebRTC activas al apagar el servicio.
    for pc in pcs:
        await pc.close()
    pcs.clear()

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
