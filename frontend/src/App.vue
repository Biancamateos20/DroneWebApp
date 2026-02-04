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
      geoFallbackTimer: null,
      wakeLock: null,
      visibilityHandler: null,

      gamePollTimer: null,
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
        this.stopGamePolling()
        this.screen = 'login'
        this.userAlias = null
      }

      // Estado juego => si admin inicia, pasamos a webrtc desde sala espera
      if ((msg.type === 'game_state' && msg.juego_en_curso === true) || msg.type === 'start') {
        if (this.screen === 'waiting') {
          this.stopGamePolling()
          this.screen = 'webrtc'
        }
      }
    }
  },

  mounted() {
    this.visibilityHandler = () => this.handleVisibilityChange()
    document.addEventListener('visibilitychange', this.visibilityHandler)
  },

  beforeUnmount() {
    this.stopLiveLocation()
    this.live?.disconnect()
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
      this.visibilityHandler = null
    }
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

      // fallback: polling estado juego
      this.startGamePolling()
    },

    handleAdminLogin() {
      this.screen = 'admin'
      this.stopLiveLocation()
      this.stopGamePolling()
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

      this.requestWakeLock()

      const options = {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 20000
      }

      this.watchId = navigator.geolocation.watchPosition(
        (pos) => this.onGeoSuccess(pos),
        (err) => this.onGeoError(err),
        options
      )

      // Primer fix inmediato para que el admin vea el punto al elegir color
      this.primeLocation()

      // Fallback: si watch se duerme, reintenta con getCurrentPosition
      this.startGeoFallbackPoll()
    },

    stopLiveLocation() {
      if (this.watchId != null) {
        navigator.geolocation.clearWatch(this.watchId)
        this.watchId = null
      }
      this.stopGeoFallbackPoll()
      this.releaseWakeLock()
      this.lastSentAt = 0
      this.lastSentCoords = null
    },

    startGamePolling() {
      this.stopGamePolling()
      this.gamePollTimer = setInterval(async () => {
        if (this.screen !== 'waiting') return
        try {
          const res = await fetch('/api/estado-juego')
          if (!res.ok) return
          const data = await res.json()
          if (data?.juego_en_curso === true) {
            this.stopGamePolling()
            this.screen = 'webrtc'
          }
        } catch (e) {
          console.warn('Error consultando estado-juego:', e)
        }
      }, 2000)
    },

    stopGamePolling() {
      if (this.gamePollTimer) clearInterval(this.gamePollTimer)
      this.gamePollTimer = null
    },

    async onGeoSuccess(pos) {
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
      const sentWs = this.live.sendLocation({ lat: latitude, lon: longitude, precision: accuracy })

      // Fallback HTTP solo si el WS no está disponible
      if (!sentWs) {
        await this.sendLocationHttp({ lat: latitude, lon: longitude, precision: accuracy, ts: now })
      }
    },

    onGeoError(err) {
      console.warn('Error geolocalización:', err)
      // reintento suave si el watch se duerme
      if (err && (err.code === 2 || err.code === 3)) {
        this.restartWatchSoon()
      }
    },

    restartWatchSoon() {
      if (this.watchId != null) {
        navigator.geolocation.clearWatch(this.watchId)
        this.watchId = null
      }
      setTimeout(() => this.startLiveLocation(), 2000)
    },

    primeLocation() {
      if (!this.userAlias || !('geolocation' in navigator)) return
      navigator.geolocation.getCurrentPosition(
        (pos) => this.onGeoSuccess(pos),
        (err) => this.onGeoError(err),
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
      )
    },

    startGeoFallbackPoll() {
      this.stopGeoFallbackPoll()
      this.geoFallbackTimer = setInterval(() => {
        if (!this.userAlias) return
        this.primeLocation()
      }, 5000)
    },

    stopGeoFallbackPoll() {
      if (this.geoFallbackTimer) clearInterval(this.geoFallbackTimer)
      this.geoFallbackTimer = null
    },

    handleVisibilityChange() {
      if (document.visibilityState === 'visible') {
        // al volver a primer plano reanudamos tracking
        if (this.userAlias) this.startLiveLocation()
      }
    },

    async requestWakeLock() {
      try {
        if ('wakeLock' in navigator && !this.wakeLock) {
          this.wakeLock = await navigator.wakeLock.request('screen')
          this.wakeLock.addEventListener('release', () => {
            this.wakeLock = null
          })
        }
      } catch (e) {
        console.warn('WakeLock no disponible:', e)
      }
    },

    async releaseWakeLock() {
      try {
        await this.wakeLock?.release()
      } catch (e) {
        // ignore
      } finally {
        this.wakeLock = null
      }
    },

    async sendLocationHttp({ lat, lon, precision, ts }) {
      try {
        await fetch('/api/ubicacion-live', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            alias: this.userAlias,
            lat,
            lon,
            precision,
            ts
          })
        })
      } catch (e) {
        console.warn('Error enviando ubicación HTTP:', e)
      }
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
