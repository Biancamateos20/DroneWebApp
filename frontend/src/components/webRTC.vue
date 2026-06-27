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
            ref="remoteFrameImage"
            :src="remoteFrameUrl"
            class="camera-video remote-video"
            alt="Imagen procesada del admin"
            @load="handleRemoteFrameLoad"
          />
          <canvas
            v-if="remoteFrameUrl"
            ref="remoteFrameCanvas"
            class="remote-overlay"
          ></canvas>
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
      <p v-else-if="isChallengeBlocking" class="turn-note">
        Completa el reto del emoji para desbloquear el siguiente color.
      </p>
      <p v-else class="turn-note">
        Ahora mismo decide {{ normalizedActivePlayerAlias || 'otro participante' }}.
      </p>

      <p v-if="isCurrentPlayer && !canPickNextPlayer && !isChallengeBlocking" class="turn-note">
        Cuando el dron termine el GOTO hasta tu posición, podrás decir el siguiente color.
      </p>

      <article v-if="showChallengePanel" class="challenge-panel">
        <div class="challenge-copy">
          <p class="challenge-label">Reto de simulación</p>
          <p v-if="challengeStage === 'countdown'" class="challenge-title">
            Empieza en {{ challengeCountdown }}
          </p>
          <p v-else-if="challengeStage === 'active'" class="challenge-title">
            Haz {{ challengePromptEmoji }} durante {{ challengeSecondsLeft }} s
          </p>
          <p v-else-if="challengeStage === 'success'" class="challenge-title">
            Emoji correcto
          </p>
          <p v-else-if="challengeStage === 'shooting'" class="challenge-title">
            Lanzando foto
          </p>
          <p v-else-if="challengeStage === 'failed'" class="challenge-title">
            Tiempo agotado
          </p>
          <p v-else-if="challengeStage === 'error'" class="challenge-title">
            Reto no disponible
          </p>
          <p class="challenge-text">
            {{ challengeMessage }}
          </p>
          <div v-if="challengePromptEmoji" class="challenge-emoji">
            {{ challengePromptEmoji }}
          </div>
          <p v-if="challengePromptText" class="challenge-text">
            Emoji objetivo: {{ challengePromptText }}
          </p>
          <p v-if="challengeDetectedText" class="challenge-text">
            Gesto detectado: {{ challengeDetectedText }}
          </p>
          <p v-if="challengeCameraHint" class="challenge-text">
            {{ challengeCameraHint }}
          </p>
          <p v-if="challengeError" class="error challenge-error">{{ challengeError }}</p>
        </div>

        <div class="challenge-media">
          <div class="challenge-status-card">
            <p class="challenge-label">Fuente analizada</p>
            <p class="challenge-text">
              Se analiza la <strong>Vista del admin</strong> que ves arriba.
            </p>
            <p class="challenge-text">
              Haz el gesto delante de esa cámara para que MediaPipe lo vea.
            </p>
          </div>

          <div v-if="challengePhotoUrl" class="challenge-photo-wrap">
            <p class="challenge-label">Foto automática</p>
            <img :src="challengePhotoUrl" alt="Foto del reto" class="challenge-photo" />
          </div>
        </div>
      </article>

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
  simulationPlayers: {
    type: Array,
    default: () => []
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
  gotoCompletedAlias: {
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
const remoteFrameImage = ref(null)
const remoteFrameCanvas = ref(null)
const voiceError = ref("");
const voiceListening = ref(false);
const voiceLoading = ref(false);
const voiceTranscript = ref("");
const voiceResultAlias = ref(null);
const challengeStage = ref("idle")
const challengeCountdown = ref(3)
const challengeSecondsLeft = ref(10)
const challengePromptType = ref("")
const challengePromptEmoji = ref("")
const challengePromptText = ref("")
const challengeMessage = ref("")
const challengeError = ref("")
const challengePhotoUrl = ref(null)
const challengeDetectedText = ref("")
const challengeCameraHint = ref("")

let cameraSnapshotTimer = null;
let cameraSnapshotPending = false;
let playersPollTimer = null;
let speechRecognition = null;
let challengeCountdownTimer = null
let challengeWindowTimer = null
let challengeHands = null
let challengeDetectionPending = false
let challengeStableMatches = 0
let remoteHandLandmarks = null

const handConnections = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17]
]

