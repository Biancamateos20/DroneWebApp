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
      @start-game="goToWebRTC"
    />

    <IniciarJuego
      v-else-if="screen === 'admin'"
    />

    <WebRTC
      v-else-if="screen === 'webrtc'"
    />
  </div>
</template>

<script>
import LoginView from './components/LoginView.vue'
import SalaDeEspera from './components/SalaDeEspera.vue'
import IniciarJuego from './components/IniciarJuego.vue'
import WebRTC from './components/webRTC.vue'

export default {
  name: 'App',

  components: {
    LoginView,
    SalaDeEspera,
    IniciarJuego,
    WebRTC
  },

  data() {
    return {
      screen: 'login',
      userAlias: null,

      watchId: null,
      lastSentAt: 0,
      lastSentCoords: null
    }
  },

  methods: {

    handleLoginSuccess(data) {
      console.log('Login jugador:', data)
      this.userAlias = data.color
      this.screen = 'waiting'

      this.startLiveLocation()
    },

    handleAdminLogin() {
      console.log('Login administrador')
      this.screen = 'admin'
    },

    goToWebRTC() {
      console.log('Juego iniciado → jugadores a WebRTC')
      this.screen = 'webrtc'
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

      if (!('geolocation' in navigator)) {
        console.warn('Geolocalización no soportada')
        return
      }

      if (this.watchId != null) return

      const options = {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 20000
      }

      this.watchId = navigator.geolocation.watchPosition(
        this.onGeoSuccess,
        this.onGeoError,
        options
      )
    },

    stopLiveLocation() {
      if (this.watchId != null) {
        navigator.geolocation.clearWatch(this.watchId)
        this.watchId = null
      }
    },

    async onGeoSuccess(pos) {
      if (!this.userAlias) return

      const { latitude, longitude, accuracy } = pos.coords
      const ts = pos.timestamp || Date.now()

      const THROTTLE_MS = 250
      const MIN_MOVE_M = 0.8
      const now = Date.now()

      if (now - this.lastSentAt < THROTTLE_MS) return

      if (this.lastSentCoords) {
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

      try {
        const r = await fetch('/api/ubicacion-live', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            alias: this.userAlias,
            lat: latitude,
            lon: longitude,
            precision: accuracy,
            ts
          })
        })

        if (!r.ok) {
          await fetch('/api/jugador', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              alias: this.userAlias,
              lat: latitude,
              lon: longitude
            })
          })
        }
      } catch (e) {
        console.warn('Error enviando ubicación:', e)
      }
    },

    onGeoError(err) {
      console.warn('Error geolocalización:', err)
    }
  },

  beforeUnmount() {
    this.stopLiveLocation()
  }
}
</script>

<style>
#app {
  background-color: black;
  min-height: 100vh;
}
</style>
