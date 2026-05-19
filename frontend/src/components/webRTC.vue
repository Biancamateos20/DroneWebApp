<template>
  <div class="webrtc-shell">
    <div class="bg">
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
      <span class="orb orb-c"></span>
      <div class="grid"></div>
    </div>

    <header class="webrtc-header">
      <div>
        <p class="eyebrow">Drone Mission Control</p>
        <h2 class="title">Vision RTC</h2>
        <p class="subtitle">Imagen procesada compartida desde el panel de admin</p>
      </div>
    </header>

    <section class="video-grid">
      <article class="video-card remote-card">
        <h3 class="video-title">Vista del admin</h3>
        <div class="video-frame remote-frame">
          <img
            v-if="remoteFrameUrl"
            :src="remoteFrameUrl"
            class="camera-video remote-video"
            alt="Imagen procesada del admin"
          />
          <div v-else class="video-placeholder">
            Esperando a que el admin active la cámara.
          </div>
        </div>
      </article>
    </section>

    <p v-if="cameraError" class="error">{{ cameraError }}</p>

    <section class="turn-panel">
      <h3>Siguiente color</h3>
      <p v-if="!droneInAir" class="turn-note">
        El dron todavía no está despegado.
      </p>
      <p v-else-if="canPickNextPlayer" class="turn-note">
        Elige a qué color deberá ir el dron después de ti.
      </p>
      <p v-else class="turn-note">
        Ahora mismo decide {{ normalizedActivePlayerAlias || 'otro participante' }}.
      </p>

      <p v-if="isCurrentPlayer && !canPickNextPlayer" class="turn-note">
        Cuando el dron llegue y te hagan la foto, podrás decir el siguiente color.
      </p>

      <p v-if="selectedNextPlayerAlias" class="turn-selected">
        Siguiente color elegido: {{ selectedNextPlayerName || selectedNextPlayerAlias }}
      </p>

      <div class="voice-panel">
        <button
          type="button"
          class="voice-button"
          :disabled="!canPickNextPlayer || voiceListening || voiceLoading"
          @click="startVoiceSelection"
        >
          {{ voiceButtonText }}
        </button>

        <p v-if="voiceTranscript" class="voice-transcript">
          Has dicho: {{ voiceTranscript }}
        </p>

        <p v-if="voiceResultLabel" class="voice-result">
          Color detectado: {{ voiceResultLabel }}
        </p>
        <p v-if="voiceError" class="error voice-error">{{ voiceError }}</p>
      </div>

      <p v-if="availablePlayers.length" class="turn-note">
        Participantes registrados: {{ availablePlayers.length }}
      </p>

      <div v-if="availablePlayers.length" class="turn-colors">
        <button
          v-for="player in availablePlayers"
          :key="player.alias"
          type="button"
          class="turn-color"
          :class="{
            selected: normalizedSelectedNextPlayerAlias === player.alias,
            readonly: !canPickNextPlayer
          }"
          :disabled="!canPickNextPlayer || pickPendingAlias === player.alias"
          @click="pickNextPlayer(player.alias)"
        >
          <span class="turn-color-main">
            <span class="turn-color-dot" :style="{ backgroundColor: player.alias }"></span>
            <span class="turn-color-name">{{ player.name }}</span>
          </span>
          <span class="turn-color-status">{{ player.status }}</span>
        </button>
      </div>

      <p v-if="availablePlayers.length === 0" class="turn-note">
        No hay otro color disponible todavía.
      </p>

      <p v-if="pickError" class="error">{{ pickError }}</p>
    </section>
  </div>
</template>

<script setup>
/* global defineProps, defineEmits */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  userAlias: {
    type: String,
    default: null
  },
  droneInAir: {
    type: Boolean,
    default: false
  },
  activePlayerAlias: {
    type: String,
    default: null
  },
  selectedNextPlayerAlias: {
    type: String,
    default: null
  },
  photoTakenAlias: {
    type: String,
    default: null
  }
})

const emit = defineEmits(["pick-next-player"])

const players = ref([]);
const cameraError = ref("");
const pickError = ref("");
const pickPendingAlias = ref(null);
const remoteFrameUrl = ref(null);
const voiceError = ref("");
const voiceListening = ref(false);
const voiceLoading = ref(false);
const voiceTranscript = ref("");
const voiceResultAlias = ref(null);

