<template>
  <div class="admin-container">
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

        <div class="panel-actions">
          <button class="btn neutral" @click="connectDrone" :disabled="connectLoading">
            {{ droneConnected ? 'Desconectar' : 'Conectar dron' }}
          </button>

          <button class="btn info" @click="checkGpsPrecision" :disabled="gpsLoading">
            📍 Ver precisión GPS
          </button>

          <button class="btn photo" @click="hacerFoto" :disabled="photoLoading">
            📸 Foto
          </button>

          <button class="btn danger" @click="landOnly" :disabled="landLoading">
            ⬇ Land
          </button>
        </div>

        <div class="gps-box" v-if="gpsAccuracy != null">
          Precisión actual: <strong>{{ gpsAccuracy }} m</strong>
          <span v-if="gpsTimestamp">· {{ gpsTimestamp }}</span>
        </div>
      </section>
    </div>

    <p v-if="loading" class="subtitle">Lanzando misión…</p>
    <p v-if="photoLoading" class="subtitle">Capturando foto…</p>
    <p v-if="landLoading" class="subtitle">Enviando LAND…</p>
    <p v-if="connectLoading" class="subtitle">Conectando dron…</p>
    <p v-if="gpsLoading" class="subtitle">Consultando precisión…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="photoError" class="error">{{ photoError }}</p>
    <p v-if="landError" class="error">{{ landError }}</p>
    <p v-if="gpsError" class="error">{{ gpsError }}</p>

    <div v-if="photoUrl" class="photo-panel">
      <h3>Última foto</h3>
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
      landLoading: false,
      landError: null,

      droneMode: 'sim',
      droneConnected: false,
      connectLoading: false,

      gpsAccuracy: null,
      gpsTimestamp: null,
      gpsLoading: false,
      gpsError: null
    }
  },

  mounted() {
    this.initMap()
    this.initWS()
    this.startPollingFallback()
  },

  beforeUnmount() {
    if (this.photoUrl) URL.revokeObjectURL(this.photoUrl)
    this.live?.disconnect()
    this.stopPollingFallback()
    if (this.map) {
      this.map.remove()
      this.map = null
    }
  },

  methods: {
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
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
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
        const res = await fetch('/api/foto', { method: 'POST' })
        if (!res.ok) throw new Error('Error capturando foto')
        const blob = await res.blob()
        if (this.photoUrl) URL.revokeObjectURL(this.photoUrl)
        this.photoUrl = URL.createObjectURL(blob)
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
      } catch (e) {
        this.landError = e.message || 'Error enviando LAND'
      } finally {
        this.landLoading = false
      }
    },

    async connectDrone() {
      this.error = null
      this.connectLoading = true
      try {
        const action = this.droneConnected ? 'disconnect' : 'connect'
        const res = await fetch('/api/connection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: this.droneMode, action })
        })
        if (!res.ok) throw new Error('Error conectando dron')
        const data = await res.json().catch(() => ({}))
        if (typeof data.connected === 'boolean') {
          this.droneConnected = data.connected
        } else {
          this.droneConnected = !this.droneConnected
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
          const acc = Number(pos.coords.accuracy)
          this.gpsAccuracy = Number.isFinite(acc) ? Math.round(acc) : null
          this.gpsTimestamp = new Date(pos.timestamp).toLocaleTimeString()
          this.gpsLoading = false
        },
        (err) => {
          this.gpsError = err?.message || 'No se pudo leer la precisión'
          this.gpsLoading = false
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
      )
    }
  }
}
</script>

<style scoped>
.admin-container {
  height: 100vh;
  background: radial-gradient(circle at top, #111 0%, #000 60%);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: white;
  text-align: center;
}

.title {
  font-size: 2.4rem;
  font-weight: 600;
  margin-bottom: 5px;
}

.subtitle {
  font-size: 1rem;
  color: #aaa;
  margin-bottom: 30px;
}

.map {
  width: 80%;
  max-width: 900px;
  height: 500px;
  margin-bottom: 40px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 0 40px rgba(0, 0, 0, 0.6);
}

.control-grid {
  width: 80%;
  max-width: 900px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
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

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
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
  min-width: 220px;
  padding: 18px 25px;
  font-size: 1.1rem;
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

.btn.start:hover:not(:disabled),
.btn.photo:hover:not(:disabled),
.btn.stop:hover {
  transform: translateY(-2px);
}

.btn.neutral:hover:not(:disabled),
.btn.info:hover:not(:disabled),
.btn.danger:hover:not(:disabled) {
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

.photo-panel {
  margin-top: 20px;
  width: 80%;
  max-width: 900px;
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

.photo-panel img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 8px;
  border: 1px solid #111;
}
</style>
