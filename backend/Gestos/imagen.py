import cv2
import math
import time
from aiohttp import web
import aiohttp_cors
from ultralytics import YOLO
import asyncio

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from av import VideoFrame

model = YOLO("yolov8n.pt")

pcs = set()
latest_jpeg = None
latest_ts = 0.0
latest_lock = asyncio.Lock()
snapshot_interval = 0.4
latest_tracking = {
    "ok": True,
    "status": "idle",
    "direction": "center",
    "offsetPx": 0,
    "offsetRatio": 0.0,
    "offsetPercent": 0.0,
    "recommendedMoveM": 0.0,
    "estimatedDistanceM": 0.0,
    "frameWidth": 0,
    "frameHeight": 0,
    "targetBox": None,
    "timestamp": 0.0
}
camera_horizontal_fov_deg = 69.0
tracking_deadband_ratio = 0.04
reference_person_width_m = 0.45


def update_latest_tracking(payload):
    global latest_tracking
    latest_tracking = payload

class ProcessedVideoTrack(VideoStreamTrack):

    def __init__(self, source):
        # Inicializa el track con el stream de video de entrada.
        super().__init__()
        self.source = source
        self.detection_interval = 0.8
        self.last_detection_enqueue = 0.0
        self.last_boxes = []
        self.pending_detection_frame = None
        self.smoothed_offset_ratio = 0.0
        self.closed = False
        self.detection_task = asyncio.create_task(self._detection_loop())

    def _extract_boxes(self, img):
        frame_height, frame_width = img.shape[:2]
        resize_scale = min(1.0, 384 / max(frame_width, frame_height))
        if resize_scale < 1.0:
            resized = cv2.resize(
                img,
                (max(1, int(frame_width * resize_scale)), max(1, int(frame_height * resize_scale))),
                interpolation=cv2.INTER_LINEAR
            )
        else:
            resized = img

        results = model.predict(
            resized,
            imgsz=320,
            conf=0.25,
            classes=[0],
            verbose=False
        )

        boxes = []
        if not results:
            return boxes

        raw_boxes = results[0].boxes
        if raw_boxes is None:
            return boxes

        for box in raw_boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            if resize_scale < 1.0:
                x1 /= resize_scale
                y1 /= resize_scale
                x2 /= resize_scale
                y2 /= resize_scale
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            boxes.append((int(x1), int(y1), int(x2), int(y2), conf))
        return boxes

    async def _detection_loop(self):
        try:
            while not self.closed:
                frame = self.pending_detection_frame
                self.pending_detection_frame = None
                if frame is None:
                    await asyncio.sleep(0.05)
                    continue

                try:
                    boxes = await asyncio.to_thread(self._extract_boxes, frame)
                    if boxes is not None:
                        self.last_boxes = boxes
                except Exception as e:
                    print("⚠️ Error procesando frame:", e)
        except asyncio.CancelledError:
            pass

    def _select_primary_box(self):
        if not self.last_boxes:
            return None
        return max(
            self.last_boxes,
            key=lambda box: max(1, (box[2] - box[0])) * max(1, (box[3] - box[1]))
        )

    def _build_tracking_payload(self, frame_width, frame_height):
        target = self._select_primary_box()
        now = time.time()

        if not target:
            self.smoothed_offset_ratio *= 0.65
            return {
                "ok": True,
                "status": "no-target",
                "direction": "center",
                "offsetPx": 0,
                "offsetRatio": 0.0,
                "offsetPercent": 0.0,
                "recommendedMoveM": 0.0,
                "estimatedDistanceM": 0.0,
                "frameWidth": int(frame_width),
                "frameHeight": int(frame_height),
                "targetBox": None,
                "timestamp": now
            }

        x1, y1, x2, y2, conf = target
        target_center_x = (x1 + x2) / 2
        frame_center_x = frame_width / 2
        raw_offset_px = target_center_x - frame_center_x
        raw_offset_ratio = raw_offset_px / max(1.0, frame_width / 2)
        self.smoothed_offset_ratio = (
            (self.smoothed_offset_ratio * 0.6) + (raw_offset_ratio * 0.4)
        )

        if abs(self.smoothed_offset_ratio) <= tracking_deadband_ratio:
            direction = "center"
        else:
            # Si la persona aparece a la derecha, el dron debe desplazarse a la izquierda
            # para recentrarla manteniendo la camara orientada al frente.
            direction = "left" if self.smoothed_offset_ratio > 0 else "right"

        box_width_px = max(1, x2 - x1)
        half_fov_rad = math.radians(camera_horizontal_fov_deg / 2)
        focal_length_px = frame_width / (2 * math.tan(half_fov_rad))
        estimated_distance_m = (reference_person_width_m * focal_length_px) / box_width_px
        angle_offset_rad = self.smoothed_offset_ratio * half_fov_rad
        recommended_move_m = abs(estimated_distance_m * math.tan(angle_offset_rad))

        return {
            "ok": True,
            "status": "tracking",
            "direction": direction,
            "offsetPx": int(round(raw_offset_px)),
            "offsetRatio": round(float(self.smoothed_offset_ratio), 4),
            "offsetPercent": round(abs(float(self.smoothed_offset_ratio)) * 100, 1),
            "recommendedMoveM": round(float(recommended_move_m), 2),
            "estimatedDistanceM": round(float(estimated_distance_m), 2),
            "frameWidth": int(frame_width),
            "frameHeight": int(frame_height),
            "targetBox": {
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2),
                "confidence": round(float(conf), 3)
            },
            "timestamp": now
        }

    async def recv(self):
        # Recibe frames, aplica deteccion de personas y actualiza snapshots.
        frame = await self.source.recv()

        try:
            while self.source._queue.qsize() > 0:
                frame = await self.source.recv()
        except Exception:
            pass

        img = frame.to_ndarray(format="bgr24")
        frame_height, frame_width = img.shape[:2]

        now = time.time()
        if (now - self.last_detection_enqueue) >= self.detection_interval:
            self.pending_detection_frame = img.copy()
            self.last_detection_enqueue = now

        if self.last_boxes:
            for x1, y1, x2, y2, conf in self.last_boxes:
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

        tracking_payload = self._build_tracking_payload(frame_width, frame_height)
        update_latest_tracking(tracking_payload)

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

    def stop(self):
        self.closed = True
        if self.detection_task and not self.detection_task.done():
            self.detection_task.cancel()
        self.detection_task = None
        super().stop()