let cameraSnapshotTimer = null;
let cameraSnapshotPending = false;
let playersPollTimer = null;
let speechRecognition = null;

const normalizedUserAlias = computed(() => {
  if (!props.userAlias) return null
  return String(props.userAlias).trim().toUpperCase() || null
})

const normalizedActivePlayerAlias = computed(() => {
  if (!props.activePlayerAlias) return null
  return String(props.activePlayerAlias).trim().toUpperCase() || null
})

const normalizedSelectedNextPlayerAlias = computed(() => {
  if (!props.selectedNextPlayerAlias) return null
  return String(props.selectedNextPlayerAlias).trim().toUpperCase() || null
})

const normalizedPhotoTakenAlias = computed(() => {
  if (!props.photoTakenAlias) return null
  return String(props.photoTakenAlias).trim().toUpperCase() || null
})

const isCurrentPlayer = computed(() => {
  return !!normalizedUserAlias.value && normalizedUserAlias.value === normalizedActivePlayerAlias.value
})

const canPickNextPlayer = computed(() => {
  return !!props.droneInAir &&
    isCurrentPlayer.value &&
    normalizedPhotoTakenAlias.value === normalizedUserAlias.value
})

const availablePlayers = computed(() => {
  const currentAlias = normalizedUserAlias.value

  return players.value
    .filter((player) => {
      const alias = String(player?.alias || "").trim().toUpperCase()
      return !!alias && alias !== currentAlias
    })
    .map((player) => {
      const hasCoordinates = Number.isFinite(Number(player?.lat)) && Number.isFinite(Number(player?.lon))
      const hasRecentTs = Number.isFinite(Number(player?.ts)) && (Date.now() - Number(player.ts)) < 15000
      let status = "Registrado"

      if (hasRecentTs) {
        status = "Activo"
      } else if (hasCoordinates) {
        status = "Ubicado"
      }

      return {
        alias: String(player.alias).trim().toUpperCase(),
        name: getColorLabel(player.alias),
        status
      }
    })
    .sort((a, b) => String(a.alias).localeCompare(String(b.alias)))
})

const selectedNextPlayerName = computed(() => {
  if (!normalizedSelectedNextPlayerAlias.value) return null
  return getColorLabel(normalizedSelectedNextPlayerAlias.value)
})

const voiceResultLabel = computed(() => {
  if (!voiceResultAlias.value) return ""
  return getColorLabel(voiceResultAlias.value)
})

const voiceButtonText = computed(() => {
  if (voiceLoading.value) return "Procesando voz..."
  if (voiceListening.value) return "Escuchando..."
  return "Decir color"
})

async function loadPlayers() {
  try {
    const response = await fetch("/api/jugadores", { cache: "no-store" })
    if (!response.ok) return

    const data = await response.json()
    if (!Array.isArray(data)) return

    players.value = data
      .map((player) => {
        const alias = String(player?.alias || "").trim().toUpperCase()
        return {
          alias,
          lat: player?.lat,
          lon: player?.lon,
          ts: player?.ts
        }
      })
      .filter((player) => !!player.alias)
  } catch (err) {
    console.warn("Error cargando jugadores:", err)
  }
}

function startPlayersPolling() {
  stopPlayersPolling()
  playersPollTimer = window.setInterval(() => {
    loadPlayers()
  }, 2000)
}

function stopPlayersPolling() {
  if (playersPollTimer) {
    window.clearInterval(playersPollTimer)
  }
  playersPollTimer = null
}

function pickNextPlayer(alias) {
  const normalizedAlias = String(alias || "").trim().toUpperCase()
  if (!canPickNextPlayer.value || !normalizedAlias) {
    pickError.value = "Ahora mismo no te toca elegir."
    return
  }

  pickError.value = ""
  pickPendingAlias.value = normalizedAlias
  emit("pick-next-player", normalizedAlias)
}

