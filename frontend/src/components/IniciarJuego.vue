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
      markers: {}, // { [alias]: L.Marker }
      polling: null,
      mapReady: false,

      // capas base
      layerEsri: null,
      layerPnoaProvWms: null,

      // ---- MI UBICACIÓN (ADMIN) ----
      myWatchId: null,
      myMarker: null,
      myAccuracyCircle: null,
      followMe: true // ponlo a false si NO quieres que el mapa te siga
    }
  },

  mounted() {
    this.initMap()
  },

  beforeUnmount() {
    if (this.polling) clearInterval(this.polling)
    this.polling = null

    this.stopMyLocationWatch()

    if (this.map) {
      this.map.remove()
      this.map = null
    }
  },

  methods: {
    createPinIcon(color) {
      const svg = `
        <svg width="36" height="36" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 22s7-5.2 7-12a7 7 0 1 0-14 0c0 6.8 7 12 7 12z"
                fill="${color}" stroke="white" stroke-width="1.5" />
          <circle cx="12" cy="10" r="2.7" fill="white" opacity="0.9"/>
        </svg>
      `
      return L.divIcon({
        className: 'player-pin',
        html: svg,
        iconSize: [36, 36],
        iconAnchor: [18, 34],
        popupAnchor: [0, -30]
      })
    },

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

          // maxZoom 19 para evitar “zoom falso” borroso
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
              format: 'image/jpeg',
              transparent: false,
              tileSize: 512,
              detectRetina: true,
              maxZoom: 19,
              attribution: '© IGN PNOA (Provisional)'
            }
          )

          // Por defecto: la más actual (según tu caso)
          this.layerPnoaProvWms.addTo(this.map)

          L.control.layers(
            {
              'IGN PNOA Provisional (OrtoimagenRapida)': this.layerPnoaProvWms,
              'Esri World Imagery': this.layerEsri
            },
            null,
            { position: 'topright' }
          ).addTo(this.map)

          // ====== MI UBICACIÓN EN TIEMPO REAL ======
          this.startMyLocationWatch()

          // ====== JUGADORES ======
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

    // --------- WATCH ADMIN LOCATION ---------
    startMyLocationWatch() {
      if (!('geolocation' in navigator)) return
      if (this.myWatchId != null) return

      const options = {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 20000
      }

      this.myWatchId = navigator.geolocation.watchPosition(
        this.onMyGeoSuccess,
        this.onMyGeoError,
        options
      )
    },

    stopMyLocationWatch() {
      if (this.myWatchId != null) {
        navigator.geolocation.clearWatch(this.myWatchId)
        this.myWatchId = null
      }

      if (this.myMarker) {
        this.myMarker.remove()
        this.myMarker = null
      }

      if (this.myAccuracyCircle) {
        this.myAccuracyCircle.remove()
        this.myAccuracyCircle = null
      }
    },

    onMyGeoSuccess(pos) {
      if (!this.map) return

      const { latitude, longitude, accuracy } = pos.coords
      const latlng = [latitude, longitude]

      // Marker “yo” (azul) + círculo de precisión
      if (!this.myMarker) {
        this.myMarker = L.circleMarker(latlng, {
          radius: 7,
          weight: 2,
          color: '#ffffff',
          fillColor: '#2e86ff',
          fillOpacity: 0.9
        })
          .addTo(this.map)
          .bindPopup('Mi ubicación (admin)')
      } else {
        this.myMarker.setLatLng(latlng)
      }

      if (!this.myAccuracyCircle) {
        this.myAccuracyCircle = L.circle(latlng, {
          radius: Math.max(accuracy || 0, 1),
          weight: 1,
          color: '#2e86ff',
          fillColor: '#2e86ff',
          fillOpacity: 0.15
        }).addTo(this.map)
      } else {
        this.myAccuracyCircle.setLatLng(latlng)
        this.myAccuracyCircle.setRadius(Math.max(accuracy || 0, 1))
      }

      // Si quieres que el mapa te siga
      if (this.followMe) {
        this.map.panTo(latlng, { animate: true })
      }
    },

    onMyGeoError(err) {
      console.warn('Error geolocalización (admin):', err)
      // No lo pongo en UI para que no moleste, pero si quieres:
      // this.error = 'Error geolocalización (admin)'
    },

    // --------- POLLING JUGADORES ---------
    startPolling() {
      if (this.polling) clearInterval(this.polling)
      this.polling = setInterval(() => {
        if (this.mapReady) this.cargarJugadores()
      }, 2000)
    },

    async cargarJugadores() {
      if (!this.mapReady || !this.map) return

      try {
        const res = await fetch('/api/jugadores')
        if (!res.ok) return
        const jugadores = await res.json()
        if (!Array.isArray(jugadores)) return

        const vivos = new Set(
          jugadores.map((j) => j?.alias).filter((a) => typeof a === 'string' && a.length > 0)
        )

        Object.keys(this.markers).forEach((alias) => {
          if (!vivos.has(alias)) {
            this.markers[alias].remove()
            delete this.markers[alias]
          }
        })

        jugadores.forEach((j) => {
          if (!j || j.lat == null || j.lon == null || !j.alias) return

          const pos = [Number(j.lat), Number(j.lon)]
          if (Number.isNaN(pos[0]) || Number.isNaN(pos[1])) return

          if (this.markers[j.alias]) {
            this.markers[j.alias].setLatLng(pos)
            return
          }

          // Mantengo tu lógica: alias actúa como color (si alias es un nombre, usa j.color)
          const icon = this.createPinIcon(j.alias)

          const marker = L.marker(pos, { icon })
            .addTo(this.map)
            .bindPopup(`Jugador ${j.alias}`)

          this.markers[j.alias] = marker
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
        Object.values(this.markers).forEach((m) => m.remove())
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

.btn.start:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 10px 30px rgba(0, 255, 136, 0.35);
}

.btn.start:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn.stop {
  background: linear-gradient(135deg, #ff4d4d, #d63031);
  color: white;
}

.btn.stop:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 30px rgba(255, 77, 77, 0.35);
}

.error {
  margin-top: 30px;
  color: #ff6b6b;
  font-weight: 600;
}

:deep(.player-pin) {
  background: transparent;
  border: none;
}
</style>
