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

    <IniciarJuego v-else-if="screen === 'admin'" />

    <WebRTC v-else-if="screen === 'webrtc'" />
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
      lastSentCoords: null,

      // solo para detectar el reset del admin
      estadoPoll: null,
      lastResetId: null
    }
  },

  methods: {
    async handleLoginSuccess(data) {
      console.log('Login jugador:', data)
      this.userAlias = data.color
      this.screen = 'waiting'

      // 1) lee estado al entrar (para guardar reset_id actual)
      await this.syncEstadoJuegoOnce()

      // 2) registra al jugador INMEDIATAMENTE para que aparezca ya en el mapa admin
      await this.registerPlayerOnce()

      // 3) arranca live + polling de reset
      this.startLiveLocation()
      this.startEstadoJuegoPolling()
    },

    handleAdminLogin() {
      console.log('Login administrador')
      this.screen = 'admin'

      // al ser admin, no rastreamos como jugador
      this.stopLiveLocation()
      this.stopEstadoJuegoPolling()
      this.userAlias = null
    },

    goToWebRTC() {
      console.log('Juego iniciado → jugadores a WebRTC')
      this.screen = 'webrtc'
      // No paramos el tracking: debe seguir hasta reset del admin
    },

    // ---------------------------
    // Estado juego: solo nos importa reset_id
    // ---------------------------
    async syncEstadoJuegoOnce() {
      try {
        const r = await fetch('/api/estado-juego')
        if (!r.ok) return
        const data = await r.json()
        if (typeof data.reset_id === 'number') {
          this.lastResetId = data.reset_id
        }
      } catch {
        // silencioso
      }
    },

    startEstadoJuegoPolling() {
      if (this.estadoPoll) return

      this.estadoPoll = setInterval(async () => {
        try {
          const r = await fetch('/api/estado-juego')
          if (!r.ok) return
          const data = await r.json()

          // Si cambia reset_id => admin ha pulsado Parar/Reset
          if (typeof data.reset_id === 'number' && this.lastResetId != null) {
            if (data.reset_id !== this.lastResetId) {
              console.log('Detectado RESET del admin → paro ubicación live')
              this.stopLiveLocation()
              this.stopEstadoJuegoPolling()
              // opcional: volver a login automáticamente
              this.screen = 'login'
              this.userAlias = null
            }
          }

          if (typeof data.reset_id === 'number') {
            this.lastResetId = data.reset_id
          }
        } catch {
          // silencioso
        }
      }, 1000)
    },

    stopEstadoJuegoPolling() {
      if (this.estadoPoll) {
        clearInterval(this.estadoPoll)
        this.estadoPoll = null
      }
    },

    // ---------------------------
    // Registro inmediato para que el admin lo vea YA
    // ---------------------------
    async registerPlayerOnce() {
      if (!this.userAlias) return
      if (!('geolocation' in navigator)) return

      const pos = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
          resolve,
          reject,
          { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        )
      }).catch(() => null)

      if (!pos) return

      const { latitude, longitude } = pos.coords

      try {
        await fetch('/api/jugador', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            alias: this.userAlias,
            lat: latitude,
            lon: longitude
          })
        })
      } catch {
        // silencioso
      }
    },

    // ---------------------------
    // Geo utils
    // ---------------------------
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

    // ---------------------------
    // Live location (SIEMPRE hasta reset)
    // ---------------------------
    startLiveLocation() {
      if (!this.userAlias) return
      if (!('geolocation' in navigator)) return
      if (this.watchId != null) return

      const options = {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 20000
      }

      // arrow functions para no perder this
      this.watchId = navigator.geolocation.watchPosition(
        (pos) => this.onGeoSuccess(pos),
        (err) => this.onGeoError(err),
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

async onGeoSuccess(pos) {
  if (!this.userAlias) return

  const { latitude, longitude, accuracy } = pos.coords
  const ts = pos.timestamp || Date.now()

  const now = Date.now()

  // Ajustes
  const THROTTLE_MS = 250
  const FORCE_EVERY_MS = 1000
  const MIN_MOVE_M = 0.8

  // Throttle duro
  if (this.lastSentAt && now - this.lastSentAt < THROTTLE_MS) return

  // Envío forzado cada X ms (para que el admin vea updates constantes)
  const force = !this.lastSentAt || (now - this.lastSentAt >= FORCE_EVERY_MS)

  // Si no es "force", aplicamos filtro de movimiento/precisión
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

    // Fallback: si no estaba registrado aún, lo registramos
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
    this.stopEstadoJuegoPolling()
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