function getColorLabel(alias) {
  const normalizedAlias = String(alias || "").trim().toUpperCase()
  if (normalizedAlias === "#1E90FF") return "Azul"
  if (normalizedAlias === "#FF0000") return "Rojo"
  if (normalizedAlias === "#32CD32") return "Verde"
  if (normalizedAlias === "#FFD700") return "Amarillo"
  if (normalizedAlias === "#800080") return "Morado"
  if (normalizedAlias === "#FF1493") return "Rosa"
  if (normalizedAlias === "#00CED1") return "Turquesa"
  if (normalizedAlias === "#FF8C00") return "Naranja"
  return normalizedAlias
}

function getSpeechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

function stopVoiceRecognition() {
  if (!speechRecognition) return
  try {
    speechRecognition.onstart = null
    speechRecognition.onresult = null
    speechRecognition.onerror = null
    speechRecognition.onend = null
    speechRecognition.stop()
  } catch (err) {
    console.warn("Error parando reconocimiento de voz:", err)
  }
  speechRecognition = null
}

function handleVoiceStart() {
  voiceListening.value = true
  voiceError.value = ""
}

function handleVoiceError(event) {
  voiceListening.value = false
  voiceLoading.value = false
  voiceError.value = event?.error ? `Error de voz: ${event.error}` : "No se pudo escuchar el color"
}

function handleVoiceEnd() {
  voiceListening.value = false
  speechRecognition = null
}

async function handleVoiceResult(event) {
  const transcript = String(event?.results?.[0]?.[0]?.transcript || "").trim()
  voiceTranscript.value = transcript
  voiceListening.value = false
  if (!transcript) {
    voiceError.value = "No se ha entendido el color"
    return
  }
  await submitVoiceColor(transcript)
}

function startVoiceSelection() {
  pickError.value = ""
  voiceError.value = ""
  voiceTranscript.value = ""
  voiceResultAlias.value = null

  if (!canPickNextPlayer.value) {
    voiceError.value = "Todavia no puedes mandar el dron por voz."
    return
  }

  const RecognitionCtor = getSpeechRecognitionCtor()
  if (!RecognitionCtor) {
    voiceError.value = "Este navegador no soporta reconocimiento de voz."
    return
  }

  stopVoiceRecognition()
  speechRecognition = new RecognitionCtor()
  speechRecognition.lang = "es-ES"
  speechRecognition.interimResults = false
  speechRecognition.maxAlternatives = 1
  speechRecognition.onstart = handleVoiceStart
  speechRecognition.onresult = handleVoiceResult
  speechRecognition.onerror = handleVoiceError
  speechRecognition.onend = handleVoiceEnd
  speechRecognition.start()
}

async function submitVoiceColor(transcript) {
  voiceLoading.value = true

  try {
    const response = await fetch("/api/voz-color", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        texto: transcript,
        current_alias: normalizedUserAlias.value
      })
    })

    const data = await response.json().catch(() => ({}))
    if (!response.ok || !data?.ok) {
      throw new Error(data?.error || "No se ha reconocido un color valido")
    }

    voiceResultAlias.value = data.alias
    pickPendingAlias.value = data.alias
    emit("pick-next-player", data.alias)
  } catch (err) {
    voiceError.value = err?.message || "No se ha podido procesar la voz"
  } finally {
    voiceLoading.value = false
  }
}

function startCameraSnapshotPolling() {
  stopCameraSnapshotPolling()
  console.log("[webRTC] Iniciando lectura de imagen compartida del admin")
  refreshRemoteSnapshot()
  cameraSnapshotTimer = window.setInterval(() => {
    refreshRemoteSnapshot()
  }, 250)
}

function stopCameraSnapshotPolling() {
  if (cameraSnapshotTimer) {
    window.clearInterval(cameraSnapshotTimer)
  }
  cameraSnapshotTimer = null
  cameraSnapshotPending = false
}

function cleanupCameraView() {
  stopCameraSnapshotPolling()
  if (remoteFrameUrl.value) {
    URL.revokeObjectURL(remoteFrameUrl.value)
    remoteFrameUrl.value = null
  }
}

