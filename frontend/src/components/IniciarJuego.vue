<template>
  <div class="admin-container" :class="{ 'camera-on': cameraActive }">
    <h1 class="title">Panel de Control</h1>
    <p class="subtitle">Administrador de la partida</p>

    <div id="map" class="map"></div>

    <div class="control-grid">
      <section class="panel">
        <h3>Operación</h3>
        <p class="panel-sub">Gestión de la partida y misión</p>

        <div class="panel-actions">
          <button class="btn start" @click="iniciarJuego" :disabled="loading">
            ▶ Iniciar juego
          </button>

          <button class="btn stop" @click="pararJuego">
            ■ Parar juego
          </button>
        </div>
      </section>

      <section class="panel lab">
        <h3>Laboratorio</h3>
        <p class="panel-sub">Pruebas rápidas de dron y geolocalización</p>

        <div class="row">
          <label class="field">
            <span>Modo</span>
            <select v-model="droneMode">
              <option value="Simulacion">Simulación</option>
              <option value="Real">Real</option>
            </select>
          </label>

          <div class="status-wrap">
            <div class="status">
              <span class="dot" :class="{ on: droneConnected }"></span>
              {{ droneConnected ? 'Dron conectado' : 'Dron desconectado' }}
            </div>
            <div class="status small">
              <span class="dot" :class="{ on: mqttConnected }"></span>
              {{ mqttConnected ? 'MQTT conectado' : 'MQTT desconectado' }}
            </div>
          </div>
        </div>
        <p v-if="telemetryAltDisplay !== null" class="mini-note">
          Altitud telemetría: {{ telemetryAltDisplay.toFixed(3) }} m
          <span v-if="telemetryAltitudeTrendText">· {{ telemetryAltitudeTrendText }}</span>
          <span v-if="lastDroneState">· {{ lastDroneState }}</span>
          <span v-if="telemetryLat !== null && telemetryLon !== null">
            · Dron: {{ telemetryLat.toFixed(6) }}, {{ telemetryLon.toFixed(6) }}
          </span>
        </p>
        <p class="mini-note">
          MQTT broker: {{ mqttBrokerUrl }}
          <span v-if="mqttDebugLastTopic">· último topic: {{ mqttDebugLastTopic }}</span>
        </p>

        <div class="lab-grid">
          <div class="lab-group">
            <div class="lab-title">Dron</div>
            <label class="mini-field">
              <span>Altura despegue (m)</span>
              <input v-model.number="takeoffAlt" type="number" min="1" max="120" step="1" />
            </label>
            <div class="panel-actions lab-actions">
              <button class="btn neutral" @click="connectDrone" :disabled="connectLoading">
                {{ droneConnected ? 'Desconectar' : 'Conectar dron' }}
              </button>
              <button
                class="btn"
                :class="droneInAir ? 'danger' : 'takeoff'"
                @click="toggleTakeoffLand"
                :disabled="landLoading || !droneConnected"
              >
                {{ droneInAir ? '⬇ Land' : '🚀 Despegar' }}
              </button>
              <button
                class="btn goto"
                @click="gotoAdmin"
                :disabled="gotoLoading || !droneConnected || !droneInAir || !adminPos"
                title="Ir a la ubicación del administrador"
              >
                🧭 Ir al admin
              </button>
            </div>
          </div>

          <div class="lab-group">
            <div class="lab-title">Cámara</div>
            <div class="panel-actions lab-actions">
              <button class="btn cam" @click="toggleCamera" :disabled="cameraLoading">
                {{ cameraActive ? '⏹ Cerrar cámara' : '🎥 Activar cámara' }}
              </button>
              <button class="btn photo" @click="hacerFoto" :disabled="photoLoading">
                📸 Foto
              </button>
            </div>
            <p v-if="cameraActive" class="mini-note">Vista de cámara activa</p>
          </div>

          <div class="lab-group">
            <div class="lab-title">Ubicación</div>
            <div class="panel-actions lab-actions">
              <button class="btn info" @click="checkGpsPrecision" :disabled="gpsLoading">
                📍 Ver precisión GPS
              </button>
              <button v-if="!geofenceMode" class="btn geofence" @click="startGeofenceEdit">
                🛡️ Editar geofence
              </button>
              <button v-else class="btn geofence" @click="stopGeofenceEdit">
                ✅ Cerrar edición geofence
              </button>
            </div>
            <div v-if="geofenceMode" class="panel-actions lab-actions">
              <button class="btn neutral" @click="clearGeofence" :disabled="!geofencePoints.length">
                🧹 Limpiar geofence
              </button>
              <button
                class="btn save"
                @click="saveGeofence"
                :disabled="geofencePoints.length < 3 || !geofenceDirty"
              >
                💾 Guardar geofence
              </button>
            </div>
            <p v-if="geofenceMode || geofencePoints.length" class="mini-note">
              Geofence: {{ geofencePoints.length }} puntos
              <span v-if="geofencePoints.length >= 3">· polígono activo</span>
              <span v-else>· añade al menos 3 puntos en el mapa</span>
              <span v-if="geofenceDirty">· cambios sin guardar</span>
            </p>
            <p v-if="geofenceNotice" class="mini-note">{{ geofenceNotice }}</p>
            <p v-if="geofenceError" class="mini-error">{{ geofenceError }}</p>
          </div>

          <div class="lab-group">
            <div class="lab-title">Modo objetivo</div>

            <label class="mini-field">
              <span>Parada antes del geofence (m)</span>
              <input
                v-model.number="geofenceStopDistance"
                type="number"
                min="0"
                max="200"
                step="0.5"
                @change="sanitizeGeofenceStopDistance"
              />
            </label>
            <p v-if="canApplyGeofenceStopDistance" class="mini-note">
              El mapa marca en vivo la parada prevista antes del geofence para el admin y el jugador seleccionado.
            </p>

            <div v-if="registeredPlayers.length" class="player-list">
              <button
                v-for="player in registeredPlayers"
                :key="player.alias"
                type="button"
                class="player-item"
                :class="{ selected: selectedPlayerAlias === player.alias }"
                @click="selectPlayer(player.alias)"
              >
                <span class="player-dot" :style="{ backgroundColor: getPlayerColor(player.alias) }"></span>
                <span class="player-name">{{ player.alias }}</span>
                <span class="player-state" :class="{ offline: player.offline }">
                  {{ player.offline ? 'sin señal' : 'activo' }}
                </span>
              </button>
            </div>
            <div class="panel-actions lab-actions">
              <button
                class="btn goto-user"
                @click="gotoSelectedPlayer"
                :disabled="gotoPlayerLoading || !droneConnected || !droneInAir || !selectedPlayer"
                title="Enviar dron al jugador seleccionado"
              >
                🎯 Ir al jugador
              </button>
            </div>

            <p v-if="selectedPlayer" class="mini-note">
              Objetivo: {{ selectedPlayer.alias }} ·
              {{ selectedPlayer.lat.toFixed(6) }}, {{ selectedPlayer.lon.toFixed(6) }}
            </p>
          </div>
        </div>

        <div class="gps-box" v-if="gpsAccuracy != null || adminPos">
          <div>
            Precisión actual: <strong>{{ gpsAccuracy }} m</strong>
            <span v-if="gpsTimestamp">· {{ gpsTimestamp }}</span>
          </div>
          <div v-if="adminPos" class="gps-coords">
            Admin: {{ adminPos.lat.toFixed(6) }}, {{ adminPos.lon.toFixed(6) }}
          </div>
        </div>
      </section>
    </div>

    <section v-if="cameraActive" class="camera-bay" :class="cameraZoomClass">
      <div class="camera-controls">
        <label class="mini-field">
          <span>Selecciona cámara</span>
          <select v-model="selectedCameraId" @change="startStream">
            <option v-for="cam in cameras" :key="cam.deviceId" :value="cam.deviceId">
              {{ cam.label || 'Cámara sin nombre' }}
            </option>
          </select>
        </label>

        <div class="camera-toolbar">
          <button class="btn tiny" @click="setCameraZoom('none')">Ver ambas</button>
          <button class="btn tiny" @click="setCameraZoom('local')">Max Local</button>
          <button class="btn tiny" @click="setCameraZoom('remote')">Max Procesado</button>
        </div>

        <p v-if="cameraError" class="mini-error">{{ cameraError }}</p>
      </div>

      <div class="camera-stage">
        <div class="tracking-panel">
          <div class="tracking-head">
            <span class="tracking-label">Corrección horizontal</span>
            <strong :class="cameraTrackingDirectionClass">{{ cameraTrackingHeadline }}</strong>
          </div>
          <div class="tracking-bar" aria-label="Corrección horizontal">
            <span class="tracking-center-line"></span>
            <span class="tracking-safe-zone"></span>
            <span class="tracking-marker" :style="cameraTrackingMarkerStyle"></span>
          </div>
          <p class="tracking-meta">{{ cameraTrackingDetail }}</p>
        </div>

        <div class="camera-grid">
          <div class="camera-card local">
            <div class="camera-title">Local</div>
            <video ref="localVideo" autoplay playsinline muted></video>
          </div>
          <div class="camera-card remote">
            <div class="camera-title">Procesado</div>
            <video ref="remoteVideo" autoplay playsinline muted></video>
          </div>
        </div>
      </div>
    </section>

    <p v-if="loading" class="subtitle">Lanzando misión…</p>
    <p v-if="photoLoading" class="subtitle">Capturando foto…</p>
    <p v-if="landLoading" class="subtitle">Enviando LAND…</p>
    <p v-if="connectLoading" class="subtitle">Conectando dron…</p>
    <p v-if="cameraLoading" class="subtitle">Activando cámara…</p>
    <p v-if="gpsLoading" class="subtitle">Consultando precisión…</p>
    <p v-if="gotoLoading" class="subtitle">Enviando GOTO…</p>
    <p v-if="gotoPlayerLoading" class="subtitle">Enviando GOTO al jugador…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="photoError" class="error">{{ photoError }}</p>
    <p v-if="landError" class="error">{{ landError }}</p>
    <p v-if="gpsError" class="error">{{ gpsError }}</p>
    <p v-if="gotoError" class="error">{{ gotoError }}</p>
    <p v-if="gotoPlayerError" class="error">{{ gotoPlayerError }}</p>

    <div v-if="photoUrl" class="photo-panel">
      <h3>Última foto <span v-if="photoSource" class="photo-source">({{ photoSource }})</span></h3>
      <img :src="photoUrl" alt="Foto dron" />
    </div>
  </div>
</template>

<script>
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { LiveWS } from '../services/liveWS'