const challengePrompts = [
  { type: "victory", emoji: "✌️", text: "V de victoria" },
  { type: "point", emoji: "☝️", text: "Índice arriba" },
  { type: "open", emoji: "🖐️", text: "Mano abierta" }
]

const hasSimulationPlayers = computed(() => {
  return Array.isArray(props.simulationPlayers) && props.simulationPlayers.length > 0
})

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

const normalizedGotoCompletedAlias = computed(() => {
  if (!props.gotoCompletedAlias) return null
  return String(props.gotoCompletedAlias).trim().toUpperCase() || null
})

const isCurrentPlayer = computed(() => {
  return !!normalizedUserAlias.value && normalizedUserAlias.value === normalizedActivePlayerAlias.value
})

const baseCanPickNextPlayer = computed(() => {
  return !!props.droneInAir &&
    isCurrentPlayer.value &&
    normalizedGotoCompletedAlias.value === normalizedUserAlias.value
})

const challengeResolved = computed(() => {
  return challengeStage.value === "success" ||
    challengeStage.value === "failed" ||
    challengeStage.value === "error"
})

const isChallengeTurn = computed(() => {
  return hasSimulationPlayers.value &&
    baseCanPickNextPlayer.value
})

const isChallengeBlocking = computed(() => {
  return isChallengeTurn.value && !challengeResolved.value
})

const showChallengePanel = computed(() => {
  return hasSimulationPlayers.value && (isChallengeTurn.value || challengeStage.value !== "idle")
})