async function refreshRemoteSnapshot() {
  if (cameraSnapshotPending) {
    return
  }

  cameraSnapshotPending = true

  try {
    const response = await fetch(getWebRtcUrl("/snapshot"), {
      method: "GET",
      cache: "no-store"
    })

    if (!response.ok) {
      if (remoteFrameUrl.value) {
        URL.revokeObjectURL(remoteFrameUrl.value)
        remoteFrameUrl.value = null
      }
      cameraError.value = ""
      return
    }

    const blob = await response.blob()
    const nextUrl = URL.createObjectURL(blob)

    if (remoteFrameUrl.value) {
      URL.revokeObjectURL(remoteFrameUrl.value)
    }

    remoteFrameUrl.value = nextUrl
    cameraError.value = ""
  } catch (err) {
    cameraError.value = err?.message || "No se pudo cargar la imagen del admin"
    console.error("[webRTC] Error cargando imagen compartida:", err)
  } finally {
    cameraSnapshotPending = false
  }
}

function getWebRtcBaseUrl() {
  let configured = String(process.env.VUE_APP_WEBRTC_TARGET || "").trim().replace(/\/$/, "")

  try {
    const isHttpsPage = window.location.protocol === "https:"
    const isHttpBase = configured.startsWith("http://")
    const isLocalBase = /^(http:\/\/|https:\/\/)?(localhost|127\.0\.0\.1)/i.test(configured)
    const isLocalPage = /^(localhost|127\.0\.0\.1)$/i.test(window.location.hostname)

    if ((isHttpsPage && isHttpBase) || (isLocalBase && !isLocalPage)) {
      configured = ""
    }
  } catch (err) {
    console.warn("Error revisando URL RTC:", err)
  }

  return configured || "/webrtc"
}

function getWebRtcUrl(path) {
  const normalizedPath = String(path || "").startsWith("/") ? path : `/${path}`
  return `${getWebRtcBaseUrl()}${normalizedPath}`
}
onMounted(async () => {
  await loadPlayers()
  startPlayersPolling()
  startCameraSnapshotPolling()
})

onBeforeUnmount(() => {
  stopPlayersPolling()
  stopVoiceRecognition()
  cleanupCameraView()
})

watch(
  () => props.selectedNextPlayerAlias,
  () => {
    pickPendingAlias.value = null
    voiceLoading.value = false
  }
)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Rajdhani:wght@500;600&display=swap');

.webrtc-shell {
  min-height: 100vh;
  min-height: 100dvh;
  position: relative;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  color: #eef1f6;
  font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
  width: 100%;
  margin: 0;
  padding: 28px 4vw 32px;
  box-sizing: border-box;
  isolation: isolate;
}

.bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: -1;
}

.grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(transparent 94%, rgba(255, 255, 255, 0.04) 100%),
    linear-gradient(90deg, transparent 94%, rgba(255, 255, 255, 0.04) 100%);
  background-size: 36px 36px;
  opacity: 0.4;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(30px);
  opacity: 0.7;
}

.orb-a {
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(0, 224, 255, 0.28), transparent 70%);
  top: -120px;
  left: -120px;
}

.orb-b {
  width: 520px;
  height: 520px;
  background: radial-gradient(circle, rgba(255, 131, 77, 0.2), transparent 70%);
  bottom: -180px;
  right: -160px;
}

.orb-c {
  width: 280px;
  height: 280px;
  background: radial-gradient(circle, rgba(111, 255, 167, 0.16), transparent 70%);
  top: 26%;
  right: 10%;
}

.webrtc-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}

.eyebrow {
  font-family: 'Rajdhani', sans-serif;
  text-transform: uppercase;
  letter-spacing: 2px;
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.7);
  margin: 0 0 8px;
}

.title {
  margin: 0;
  font-size: clamp(2rem, 3vw, 3rem);
  line-height: 1.05;
}

.subtitle {
  margin: 6px 0 0;
  color: rgba(240, 244, 250, 0.72);
  font-size: 1rem;
}

.video-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 22px;
  align-items: stretch;
}