export default {
  name: 'IniciarJuego',

  data() {
    return {
      map: null,
      error: null,
      loading: false,
      mapReady: false,
      markers: {},

      layerEsri: null,
      layerPnoaProvWms: null,

      live: null,
      wsReady: false,
      pollTimer: null,
      mqttClient: null,
      mqttConnected: false,
      mqttBrokerUrl: (process.env.VUE_APP_MQTT_BROKER_URL || 'ws://broker.hivemq.com:8000/mqtt').trim(),
      mqttSubTopic: (process.env.VUE_APP_MQTT_SUB_TOPIC || 'demoDash/mobileFlask/#').trim(),
      mqttTelemetryTopic: (process.env.VUE_APP_MQTT_TOPIC_TELEMETRY || 'demoDash/mobileFlask/telemetryInfo').trim(),
      mqttGeofencePointsTopic: (process.env.VUE_APP_MQTT_TOPIC_GEOFENCE_POINTS || 'mobileFlask/demoDash/geofencePoints').trim(),
      mqttDebugLastTopic: null,
      mqttDebugLastPayload: null,
      mqttTopics: {
        connect: (process.env.VUE_APP_MQTT_TOPIC_CONNECT || 'mobileFlask/demoDash/connect').trim(),
        disconnect: (process.env.VUE_APP_MQTT_TOPIC_DISCONNECT || 'mobileFlask/demoDash/disconnection').trim(),
        takeoff: (process.env.VUE_APP_MQTT_TOPIC_TAKEOFF || 'mobileFlask/demoDash/arm_takeOff').trim(),
        land: (process.env.VUE_APP_MQTT_TOPIC_LAND || 'mobileFlask/demoDash/Land').trim(),
        goto: (process.env.VUE_APP_MQTT_TOPIC_GOTO || 'mobileFlask/demoDash/GoTo').trim(),
        geofence: (process.env.VUE_APP_MQTT_TOPIC_GEOFENCE || 'mobileFlask/demoDash/setGeofence').trim()
      },
      telemetryAlt: null,
      telemetryAltDisplay: null,
      telemetryLat: null,
      telemetryLon: null,
      telemetryHeading: null,
      telemetryVerticalSpeed: null,
      droneAltTrend: 'stable',
      lastTelemetryTs: null,
      altitudeAnimation: null,
      lastDroneState: null,
      dronePos: null,
      droneMarker: null,
      droneAcc: null,
      droneAnimation: null,

      photoUrl: null,
      photoLoading: false,
      photoError: null,
      photoSource: null,
      landLoading: false,
      landError: null,

      droneMode: 'Simulacion',
      droneConnected: false,
      connectLoading: false,
      droneInAir: false,
      takeoffAlt: 5,

      cameraActive: false,
      cameraLoading: false,
      cameraError: null,
      cameras: [],
      selectedCameraId: null,
      cameraZoom: 'none',
      pc: null,
      localStream: null,
      cameraTracking: null,
      cameraTrackingTimer: null,
      cameraTrackingPending: false,

      gpsAccuracy: null,
      gpsTimestamp: null,
      gpsLoading: false,
      gpsError: null,
      adminPos: null,
      adminMarker: null,
      adminAcc: null,
      adminCentered: false,
      gotoLoading: false,
      gotoError: null,

      geofenceMode: false,
      geofencePoints: [],
      geofencePointMarkers: [],
      geofencePreviewLine: null,
      geofencePolygon: null,
      geofenceMask: null,
      stopPreviewLayers: {},
      geofenceDirty: false,
      geofenceNotice: null,
      geofenceError: null,
      geofencePendingFromMqtt: null,

      playersByAlias: {},
      playerAnimations: {},
      selectedPlayerAlias: null,
      geofenceStopDistance: 5,
      gotoPlayerLoading: false,
      gotoPlayerError: null
    }
  },

  computed: {
    cameraZoomClass() {
      return this.cameraZoom === 'local'
        ? 'zoom-local'
        : this.cameraZoom === 'remote'
          ? 'zoom-remote'
          : 'zoom-none'
    },
    cameraTrackingNormalizedOffset() {
      const value = Number(this.cameraTracking?.offsetRatio)
      if (!Number.isFinite(value)) return 0
      return Math.max(-1, Math.min(1, value))
    },
    cameraTrackingHeadline() {
      const status = this.cameraTracking?.status
      const direction = this.cameraTracking?.direction
      const meters = Number(this.cameraTracking?.recommendedMoveM || 0)

      if (status === 'tracking' && direction === 'left') {
        return `Mover a la izquierda ${meters.toFixed(2)} m`
      }
      if (status === 'tracking' && direction === 'right') {
        return `Mover a la derecha ${meters.toFixed(2)} m`
      }
      if (status === 'tracking' && direction === 'center') {
        return 'Objetivo centrado'
      }
      if (status === 'stale') {
        return 'Esperando frames recientes'
      }
      return 'Sin persona detectada'
    },
    cameraTrackingDetail() {
      const tracking = this.cameraTracking
      if (!tracking || tracking.status !== 'tracking') {
        return 'La guía se actualizará cuando el detector vea una persona.'
      }

      return `Corrección lateral estimada ${Number(tracking.recommendedMoveM || 0).toFixed(2)} m · persona a ${Number(tracking.estimatedDistanceM || 0).toFixed(2)} m`
    },
    cameraTrackingDirectionClass() {
      const direction = this.cameraTracking?.direction
      if (direction === 'left') return 'tracking-left'
      if (direction === 'right') return 'tracking-right'
      return 'tracking-center'
    },
    cameraTrackingMarkerStyle() {
      const left = 50 + (this.cameraTrackingNormalizedOffset * 44)
      return { left: `${Math.max(6, Math.min(94, left))}%` }
    },
    registeredPlayers() {
      return Object.values(this.playersByAlias)
        .filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon))
        .sort((a, b) => String(a.alias).localeCompare(String(b.alias)))
    },
    selectedPlayer() {
      if (!this.selectedPlayerAlias) return null
      return this.playersByAlias[this.selectedPlayerAlias] || null
    },
    telemetryAltitudeTrendText() {
      if (!Number.isFinite(this.telemetryAltDisplay) || !this.droneAltTrend) return ''
      const vs = Number(this.telemetryVerticalSpeed)
      const speedText = Number.isFinite(vs) ? ` (${vs > 0 ? '+' : ''}${vs.toFixed(2)} m/s)` : ''
      if (this.droneAltTrend === 'up') return `Subiendo${speedText}`
      if (this.droneAltTrend === 'down') return `Bajando${speedText}`
      return `Altitud estable${speedText}`
    },
    canApplyGeofenceStopDistance() {
      return this.geofencePoints.length >= 3
    },
    sanitizedGeofenceStopDistance() {
      const value = Number(this.geofenceStopDistance)
      if (!Number.isFinite(value)) return 0
      return Math.max(0, value)
    }
  },

  watch: {
    mapReady() {
      this.refreshAllStopPreviews()
    },
    geofenceStopDistance() {
      this.refreshAllStopPreviews()
    },
    geofencePoints: {
      handler() {
        this.refreshAllStopPreviews()
      },
      deep: true
    },
    dronePos: {
      handler() {
        this.refreshAllStopPreviews()
      },
      deep: true
    },
    adminPos: {
      handler() {
        this.refreshAllStopPreviews()
      },
      deep: true
    },
    selectedPlayerAlias() {
      this.refreshAllStopPreviews()
    },
    selectedPlayer: {
      handler() {
        this.refreshAllStopPreviews()
      },
      deep: true
    }
  },

  mounted() {
    this.initMap()
    this.initWS()
    this.startPollingFallback()
    this.initMqtt()

    if (navigator.mediaDevices) {
      this.deviceChangeHandler = async () => {
        if (!this.cameraActive) return
        await this.loadCameras()
        await this.startStream()
      }
      navigator.mediaDevices.ondevicechange = this.deviceChangeHandler
    }
  },

    beforeUnmount() {
    if (this.photoUrl) URL.revokeObjectURL(this.photoUrl)
    this.cleanupCamera()
    if (navigator.mediaDevices && navigator.mediaDevices.ondevicechange === this.deviceChangeHandler) {
      navigator.mediaDevices.ondevicechange = null
    }
    this.disconnectMqtt()
    this.live?.disconnect()
    this.stopPollingFallback()
    this.setGeofenceMode(false)
    this.clearGeofence(true)
    this.clearMarkers()
    this.clearDroneLocation()
    if (this.map) {
      this.map.remove()
      this.map = null
    }
  },

  methods: {
    setCameraZoom(mode) {
      this.cameraZoom = mode
    },
    getWebRtcBaseUrl() {
      const configured = String(process.env.VUE_APP_WEBRTC_TARGET || '').trim().replace(/\/$/, '')
      return configured || '/webrtc'
    },
    getWebRtcUrl(path) {
      const normalizedPath = String(path || '').startsWith('/') ? path : `/${path}`
      return `${this.getWebRtcBaseUrl()}${normalizedPath}`
    },
    initMqtt() {
      const mqttLib = typeof window !== 'undefined' ? window.mqtt : null
      if (!mqttLib) {
        this.error = 'No se encontró la librería MQTT en el navegador'
        return
      }

      this.disconnectMqtt()
      try {
        this.mqttClient = mqttLib.connect(this.mqttBrokerUrl)
      } catch (e) {
        this.error = e.message || 'No se pudo crear el cliente MQTT'
        return
      }

      this.mqttClient.on('connect', () => {
        this.mqttConnected = true
        this.subscribeToMqttTopics()
      })

      this.mqttClient.on('message', (topic, message) => {
        this.handleMqttMessage(topic, message)
      })

      this.mqttClient.on('close', () => {
        this.mqttConnected = false
      })

      this.mqttClient.on('error', (err) => {
        console.warn('Error MQTT:', err)
        this.mqttConnected = false
      })
    },

    disconnectMqtt() {
      if (this.mqttClient) {
        try {
          this.mqttClient.end(true)
        } catch (e) {
          console.warn('Error cerrando MQTT:', e)
        }
      }
      this.mqttClient = null
      this.mqttConnected = false
    },

    normalizeMqttTopic(topic) {
      return String(topic || '')
        .trim()
        .replace(/^\/+|\/+$/g, '')
        .replace(/\/+/g, '/')
    },

    topicToWildcard(topic) {
      const normalized = this.normalizeMqttTopic(topic)
      if (!normalized || normalized.includes('#') || normalized.includes('+')) return normalized
      const idx = normalized.lastIndexOf('/')
      if (idx <= 0) return normalized
      return `${normalized.slice(0, idx)}/#`
    },

    getMqttSubscriptionTopics() {
      const topics = [
        this.mqttSubTopic,
        this.mqttTelemetryTopic,
        this.topicToWildcard(this.mqttTelemetryTopic),
        this.mqttGeofencePointsTopic,
        this.topicToWildcard(this.mqttGeofencePointsTopic)
      ]

      return [...new Set(topics.map(topic => this.normalizeMqttTopic(topic)).filter(Boolean))]
    },

    subscribeToMqttTopics() {
      if (!this.mqttClient || !this.mqttConnected) return

      this.getMqttSubscriptionTopics().forEach((topic) => {
        this.mqttClient.subscribe(topic, (err) => {
          if (err) {
            console.warn(`Error en suscripción MQTT (${topic}):`, err)
          } else {
            console.info(`Suscrito a MQTT: ${topic}`)
          }
        })
      })
    },

    mqttPublish(topic, payload = '') {
      return new Promise((resolve, reject) => {
        if (!this.mqttClient || !this.mqttConnected) {
          reject(new Error('MQTT no conectado'))
          return
        }
        this.mqttClient.publish(topic, payload, {}, (err) => {
          if (err) {
            reject(err)
            return
          }
          resolve()
        })
      })
    },

    buildConnectPayload() {
      const mode = String(this.droneMode || '').trim().toLowerCase()
      return mode === 'real' ? 'Real' : 'Simulacion'
    },

    isTelemetryTopic(topic) {
      const received = this.normalizeMqttTopic(topic).toLowerCase()
      if (!received) return false
      const configured = this.normalizeMqttTopic(this.mqttTelemetryTopic).toLowerCase()
      if (configured && received === configured) return true
      return received === 'telemetryinfo' || received.endsWith('/telemetryinfo')
    },

    isGeofencePointsTopic(topic) {
      const received = this.normalizeMqttTopic(topic).toLowerCase()
      if (!received) return false
      const configured = this.normalizeMqttTopic(this.mqttGeofencePointsTopic).toLowerCase()
      if (configured && received === configured) return true
      return received.endsWith('/geofencepoints') || received === 'geofencepoints'
    },

    normalizeJsonLikePayload(raw) {
      return String(raw || '')
        .replace(/\bNone\b/g, 'null')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false')
        .replace(/\((\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*)\)/g, '[$1]')
        .replace(/'/g, '"')
    },

    parseTelemetryPayload(message) {
      const raw = (message == null ? '' : message.toString()).trim()
      if (!raw) return null

      try {
        return JSON.parse(raw)
      } catch (e) {
        // payload con prefijo o con formato python
      }

      const candidates = []
      const objectStart = raw.indexOf('{')
      const objectEnd = raw.lastIndexOf('}')
      if (objectStart >= 0 && objectEnd > objectStart) {
        candidates.push(raw.slice(objectStart, objectEnd + 1))
      }

      const arrayStart = raw.indexOf('[')
      const arrayEnd = raw.lastIndexOf(']')
      if (arrayStart >= 0 && arrayEnd > arrayStart) {
        candidates.push(raw.slice(arrayStart, arrayEnd + 1))
      }

      for (const candidate of candidates) {
        try {
          return JSON.parse(candidate)
        } catch (e) {
          try {
            const normalized = this.normalizeJsonLikePayload(candidate)
            return JSON.parse(normalized)
          } catch (err) {
            // seguimos con el siguiente candidato
          }
        }
      }

      return null
    },

    extractGeofencePointsFromPayload(payload) {
      if (!payload) return []
      if (Array.isArray(payload)) return this.normalizeGeofencePoints(payload)
      if (Array.isArray(payload?.puntos)) return this.normalizeGeofencePoints(payload.puntos)
      if (Array.isArray(payload?.points)) return this.normalizeGeofencePoints(payload.points)
      return []
    },

    applyGeofenceFromMqttOnDroneConnect() {
      if (!this.mapReady || !this.map) return
      const pending = this.extractGeofencePointsFromPayload(this.geofencePendingFromMqtt)
      if (pending.length < 3) {
        this.geofenceError = 'No hay geofence válido en MQTT. Puedes dibujarlo manualmente.'
        return
      }

      this.geofencePoints = pending
      this.rebuildGeofencePointMarkers()
      this.renderGeofence()
      this.focusMapOnGeofence(pending)
      this.geofenceDirty = false
      this.geofenceNotice = 'Geofence cargado desde MQTT al conectar el dron'
      this.geofenceError = null
    },

    focusMapOnGeofence(points) {
      if (!this.map || !Array.isArray(points) || points.length < 3) return
      try {
        const bounds = L.latLngBounds(points)
        if (!bounds.isValid()) return
        this.map.fitBounds(bounds, {
          padding: [36, 36],
          maxZoom: 19
        })
      } catch (e) {
        console.warn('No se pudo centrar el mapa en el geofence:', e)
      }
    },

    handleIncomingGeofencePoints(message) {
      const data = this.parseTelemetryPayload(message)
      const points = this.extractGeofencePointsFromPayload(data)
      if (points.length < 3) {
        if (this.droneConnected) {
          this.geofenceError = 'Geofence recibido por MQTT inválido. Puedes dibujarlo manualmente.'
        }
        return
      }

      this.geofencePendingFromMqtt = { puntos: points }
      if (this.droneConnected) {
        this.applyGeofenceFromMqttOnDroneConnect()
      }
    },

    handleMqttMessage(topic, message) {
      this.mqttDebugLastTopic = this.normalizeMqttTopic(topic)
      this.mqttDebugLastPayload = message == null ? '' : message.toString()

      if (this.isGeofencePointsTopic(topic)) {
        this.handleIncomingGeofencePoints(message)
        return
      }

      if (!this.isTelemetryTopic(topic)) return
      const data = this.parseTelemetryPayload(message)
      if (!data || typeof data !== 'object') {
        console.warn('Mensaje telemetría inválido (no parseable):', message?.toString?.())
        return
      }

      const alt = this.readTelemetryNumber(data, [
        ['alt'],
        ['altitude'],
        ['relative_alt'],
        ['gps', 'alt'],
        ['gps', 'altitude'],
        ['position', 'alt'],
        ['position', 'altitude'],
        ['location', 'alt'],
        ['location', 'altitude']
      ])
      const now = Date.now()
      if (Number.isFinite(alt)) {
        this.updateAltitudeTrend(alt, now)
      }

      const heading = this.readTelemetryNumber(data, [
        ['heading'],
        ['yaw'],
        ['attitude', 'yaw'],
        ['navigation', 'heading'],
        ['navigation', 'yaw']
      ])
      if (Number.isFinite(heading)) {
        this.telemetryHeading = ((heading % 360) + 360) % 360
      }

      const telemetryLoc = this.extractTelemetryLocation(data)
      if (telemetryLoc) {
        this.telemetryLat = telemetryLoc.lat
        this.telemetryLon = telemetryLoc.lon
        this.dronePos = {
          lat: telemetryLoc.lat,
          lon: telemetryLoc.lon,
          precision: telemetryLoc.precision,
          alt: Number.isFinite(this.telemetryAlt) ? this.telemetryAlt : null,
          heading: Number.isFinite(this.telemetryHeading) ? this.telemetryHeading : null,
          trend: this.droneAltTrend,
          ts: now
        }
        this.updateDroneLocation(telemetryLoc.lat, telemetryLoc.lon, telemetryLoc.precision, now)
      }

      this.updateDroneMarkerVisuals()

      const state = String(data?.state || '').trim().toLowerCase()
      const ALT_LANDED_THRESHOLD = 0.05
      const ALT_AIRBORNE_THRESHOLD = 0.25
      const altIndicatesLanded = Number.isFinite(this.telemetryAlt) && this.telemetryAlt <= ALT_LANDED_THRESHOLD
      const altIndicatesAirborne = Number.isFinite(this.telemetryAlt) && this.telemetryAlt >= ALT_AIRBORNE_THRESHOLD

      if (state) {
        this.lastDroneState = state
        if (['flying', 'takingoff', 'hovering', 'airborne'].includes(state)) {
          this.droneConnected = true
          this.droneInAir = true
        } else if (['landed', 'landing', 'ready', 'idle'].includes(state)) {
          this.droneConnected = true
          this.droneInAir = false
        } else if (['disconnected', 'offline'].includes(state)) {
          this.droneConnected = false
          this.droneInAir = false
        } else {
          this.droneConnected = true
        }
      }

      // Si la telemetría marca altitud 0 (o casi 0), forzamos estado en tierra.
      if (altIndicatesLanded) {
        this.droneInAir = false
      } else if (altIndicatesAirborne) {
        // Si la altitud sube claramente, marcamos en vuelo aunque el estado tarde en llegar.
        this.droneInAir = true
      }
    },

    cancelAltitudeAnimation() {
      if (!this.altitudeAnimation) return
      if (this.altitudeAnimation.rafId && typeof cancelAnimationFrame === 'function') {
        cancelAnimationFrame(this.altitudeAnimation.rafId)
      }
      this.altitudeAnimation = null
    },

    queueAltitudeAnimation(targetAlt, sampleIntervalMs = 1000) {
      const target = Number(targetAlt)
      if (!Number.isFinite(target)) return

      if (typeof requestAnimationFrame !== 'function') {
        this.telemetryAltDisplay = target
        this.updateDroneMarkerVisuals()
        return
      }

      if (!this.altitudeAnimation) {
        this.altitudeAnimation = {
          rafId: null,
          segmentStartAt: null,
          segmentDurationMs: 1000,
          fromAlt: target,
          toAlt: target,
          renderAlt: target
        }
      }

      const nowPerf = typeof performance !== 'undefined' && performance.now
        ? performance.now()
        : Date.now()

      const anim = this.altitudeAnimation
      const currentAlt = Number.isFinite(anim.renderAlt)
        ? anim.renderAlt
        : (Number.isFinite(this.telemetryAltDisplay) ? this.telemetryAltDisplay : target)

      anim.fromAlt = currentAlt
      anim.toAlt = target
      anim.renderAlt = currentAlt
      anim.segmentStartAt = nowPerf
      anim.segmentDurationMs = Math.max(260, Math.min(1500, Number(sampleIntervalMs) * 1.05 || 1050))

      this.startAltitudeAnimationLoop()
    },

    startAltitudeAnimationLoop() {
      if (!this.altitudeAnimation) return
      if (typeof requestAnimationFrame !== 'function') return
      if (this.altitudeAnimation.rafId) return

      const easeInOutSine = t => -(Math.cos(Math.PI * t) - 1) / 2
      const tick = (ts) => {
        if (!this.altitudeAnimation) return
        const anim = this.altitudeAnimation
        const start = Number(anim.segmentStartAt)
        const duration = Number(anim.segmentDurationMs)

        if (!Number.isFinite(start) || !Number.isFinite(duration) || duration <= 0) {
          this.telemetryAltDisplay = Number(anim.toAlt)
          this.updateDroneMarkerVisuals()
          anim.rafId = null
          return
        }

        const raw = Math.min(1, Math.max(0, (ts - start) / duration))
        const p = easeInOutSine(raw)
        const from = Number(anim.fromAlt)
        const to = Number(anim.toAlt)
        if (!Number.isFinite(from) || !Number.isFinite(to)) {
          anim.rafId = null
          return
        }

        anim.renderAlt = from + ((to - from) * p)
        this.telemetryAltDisplay = anim.renderAlt
        this.updateDroneMarkerVisuals()

        if (raw < 1) {
          anim.rafId = requestAnimationFrame(tick)
        } else {
          anim.renderAlt = to
          this.telemetryAltDisplay = to
          this.updateDroneMarkerVisuals()
          anim.rafId = null
        }
      }

      this.altitudeAnimation.rafId = requestAnimationFrame(tick)
    },

    updateAltitudeTrend(nextAlt, tsNow) {
      const alt = Number(nextAlt)
      if (!Number.isFinite(alt)) return

      const prevAlt = Number(this.telemetryAlt)
      const prevTs = Number(this.lastTelemetryTs)
      this.telemetryAlt = Number(alt.toFixed(3))
      if (!Number.isFinite(this.telemetryAltDisplay)) {
        this.telemetryAltDisplay = this.telemetryAlt
      }
      const sampleIntervalMs = Number.isFinite(prevTs) && tsNow > prevTs ? (tsNow - prevTs) : 1000
      this.queueAltitudeAnimation(this.telemetryAlt, sampleIntervalMs)

      if (Number.isFinite(prevAlt) && Number.isFinite(prevTs) && tsNow > prevTs) {
        const delta = alt - prevAlt
        const dt = Math.max(1, tsNow - prevTs) / 1000
        this.telemetryVerticalSpeed = delta / dt

        const ALT_DELTA_THRESHOLD = 0.0008
        if (delta > ALT_DELTA_THRESHOLD) {
          this.droneAltTrend = 'up'
        } else if (delta < -ALT_DELTA_THRESHOLD) {
          this.droneAltTrend = 'down'
        } else {
          this.droneAltTrend = 'stable'
        }
      } else {
        this.telemetryVerticalSpeed = null
        this.droneAltTrend = 'stable'
      }

      this.lastTelemetryTs = tsNow
    },

    initWS() {
      this.live = new LiveWS()

      this.live.onMessage = (msg) => {
        if (!msg) return

        if (msg.type === 'snapshot' && Array.isArray(msg.players)) {
          this.applyPlayersSnapshot(msg.players)
        }

        if (msg.type === 'player_update' && msg.player) {
          this.upsertPlayer(msg.player)
        }

        if (msg.type === 'reset') {
          this.clearMarkers()
        }
      }

      this.live.onOpen = () => {
        this.wsReady = true
      }

      this.live.onClose = () => {
        this.wsReady = false
      }

      this.live.connect({ role: 'admin' })
    },

    initMap() {
      const container = L.DomUtil.get('map')
      if (container) container._leaflet_id = null

      const fallbackLat = 41.2766
      const fallbackLon = 1.9890

      const start = (lat, lon) => {
        this.map = L.map('map', { maxZoom: 20 }).setView([lat, lon], 18)

        this.layerEsri = L.tileLayer(
          'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          { maxZoom: 19, attribution: 'Tiles © Esri' }
        )

        this.layerPnoaProvWms = L.tileLayer.wms(
          'https://wms-pnoa.idee.es/pnoa-provisionales',
          {
            layers: 'OrtoimagenRapida',
            format: 'image/jpeg',
            transparent: false,
            tileSize: 512,
            detectRetina: true,
            maxZoom: 19,
            attribution: '© IGN PNOA (Provisional)'
          }
        )

        this.layerPnoaProvWms.addTo(this.map)

        L.control.layers(
          {
            'PNOA (Provisional)': this.layerPnoaProvWms,
            'Esri World Imagery': this.layerEsri
          },
          null,
          { position: 'topright' }
        ).addTo(this.map)

        this.$nextTick(() => this.map?.invalidateSize(true))
        this.mapReady = true
        this.syncGeofenceMapClickBinding()
        this.rebuildGeofencePointMarkers()
        this.renderGeofence()
        if (this.droneConnected) {
          this.applyGeofenceFromMqttOnDroneConnect()
        }
        if (this.dronePos) {
          this.updateDroneLocation(this.dronePos.lat, this.dronePos.lon, this.dronePos.precision)
        }
      }

      if (!navigator.geolocation) return start(fallbackLat, fallbackLon)

      navigator.geolocation.getCurrentPosition(
        (pos) => start(pos.coords.latitude, pos.coords.longitude),
        () => start(fallbackLat, fallbackLon),
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
      )
    },

    syncGeofenceMapClickBinding() {
      if (!this.map) return
      this.map.off('click', this.handleGeofenceMapClick)
      if (this.geofenceMode) {
        this.map.on('click', this.handleGeofenceMapClick)
      }
    },

    normalizeGeofencePoints(points) {
      if (!Array.isArray(points)) return []
      return points
        .map((point) => {
          if (Array.isArray(point) && point.length >= 2) {
            return [Number(point[0]), Number(point[1])]
          }
          if (point && typeof point === 'object') {
            return [Number(point.lat), Number(point.lon)]
          }
          return null
        })
        .filter((pair) => {
          if (!Array.isArray(pair)) return false
          const [lat, lon] = pair
          return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180
        })
        .map(([lat, lon]) => [Number(lat.toFixed(7)), Number(lon.toFixed(7))])
    },

    createGeofencePointIcon() {
      return L.divIcon({
        className: `geofence-point-icon${this.geofenceMode ? ' editing' : ''}`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
        html: '<span class="geofence-point-dot"></span>'
      })
    },

    createGeofencePointMarker(point, index) {
      if (!this.map) return null
      const marker = L.marker(point, {
        icon: this.createGeofencePointIcon(),
        draggable: this.geofenceMode,
        keyboard: false,
        zIndexOffset: 950
      }).addTo(this.map)

      if (this.geofenceMode) {
        marker.on('drag', (evt) => this.handleGeofencePointDrag(index, evt))
        marker.on('dragend', () => this.markGeofenceChanged())
      }
      return marker
    },

    rebuildGeofencePointMarkers() {
      this.geofencePointMarkers.forEach((marker) => {
        try { marker.remove() } catch (e) { console.warn('Error', e) }
      })
      this.geofencePointMarkers = []

      if (!this.map || !this.geofencePoints.length) return
      this.geofencePoints.forEach((point, index) => {
        const marker = this.createGeofencePointMarker(point, index)
        if (marker) this.geofencePointMarkers.push(marker)
      })
    },

    markGeofenceChanged() {
      this.geofenceDirty = true
      this.geofenceError = null
      this.geofenceNotice = null
    },

    startGeofenceEdit() {
      this.setGeofenceMode(true)
      this.geofenceError = null
      this.geofenceNotice = 'Edición geofence activa'
    },

    stopGeofenceEdit() {
      this.setGeofenceMode(false)
      this.geofenceError = null
      this.geofenceNotice = null
    },

    setGeofenceMode(enabled) {
      this.geofenceMode = Boolean(enabled)
      this.syncGeofenceMapClickBinding()
      this.rebuildGeofencePointMarkers()
    },

    handleGeofencePointDrag(index, evt) {
      if (!this.geofenceMode) return
      const latlng = evt?.target?.getLatLng?.()
      if (!latlng) return
      const normalized = this.normalizeGeofencePoints([[latlng.lat, latlng.lng]])
      if (!normalized.length) return
      if (index < 0 || index >= this.geofencePoints.length) return
      this.geofencePoints.splice(index, 1, normalized[0])
      this.renderGeofence()
    },

    handleGeofenceMapClick(evt) {
      if (!this.geofenceMode || !this.map || !evt?.latlng) return
      this.addGeofencePoint(evt.latlng)
    },

    addGeofencePoint(latlng) {
      const normalized = this.normalizeGeofencePoints([[latlng.lat, latlng.lng]])
      if (!normalized.length) return
      const point = normalized[0]
      this.geofencePoints.push(point)
      const marker = this.createGeofencePointMarker(point, this.geofencePoints.length - 1)
      if (marker) this.geofencePointMarkers.push(marker)
      this.markGeofenceChanged()
      this.renderGeofence()
    },

    removeGeofenceLayers() {
      if (this.geofencePreviewLine) {
        try { this.geofencePreviewLine.remove() } catch (e) { console.warn('Error', e) }
      }
      if (this.geofencePolygon) {
        try { this.geofencePolygon.remove() } catch (e) { console.warn('Error', e) }
      }
      if (this.geofenceMask) {
        try { this.geofenceMask.remove() } catch (e) { console.warn('Error', e) }
      }
      this.geofencePreviewLine = null
      this.geofencePolygon = null
      this.geofenceMask = null
    },

    getStopPreviewStyle(kind) {
      if (kind === 'admin') {
        return {
          color: '#38bdf8',
          blockedColor: '#7dd3fc',
          tooltip: 'Parada admin'
        }
      }

      return {
        color: '#f59e0b',
        blockedColor: '#fdba74',
        tooltip: this.selectedPlayer?.alias
          ? `Parada ${this.selectedPlayer.alias}`
          : 'Parada jugador'
      }
    },

    ensureStopPreviewLayers(kind) {
      if (!this.map) return null
      if (this.stopPreviewLayers[kind]) return this.stopPreviewLayers[kind]

      const style = this.getStopPreviewStyle(kind)
      const routeLine = L.polyline([], {
        color: style.color,
        weight: 3,
        dashArray: '7 7',
        lineCap: 'round',
        interactive: false,
        opacity: 0.95
      }).addTo(this.map)

      const blockedLine = L.polyline([], {
        color: style.blockedColor,
        weight: 2,
        dashArray: '2 10',
        lineCap: 'round',
        interactive: false,
        opacity: 0.9
      }).addTo(this.map)

      const marker = L.circleMarker([0, 0], {
        radius: 7,
        weight: 2,
        color: '#ffffff',
        fillColor: style.color,
        fillOpacity: 0.95,
        interactive: false
      }).addTo(this.map)

      marker.bindTooltip(style.tooltip, {
        permanent: true,
        direction: 'top',
        offset: [0, -10],
        className: `stop-preview-tooltip stop-preview-tooltip-${kind}`
      })

      this.stopPreviewLayers[kind] = { routeLine, blockedLine, marker }
      return this.stopPreviewLayers[kind]
    },

    clearStopPreview(kind) {
      const keys = kind ? [kind] : Object.keys(this.stopPreviewLayers)
      keys.forEach((key) => {
        const layers = this.stopPreviewLayers[key]
        if (!layers) return
        try { layers.routeLine?.remove?.() } catch (e) { console.warn('Error', e) }
        try { layers.blockedLine?.remove?.() } catch (e) { console.warn('Error', e) }
        try { layers.marker?.remove?.() } catch (e) { console.warn('Error', e) }
        delete this.stopPreviewLayers[key]
      })
    },

    refreshAllStopPreviews() {
      this.refreshStopPreview('admin')
      this.refreshStopPreview('player')
    },

    refreshStopPreview(kind) {
      if (!this.mapReady || !this.map) {
        this.clearStopPreview(kind)
        return
      }

      const target = kind === 'admin'
        ? this.adminPos
        : this.selectedPlayer

      const droneLat = Number(this.dronePos?.lat)
      const droneLon = Number(this.dronePos?.lon)
      const hasDronePosition = Number.isFinite(droneLat) && Number.isFinite(droneLon)
      const targetLat = Number(target?.lat)
      const targetLon = Number(target?.lon)

      if (
        !Number.isFinite(targetLat) ||
        !Number.isFinite(targetLon) ||
        this.geofencePoints.length < 3
      ) {
        this.clearStopPreview(kind)
        return
      }

      const resolved = this.resolveGotoTarget(targetLat, targetLon)
      if (!resolved.adjusted) {
        this.clearStopPreview(kind)
        return
      }

      const layers = this.ensureStopPreviewLayers(kind)
      if (!layers) return

      const style = this.getStopPreviewStyle(kind)
      const stopLatLng = [resolved.lat, resolved.lon]
      const targetLatLng = [targetLat, targetLon]

      layers.routeLine.setStyle({ color: style.color })
      layers.routeLine.setLatLngs(hasDronePosition ? [[droneLat, droneLon], stopLatLng] : [])

      layers.blockedLine.setStyle({ color: style.blockedColor })
      layers.blockedLine.setLatLngs([stopLatLng, targetLatLng])

      layers.marker.setStyle({ fillColor: style.color })
      layers.marker.setLatLng(stopLatLng)
      layers.marker.setTooltipContent(
        `${style.tooltip} · ${resolved.appliedBackoffMeters.toFixed(1)} m antes`
      )

      layers.routeLine.bringToFront()
      layers.blockedLine.bringToFront()
      layers.marker.bringToFront()
    },

    renderGeofence() {
      if (!this.map) return
      this.removeGeofenceLayers()

      if (this.geofencePoints.length >= 2) {
        this.geofencePreviewLine = L.polyline(this.geofencePoints, {
          color: '#22c55e',
          weight: 2,
          dashArray: '6 6',
          interactive: false
        }).addTo(this.map)
      }

      if (this.geofencePoints.length >= 3) {
        this.geofencePolygon = L.polygon(this.geofencePoints, {
          color: '#22c55e',
          weight: 2,
          fillColor: '#22c55e',
          fillOpacity: 0.1,
          interactive: false
        }).addTo(this.map)

        const worldRing = [
          [-90, -360],
          [-90, 360],
          [90, 360],
          [90, -360]
        ]

        this.geofenceMask = L.polygon([worldRing, this.geofencePoints], {
          stroke: false,
          fillColor: '#ff0000',
          fillOpacity: 0.34,
          fillRule: 'evenodd',
          interactive: false
        }).addTo(this.map)

        this.geofenceMask.bringToBack()
        this.geofencePolygon.bringToFront()
      }

      if (this.geofencePreviewLine) this.geofencePreviewLine.bringToFront()
      this.refreshAllStopPreviews()
      this.geofencePointMarkers.forEach((m) => m?.bringToFront?.())
    },

    buildSetGeofencePayload(points) {
      const puntos = this.normalizeGeofencePoints(points).map(([lat, lon]) => ({ lat, lon }))
      return { puntos }
    },

    async saveGeofence() {
      this.geofenceError = null
      this.geofenceNotice = null
      const points = this.normalizeGeofencePoints(this.geofencePoints)
      if (points.length < 3) {
        this.geofenceError = 'Necesitas al menos 3 puntos para guardar el geofence'
        return
      }

      const mqttPayload = this.buildSetGeofencePayload(points)
      try {
        await this.mqttPublish(this.mqttTopics.geofence, JSON.stringify(mqttPayload))
        this.geofenceDirty = false
        this.geofenceNotice = `Geofence guardado y publicado en ${this.mqttTopics.geofence}`
      } catch (e) {
        this.geofenceError = `No se pudo publicar el geofence por MQTT: ${e.message || 'error desconocido'}`
      }
    },

    clearGeofence(silent = false) {
      const hadPoints = this.geofencePoints.length > 0
      this.geofencePoints = []
      this.removeGeofenceLayers()
      this.rebuildGeofencePointMarkers()
      this.geofenceError = null
      this.geofenceNotice = null
      if (!silent && hadPoints) {
        this.markGeofenceChanged()
      }
    },

    ensurePlayerLayers(aliasColor, latlng) {
      const color = aliasColor
      if (this.markers[aliasColor]) return this.markers[aliasColor]

      const dot = L.circleMarker(latlng, {
        radius: 6,
        weight: 2,
        color: '#ffffff',
        fillColor: color,
        fillOpacity: 0.95
      })
        .addTo(this.map)
        .bindPopup(`Jugador ${aliasColor}`)

      const acc = L.circle(latlng, {
        radius: 5,
        weight: 1,
        color,
        fillColor: color,
        fillOpacity: 0.15
      }).addTo(this.map)

      this.markers[aliasColor] = { dot, acc }
      return this.markers[aliasColor]
    },

    cancelPlayerAnimation(alias) {
      const key = String(alias || '')
      if (!key) return
      const anim = this.playerAnimations[key]
      if (!anim) return
      if (anim.rafId && typeof cancelAnimationFrame === 'function') {
        cancelAnimationFrame(anim.rafId)
      }
      delete this.playerAnimations[key]
    },

    animatePlayerTo(alias, layers, lat, lon) {
      if (!layers?.dot || !layers?.acc) return

      const targetLat = Number(lat)
      const targetLon = Number(lon)
      if (!Number.isFinite(targetLat) || !Number.isFinite(targetLon)) return

      const target = [targetLat, targetLon]
      const current = layers.dot.getLatLng?.()
      if (!current || !Number.isFinite(current.lat) || !Number.isFinite(current.lng)) {
        layers.dot.setLatLng(target)
        layers.acc.setLatLng(target)
        return
      }

      if (typeof requestAnimationFrame !== 'function') {
        layers.dot.setLatLng(target)
        layers.acc.setLatLng(target)
        return
      }

      const now = typeof performance !== 'undefined' && performance.now
        ? performance.now()
        : Date.now()

      const prevAnim = this.playerAnimations[alias]
      if (prevAnim?.rafId && typeof cancelAnimationFrame === 'function') {
        cancelAnimationFrame(prevAnim.rafId)
      }

      const fromLat = Number(current.lat)
      const fromLon = Number(current.lng)
      const deltaLat = targetLat - fromLat
      const deltaLon = targetLon - fromLon

      if (Math.abs(deltaLat) < 1e-8 && Math.abs(deltaLon) < 1e-8) {
        layers.dot.setLatLng(target)
        layers.acc.setLatLng(target)
        this.playerAnimations[alias] = {
          rafId: null,
          lastUpdateAt: now
        }
        return
      }

      const elapsed = prevAnim?.lastUpdateAt ? now - prevAnim.lastUpdateAt : 280
      const duration = Math.max(120, Math.min(520, elapsed * 1.1))
      const easeOutCubic = t => 1 - ((1 - t) ** 3)

      const anim = {
        rafId: null,
        lastUpdateAt: now
      }
      this.playerAnimations[alias] = anim

      const step = (ts) => {
        const progress = Math.min(1, (ts - now) / duration)
        const eased = easeOutCubic(progress)
        const curLat = fromLat + (deltaLat * eased)
        const curLon = fromLon + (deltaLon * eased)
        const curPos = [curLat, curLon]
        layers.dot.setLatLng(curPos)
        layers.acc.setLatLng(curPos)

        if (progress < 1) {
          anim.rafId = requestAnimationFrame(step)
        } else {
          anim.rafId = null
        }
      }

      anim.rafId = requestAnimationFrame(step)
    },

    upsertPlayer(p) {
      if (!this.mapReady || !this.map) return
      if (!p || !p.alias || p.lat == null || p.lon == null) return

      const alias = String(p.alias)
      const lat = Number(p.lat)
      const lon = Number(p.lon)
      if (Number.isNaN(lat) || Number.isNaN(lon)) return

      const precision = Number(p.precision ?? 0)
      const ts = Number(p.ts ?? 0)

      const now = Date.now()
      const OFFLINE_MS = 8000
      const offline = ts ? (now - ts > OFFLINE_MS) : false

      const pos = [lat, lon]
      const layers = this.ensurePlayerLayers(alias, pos)

      this.animatePlayerTo(alias, layers, lat, lon)

      const capped = !Number.isNaN(precision) && precision > 0 ? Math.min(precision, 200) : 5
      layers.acc.setRadius(capped)

      layers.dot.setStyle({
        opacity: offline ? 0.35 : 1,
        fillOpacity: offline ? 0.25 : 0.95
      })

      layers.acc.setStyle({
        opacity: offline ? 0.2 : 1,
        fillOpacity: offline ? 0.05 : 0.15
      })

      this.playersByAlias[alias] = {
        alias,
        lat,
        lon,
        precision: Number.isFinite(precision) ? precision : null,
        ts: Number.isFinite(ts) ? ts : null,
        offline
      }

      if (!this.selectedPlayerAlias) {
        this.selectedPlayerAlias = alias
      }
    },

    removePlayer(alias) {
      const key = String(alias || '')
      if (!key) return

      this.cancelPlayerAnimation(key)

      const layers = this.markers[key]
      if (layers) {
        try { layers.dot.remove() } catch (e) { console.warn('Error', e) }
        try { layers.acc.remove() } catch (e) { console.warn('Error', e) }
        delete this.markers[key]
      }

      if (this.playersByAlias[key]) {
        delete this.playersByAlias[key]
      }

      if (this.selectedPlayerAlias === key) {
        this.selectedPlayerAlias = null
      }
    },

    applyPlayersSnapshot(players) {
      const present = new Set()
      if (Array.isArray(players)) {
        players.forEach((p) => {
          if (!p || !p.alias || p.lat == null || p.lon == null) return
          const lat = Number(p.lat)
          const lon = Number(p.lon)
          if (Number.isNaN(lat) || Number.isNaN(lon)) return
          const alias = String(p.alias)
          present.add(alias)
          this.upsertPlayer({ ...p, alias, lat, lon })
        })
      }

      Object.keys(this.playersByAlias).forEach((alias) => {
        if (!present.has(alias)) {
          this.removePlayer(alias)
        }
      })

      if (!this.selectedPlayerAlias) {
        const first = Object.keys(this.playersByAlias)
          .sort((a, b) => a.localeCompare(b))[0] || null
        this.selectedPlayerAlias = first
      }
    },

    clearMarkers() {
      this.clearStopPreview('player')
      Object.keys(this.playersByAlias).forEach((alias) => this.removePlayer(alias))
      this.markers = {}
      this.playersByAlias = {}
      this.playerAnimations = {}
      this.selectedPlayerAlias = null
      this.gotoPlayerError = null
    },

    sanitizeGeofenceStopDistance() {
      const normalized = Number(this.sanitizedGeofenceStopDistance.toFixed(1))
      this.geofenceStopDistance = normalized
      return normalized
    },

    latLonToMeters(lat, lon, originLat, originLon) {
      const earthRadius = 6371000
      const toRad = (degrees) => (degrees * Math.PI) / 180
      const dLat = toRad(lat - originLat)
      const dLon = toRad(lon - originLon)
      const refLat = toRad(originLat)

      return {
        x: dLon * earthRadius * Math.cos(refLat),
        y: dLat * earthRadius
      }
    },

    metersToLatLon(x, y, originLat, originLon) {
      const earthRadius = 6371000
      const toDeg = (radians) => (radians * 180) / Math.PI
      const refLat = (originLat * Math.PI) / 180
      const lat = originLat + toDeg(y / earthRadius)
      const lon = originLon + toDeg(x / (earthRadius * Math.cos(refLat)))
      return { lat, lon }
    },

    findSegmentIntersection(start, end, edgeStart, edgeEnd) {
      const EPSILON = 1e-9
      const abx = end.x - start.x
      const aby = end.y - start.y
      const cdx = edgeEnd.x - edgeStart.x
      const cdy = edgeEnd.y - edgeStart.y
      const denominator = (abx * cdy) - (aby * cdx)

      if (Math.abs(denominator) < EPSILON) return null

      const acx = edgeStart.x - start.x
      const acy = edgeStart.y - start.y
      const t = ((acx * cdy) - (acy * cdx)) / denominator
      const u = ((acx * aby) - (acy * abx)) / denominator

      if (t < -EPSILON || t > 1 + EPSILON || u < -EPSILON || u > 1 + EPSILON) {
        return null
      }

      return {
        t: Math.min(1, Math.max(0, t)),
        x: start.x + (t * abx),
        y: start.y + (t * aby)
      }
    },

    isPointInsidePolygon(lat, lon, polygonPoints = this.geofencePoints) {
      const polygon = this.normalizeGeofencePoints(polygonPoints)
      if (polygon.length < 3) return false

      let inside = false
      for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
        const [latI, lonI] = polygon[i]
        const [latJ, lonJ] = polygon[j]
        const intersects = ((lonI > lon) !== (lonJ > lon))
          && (lat < (((latJ - latI) * (lon - lonI)) / ((lonJ - lonI) || 1e-12)) + latI)
        if (intersects) inside = !inside
      }

      return inside
    },

    getPolygonCentroidMeters(polygon, originLat, originLon) {
      if (!polygon.length) return null
      const points = polygon.map(([lat, lon]) => this.latLonToMeters(lat, lon, originLat, originLon))

      let area = 0
      let centroidX = 0
      let centroidY = 0
      for (let i = 0; i < points.length; i += 1) {
        const current = points[i]
        const next = points[(i + 1) % points.length]
        const cross = (current.x * next.y) - (next.x * current.y)
        area += cross
        centroidX += (current.x + next.x) * cross
        centroidY += (current.y + next.y) * cross
      }

      if (Math.abs(area) < 1e-9) {
        return {
          x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
          y: points.reduce((sum, point) => sum + point.y, 0) / points.length
        }
      }

      const factor = 1 / (3 * area)
      return {
        x: centroidX * factor,
        y: centroidY * factor
      }
    },

    findClosestPointOnSegment(point, segStart, segEnd) {
      const dx = segEnd.x - segStart.x
      const dy = segEnd.y - segStart.y
      const lengthSquared = (dx * dx) + (dy * dy)

      if (lengthSquared <= 1e-9) {
        return {
          x: segStart.x,
          y: segStart.y,
          distance: Math.hypot(point.x - segStart.x, point.y - segStart.y)
        }
      }

      const rawT = (((point.x - segStart.x) * dx) + ((point.y - segStart.y) * dy)) / lengthSquared
      const t = Math.max(0, Math.min(1, rawT))
      const x = segStart.x + (t * dx)
      const y = segStart.y + (t * dy)

      return {
        x,
        y,
        distance: Math.hypot(point.x - x, point.y - y)
      }
    },

    resolveTargetFromGeofence(targetLat, targetLon) {
      const polygon = this.normalizeGeofencePoints(this.geofencePoints)
      if (polygon.length < 3) {
        return { lat: targetLat, lon: targetLon, adjusted: false, appliedBackoffMeters: 0 }
      }

      if (this.isPointInsidePolygon(targetLat, targetLon, polygon)) {
        return { lat: targetLat, lon: targetLon, adjusted: false, appliedBackoffMeters: 0 }
      }

      const originLat = polygon[0][0]
      const originLon = polygon[0][1]
      const target = this.latLonToMeters(targetLat, targetLon, originLat, originLon)
      const centroid = this.getPolygonCentroidMeters(polygon, originLat, originLon)
      if (!centroid) {
        return { lat: targetLat, lon: targetLon, adjusted: false, appliedBackoffMeters: 0 }
      }

      let closest = null
      for (let i = 0; i < polygon.length; i += 1) {
        const current = polygon[i]
        const next = polygon[(i + 1) % polygon.length]
        const segStart = this.latLonToMeters(current[0], current[1], originLat, originLon)
        const segEnd = this.latLonToMeters(next[0], next[1], originLat, originLon)
        const candidate = this.findClosestPointOnSegment(target, segStart, segEnd)
        if (!closest || candidate.distance < closest.distance) {
          closest = candidate
        }
      }

      if (!closest) {
        return { lat: targetLat, lon: targetLon, adjusted: false, appliedBackoffMeters: 0 }
      }

      const stopDistance = this.sanitizeGeofenceStopDistance()
      const inwardX = centroid.x - closest.x
      const inwardY = centroid.y - closest.y
      const inwardLength = Math.hypot(inwardX, inwardY)
      if (inwardLength <= 1e-6) {
        return { lat: targetLat, lon: targetLon, adjusted: false, appliedBackoffMeters: 0 }
      }

      let adjustedX = closest.x + ((inwardX / inwardLength) * stopDistance)
      let adjustedY = closest.y + ((inwardY / inwardLength) * stopDistance)
      let adjusted = this.metersToLatLon(adjustedX, adjustedY, originLat, originLon)

      if (!this.isPointInsidePolygon(adjusted.lat, adjusted.lon, polygon)) {
        adjustedX = closest.x + (inwardX * 0.5)
        adjustedY = closest.y + (inwardY * 0.5)
        adjusted = this.metersToLatLon(adjustedX, adjustedY, originLat, originLon)
      }

      return {
        lat: Number(adjusted.lat.toFixed(7)),
        lon: Number(adjusted.lon.toFixed(7)),
        adjusted: true,
        appliedBackoffMeters: stopDistance,
        reference: 'geofence'
      }
    },

    findFirstRouteGeofenceIntersection(startLat, startLon, endLat, endLon) {
      const polygon = this.normalizeGeofencePoints(this.geofencePoints)
      if (polygon.length < 3) return null

      const originLat = startLat
      const originLon = startLon
      const start = this.latLonToMeters(startLat, startLon, originLat, originLon)
      const end = this.latLonToMeters(endLat, endLon, originLat, originLon)
      const routeLength = Math.hypot(end.x - start.x, end.y - start.y)
      if (routeLength <= 0) return null

      const hits = []
      for (let i = 0; i < polygon.length; i += 1) {
        const current = polygon[i]
        const next = polygon[(i + 1) % polygon.length]
        if (!current || !next) continue

        const edgeStart = this.latLonToMeters(current[0], current[1], originLat, originLon)
        const edgeEnd = this.latLonToMeters(next[0], next[1], originLat, originLon)
        const hit = this.findSegmentIntersection(start, end, edgeStart, edgeEnd)
        if (!hit) continue

        const duplicated = hits.some(existing => Math.abs(existing.t - hit.t) < 1e-6)
        if (!duplicated) hits.push(hit)
      }

      if (!hits.length) return null

      hits.sort((a, b) => a.t - b.t)
      return {
        ...hits[0],
        start,
        routeLength,
        originLat,
        originLon
      }
    },

    resolveGotoTarget(lat, lon) {
      const targetLat = Number(lat)
      const targetLon = Number(lon)
      if (!Number.isFinite(targetLat) || !Number.isFinite(targetLon)) {
        throw new Error('Coordenadas de destino inválidas')
      }

      const droneLat = Number(this.dronePos?.lat)
      const droneLon = Number(this.dronePos?.lon)
      const directTarget = {
        lat: targetLat,
        lon: targetLon,
        adjusted: false,
        appliedBackoffMeters: 0
      }

      if (!Number.isFinite(droneLat) || !Number.isFinite(droneLon) || this.geofencePoints.length < 3) {
        return this.resolveTargetFromGeofence(targetLat, targetLon)
      }

      const hit = this.findFirstRouteGeofenceIntersection(droneLat, droneLon, targetLat, targetLon)
      if (!hit) {
        return directTarget
      }

      const distanceToIntersection = hit.routeLength * hit.t
      if (distanceToIntersection <= 0) {
        return directTarget
      }

      const stopDistance = this.sanitizeGeofenceStopDistance()
      const backoffMeters = Math.min(stopDistance, distanceToIntersection)
      const unitBackX = (hit.start.x - hit.x) / distanceToIntersection
      const unitBackY = (hit.start.y - hit.y) / distanceToIntersection
      const adjusted = this.metersToLatLon(
        hit.x + (unitBackX * backoffMeters),
        hit.y + (unitBackY * backoffMeters),
        hit.originLat,
        hit.originLon
      )

      return {
        lat: Number(adjusted.lat.toFixed(7)),
        lon: Number(adjusted.lon.toFixed(7)),
        adjusted: true,
        appliedBackoffMeters: backoffMeters,
        reference: 'route'
      }
    },

    parseTelemetryNumber(value) {
      if (value == null) return null
      if (typeof value === 'string') {
        const normalized = value.trim().replace(',', '.')
        if (!normalized) return null
        const parsed = Number(normalized)
        return Number.isFinite(parsed) ? parsed : null
      }
      const n = Number(value)
      return Number.isFinite(n) ? n : null
    },

    readTelemetryNumber(data, paths) {
      if (!data || !Array.isArray(paths)) return null
      for (const path of paths) {
        let cur = data
        let missing = false
        for (const key of path) {
          if (cur == null || typeof cur !== 'object' || !(key in cur)) {
            missing = true
            break
          }
          cur = cur[key]
        }
        if (missing) continue
        const n = this.parseTelemetryNumber(cur)
        if (Number.isFinite(n)) return n
      }
      return null
    },

    extractTelemetryLocation(data) {
      const lat = this.readTelemetryNumber(data, [
        ['lat'],
        ['latitude'],
        ['gps', 'lat'],
        ['gps', 'latitude'],
        ['position', 'lat'],
        ['position', 'latitude'],
        ['location', 'lat'],
        ['location', 'latitude']
      ])
      const lon = this.readTelemetryNumber(data, [
        ['lon'],
        ['lng'],
        ['longitude'],
        ['gps', 'lon'],
        ['gps', 'lng'],
        ['gps', 'longitude'],
        ['position', 'lon'],
        ['position', 'lng'],
        ['position', 'longitude'],
        ['location', 'lon'],
        ['location', 'lng'],
        ['location', 'longitude']
      ])
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null

      const precision = this.readTelemetryNumber(data, [
        ['precision'],
        ['accuracy'],
        ['gps', 'precision'],
        ['gps', 'accuracy'],
        ['position', 'precision'],
        ['position', 'accuracy'],
        ['location', 'precision'],
        ['location', 'accuracy']
      ])

      return {
        lat,
        lon,
        precision: Number.isFinite(precision) ? precision : null
      }
    },

    ensureDroneLayers(latlng, accuracy) {
      if (!this.mapReady || !this.map) return
      if (!this.droneMarker) {
        this.droneMarker = L.marker(latlng, {
          icon: this.createDroneIcon(),
          zIndexOffset: 900
        }).addTo(this.map).bindPopup('Dron')
      }
      if (!this.droneAcc) {
        this.droneAcc = L.circle(latlng, {
          radius: Number.isFinite(accuracy) && accuracy > 0 ? Math.min(accuracy, 80) : 8,
          weight: 1,
          color: '#ff9800',
          fillColor: '#ff9800',
          fillOpacity: 0.08
        }).addTo(this.map)
      }
      this.updateDroneMarkerVisuals()
    },

    createDroneIcon() {
      return L.divIcon({
        className: 'drone-icon-host',
        iconSize: [58, 58],
        iconAnchor: [29, 29],
        popupAnchor: [0, -26],
        html: `
          <div class="drone-marker trend-stable" style="--heading-deg: 0deg;">
            <div class="drone-rotatable">
              <span class="drone-arm drone-arm-h"></span>
              <span class="drone-arm drone-arm-v"></span>
              <span class="drone-prop drone-prop-tl"></span>
              <span class="drone-prop drone-prop-tr"></span>
              <span class="drone-prop drone-prop-bl"></span>
              <span class="drone-prop drone-prop-br"></span>
              <span class="drone-body"></span>
              <span class="drone-nose"></span>
            </div>
            <div class="drone-alt-badge">
              <span class="drone-alt-arrow">↔</span>
              <span class="drone-alt-value">--.- m</span>
            </div>
          </div>
        `
      })
    },

    updateDroneMarkerVisuals() {
      if (!this.droneMarker) return
      const markerEl = this.droneMarker.getElement?.()
      if (!markerEl) return

      const root = markerEl.querySelector('.drone-marker')
      if (!root) return

      const trend = this.droneAltTrend || 'stable'
      root.classList.remove('trend-up', 'trend-down', 'trend-stable')
      root.classList.add(`trend-${trend}`)

      const heading = Number.isFinite(this.telemetryHeading) ? this.telemetryHeading : 0
      root.style.setProperty('--heading-deg', `${heading.toFixed(2)}deg`)

      const altArrow = markerEl.querySelector('.drone-alt-arrow')
      if (altArrow) {
        altArrow.textContent = trend === 'up' ? '↑' : trend === 'down' ? '↓' : '↔'
      }

      const altValue = markerEl.querySelector('.drone-alt-value')
      if (altValue) {
        const altToRender = Number.isFinite(this.telemetryAltDisplay) ? this.telemetryAltDisplay : this.telemetryAlt
        altValue.textContent = Number.isFinite(altToRender) ? `${altToRender.toFixed(3)} m` : '--.- m'
      }
    },

    cancelDroneAnimation() {
      if (!this.droneAnimation) return
      if (this.droneAnimation.rafId && typeof cancelAnimationFrame === 'function') {
        cancelAnimationFrame(this.droneAnimation.rafId)
      }
      this.droneAnimation = null
    },

    setDronePosition(lat, lon) {
      if (!this.droneMarker) return
      const latNum = Number(lat)
      const lonNum = Number(lon)
      if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) return
      const pos = [latNum, lonNum]
      this.droneMarker.setLatLng(pos)
      if (this.droneAcc) this.droneAcc.setLatLng(pos)
      if (this.droneAnimation) {
        this.droneAnimation.renderLat = latNum
        this.droneAnimation.renderLon = lonNum
      }
    },

    updateDroneTarget(lat, lon, sampleTs = Date.now()) {
      if (!this.droneMarker) return
      const targetLat = Number(lat)
      const targetLon = Number(lon)
      if (!Number.isFinite(targetLat) || !Number.isFinite(targetLon)) return

      if (typeof requestAnimationFrame !== 'function') {
        this.setDronePosition(targetLat, targetLon)
        return
      }

      if (!this.droneAnimation) {
        this.droneAnimation = {
          rafId: null,
          lastSampleTs: null,
          segmentStartAt: null,
          segmentDurationMs: 1000,
          fromLat: targetLat,
          fromLon: targetLon,
          toLat: targetLat,
          toLon: targetLon,
          renderLat: null,
          renderLon: null
        }
      }

      const anim = this.droneAnimation

      const current = this.droneMarker.getLatLng?.()
      if (
        current &&
        Number.isFinite(current.lat) &&
        Number.isFinite(current.lng) &&
        (!Number.isFinite(this.droneAnimation.renderLat) || !Number.isFinite(this.droneAnimation.renderLon))
      ) {
        anim.renderLat = Number(current.lat)
        anim.renderLon = Number(current.lng)
      }

      const lastSampleTs = Number(anim.lastSampleTs)
      const sampleIntervalMs = Number.isFinite(lastSampleTs) && sampleTs > lastSampleTs
        ? sampleTs - lastSampleTs
        : 1000

      const nowPerf = typeof performance !== 'undefined' && performance.now
        ? performance.now()
        : Date.now()

      const fromLat = Number.isFinite(anim.renderLat) ? anim.renderLat : targetLat
      const fromLon = Number.isFinite(anim.renderLon) ? anim.renderLon : targetLon

      anim.fromLat = fromLat
      anim.fromLon = fromLon
      anim.toLat = targetLat
      anim.toLon = targetLon
      anim.segmentStartAt = nowPerf
      anim.segmentDurationMs = Math.max(260, Math.min(1500, sampleIntervalMs * 1.05))
      anim.lastSampleTs = sampleTs

      this.startDroneSmoothingLoop()
    },

    startDroneSmoothingLoop() {
      if (!this.droneMarker || !this.droneAnimation) return
      if (typeof requestAnimationFrame !== 'function') return
      if (this.droneAnimation.rafId) return

      const easeInOutSine = t => -(Math.cos(Math.PI * t) - 1) / 2
      const tick = (ts) => {
        if (!this.droneMarker || !this.droneAnimation) return

        const anim = this.droneAnimation
        const fromLat = Number(anim.fromLat)
        const fromLon = Number(anim.fromLon)
        const toLat = Number(anim.toLat)
        const toLon = Number(anim.toLon)
        const start = Number(anim.segmentStartAt)
        const duration = Number(anim.segmentDurationMs)

        if (
          !Number.isFinite(fromLat) ||
          !Number.isFinite(fromLon) ||
          !Number.isFinite(toLat) ||
          !Number.isFinite(toLon) ||
          !Number.isFinite(start) ||
          !Number.isFinite(duration) ||
          duration <= 0
        ) {
          anim.rafId = null
          return
        }

        const raw = Math.min(1, Math.max(0, (ts - start) / duration))
        const p = easeInOutSine(raw)

        anim.renderLat = fromLat + ((toLat - fromLat) * p)
        anim.renderLon = fromLon + ((toLon - fromLon) * p)
        this.setDronePosition(anim.renderLat, anim.renderLon)

        if (raw < 1) {
          anim.rafId = requestAnimationFrame(tick)
        } else {
          anim.renderLat = toLat
          anim.renderLon = toLon
          this.setDronePosition(toLat, toLon)
          anim.rafId = null
        }
      }

      this.droneAnimation.rafId = requestAnimationFrame(tick)
    },

    updateDroneLocation(lat, lon, accuracy, sampleTs = Date.now()) {
      if (!this.mapReady || !this.map) return
      const latNum = Number(lat)
      const lonNum = Number(lon)
      if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) return
      const latlng = [latNum, lonNum]
      this.ensureDroneLayers(latlng, accuracy)
      this.updateDroneTarget(latNum, lonNum, sampleTs)
      if (this.droneAcc && Number.isFinite(accuracy) && accuracy > 0) {
        this.droneAcc.setRadius(Math.min(accuracy, 80))
      }
      this.updateDroneMarkerVisuals()
    },

    clearDroneLocation() {
      this.clearStopPreview()
      this.cancelDroneAnimation()
      this.cancelAltitudeAnimation()
      if (this.droneMarker) {
        try { this.droneMarker.remove() } catch (e) { console.warn('Error', e) }
      }
      if (this.droneAcc) {
        try { this.droneAcc.remove() } catch (e) { console.warn('Error', e) }
      }
      this.droneMarker = null
      this.droneAcc = null
      this.droneAnimation = null
      this.dronePos = null
      this.telemetryAlt = null
      this.telemetryAltDisplay = null
      this.telemetryLat = null
      this.telemetryLon = null
      this.telemetryHeading = null
      this.telemetryVerticalSpeed = null
      this.lastTelemetryTs = null
      this.altitudeAnimation = null
      this.droneAltTrend = 'stable'
    },

    clearAdminLocation() {
      this.clearStopPreview('admin')
      if (this.adminMarker) {
        try { this.adminMarker.remove() } catch (e) { console.warn("Error", e) }
      }
      if (this.adminAcc) {
        try { this.adminAcc.remove() } catch (e) { console.warn("Error", e) }
      }
      this.adminMarker = null
      this.adminAcc = null
      this.adminPos = null
      this.gpsAccuracy = null
      this.gpsTimestamp = null
      this.adminCentered = false
    },

    startPollingFallback() {
      this.stopPollingFallback()
      this.pollTimer = setInterval(async () => {
        // si el WS está activo, no hace falta poll
        if (this.live?.enabled && this.wsReady) return
        try {
          const url = this.getPlayersUrl()
          if (!url) return
          let res = await fetch(url)
          if (!res.ok && url !== '/api/jugadores') {
            // fallback al backend local si el live no responde
            res = await fetch('/api/jugadores')
          }
          if (!res.ok) return
          const players = await res.json()
          if (Array.isArray(players)) {
            this.applyPlayersSnapshot(players)
          }
        } catch (e) {
          try {
            const res = await fetch('/api/jugadores')
            if (!res.ok) return
            const players = await res.json()
            if (Array.isArray(players)) {
              this.applyPlayersSnapshot(players)
            }
          } catch (err) {
            console.warn('Error polling jugadores:', err)
          }
        }
      }, 600)
    },

    stopPollingFallback() {
      if (this.pollTimer) clearInterval(this.pollTimer)
      this.pollTimer = null
    },

    getPlayersUrl() {
      if (!this.live?.enabled) return '/api/jugadores'
      let base = (process.env.VUE_APP_LIVE_URL || '').trim().replace(/\/$/, '')
      // Evitar mixed-content o localhost en producción
      try {
        const isHttpsPage = window.location.protocol === 'https:'
        const isHttpBase = base.startsWith('http://')
        const isLocalBase = /^(http:\/\/|https:\/\/)?(localhost|127\.0\.0\.1)/i.test(base)
        const isLocalPage = /^(localhost|127\.0\.0\.1)$/i.test(window.location.hostname)
        if ((isHttpsPage && isHttpBase) || (isLocalBase && !isLocalPage)) {
          base = ''
        }
      } catch (e) {
        // ignore
      }
      if (base) return `${base}/jugadores`
      return '/api/jugadores'
    },

    async iniciarJuego() {
      this.error = null
      this.loading = true
      try {
        await fetch('/api/iniciar-juego', { method: 'POST' }).catch(() => {})

        this.live.startGame()
      } catch (e) {
        this.error = e.message || 'Error al iniciar el juego'
      } finally {
        this.loading = false
      }
    },

    async pararJuego() {
      this.error = null
      try {
        // Reset real en backend/VM
        await fetch('/api/reset', { method: 'POST' }).catch(() => {})

        // ✅ Reset global del live:
        this.live.reset()
        this.clearMarkers()
        this.clearAdminLocation()
        this.clearDroneLocation()
      } catch {
        this.error = 'Error al parar el juego'
      }
    },

    async hacerFoto() {
      this.photoError = null
      this.photoLoading = true
      try {
        const remoteVideo = this.$refs.remoteVideo
        if (this.cameraActive && remoteVideo && remoteVideo.videoWidth > 0 && remoteVideo.videoHeight > 0) {
          const canvas = document.createElement('canvas')
          canvas.width = remoteVideo.videoWidth
          canvas.height = remoteVideo.videoHeight
          const ctx = canvas.getContext('2d')
          if (!ctx) throw new Error('No se pudo crear el canvas')
          ctx.drawImage(remoteVideo, 0, 0, canvas.width, canvas.height)

          const blob = await new Promise((resolve, reject) => {
            canvas.toBlob(
              (b) => (b ? resolve(b) : reject(new Error('No se pudo generar la imagen'))),
              'image/jpeg',
              0.92
            )
          })

          if (this.photoUrl) URL.revokeObjectURL(this.photoUrl)
          this.photoUrl = URL.createObjectURL(blob)
          this.photoSource = 'RTC'
        } else {
          throw new Error('Activa la cámara para capturar la imagen procesada')
        }
      } catch (e) {
        this.photoError = e.message || 'Error capturando foto'
      } finally {
        this.photoLoading = false
      }
    },

    async landOnly() {
      this.landError = null
      this.landLoading = true
      try {
        await this.mqttPublish(this.mqttTopics.land)
        this.droneInAir = false
      } catch (e) {
        this.landError = e.message || 'Error enviando LAND'
      } finally {
        this.landLoading = false
      }
    },

    async takeoff() {
      this.landError = null
      this.landLoading = true
      try {
        const height = Number(this.takeoffAlt)
        if (!Number.isFinite(height) || height <= 0) {
          throw new Error('Altura de despegue inválida')
        }
        await this.mqttPublish(this.mqttTopics.takeoff, String(height))
        this.droneConnected = true
        this.droneInAir = true
      } catch (e) {
        this.landError = e.message || 'Error en despegue'
      } finally {
        this.landLoading = false
      }
    },

    async toggleTakeoffLand() {
      if (this.droneInAir) {
        await this.landOnly()
        return
      }
      await this.takeoff()
    },

    async connectDrone() {
      this.error = null
      this.connectLoading = true
      try {
        if (this.droneConnected) {
          await this.mqttPublish(this.mqttTopics.disconnect)
          this.droneConnected = false
          this.droneInAir = false
        } else {
          await this.mqttPublish(this.mqttTopics.connect, this.buildConnectPayload())
          this.droneConnected = true
          this.applyGeofenceFromMqttOnDroneConnect()
        }
      } catch (e) {
        this.error = e.message || 'Error conectando dron'
      } finally {
        this.connectLoading = false
      }
    },

    checkGpsPrecision() {
      this.gpsError = null
      this.gpsLoading = true
      if (!navigator.geolocation) {
        this.gpsError = 'Geolocalización no disponible en este navegador'
        this.gpsLoading = false
        return
      }

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const { latitude, longitude, accuracy } = pos.coords
          const acc = Number(accuracy)
          this.gpsAccuracy = Number.isFinite(acc) ? Math.round(acc) : null
          this.gpsTimestamp = new Date(pos.timestamp).toLocaleTimeString()
          this.adminPos = { lat: Number(latitude), lon: Number(longitude) }
          this.updateAdminLocation(latitude, longitude, acc)
          this.gpsLoading = false
        },
        (err) => {
          this.gpsError = err?.message || 'No se pudo leer la precisión'
          this.gpsLoading = false
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
      )
    },

    ensureAdminLayers(latlng, accuracy) {
      if (!this.mapReady || !this.map) return
      if (!this.adminMarker) {
        this.adminMarker = L.circleMarker(latlng, {
          radius: 7,
          weight: 2,
          color: '#00e5ff',
          fillColor: '#00e5ff',
          fillOpacity: 0.9
        }).addTo(this.map).bindPopup('Administrador')
      }
      if (!this.adminAcc) {
        this.adminAcc = L.circle(latlng, {
          radius: accuracy && accuracy > 0 ? accuracy : 5,
          weight: 1,
          color: '#00e5ff',
          fillColor: '#00e5ff',
          fillOpacity: 0.08
        }).addTo(this.map)
      }
    },

    updateAdminLocation(lat, lon, accuracy) {
      if (!this.mapReady || !this.map) return
      const latlng = [Number(lat), Number(lon)]
      this.ensureAdminLayers(latlng, accuracy)
      if (this.adminMarker) this.adminMarker.setLatLng(latlng)
      if (this.adminAcc) this.adminAcc.setLatLng(latlng)
      if (this.adminAcc && Number.isFinite(accuracy) && accuracy > 0) {
        this.adminAcc.setRadius(accuracy)
      }
      if (!this.adminCentered) {
        this.map.setView(latlng, 18)
        this.adminCentered = true
      }
    },

    async toggleCamera() {
      this.cameraError = null
      if (this.cameraActive) {
        this.cleanupCamera()
        this.cameraActive = false
        this.cameraZoom = 'none'
        return
      }
      this.cameraLoading = true
      try {
        await this.loadCameras()
        this.cameraActive = true
        await this.$nextTick()
        if (this.selectedCameraId || this.cameras.length) {
          await this.startStream()
        }
      } catch (e) {
        this.cameraError = e.message || 'Error activando cámara'
      } finally {
        this.cameraLoading = false
      }
    },

    async loadCameras() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Cámara no disponible en este navegador')
      }
      try {
        const tempStream = await navigator.mediaDevices.getUserMedia({ video: true })
        tempStream.getTracks().forEach(t => t.stop())
      } catch (e) {
        throw new Error('Permiso de cámara denegado')
      }

      const devices = await navigator.mediaDevices.enumerateDevices()
      this.cameras = devices.filter(d => d.kind === 'videoinput')
      if (this.cameras.length && !this.selectedCameraId) {
        this.selectedCameraId = this.cameras[0].deviceId
      }
    },

    async startStream() {
      if (!this.cameraActive) return
      this.cleanupCamera()
      try {
        this.pc = new RTCPeerConnection(this.buildRtcConfiguration())

        this.pc.ontrack = async (event) => {
          const stream = new MediaStream([event.track])
          const remoteVideo = this.$refs.remoteVideo
          if (remoteVideo) {
            remoteVideo.srcObject = stream
            await remoteVideo.play().catch(() => {})
          }
        }

        this.localStream = await navigator.mediaDevices.getUserMedia({
          video: this.selectedCameraId
            ? {
                deviceId: { exact: this.selectedCameraId },
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
        })

        const localVideo = this.$refs.localVideo
        if (localVideo) localVideo.srcObject = this.localStream

        this.localStream.getTracks().forEach(track => {
          if ('contentHint' in track) {
            track.contentHint = 'motion'
          }
          const sender = this.pc.addTrack(track, this.localStream)
          this.applySenderQualityProfile(sender)
        })

        const offer = await this.pc.createOffer()
        await this.pc.setLocalDescription(offer)
        await this.waitForIceGathering(this.pc, 250)

        const offerUrl = this.getWebRtcUrl('/offer')

        const response = await fetch(offerUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sdp: this.pc.localDescription.sdp,
            type: this.pc.localDescription.type
          })
        })

        const answer = await response.json()
        await this.pc.setRemoteDescription(answer)
        this.startCameraTrackingPolling()
      } catch (e) {
        this.cameraError = e.message || 'Error iniciando cámara'
        this.cleanupCamera()
      }
    },

    cleanupCamera() {
      this.stopCameraTrackingPolling()
      if (this.localStream) {
        this.localStream.getTracks().forEach(t => t.stop())
        this.localStream = null
      }
      if (this.pc) {
        this.pc.close()
        this.pc = null
      }
      const localVideo = this.$refs.localVideo
      if (localVideo) localVideo.srcObject = null
      const remoteVideo = this.$refs.remoteVideo
      if (remoteVideo) remoteVideo.srcObject = null
    },

    startCameraTrackingPolling() {
      this.stopCameraTrackingPolling()
      this.pollCameraTracking()
      this.cameraTrackingTimer = window.setInterval(() => {
        this.pollCameraTracking()
      }, 800)
    },

    stopCameraTrackingPolling() {
      if (this.cameraTrackingTimer) {
        window.clearInterval(this.cameraTrackingTimer)
      }
      this.cameraTrackingTimer = null
      this.cameraTrackingPending = false
      this.cameraTracking = null
    },

    async pollCameraTracking() {
      if (!this.cameraActive || this.cameraTrackingPending) return
      this.cameraTrackingPending = true

      try {
        const response = await fetch(this.getWebRtcUrl('/tracking'), {
          method: 'GET',
          cache: 'no-store'
        })

        if (!response.ok) {
          throw new Error(`Tracking HTTP ${response.status}`)
        }

        const payload = await response.json()
        this.cameraTracking = payload
      } catch (e) {
        console.warn('No se pudo obtener tracking horizontal:', e)
      } finally {
        this.cameraTrackingPending = false
      }
    },

    applySenderQualityProfile(sender) {
      if (!sender || typeof sender.getParameters !== 'function' || typeof sender.setParameters !== 'function') {
        return
      }

      try {
        const params = sender.getParameters() || {}
        if (!Array.isArray(params.encodings) || !params.encodings.length) {
          params.encodings = [{}]
        }
        params.encodings[0] = {
          ...params.encodings[0],
          maxBitrate: 2_500_000,
          maxFramerate: 24,
          scaleResolutionDownBy: 1
        }
        sender.setParameters(params).catch?.(() => {})
      } catch (e) {
        console.warn('No se pudieron aplicar parametros RTC de calidad:', e)
      }
    },

    buildRtcConfiguration() {
      const useStun = String(process.env.VUE_APP_WEBRTC_USE_STUN || '').trim().toLowerCase() === 'true'
      return useStun
        ? { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] }
        : { iceServers: [] }
    },

    waitForIceGathering(pc, timeoutMs = 250) {
      return new Promise(resolve => {
        if (pc.iceGatheringState === 'complete') return resolve()
        const timer = window.setTimeout(() => {
          cleanup()
          resolve()
        }, timeoutMs)
        const cleanup = () => {
          window.clearTimeout(timer)
          pc.onicegatheringstatechange = null
        }
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === 'complete') {
            cleanup()
            resolve()
          }
        }
      })
    },

    async gotoAdmin() {
      this.gotoError = null
      if (!this.adminPos) {
        this.gotoError = 'Ubicación del administrador no disponible'
        return
      }
      this.gotoLoading = true
      try {
        await this.publishGoto(this.adminPos.lat, this.adminPos.lon)
      } catch (e) {
        this.gotoError = e.message || 'Error enviando GOTO'
      } finally {
        this.gotoLoading = false
      }
    },

    getPlayerColor(alias) {
      const raw = String(alias || '').trim()
      if (!raw) return '#6b7280'
      if (typeof CSS !== 'undefined' && typeof CSS.supports === 'function') {
        if (CSS.supports('color', raw)) return raw
      }
      return '#6b7280'
    },

    selectPlayer(alias) {
      this.selectedPlayerAlias = alias
      this.gotoPlayerError = null
    },

    async publishGoto(lat, lon) {
      const target = this.resolveGotoTarget(lat, lon)
      await this.mqttPublish(this.mqttTopics.goto, JSON.stringify({
        lat: target.lat,
        lon: target.lon,
        h: Number(this.takeoffAlt)
      }))
    },

    async gotoSelectedPlayer() {
      this.gotoPlayerError = null
      if (!this.selectedPlayer) {
        this.gotoPlayerError = 'Selecciona un jugador para enviar el dron'
        return
      }
      this.gotoPlayerLoading = true
      try {
        await this.publishGoto(this.selectedPlayer.lat, this.selectedPlayer.lon)
      } catch (e) {
        this.gotoPlayerError = e.message || 'Error enviando GOTO al jugador'
      } finally {
        this.gotoPlayerLoading = false
      }
    }
  }
}
</script>