const canPickNextPlayer = computed(() => {
  if (!baseCanPickNextPlayer.value) return false
  if (!hasSimulationPlayers.value) return true
  return challengeResolved.value
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

function stopChallengeTimers() {
  if (challengeCountdownTimer) {
    window.clearInterval(challengeCountdownTimer)
  }
  if (challengeWindowTimer) {
    window.clearInterval(challengeWindowTimer)
  }
  challengeCountdownTimer = null
  challengeWindowTimer = null
}

function clearRemoteHandOverlay() {
  try {
    const canvas = remoteFrameCanvas.value
    if (!canvas) return

    const context = canvas.getContext("2d")
    if (!context) return
    context.clearRect(0, 0, canvas.width, canvas.height)
  } catch (err) {
    console.error("[webRTC] Error limpiando overlay de mano:", err)
  }
}

function resizeRemoteHandOverlay() {
  try {
    const image = remoteFrameImage.value
    const canvas = remoteFrameCanvas.value
    if (!image || !canvas) return false

    const width = Math.max(1, Math.round(image.clientWidth || image.width || 0))
    const height = Math.max(1, Math.round(image.clientHeight || image.height || 0))
    if (!width || !height) return false

    if (canvas.width !== width) canvas.width = width
    if (canvas.height !== height) canvas.height = height
    return true
  } catch (err) {
    console.error("[webRTC] Error ajustando overlay de mano:", err)
    return false
  }
}

function drawRemoteHandOverlay() {
  try {
    const canvas = remoteFrameCanvas.value
    if (!canvas) return

    if (!resizeRemoteHandOverlay()) {
      clearRemoteHandOverlay()
      return
    }

    const context = canvas.getContext("2d")
    if (!context) return

    context.clearRect(0, 0, canvas.width, canvas.height)
    if (!Array.isArray(remoteHandLandmarks) || !remoteHandLandmarks.length) return

    context.lineWidth = 3
    context.strokeStyle = "#55f56a"
    context.fillStyle = "#7dd3fc"

    handConnections.forEach(([startIndex, endIndex]) => {
      const startPoint = remoteHandLandmarks[startIndex]
      const endPoint = remoteHandLandmarks[endIndex]
      if (!startPoint || !endPoint) return

      context.beginPath()
      context.moveTo(startPoint.x * canvas.width, startPoint.y * canvas.height)
      context.lineTo(endPoint.x * canvas.width, endPoint.y * canvas.height)
      context.stroke()
    })

    remoteHandLandmarks.forEach((point, index) => {
      const radius = index === 8 || index === 12 || index === 16 || index === 20 ? 6 : 4
      context.beginPath()
      context.arc(point.x * canvas.width, point.y * canvas.height, radius, 0, Math.PI * 2)
      context.fill()
    })
  } catch (err) {
    console.error("[webRTC] Error dibujando overlay de mano:", err)
  }
}

function clearChallengePhoto() {
  if (challengePhotoUrl.value) {
    URL.revokeObjectURL(challengePhotoUrl.value)
  }
  challengePhotoUrl.value = null
}

function resetChallengeState() {
  stopChallengeTimers()
  challengeDetectionPending = false
  challengeStableMatches = 0
  remoteHandLandmarks = null
  challengeStage.value = "idle"
  challengeCountdown.value = 3
  challengeSecondsLeft.value = 10
  challengePromptType.value = ""
  challengePromptEmoji.value = ""
  challengePromptText.value = ""
  challengeMessage.value = ""
  challengeError.value = ""
  challengeDetectedText.value = ""
  challengeCameraHint.value = ""
  clearChallengePhoto()
  clearRemoteHandOverlay()
}

function selectChallengePrompt() {
  const index = Math.floor(Math.random() * challengePrompts.length)
  const selected = challengePrompts[index]
  challengePromptType.value = selected.type
  challengePromptEmoji.value = selected.emoji
  challengePromptText.value = selected.text
}

function handleChallengeResults(results) {
  try {
    if (challengeStage.value !== "active") return

    const landmarks = results?.multiHandLandmarks?.[0]
    if (!landmarks) {
      challengeStableMatches = 0
      remoteHandLandmarks = null
      challengeDetectedText.value = ""
      challengeCameraHint.value = "No veo la mano en la vista del admin."
      drawRemoteHandOverlay()
      return
    }

    remoteHandLandmarks = landmarks
    drawRemoteHandOverlay()

    const detection = detectChallengeGesture(landmarks)
    const detected = detection.gesture

    challengeDetectedText.value = detected ? getChallengeGestureLabel(detected) : ""
    challengeCameraHint.value = detection.hint

    if (!detected || detected !== challengePromptType.value) {
      challengeStableMatches = 0
      return
    }

    challengeStableMatches += 1
    if (challengeStableMatches < 3) return

    handleChallengeSuccess()
  } catch (err) {
    console.error("[webRTC] Error procesando gesto:", err)
  }
}

function getChallengeGestureLabel(type) {
  if (type === "victory") return "V de victoria"
  if (type === "point") return "Índice arriba"
  if (type === "open") return "Mano abierta"
  return ""
}

function getLandmarkDistance(pointA, pointB) {
  if (!pointA || !pointB) return 0

  const deltaX = Number(pointA.x || 0) - Number(pointB.x || 0)
  const deltaY = Number(pointA.y || 0) - Number(pointB.y || 0)
  return Math.hypot(deltaX, deltaY)
}

function getPalmCenter(wrist, indexMcp, middleMcp, ringMcp, pinkyMcp) {
  try {
    return {
      x: (
        Number(wrist?.x || 0) +
        Number(indexMcp?.x || 0) +
        Number(middleMcp?.x || 0) +
        Number(ringMcp?.x || 0) +
        Number(pinkyMcp?.x || 0)
      ) / 5,
      y: (
        Number(wrist?.y || 0) +
        Number(indexMcp?.y || 0) +
        Number(middleMcp?.y || 0) +
        Number(ringMcp?.y || 0) +
        Number(pinkyMcp?.y || 0)
      ) / 5
    }
  } catch (err) {
    console.error("[webRTC] Error calculando centro de palma:", err)
    return { x: 0, y: 0 }
  }
}

function isFingerExtended(tip, pip, mcp, palmCenter) {
  try {
    const tipToPalm = getLandmarkDistance(tip, palmCenter)
    const pipToPalm = getLandmarkDistance(pip, palmCenter)
    const tipToMcp = getLandmarkDistance(tip, mcp)
    const pipToMcp = getLandmarkDistance(pip, mcp)

    return tipToPalm > pipToPalm * 1.22 &&
      tipToMcp > pipToMcp * 1.55
  } catch (err) {
    console.error("[webRTC] Error comprobando dedo extendido:", err)
    return false
  }
}

function isFingerCurled(tip, pip, mcp, palmCenter, palmSize) {
  try {
    const tipToPalm = getLandmarkDistance(tip, palmCenter)
    const pipToPalm = getLandmarkDistance(pip, palmCenter)
    const tipToMcp = getLandmarkDistance(tip, mcp)
    const pipToMcp = getLandmarkDistance(pip, mcp)

    return tipToPalm < pipToPalm * 1.1 &&
      tipToMcp < pipToMcp * 1.18 &&
      tipToPalm < palmSize * 1.55
  } catch (err) {
    console.error("[webRTC] Error comprobando dedo curvado:", err)
    return false
  }
}

function detectChallengeGesture(landmarks) {
  try {
    const widthValues = landmarks.map((point) => Number(point?.x || 0))
    const heightValues = landmarks.map((point) => Number(point?.y || 0))
    const handWidth = Math.max(...widthValues) - Math.min(...widthValues)
    const handHeight = Math.max(...heightValues) - Math.min(...heightValues)
    const handCenterX = (Math.max(...widthValues) + Math.min(...widthValues)) / 2
    const handCenterY = (Math.max(...heightValues) + Math.min(...heightValues)) / 2

    if (handWidth > 0.62 || handHeight > 0.62) {
      return {
        gesture: "",
        hint: "Aleja la mano un poco de la cámara del admin."
      }
    }

    if (handWidth < 0.08 || handHeight < 0.08) {
      return {
        gesture: "",
        hint: "Acerca la mano a la cámara del admin o hazla más grande en pantalla."
      }
    }

    if (Math.abs(handCenterX - 0.5) > 0.28 || Math.abs(handCenterY - 0.5) > 0.28) {
      return {
        gesture: "",
        hint: "Centra mejor la mano dentro de la vista del admin."
      }
    }

    const wrist = landmarks[0]
    const thumbTip = landmarks[4]
    const thumbMcp = landmarks[2]
    const indexMcp = landmarks[5]
    const indexPip = landmarks[6]
    const indexTip = landmarks[8]
    const middleMcp = landmarks[9]
    const middlePip = landmarks[10]
    const middleTip = landmarks[12]
    const ringMcp = landmarks[13]
    const ringPip = landmarks[14]
    const ringTip = landmarks[16]
    const pinkyMcp = landmarks[17]
    const pinkyPip = landmarks[18]
    const pinkyTip = landmarks[20]
    const palmCenter = getPalmCenter(wrist, indexMcp, middleMcp, ringMcp, pinkyMcp)

    const palmSize = (
      getLandmarkDistance(wrist, indexMcp) +
      getLandmarkDistance(wrist, middleMcp) +
      getLandmarkDistance(wrist, ringMcp) +
      getLandmarkDistance(wrist, pinkyMcp)
    ) / 4

    if (palmSize < 0.04) {
      return {
        gesture: "",
        hint: "La mano sale demasiado pequeña en la vista del admin."
      }
    }

    const indexUp = isFingerExtended(indexTip, indexPip, indexMcp, palmCenter)
    const middleUp = isFingerExtended(middleTip, middlePip, middleMcp, palmCenter)
    const ringUp = isFingerExtended(ringTip, ringPip, ringMcp, palmCenter)
    const pinkyUp = isFingerExtended(pinkyTip, pinkyPip, pinkyMcp, palmCenter)

    const indexCurled = isFingerCurled(indexTip, indexPip, indexMcp, palmCenter, palmSize)
    const middleCurled = isFingerCurled(middleTip, middlePip, middleMcp, palmCenter, palmSize)
    const ringCurled = isFingerCurled(ringTip, ringPip, ringMcp, palmCenter, palmSize)
    const pinkyCurled = isFingerCurled(pinkyTip, pinkyPip, pinkyMcp, palmCenter, palmSize)

    const thumbCompact = getLandmarkDistance(thumbTip, palmCenter) < palmSize * 1.45 &&
      getLandmarkDistance(thumbTip, thumbMcp) < palmSize * 1.2

    const fingerSeparation = getLandmarkDistance(indexTip, middleTip)
    const indexToPalm = getLandmarkDistance(indexTip, palmCenter)
    const middleToPalm = getLandmarkDistance(middleTip, palmCenter)
    const ringToPalm = getLandmarkDistance(ringTip, palmCenter)
    const pinkyToPalm = getLandmarkDistance(pinkyTip, palmCenter)

    if (indexUp && middleUp && ringUp && pinkyUp &&
      indexToPalm > palmSize * 1.95 &&
      middleToPalm > palmSize * 2 &&
      ringToPalm > palmSize * 1.85 &&
      pinkyToPalm > palmSize * 1.7) {
      return {
        gesture: "open",
        hint: "Perfecto, mantén la mano así."
      }
    }

    if (indexUp && middleUp && ringCurled && pinkyCurled &&
      indexToPalm > palmSize * 1.9 &&
      middleToPalm > palmSize * 1.95 &&
      ringToPalm < palmSize * 1.5 &&
      pinkyToPalm < palmSize * 1.45 &&
      fingerSeparation > palmSize * 0.6) {
      return {
        gesture: "victory",
        hint: "Perfecto, mantén la mano así."
      }
    }

    if (indexUp && middleCurled && ringCurled && pinkyCurled &&
      indexToPalm > palmSize * 1.95 &&
      middleToPalm < palmSize * 1.55 &&
      ringToPalm < palmSize * 1.5 &&
      pinkyToPalm < palmSize * 1.45) {
      return {
        gesture: "point",
        hint: "Perfecto, mantén la mano así."
      }
    }

    if (indexCurled && middleCurled && ringCurled && pinkyCurled && thumbCompact) {
      return {
        gesture: "",
        hint: "Abre un poco la mano. Cerrada del todo da muchos fallos."
      }
    }

    return {
      gesture: "",
      hint: "No reconozco el gesto todavía en la vista del admin."
    }
  } catch (err) {
    console.error("[webRTC] Error detectando gesto del reto:", err)
    return {
      gesture: "",
      hint: "Error leyendo la mano."
    }
  }
}

async function ensureChallengeHands() {
  try {
    if (challengeHands) return

    if (!window.Hands) {
      throw new Error("MediaPipe Hands no está cargado")
    }

    challengeHands = new window.Hands({
      locateFile(file) {
        return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
      }
    })

    challengeHands.setOptions({
      maxNumHands: 1,
      modelComplexity: 0,
      minDetectionConfidence: 0.45,
      minTrackingConfidence: 0.45
    })

    challengeHands.onResults(handleChallengeResults)
    console.log("[webRTC] MediaPipe Hands listo para el reto")
  } catch (err) {
    console.error("[webRTC] Error preparando MediaPipe Hands:", err)
    throw err
  }
}

async function processChallengeFrame() {
  try {
    if (challengeStage.value !== "active") return
    if (!challengeHands || !remoteFrameImage.value) return
    if (!remoteFrameImage.value.complete) return
    if (challengeDetectionPending) return

    challengeDetectionPending = true
    await challengeHands.send({
      image: remoteFrameImage.value
    })
  } catch (err) {
    console.error("[webRTC] Error enviando frame a MediaPipe:", err)
  } finally {
    challengeDetectionPending = false
  }
}

function handleChallengeFailure() {
  try {
    if (challengeStage.value !== "active") return
    stopChallengeTimers()
    challengeStage.value = "failed"
    challengeMessage.value = "No pasa nada. Ahora puedes mandar el dron al siguiente usuario."
    challengeError.value = ""
    console.log("[webRTC] Reto fallado por tiempo")
  } catch (err) {
    console.error("[webRTC] Error cerrando reto fallido:", err)
  }
}

async function saveChallengePhotoState() {
  try {
    const response = await fetch("/api/estado-juego", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        foto_tomada_alias: normalizedUserAlias.value
      })
    })

    if (!response.ok) {
      throw new Error("No se pudo guardar la foto del reto")
    }
  } catch (err) {
    console.error("[webRTC] Error guardando estado de foto:", err)
    throw err
  }
}

