<template>
  <div id="app">
    <LoginView
      v-if="screen === 'login'"
      @login-success="handleLoginSuccess"
      @admin-login="handleAdminLogin"
    />

    <SalaDeEspera
      v-else-if="screen === 'waiting'"
      :alias="userAlias"
    />

    <IniciarJuego v-else-if="screen === 'admin'" />

    <WebRTC v-else-if="screen === 'webrtc'" />
  </div>
</template>

<script>
import LoginView from './components/LoginView.vue'
import SalaDeEspera from './components/SalaDeEspera.vue'
import IniciarJuego from './components/IniciarJuego.vue'
import WebRTC from './components/webRTC.vue'
import { LiveWS } from './services/liveWS'

export default {
  name: 'App',
  components: { LoginView, SalaDeEspera, IniciarJuego, WebRTC },

  data() {
    return {
      screen: 'login',
      userAlias: null,

      live: null,
      watchId: null,

      lastSentAt: 0,
      lastSentCoords: null
    }
  },

  created() {
    this.live = new LiveWS()

    this.live.onMessage = (msg) => {
      if (!msg) return

      // Reset global => volver a login y parar tracking
      if (msg.type === 'reset') {
        this.stopLiveLocation()
        this.screen = 'login'
        this.userAlias = null
      }

      // Estado juego => si admin inicia, pasamos a webrtc desde sala espera
      if (msg.type === 'game_state' && msg.juego_en_curso === true) {
        if (this.screen === 'waiting') {
          this.screen = 'webrtc'
        }
      }
    }
  },

  beforeUnmount() {
    this.stopLiveLocation()
    this.live?.disconnect()
  },

  methods: {
    handleLoginSuccess(data) {
      this.userAlias = data.color
      this.screen = 'waiting'

      // WS player
      this.live.setAlias(this.userAlias)
      this.live.connect({ role: 'player', alias: this.userAlias })

      // tracking continuo (hasta reset)
      this.startLiveLocation()
    },

    handleAdminLogin() {
      this.screen = 'admin'
      this.stopLiveLocation()
      this.userAlias = null

      // WS admin
      this.live.connect({ role: 'admin' })
    },

    haversineMeters(lat1, lon1, lat2, lon2) {
      const R = 6371000
      const toRad = d => (d * Math.PI) / 180
      const dLat = toRad(lat2 - lat1)
      const dLon = toRad(lon2 - lon1)
      const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
      return 2 * R * Math.asin(Math.sqrt(a))
    },

    startLiveLocation() {
      if (!this.userAlias) return
      if (!('geolocation' in navigator)) return
      if (this.watchId != null) return

      const options = {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 20000
      }

      this.watchId = navigator.geolocation.watchPosition(
        (pos) => this.onGeoSuccess(pos),
        (err) => console.warn('Error geolocalización:', err),
        options
      )
    },

    stopLiveLocation() {
      if (this.watchId != null) {
        navigator.geolocation.clearWatch(this.watchId)
        this.watchId = null
      }
      this.lastSentAt = 0
      this.lastSentCoords = null
    },

    onGeoSuccess(pos) {
      if (!this.userAlias) return

      const { latitude, longitude, accuracy } = pos.coords
      const now = Date.now()

      // Ajustes: muy “Google Maps feel”
      const THROTTLE_MS = 250
      const FORCE_EVERY_MS = 1000
      const MIN_MOVE_M = 0.8

      if (this.lastSentAt && now - this.lastSentAt < THROTTLE_MS) return

      const force = !this.lastSentAt || (now - this.lastSentAt >= FORCE_EVERY_MS)

      if (!force && this.lastSentCoords) {
        const moved = this.haversineMeters(
          this.lastSentCoords.lat,
          this.lastSentCoords.lon,
          latitude,
          longitude
        )
        const improvedAccuracy = accuracy < (this.lastSentCoords.accuracy ?? 1e9)
        if (moved < MIN_MOVE_M && !improvedAccuracy) return
      }

      this.lastSentAt = now
      this.lastSentCoords = { lat: latitude, lon: longitude, accuracy }

      // ✅ enviar por WS
      this.live.sendLocation({ lat: latitude, lon: longitude, precision: accuracy })
    }
  }
}
</script>

<style>
#app {
  background-color: black;
  min-height: 100vh;
}
</style>