<style scoped>
.admin-container {
  min-height: 100vh;
  background: radial-gradient(circle at top, #111 0%, #000 60%);
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: center;
  color: white;
  text-align: center;
  padding: 18px 0 18px;
  overflow: auto;
}

.title {
  font-size: 2rem;
  font-weight: 600;
  margin-bottom: 4px;
}

.subtitle {
  font-size: 0.95rem;
  color: #aaa;
  margin-bottom: 16px;
}

.map {
  width: 96%;
  max-width: 1400px;
  flex: 1 1 auto;
  height: 46vh;
  min-height: 320px;
  max-height: 480px;
  margin-bottom: 14px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 0 40px rgba(0, 0, 0, 0.6);
}

:deep(.geofence-point-icon) {
  background: transparent;
  border: none;
}

:deep(.geofence-point-dot) {
  display: block;
  width: 14px;
  height: 14px;
  border-radius: 999px;
  border: 2px solid #ffffff;
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
}

:deep(.geofence-point-icon.editing .geofence-point-dot) {
  cursor: grab;
  background: #16a34a;
}

:deep(.stop-preview-tooltip) {
  background: rgba(15, 23, 42, 0.96);
  border: 1px solid rgba(148, 163, 184, 0.45);
  border-radius: 999px;
  color: #e2e8f0;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  box-shadow: 0 10px 24px rgba(2, 6, 23, 0.35);
}

:deep(.stop-preview-tooltip::before) {
  border-top-color: rgba(15, 23, 42, 0.96);
}

:deep(.stop-preview-tooltip-admin) {
  color: #bae6fd;
}

:deep(.stop-preview-tooltip-player) {
  color: #fed7aa;
}

:deep(.drone-icon-host) {
  width: 58px !important;
  height: 58px !important;
  margin-left: -29px !important;
  margin-top: -29px !important;
  background: transparent;
  border: none;
}

:deep(.drone-marker) {
  position: relative;
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  transform-origin: center;
  will-change: transform;
}

:deep(.drone-rotatable) {
  position: relative;
  width: 32px;
  height: 32px;
  transform: rotate(var(--heading-deg, 0deg));
  transition: transform 0.18s linear;
}

:deep(.drone-arm) {
  position: absolute;
  left: 50%;
  top: 50%;
  background: #f8fafc;
  opacity: 0.85;
  transform: translate(-50%, -50%);
}

:deep(.drone-arm-h) {
  width: 24px;
  height: 2px;
}

:deep(.drone-arm-v) {
  width: 2px;
  height: 24px;
}

:deep(.drone-prop) {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  border: 1px solid #e2e8f0;
  background: #22d3ee;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.45);
}

:deep(.drone-prop-tl) { left: 0; top: 0; }
:deep(.drone-prop-tr) { right: 0; top: 0; }
:deep(.drone-prop-bl) { left: 0; bottom: 0; }
:deep(.drone-prop-br) { right: 0; bottom: 0; }

:deep(.drone-body) {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: #f59e0b;
  border: 2px solid #111827;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 14px rgba(245, 158, 11, 0.45);
}

:deep(.drone-nose) {
  position: absolute;
  left: 50%;
  top: 3px;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-bottom: 7px solid #fb7185;
  transform: translateX(-50%);
}

:deep(.drone-alt-badge) {
  position: absolute;
  left: 50%;
  bottom: -8px;
  transform: translateX(-50%);
  background: rgba(15, 23, 42, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.45);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  line-height: 1;
  color: #e2e8f0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

:deep(.drone-marker.trend-up) {
  animation: drone-rise 0.55s ease-in-out infinite alternate;
}

:deep(.drone-marker.trend-up .drone-alt-badge) {
  color: #86efac;
  border-color: rgba(22, 163, 74, 0.65);
}

:deep(.drone-marker.trend-up .drone-body) {
  background: #22c55e;
}

:deep(.drone-marker.trend-down) {
  animation: drone-fall 0.55s ease-in-out infinite alternate;
}

:deep(.drone-marker.trend-down .drone-alt-badge) {
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.65);
}

:deep(.drone-marker.trend-down .drone-body) {
  background: #ef4444;
}

:deep(.drone-marker.trend-stable .drone-alt-badge) {
  color: #cbd5e1;
}

@keyframes drone-rise {
  from { transform: translateY(1px); }
  to { transform: translateY(-3px); }
}

@keyframes drone-fall {
  from { transform: translateY(-1px); }
  to { transform: translateY(3px); }
}

.admin-container.camera-on .map {
  height: 38vh;
  min-height: 260px;
  max-height: 420px;
}

.control-grid {
  width: 96%;
  max-width: 1400px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
  margin-bottom: 10px;
}

.panel {
  background: linear-gradient(180deg, #0f0f0f 0%, #0a0a0a 100%);
  border: 1px solid #1d1d1d;
  border-radius: 14px;
  padding: 18px;
  text-align: left;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}

.panel h3 {
  margin: 0 0 6px 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.panel-sub {
  margin: 0 0 16px 0;
  color: #9b9b9b;
  font-size: 0.9rem;
}

.lab-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.lab-group {
  background: #0b0b0b;
  border: 1px solid #1a1a1a;
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lab-title {
  font-size: 0.85rem;
  letter-spacing: 0.6px;
  color: #c9c9c9;
  text-transform: uppercase;
  margin-bottom: 2px;
}

.mini-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.8rem;
  color: #bdbdbd;
}

.mini-field input {
  background: #111;
  color: #e5e7eb;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 8px 10px;
}

.mini-field select {
  background: #111;
  color: #e5e7eb;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 8px 10px;
}

.mini-note {
  margin: 8px 0 0 0;
  font-size: 0.8rem;
  color: #9fb0c5;
}

.camera-bay {
  width: 96%;
  max-width: 1400px;
  border-radius: 12px;
  background: #0b0b0b;
  border: 1px solid #1b1b1b;
  padding: 12px;
  margin-bottom: 8px;
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  height: 38vh;
  min-height: 340px;
  max-height: 560px;
  align-items: stretch;
}

.camera-controls {
  display: grid;
  gap: 10px;
  align-content: start;
}

.camera-stage {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 8px;
  min-height: 0;
}

.camera-toolbar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.camera-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.camera-card {
  background: #0f1318;
  border: 1px solid #1f2a35;
  border-radius: 10px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: hidden;
}

.camera-title {
  font-size: 0.75rem;
  color: #9fb0c5;
  margin-bottom: 6px;
}

.tracking-panel {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(16, 26, 36, 0.96), rgba(8, 13, 18, 0.92));
  border: 1px solid #203246;
}

.tracking-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.83rem;
}

.tracking-label {
  color: #8ea3b8;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 0.7rem;
}

.tracking-left {
  color: #f59e0b;
}

.tracking-right {
  color: #38bdf8;
}

.tracking-center {
  color: #22c55e;
}

.tracking-bar {
  position: relative;
  height: 16px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.22), rgba(34, 197, 94, 0.18), rgba(56, 189, 248, 0.22));
  overflow: hidden;
}