async function handleChallengeSuccess() {
  try {
    if (challengeStage.value !== "active") return

    stopChallengeTimers()
    challengeStage.value = "shooting"
    challengeMessage.value = "Emoji correcto. Lanzando foto automática..."
    challengeError.value = ""
    console.log("[webRTC] Reto superado, lanzando foto")

    const response = await fetch("/api/foto", {
      method: "POST",
      cache: "no-store"
    })

    if (!response.ok) {
      throw new Error("No se pudo lanzar la foto automática")
    }

    const blob = await response.blob()
    clearChallengePhoto()
    challengePhotoUrl.value = URL.createObjectURL(blob)
    await saveChallengePhotoState()
    challengeStage.value = "success"
    challengeMessage.value = "Emoji correcto. Foto tomada. Ya puedes elegir el siguiente color."
  } catch (err) {
    challengeStage.value = "error"
    challengeMessage.value = "El gesto ha sido correcto, pero la foto no se ha podido tomar."
    challengeError.value = err?.message || "No se pudo completar la foto del reto"
    console.error("[webRTC] Error en la foto automática del reto:", err)
  }
}

function handleChallengeWindowTick() {
  if (!isChallengeTurn.value) {
    resetChallengeState()
    return
  }

  if (challengeSecondsLeft.value <= 1) {
    handleChallengeFailure()
    return
  }

  challengeSecondsLeft.value -= 1
}