async def offer(request):
    # Gestiona la oferta WebRTC y responde con el SDP de respuesta.
    params = await request.json()

    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"]
    )

    pc = RTCPeerConnection()

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

async def snapshot(request):
    # Devuelve el ultimo frame JPEG disponible.
    async with latest_lock:
        if latest_jpeg is None:
            return web.json_response({"error": "No hay frames aún"}, status=503)
        return web.Response(body=latest_jpeg, content_type="image/jpeg")


async def tracking(request):
    # Devuelve la correccion horizontal recomendada para centrar la persona.
    payload = dict(latest_tracking)

    stale_after_s = 1.5
    now = time.time()
    if payload.get("timestamp", 0) and (now - payload["timestamp"]) > stale_after_s:
        payload.update({
            "status": "stale",
            "direction": "center",
            "offsetPx": 0,
            "offsetRatio": 0.0,
            "offsetPercent": 0.0,
            "recommendedMoveM": 0.0,
            "estimatedDistanceM": 0.0,
            "targetBox": None
        })

    return web.json_response(payload)

async def cleanup(app):
    # Cierra conexiones WebRTC activas al apagar el servicio.
    for pc in pcs:
        await pc.close()
    pcs.clear()

app = web.Application()
app.router.add_post("/offer", offer)
app.router.add_get("/snapshot", snapshot)
app.router.add_get("/tracking", tracking)
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
