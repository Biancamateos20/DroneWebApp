import cv2
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

pcs = set()


class ProcessedVideoTrack(VideoStreamTrack):
    """
    Recibe el track del navegador, procesa cada frame con OpenCV
    y lo devuelve como nuevo stream WebRTC
    """
    def __init__(self, source):
        super().__init__()
        self.source = source

    async def recv(self):
        frame = await self.source.recv()
        img = frame.to_ndarray(format="bgr24")

        # === PROCESADO OPENCV ===
        cv2.putText(
            img,
            "Drone WebRTC OK",
            (50, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        new_frame = VideoFrame.from_ndarray(img, format="bgr24")

        # 🔑 timestamps correctos (OBLIGATORIO)
        pts, time_base = await self.next_timestamp()
        new_frame.pts = pts
        new_frame.time_base = time_base

        return new_frame


async def offer(request):
    params = await request.json()

    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"]
    )

    # 🔑 CONFIGURACIÓN ICE CORRECTA (NO dict)
    pc = RTCPeerConnection(
        RTCConfiguration(
            iceServers=[
                RTCIceServer(urls="stun:stun.l.google.com:19302")
            ]
        )
    )

    pcs.add(pc)

    @pc.on("track")
    def on_track(track):
        print("Track recibido:", track.kind)
        if track.kind == "video":
            pc.addTrack(ProcessedVideoTrack(track))

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


async def cleanup(app):
    for pc in pcs:
        await pc.close()
    pcs.clear()


# === APP AIOHTTP ===
app = web.Application()
app.router.add_post("/offer", offer)
app.on_shutdown.append(cleanup)

# === CORS ===
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
