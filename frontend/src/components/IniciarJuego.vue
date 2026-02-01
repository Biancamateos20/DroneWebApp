<template>
  <div class="admin-container">
    <h1 class="title">Panel de Control</h1>
    <p class="subtitle">Administrador de la partida</p>

    <div id="map" class="map"></div>

    <div class="buttons">
      <button class="btn start" @click="iniciarJuego" :disabled="loading">
        ▶ Iniciar juego
      </button>

      <button class="btn stop" @click="pararJuego">
        ■ Parar juego
      </button>
    </div>

    <p v-if="loading" class="subtitle">Lanzando misión…</p>
    <p v-if="error" class="error">{{ error }}</p>
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

      live: null
    }
  },

  mounted() {
    this.initMap()
    this.initWS()
  },

  beforeUnmount() {
    this.live?.disconnect()
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

    async iniciarJuego() {
      this.error = null
      this.loading = true
      try {
        // Si tienes un backend real para misión, lo llamas aquí.
        // En Pages puro, /api/iniciar-juego no existe salvo que lo implementes como Function.
        // Si ahora mismo NO tienes backend público, comenta estas dos líneas:
        // const res = await fetch('/api/iniciar-juego', { method: 'POST' })
        // if (!res.ok) throw new Error('Error al iniciar juego')

        // ✅ Esto sí es lo importante para la app:
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
        // Igual: si existe endpoint público para reset real, lo llamas aquí.
        // await fetch('/api/reset', { method: 'POST' }).catch(() => {})

        // ✅ Reset global del live:
        this.live.reset()
        this.clearMarkers()
      } catch {
        this.error = 'Error al parar el juego'
      }
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

.buttons {
  display: flex;
  gap: 40px;
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

.btn.start:hover:not(:disabled),
.btn.stop:hover {
  transform: translateY(-2px);
}

.error {
  margin-top: 30px;
  color: #ff6b6b;
  font-weight: 600;
}
</style>