.video-card {
  padding: 24px;
  border-radius: 22px;
  background: rgba(6, 9, 15, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(10px);
}

.remote-card {
  border-color: rgba(125, 211, 252, 0.22);
}

.video-title {
  margin: 0 0 12px;
  font-family: 'Rajdhani', sans-serif;
  font-size: 1.02rem;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: rgba(240, 244, 250, 0.9);
}

.video-frame {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 16px;
  overflow: hidden;
  background: #05070d;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.remote-frame {
  border-color: rgba(73, 200, 255, 0.4);
  box-shadow: inset 0 0 0 1px rgba(73, 200, 255, 0.08);
}

.camera-video {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  background: #000;
}

.remote-video {
  image-rendering: auto;
}

.video-placeholder {
  width: 100%;
  height: 100%;
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  text-align: center;
  color: rgba(240, 244, 250, 0.68);
  font-size: 0.95rem;
  background:
    radial-gradient(circle at top, rgba(125, 211, 252, 0.12), transparent 55%),
    #05070d;
}

.turn-panel {
  margin-top: 24px;
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  width: 100%;
  max-width: 100%;
  background: rgba(6, 9, 15, 0.78);
  box-sizing: border-box;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(10px);
}

.turn-panel h3 {
  margin: 0 0 10px;
  font-family: 'Rajdhani', sans-serif;
  font-size: 1.08rem;
  letter-spacing: 0.8px;
  text-transform: uppercase;
}

.turn-note {
  margin: 8px 0;
  color: rgba(240, 244, 250, 0.68);
  font-size: 0.95rem;
}

.turn-selected {
  margin: 10px 0 14px;
  color: #7dd3fc;
  font-weight: 600;
}

.voice-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 14px 0 16px;
}

.voice-button {
  min-width: 0;
  width: fit-content;
  padding: 11px 16px;
  font-size: 0.9rem;
  font-weight: 600;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  letter-spacing: 0.5px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
  background: linear-gradient(135deg, #ffc36b, #ff9c59);
  color: #411f00;
}

.voice-button:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.3);
  box-shadow: 0 18px 30px rgba(0, 0, 0, 0.3);
}

.voice-button:disabled {
  opacity: 0.55;
  cursor: default;
}

.voice-transcript,
.voice-result {
  margin: 0;
  font-size: 0.92rem;
  color: rgba(240, 244, 250, 0.72);
}

.voice-result {
  color: #7dd3fc;
  font-weight: 600;
}

.turn-colors {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.turn-color {
  min-width: 160px;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  color: #eef1f6;
  font-weight: 700;
  cursor: pointer;
  background: rgba(10, 14, 22, 0.65);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  text-align: left;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
  backdrop-filter: blur(8px);
}

.turn-color-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.turn-color-dot {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.92);
  flex: 0 0 auto;
  box-shadow: 0 0 18px rgba(255, 255, 255, 0.12);
}

.turn-color-name {
  letter-spacing: 0.02em;
  word-break: break-word;
}

.turn-color-status {
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(240, 244, 250, 0.62);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.turn-color.selected {
  border-color: rgba(255, 255, 255, 0.28);
  background: rgba(16, 24, 38, 0.88);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
}

.turn-color:not(:disabled):hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.28);
  box-shadow: 0 18px 30px rgba(0, 0, 0, 0.3);
}

.turn-color.readonly {
  cursor: default;
}

.turn-color:disabled {
  opacity: 0.55;
  cursor: default;
}

.error {
  margin: 14px 0 0;
  color: #fda4af;
  font-size: 0.9rem;
}

.voice-error {
  margin-top: 0;
}

@media (max-width: 980px) {
  .webrtc-header {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 640px) {
  .webrtc-shell {
    padding: 18px 0 24px;
    padding-left: 5vw;
    padding-right: 5vw;
  }

  .title {
    font-size: 1.75rem;
  }

  .subtitle {
    font-size: 0.95rem;
  }

  .video-grid {
    gap: 14px;
  }

  .video-card {
    padding: 16px;
    border-radius: 18px;
  }

  .video-frame {
    border-radius: 12px;
  }

  .turn-panel {
    margin-top: 18px;
    padding: 16px;
  }

  .voice-button {
    width: 100%;
  }

  .turn-colors {
    gap: 10px;
  }

  .turn-color {
    flex: 1 1 calc(50% - 10px);
    min-width: 0;
    padding: 12px 10px;
    font-size: 0.92rem;
  }

  .turn-color-status {
    font-size: 0.75rem;
  }
}

@media (max-width: 420px) {
  .webrtc-shell {
    padding-top: 10px;
    padding-left: 16px;
    padding-right: 16px;
  }

  .video-card {
    padding: 10px;
  }

  .turn-panel {
    padding: 12px;
  }

  .turn-color {
    flex-basis: 100%;
  }
}
</style>