.tracking-center-line {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgba(255, 255, 255, 0.85);
  transform: translateX(-50%);
}

.tracking-safe-zone {
  position: absolute;
  left: 46%;
  top: 2px;
  bottom: 2px;
  width: 8%;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
}

.tracking-marker {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: #f8fafc;
  border: 2px solid #0f172a;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 3px rgba(148, 163, 184, 0.18);
}

.tracking-meta {
  margin: 0;
  font-size: 0.78rem;
  color: #b7c5d4;
  text-align: left;
}

.camera-card video {
  width: 100%;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  background: #05070a;
  border-radius: 8px;
  display: block;
  object-fit: contain;
}

.camera-bay.zoom-local .camera-card.remote,
.camera-bay.zoom-remote .camera-card.local {
  display: none;
}

.camera-bay.zoom-local .camera-grid,
.camera-bay.zoom-remote .camera-grid {
  grid-template-columns: 1fr;
}

.camera-bay.zoom-local .camera-card.local video,
.camera-bay.zoom-remote .camera-card.remote video {
  max-height: 100%;
}

.btn.tiny {
  padding: 8px 10px;
  font-size: 0.8rem;
  border-radius: 8px;
}

.mini-error {
  margin: 0;
  font-size: 0.8rem;
  color: #ff8b8b;
}

