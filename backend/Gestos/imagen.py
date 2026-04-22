import cv2
import math
import numpy as np
import os
import time
import functools
from aiohttp import web
import aiohttp_cors
from ultralytics import YOLO
import asyncio
import glob
import yaml

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
calibration_file_env = "DRONE_CALIBRATION_YAML"
calibration_alpha = 0.0


async def run_in_worker_thread(func, *args, **kwargs):
    if hasattr(asyncio, "to_thread"):
        return await asyncio.to_thread(func, *args, **kwargs)

    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, call)


def resolve_calibration_file():
    explicit = os.environ.get(calibration_file_env, "").strip()
    if explicit:
        return explicit

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "calibration_data_px.yaml"),
        os.path.join(here, "output", "calibration_data_px.yaml"),
        os.path.join(here, "output21", "calibration_data_px.yaml"),
    ]
    candidates.extend(sorted(glob.glob(os.path.join(here, "output*", "calibration_data_px.yaml"))))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def parse_calibration_size(data):
    image_size = data.get("image_size")
    if isinstance(image_size, (list, tuple)) and len(image_size) == 2:
        width = int(image_size[0])
        height = int(image_size[1])
        if width > 0 and height > 0:
            return (width, height)

    frame_size = data.get("frame_size")
    if isinstance(frame_size, dict):
        width = int(frame_size.get("width", 0) or 0)
        height = int(frame_size.get("height", 0) or 0)
        if width > 0 and height > 0:
            return (width, height)

    image_width = int(data.get("image_width", 0) or 0)
    image_height = int(data.get("image_height", 0) or 0)
    if image_width > 0 and image_height > 0:
        return (image_width, image_height)

    return None


def detect_calibration_size_from_images():
    here = os.path.dirname(os.path.abspath(__file__))
    patterns = [
        os.path.join(here, "input*", "*.jpg"),
        os.path.join(here, "input*", "*.jpeg"),
        os.path.join(here, "input*", "*.png"),
    ]

    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            img = cv2.imread(candidate)
            if img is None:
                continue
            height, width = img.shape[:2]
            if width > 0 and height > 0:
                return (width, height)

    return None


def load_calibration():
    calibration_path = resolve_calibration_file()
    if not calibration_path:
        print("ℹ️ No se encontró YAML de calibración. El stream RTC se enviará sin corregir.")
        return None

    try:
        with open(calibration_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        camera_matrix = data.get("camera_matrix")
        distortion_coefficients = data.get("distortion_coefficients")
        if camera_matrix is None or distortion_coefficients is None:
            raise ValueError("Faltan camera_matrix o distortion_coefficients")

        calibration_size = parse_calibration_size(data) or detect_calibration_size_from_images()

        calibration = {
            "path": calibration_path,
            "camera_matrix": np.array(camera_matrix, dtype=np.float32),
            "distortion_coefficients": np.array(distortion_coefficients, dtype=np.float32),
            "image_size": calibration_size,
            "maps": {}
        }
        if calibration_size is not None:
            print(f"✅ Calibración cargada desde {calibration_path} para {calibration_size[0]}x{calibration_size[1]}")
        else:
            print(f"✅ Calibración cargada desde {calibration_path} sin tamaño de referencia; se usará el tamaño de entrada")
        return calibration
    except Exception as e:
        print(f"⚠️ No se pudo cargar la calibración desde {calibration_path}: {e}")
        return None


calibration_state = load_calibration()


def update_latest_tracking(payload):
    global latest_tracking
    latest_tracking = payload


def undistort_frame(img):
    if calibration_state is None:
        return img

    target_size = calibration_state.get("image_size")
    if target_size is not None:
        target_width, target_height = target_size
        if img.shape[1] != target_width or img.shape[0] != target_height:
            img = cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

    frame_height, frame_width = img.shape[:2]
    key = (frame_width, frame_height)
    maps = calibration_state["maps"].get(key)

    if maps is None:
        camera_matrix = calibration_state["camera_matrix"]
        distortion = calibration_state["distortion_coefficients"]
        optimal_matrix, _roi = cv2.getOptimalNewCameraMatrix(
            camera_matrix,
            distortion,
            (frame_width, frame_height),
            calibration_alpha,
            (frame_width, frame_height)
        )
        map_x, map_y = cv2.initUndistortRectifyMap(
            camera_matrix,
            distortion,
            None,
            optimal_matrix,
            (frame_width, frame_height),
            cv2.CV_32FC1
        )
        maps = (map_x, map_y)
        calibration_state["maps"][key] = maps

    map_x, map_y = maps
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

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
        self.primary_box = None
        self.closed = False
        self.detection_task = asyncio.create_task(self._detection_loop())

    @staticmethod
    def _box_area(box):
        return max(1, (box[2] - box[0])) * max(1, (box[3] - box[1]))

    @staticmethod
    def _box_center(box):
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    @staticmethod
    def _box_iou(box_a, box_b):
        x_left = max(box_a[0], box_b[0])
        y_top = max(box_a[1], box_b[1])
        x_right = min(box_a[2], box_b[2])
        y_bottom = min(box_a[3], box_b[3])

        inter_width = max(0.0, x_right - x_left)
        inter_height = max(0.0, y_bottom - y_top)
        intersection = inter_width * inter_height
        if intersection <= 0.0:
            return 0.0

        area_a = ProcessedVideoTrack._box_area(box_a)
        area_b = ProcessedVideoTrack._box_area(box_b)
        union = max(1.0, float(area_a + area_b - intersection))
        return float(intersection / union)

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
                    boxes = await run_in_worker_thread(self._extract_boxes, frame)
                    if boxes is not None:
                        self.last_boxes = boxes
                except Exception as e:
                    print("⚠️ Error procesando frame:", e)
        except asyncio.CancelledError:
            pass

    def _select_primary_box(self):
        if not self.last_boxes:
            self.primary_box = None
            return None

        largest_box = max(self.last_boxes, key=self._box_area)
        largest_area = float(self._box_area(largest_box))

        if self.primary_box is None:
            self.primary_box = largest_box
            return largest_box

        prev_box = self.primary_box
        prev_center_x, prev_center_y = self._box_center(prev_box)
        prev_span = max(1.0, float(max(prev_box[2] - prev_box[0], prev_box[3] - prev_box[1])))

        continuation_box = None
        continuation_score = -1.0

        for candidate in self.last_boxes:
            candidate_area = float(self._box_area(candidate))
            candidate_center_x, candidate_center_y = self._box_center(candidate)
            center_distance = math.hypot(candidate_center_x - prev_center_x, candidate_center_y - prev_center_y)
            center_ratio = center_distance / prev_span
            iou = self._box_iou(prev_box, candidate)

            # Mantiene la misma persona si la caja sigue cerca de la anterior.
            if iou < 0.1 and center_ratio > 0.7:
                continue

            score = (iou * 0.65) + (max(0.0, 1.0 - min(center_ratio, 1.5)) * 0.2) + ((candidate_area / largest_area) * 0.15)
            if score > continuation_score:
                continuation_score = score
                continuation_box = candidate

        if continuation_box is not None:
            continuation_area = float(self._box_area(continuation_box))
            if continuation_area >= (largest_area * 0.72):
                self.primary_box = continuation_box
                return continuation_box

        self.primary_box = largest_box
        return largest_box

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
        img = undistort_frame(img)
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
