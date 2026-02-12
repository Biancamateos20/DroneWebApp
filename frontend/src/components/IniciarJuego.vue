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
              <option value="sim">Simulación</option>
              <option value="real">Real</option>
            </select>
          </label>

          <div class="status">
            <span class="dot" :class="{ on: droneConnected }"></span>
            {{ droneConnected ? 'Dron conectado' : 'Dron desconectado' }}
          </div>
        </div>

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
            </div>
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
    </section>

    <p v-if="loading" class="subtitle">Lanzando misión…</p>
    <p v-if="photoLoading" class="subtitle">Capturando foto…</p>
    <p v-if="landLoading" class="subtitle">Enviando LAND…</p>
    <p v-if="connectLoading" class="subtitle">Conectando dron…</p>
    <p v-if="cameraLoading" class="subtitle">Activando cámara…</p>
    <p v-if="gpsLoading" class="subtitle">Consultando precisión…</p>
    <p v-if="gotoLoading" class="subtitle">Enviando GOTO…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="photoError" class="error">{{ photoError }}</p>
    <p v-if="landError" class="error">{{ landError }}</p>
    <p v-if="gpsError" class="error">{{ gpsError }}</p>
    <p v-if="gotoError" class="error">{{ gotoError }}</p>

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

      photoUrl: null,
      photoLoading: false,
      photoError: null,
      photoSource: null,
      landLoading: false,
      landError: null,

      droneMode: 'sim',
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

      gpsAccuracy: null,
      gpsTimestamp: null,
      gpsLoading: false,
      gpsError: null,
      adminPos: null,
      adminMarker: null,
      adminAcc: null,
      adminCentered: false,
      gotoLoading: false,
      gotoError: null
    }
  },

  computed: {
    cameraZoomClass() {
      return this.cameraZoom === 'local'
        ? 'zoom-local'
        : this.cameraZoom === 'remote'
          ? 'zoom-remote'
          : 'zoom-none'
    }
  },

  mounted() {
    this.initMap()
    this.initWS()
    this.startPollingFallback()

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
    this.live?.disconnect()
    this.stopPollingFallback()
    if (this.map) {
      this.map.remove()
      this.map = null
    }
  },

  methods: {
    setCameraZoom(mode) {
      this.cameraZoom = mode
    },
    initWS() {
      this.live = new LiveWS()

      this.live.onMessage = (msg) => {
        if (!msg) return

        if (msg.type === 'snapshot' && Array.isArray(msg.players)) {
          msg.players.forEach(p => this.upsertPlayer(p))
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
      }

      if (!navigator.geolocation) return start(fallbackLat, fallbackLon)

      navigator.geolocation.getCurrentPosition(
        (pos) => start(pos.coords.latitude, pos.coords.longitude),
        () => start(fallbackLat, fallbackLon),
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
      )
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

      layers.dot.setLatLng(pos)
      layers.acc.setLatLng(pos)

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
    },

    clearMarkers() {
      Object.values(this.markers).forEach(({ dot, acc }) => {
        try { dot.remove() } catch (e) { console.warn("Error", e)}
        try { acc.remove() } catch (e) { console.warn("Error", e) }
      })
      this.markers = {}
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
            players.forEach(p => this.upsertPlayer(p))
          }
        } catch (e) {
          try {
            const res = await fetch('/api/jugadores')
            if (!res.ok) return
            const players = await res.json()
            if (Array.isArray(players)) {
              players.forEach(p => this.upsertPlayer(p))
            }
          } catch (err) {
            console.warn('Error polling jugadores:', err)
          }
        }
      }, 2000)
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
        const res = await fetch('/api/land', { method: 'POST' })
        if (!res.ok) throw new Error('Error enviando LAND')
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
        const res = await fetch('/api/despegue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ h: height })
        })
        if (!res.ok) throw new Error('Error en despegue')
        const data = await res.json().catch(() => ({}))
        if (data.ok === false || data.despegue === false) {
          throw new Error('Despegue fallido')
        }
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
        const endpoint = this.droneConnected ? '/api/disconnection' : '/api/connection'
        const payload = this.droneConnected ? null : { tipo: this.droneMode === 'sim' ? 'Simulacion' : 'Real' }
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: payload ? { 'Content-Type': 'application/json' } : undefined,
          body: payload ? JSON.stringify(payload) : undefined
        })
        if (!res.ok) throw new Error('Error conectando/desconectando dron')
        const data = await res.json().catch(() => ({}))
        if (this.droneConnected) {
          const disconnected = typeof data.disconnected === 'boolean' ? data.disconnected : true
          this.droneConnected = !disconnected
          if (disconnected) this.droneInAir = false
        } else {
          this.droneConnected = typeof data.connected === 'boolean' ? data.connected : true
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
        this.pc = new RTCPeerConnection({
          iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        })

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
                width: { ideal: 1280 },
                height: { ideal: 720 },
                frameRate: { ideal: 30, max: 30 }
              }
            : {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                frameRate: { ideal: 30, max: 30 }
              },
          audio: false
        })

        const localVideo = this.$refs.localVideo
        if (localVideo) localVideo.srcObject = this.localStream

        this.localStream.getTracks().forEach(track => {
          this.pc.addTrack(track, this.localStream)
        })

        const offer = await this.pc.createOffer()
        await this.pc.setLocalDescription(offer)
        await this.waitForIceGathering(this.pc)

        const offerUrl = (process.env.VUE_APP_WEBRTC_TARGET
          ? `${process.env.VUE_APP_WEBRTC_TARGET.replace(/\/$/, '')}/offer`
          : '/webrtc/offer')

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
      } catch (e) {
        this.cameraError = e.message || 'Error iniciando cámara'
        this.cleanupCamera()
      }
    },

    cleanupCamera() {
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

    waitForIceGathering(pc) {
      return new Promise(resolve => {
        if (pc.iceGatheringState === 'complete') return resolve()
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === 'complete') resolve()
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
        const res = await fetch('/api/goto-admin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lat: this.adminPos.lat,
            lon: this.adminPos.lon,
            h: Number(this.takeoffAlt)
          })
        })
        if (!res.ok) throw new Error('Error enviando GOTO')
        const data = await res.json().catch(() => ({}))
        if (data.ok === false) throw new Error(data.error || 'GOTO fallido')
      } catch (e) {
        this.gotoError = e.message || 'Error enviando GOTO'
      } finally {
        this.gotoLoading = false
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
  grid-template-columns: 260px 1fr;
  gap: 12px;
  height: 24vh;
  min-height: 200px;
  align-items: stretch;
}

.camera-controls {
  display: grid;
  gap: 10px;
  align-content: start;
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
  min-height: 0;
  overflow: hidden;
}

.camera-title {
  font-size: 0.75rem;
  color: #9fb0c5;
  margin-bottom: 6px;
}

.camera-card video {
  width: 100%;
  height: auto;
  max-height: 100%;
  background: #05070a;
  border-radius: 8px;
  display: block;
  object-fit: cover;
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
.btn.goto:hover:not(:disabled) {
  transform: translateY(-2px);
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