function startChallengeWindow() {
  stopChallengeTimers()
  challengeStableMatches = 0
  challengeStage.value = "active"
  challengeSecondsLeft.value = 10
  challengeMessage.value = "Tienes 10 segundos para hacer el emoji correctamente."
  challengeCameraHint.value = "Haz el gesto delante de la cámara del admin y procura que se vea la mano entera."
  challengeWindowTimer = window.setInterval(() => {
    handleChallengeWindowTick()
  }, 1000)
}

function handleChallengeCountdownTick() {
  if (!isChallengeTurn.value) {
    resetChallengeState()
    return
  }

  if (challengeCountdown.value <= 1) {
    startChallengeWindow()
    return
  }

  challengeCountdown.value -= 1
}

function startChallengeCountdown() {
  stopChallengeTimers()
  challengeStage.value = "countdown"
  challengeCountdown.value = 3
  challengeSecondsLeft.value = 10
  challengeMessage.value = "Prepárate. El reto empieza en 3 segundos."
  challengeCountdownTimer = window.setInterval(() => {
    handleChallengeCountdownTick()
  }, 1000)
}

async function startGestureChallenge() {
  try {
    if (!isChallengeTurn.value) return
    if (!hasSimulationPlayers.value) return
    if (challengeStage.value !== "idle") return

    clearChallengePhoto()
    challengeStableMatches = 0
    challengeError.value = ""
    challengeDetectedText.value = ""
    challengeCameraHint.value = ""
    selectChallengePrompt()
    challengeStage.value = "countdown"
    challengeMessage.value = "Preparando cámara y detección del reto..."
    console.log("[webRTC] Iniciando reto de simulación para", normalizedUserAlias.value)

    await ensureChallengeHands()

    if (!isChallengeTurn.value) {
      resetChallengeState()
      return
    }

    startChallengeCountdown()
  } catch (err) {
    challengeStage.value = "error"
    challengeMessage.value = "No se ha podido iniciar el reto, pero puedes seguir jugando."
    challengeError.value = err?.message || "No se pudo preparar la detección del reto"
    stopChallengeTimers()
    console.error("[webRTC] Error iniciando reto:", err)
  }
}

