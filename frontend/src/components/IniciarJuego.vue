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

export default {
  name: 'IniciarJuego',

  data() {
    return {
      map: null,
      error: null,
      loading: false,

      // markers[alias] = { dot: L.CircleMarker, acc: L.Circle }
      markers: {},

      polling: null,
      mapReady: false,

      layerEsri: null,
      layerPnoaProvWms: null
    }
  },

  mounted() {
    this.initMap()
  },

  beforeUnmount() {
    if (this.polling) clearInterval(this.polling)
    this.polling = null

    if (this.map) {
      this.map.remove()
      this.map = null
    }
  },

  methods: {
    initMap() {
      const container = L.DomUtil.get('map')
      if (container) container._leaflet_id = null

      if (!navigator.geolocation) {
        this.error = 'Geolocalización no soportada'
        return
      }

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = pos.coords.latitude
          const lon = pos.coords.longitude

          // maxZoom 19 evita “zoom falso” borroso en WMS
          this.map = L.map('map', { maxZoom: 19 }).setView([lat, lon], 18.5)

          // ====== BASES ======
          this.layerEsri = L.tileLayer(
            'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { maxZoom: 19, attribution: 'Tiles © Esri' }
          )

          this.layerPnoaProvWms = L.tileLayer.wms(
            'https://wms-pnoa.idee.es/pnoa-provisionales',
            {
              layers: 'OrtoimagenRapida',
              format: 'image/jpeg', // prueba image/png si quieres, pesa más
              transparent: false,
              tileSize: 512,
              detectRetina: true,
              maxZoom: 19,
              attribution: '© IGN PNOA (Provisional)'
            }
          )

          // Por defecto: PNOA Provisional (tu más actual)
          this.layerPnoaProvWms.addTo(this.map)

          L.control
            .layers(
              {
                'IGN PNOA Provisional (OrtoimagenRapida)': this.layerPnoaProvWms,
                'Esri World Imagery': this.layerEsri
              },
              null,
              { position: 'topright' }
            )
            .addTo(this.map)

          this.mapReady = true
          this.cargarJugadores()
          this.startPolling()
        },
        () => {
          this.error = 'No se pudo obtener la ubicación'
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
      )
    },

    startPolling() {
      if (this.polling) clearInterval(this.polling)

      // 500ms = sensación “Google Maps” (sin websockets)
      this.polling = setInterval(() => {
        if (this.mapReady) this.cargarJugadores()
      }, 500)
    },

    ensurePlayerLayers(aliasColor, latlng) {
      // aliasColor en tu sistema == color hex
      const color = aliasColor

      if (this.markers[aliasColor]) return this.markers[aliasColor]

      const dot = L.circleMarker(latlng, {
        radius: 7,
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

    async cargarJugadores() {
      if (!this.mapReady || !this.map) return

      try {
        const res = await fetch('/api/jugadores')
        if (!res.ok) return
        const jugadores = await res.json()
        if (!Array.isArray(jugadores)) return

        const now = Date.now()
        const OFFLINE_MS = 8000 // si no actualiza en 8s => offline (pero NO se borra)

        jugadores.forEach((j) => {
          if (!j || j.lat == null || j.lon == null || !j.alias) return

          const lat = Number(j.lat)
          const lon = Number(j.lon)
          if (Number.isNaN(lat) || Number.isNaN(lon)) return

          const alias = j.alias              // en tu caso alias = color
          const pos = [lat, lon]
          const precision = Number(j.precision ?? 0)
          const ts = Number(j.ts ?? 0)

          const age = ts ? now - ts : 0
          const offline = ts ? age > OFFLINE_MS : false

          const layers = this.ensurePlayerLayers(alias, pos)

          // mueve el “punto” y el círculo
          layers.dot.setLatLng(pos)
          layers.acc.setLatLng(pos)

          // radio de precisión (cap para no tapar todo)
          const capped = !Number.isNaN(precision) && precision > 0 ? Math.min(precision, 200) : 5
          layers.acc.setRadius(capped)

          // offline => baja opacidad, pero NO desaparece
          layers.dot.setStyle({
            opacity: offline ? 0.35 : 1,
            fillOpacity: offline ? 0.25 : 0.95
          })

          layers.acc.setStyle({
            opacity: offline ? 0.2 : 1,
            fillOpacity: offline ? 0.05 : 0.15
          })
        })
      } catch (e) {
        console.error('Error cargando jugadores', e)
      }
    },

    async iniciarJuego() {
      this.error = null
      this.loading = true

      try {
        const res = await fetch('/api/iniciar-juego', { method: 'POST' })
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.error || 'Error al iniciar el juego')
        }
      } catch (e) {
        this.error = e.message
      } finally {
        this.loading = false
      }
    },

    async pararJuego() {
      this.error = null
      try {
        await fetch('/api/reset', { method: 'POST' })

        // limpia todo en el mapa solo aquí (reset)
        Object.values(this.markers).forEach(({ dot, acc }) => {
          dot.remove()
          acc.remove()
        })
        this.markers = {}
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