.panel-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.panel-actions.lab-actions {
  grid-template-columns: 1fr;
}

.btn-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.85rem;
  color: #bdbdbd;
}

.field select {
  background: #111;
  color: white;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 8px 10px;
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  color: #cfcfcf;
}

.status-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}

.status.small {
  font-size: 0.8rem;
  color: #a9a9a9;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #5b5b5b;
  box-shadow: 0 0 0 3px rgba(91, 91, 91, 0.2);
}

.dot.on {
  background: #00ff88;
  box-shadow: 0 0 0 3px rgba(0, 255, 136, 0.2);
}

.btn {
  min-width: 0;
  width: 100%;
  padding: 10px 12px;
  font-size: 0.9rem;
  font-weight: 600;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  letter-spacing: 0.5px;
}

.btn.start {
  background: linear-gradient(135deg, #00ff88, #00cc6a);
  color: #003320;
}

.btn.stop {
  background: linear-gradient(135deg, #ff4d4d, #d63031);
  color: white;
}

.btn.photo {
  background: linear-gradient(135deg, #ffd166, #f4a261);
  color: #3a2a00;
}

.btn.neutral {
  background: linear-gradient(135deg, #4b5563, #1f2937);
  color: #f1f5f9;
}

.btn.info {
  background: linear-gradient(135deg, #38bdf8, #0ea5e9);
  color: #00263a;
}

.btn.geofence {
  background: linear-gradient(135deg, #86efac, #22c55e);
  color: #03240f;
}

.btn.save {
  background: linear-gradient(135deg, #fcd34d, #f59e0b);
  color: #3f2400;
}

.btn.danger {
  background: linear-gradient(135deg, #ff4d4d, #d63031);
  color: white;
}

.btn.cam {
  background: linear-gradient(135deg, #a78bfa, #6366f1);
  color: #1f143d;
}

.btn.takeoff {
  background: linear-gradient(135deg, #34d399, #10b981);
  color: #003320;
}

.btn.goto {
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  color: #0b1b3a;
}

.btn.goto-user {
  background: linear-gradient(135deg, #f59e0b, #f97316);
  color: #411f00;
}

.btn.start:hover:not(:disabled),
.btn.photo:hover:not(:disabled),
.btn.stop:hover {
  transform: translateY(-2px);
}

.btn.neutral:hover:not(:disabled),
.btn.info:hover:not(:disabled),
.btn.danger:hover:not(:disabled),
.btn.cam:hover:not(:disabled),
.btn.takeoff:hover:not(:disabled),
.btn.goto:hover:not(:disabled),
.btn.save:hover:not(:disabled),
.btn.geofence:hover:not(:disabled) {
  transform: translateY(-2px);
}

.btn.goto-user:hover:not(:disabled) {
  transform: translateY(-2px);
}

.player-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 180px;
  overflow: auto;
}

.player-item {
  width: 100%;
  border: 1px solid #2b2b2b;
  background: #0f0f0f;
  border-radius: 10px;
  padding: 8px 10px;
  display: grid;
  grid-template-columns: 14px 1fr auto;
  gap: 8px;
  align-items: center;
  color: #dfdfdf;
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.player-item:hover {
  border-color: #3f3f3f;
  transform: translateY(-1px);
}

.player-item.selected {
  border-color: #f59e0b;
  box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.35);
}

.player-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.player-name {
  font-size: 0.85rem;
  text-transform: capitalize;
}

.player-state {
  font-size: 0.75rem;
  color: #86efac;
}

.player-state.offline {
  color: #fca5a5;
}

.error {
  margin-top: 30px;
  color: #ff6b6b;
  font-weight: 600;
}

.gps-box {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #0b1117;
  border: 1px solid #1e293b;
  font-size: 0.9rem;
  color: #cbd5f5;
}

.gps-coords {
  margin-top: 6px;
  font-size: 0.85rem;
  color: #a9b9e9;
}

.photo-panel {
  margin-top: 12px;
  width: 96%;
  max-width: 1400px;
  background: #0c0c0c;
  border: 1px solid #222;
  border-radius: 12px;
  padding: 14px;
  text-align: left;
}

.photo-panel h3 {
  margin: 0 0 10px 0;
  color: #ddd;
  font-size: 1rem;
  font-weight: 600;
}

.photo-source {
  font-size: 0.85rem;
  color: #9fb0c5;
  font-weight: 500;
}

.photo-panel img {
  width: 100%;
  max-height: 260px;
  height: auto;
  object-fit: contain;
  display: block;
  border-radius: 8px;
  border: 1px solid #111;
}
</style>