function handleRemoteFrameLoad() {
  resizeRemoteHandOverlay()
  drawRemoteHandOverlay()
  if (challengeStage.value !== "active") return
  processChallengeFrame()
}

async function loadPlayers() {
  if (hasSimulationPlayers.value) {
    players.value = props.simulationPlayers
      .map((player) => {
        const alias = String(player?.alias || "").trim().toUpperCase()
        return {
          alias,
          lat: player?.lat,
          lon: player?.lon,
          ts: player?.ts || Date.now()
        }
      })
      .filter((player) => !!player.alias)
    return
  }

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
  if (hasSimulationPlayers.value) {
    loadPlayers()
    return
  }
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
    const availableAliases = availablePlayers.value.map((player) => player.alias)
    const response = await fetch("/api/voz-color", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        texto: transcript,
        current_alias: normalizedUserAlias.value,
        available_aliases: availableAliases
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
  remoteHandLandmarks = null
  clearRemoteHandOverlay()
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
      remoteHandLandmarks = null
      clearRemoteHandOverlay()
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
  resetChallengeState()
})

watch(
  () => props.selectedNextPlayerAlias,
  () => {
    pickPendingAlias.value = null
    voiceLoading.value = false
  }
)

watch(
  () => props.simulationPlayers,
  () => {
    if (!hasSimulationPlayers.value) return
    loadPlayers()
  },
  { deep: true }
)

