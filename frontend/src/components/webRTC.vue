<template>
  <div>
    <h2>Selector de Cámara</h2>

    <select v-model="selectedCameraId" @change="startStream">
      <option
        v-for="cam in cameras"
        :key="cam.deviceId"
        :value="cam.deviceId"
      >
        {{ cam.label || "Cámara sin nombre" }}
      </option>
    </select>

    <div style="display: flex; gap: 20px; margin-top: 20px;">
      <div>
        <h2>Cámara Local</h2>
        <video
          ref="localVideo"
          autoplay
          playsinline
          muted
          style="width: 320px; border: 2px solid white;"
        ></video>
      </div>

      <div>
        <h2>Vídeo Procesado (Backend)</h2>
        <video
          ref="remoteVideo"
          autoplay
          playsinline
          muted
          style="width: 320px; border: 2px solid green;"
        ></video>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";

const localVideo = ref(null);
const remoteVideo = ref(null);

const cameras = ref([]);
const selectedCameraId = ref(null);

let pc = null;
let localStream = null;

async function loadCameras() {
  try {
    const tempStream = await navigator.mediaDevices.getUserMedia({ video: true });
    tempStream.getTracks().forEach(t => t.stop());

    const devices = await navigator.mediaDevices.enumerateDevices();
    cameras.value = devices.filter(d => d.kind === "videoinput");

    console.log("Cámaras detectadas:", cameras.value);

    if (cameras.value.length > 0) {
      selectedCameraId.value = cameras.value[0].deviceId;
    }
  } catch (err) {
    console.error("Error cargando cámaras:", err);
  }
}

async function startStream() {
  cleanup();

  try {
    pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
    });

    pc.oniceconnectionstatechange = () => {
      console.log("ICE:", pc.iceConnectionState);
    };

    pc.ontrack = async (event) => {
      const stream = new MediaStream([event.track]);
      remoteVideo.value.srcObject = stream;
      await remoteVideo.value.play();
    };

    localStream = await navigator.mediaDevices.getUserMedia({
      video: selectedCameraId.value
        ? {
            deviceId: { exact: selectedCameraId.value },
            width: { ideal: 960, max: 960 },
            height: { ideal: 540, max: 540 },
            frameRate: { ideal: 24, max: 24 }
          }
        : {
            width: { ideal: 960, max: 960 },
            height: { ideal: 540, max: 540 },
            frameRate: { ideal: 24, max: 24 }
          },
      audio: false
    });

    localVideo.value.srcObject = localStream;

    localStream.getTracks().forEach(track => {
      if ("contentHint" in track) {
        track.contentHint = "motion";
      }
      const sender = pc.addTrack(track, localStream);
      applySenderQualityProfile(sender);
    });

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    await waitForIceGathering(pc);

    const offerUrl = (process.env.VUE_APP_WEBRTC_TARGET
      ? `${process.env.VUE_APP_WEBRTC_TARGET.replace(/\/$/, "")}/offer`
      : "/webrtc/offer")

    const response = await fetch(offerUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type
      })
    });

    const answer = await response.json();
    await pc.setRemoteDescription(answer);

  } catch (err) {
    console.error("Error iniciando stream:", err);
  }
}

// ===============================
// Helpers
// ===============================
function cleanup() {
  if (localStream) {
    localStream.getTracks().forEach(t => t.stop());
    localStream = null;
  }

  if (pc) {
    pc.close();
    pc = null;
  }
}

function applySenderQualityProfile(sender) {
  if (!sender || typeof sender.getParameters !== "function" || typeof sender.setParameters !== "function") {
    return;
  }

  try {
    const params = sender.getParameters() || {};
    if (!Array.isArray(params.encodings) || !params.encodings.length) {
      params.encodings = [{}];
    }
    params.encodings[0] = {
      ...params.encodings[0],
      maxBitrate: 2500000,
      maxFramerate: 24,
      scaleResolutionDownBy: 1
    };
    sender.setParameters(params).catch?.(() => {});
  } catch (err) {
    console.warn("No se pudieron aplicar parametros RTC de calidad:", err);
  }
}

function waitForIceGathering(pc) {
  return new Promise(resolve => {
    if (pc.iceGatheringState === "complete") return resolve();

    pc.onicegatheringstatechange = () => {
      if (pc.iceGatheringState === "complete") resolve();
    };
  });
}

// ===============================
// Lifecycle
// ===============================
onMounted(async () => {
  await loadCameras();
  if (selectedCameraId.value) {
    await startStream();
  }

  navigator.mediaDevices.ondevicechange = async () => {
    console.log("Cambio de dispositivos detectado");
    await loadCameras();
  };
});

onBeforeUnmount(() => {
  cleanup();
});
</script>

<style scoped>
select {
  padding: 6px;
  font-size: 14px;
  margin-bottom: 10px;
}
</style>