watch(
  [
    () => props.droneInAir,
    () => normalizedActivePlayerAlias.value,
    () => normalizedGotoCompletedAlias.value,
    () => normalizedUserAlias.value
  ],
  () => {
    if (!hasSimulationPlayers.value) {
      resetChallengeState()
      return
    }

    if (isChallengeTurn.value) {
      startGestureChallenge()
      return
    }

    resetChallengeState()
  },
  { immediate: true }
)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Rajdhani:wght@500;600&display=swap');

.webrtc-shell {
  min-height: 100vh;
  min-height: 100svh;
  position: relative;
  overflow-x: hidden;
  overflow-y: visible;
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
  position: relative;
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
  transform: scaleX(-1);
  image-rendering: auto;
}

.remote-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  transform: scaleX(-1);
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

.challenge-panel {
  margin: 16px 0;
  padding: 18px;
  border-radius: 18px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 360px);
  gap: 18px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  background:
    radial-gradient(circle at top left, rgba(22, 163, 74, 0.12), transparent 38%),
    rgba(9, 13, 21, 0.82);
}

.challenge-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.challenge-label {
  margin: 0;
  font-family: 'Rajdhani', sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(125, 211, 252, 0.84);
}

.challenge-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: #eef1f6;
}

.challenge-text {
  margin: 0;
  color: rgba(240, 244, 250, 0.72);
  font-size: 0.94rem;
}

.challenge-emoji {
  font-size: clamp(3rem, 7vw, 4.4rem);
  line-height: 1;
}

.challenge-media {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.challenge-status-card {
  min-height: 220px;
  padding: 18px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(circle at top, rgba(125, 211, 252, 0.1), transparent 55%),
    #05070d;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
}

.challenge-photo-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.challenge-photo {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: #000;
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

.challenge-error {
  margin-top: 0;
}

@media (max-width: 980px) {
  .webrtc-header {
    flex-direction: column;
    align-items: stretch;
  }

  .challenge-panel {
    grid-template-columns: 1fr;
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

  .challenge-panel {
    padding: 14px;
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
