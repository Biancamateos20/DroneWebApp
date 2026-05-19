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

    <WebRTC
      v-else-if="screen === 'webrtc'"
      :user-alias="userAlias"
      :drone-in-air="droneInAir"
      :active-player-alias="activePlayerAlias"
      :selected-next-player-alias="selectedNextPlayerAlias"
      :photo-taken-alias="photoTakenAlias"
      @pick-next-player="handleNextPlayerSelected"
    />
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
      lastSentCoords: null,
      lastHttpLiveSentAt: 0,
      httpLiveSending: false,

      droneInAir: false,
      activePlayerAlias: null,
      selectedNextPlayerAlias: null,
      photoTakenAlias: null,

      lastStartId: null,
      lastResetId: null
    }
  },

  created() {
    this.live = new LiveWS()

    this.live.onMessage = (msg) => {
      if (!msg) return

      // Reset global => volver a login y parar tracking
      if (msg.type === 'reset') {
        this.handleReset()
      }

      if (msg.type === 'game_state') {
        this.applyGameState(msg)
      }

      // Estado juego => si admin inicia, pasamos a webrtc desde sala espera
      if ((msg.type === 'game_state' && msg.juego_en_curso === true) || msg.type === 'start') {
        if (this.screen === 'waiting') {
          const startId = Number(msg.game_start_id ?? msg.start_id ?? 0)
          if (this.shouldStartWithId(startId)) {
            this.markStartSeen(startId)
            this.screen = 'webrtc'
          }
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
    async handleLoginSuccess(data) {
      this.userAlias = data.color
      this.screen = 'waiting'

      // Primero sincronizamos reset/start actuales antes de mandar la primera ubicación.
      await this.syncGameStateOnJoin()

      const initialLocation = data?.initialLocation || null
      const initialLat = Number(initialLocation?.lat)
      const initialLon = Number(initialLocation?.lon)
      const initialPrecision = Number(initialLocation?.precision)
      const hasInitialLocation = Number.isFinite(initialLat) && Number.isFinite(initialLon)

      if (hasInitialLocation) {
        const now = Date.now()
        const playerId = this.live?.session?.playerId
        this.lastSentAt = now
        this.lastSentCoords = {
          lat: initialLat,
          lon: initialLon,
          accuracy: Number.isFinite(initialPrecision) ? initialPrecision : null
        }

        try {
          await fetch('/api/jugador', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              alias: this.userAlias,
              playerId,
              lat: initialLat,
              lon: initialLon,
              precision: Number.isFinite(initialPrecision) ? initialPrecision : null,
              resetId: this.getLastResetSeen() || 0,
              ts: now
            })
          })
        } catch (e) {
          console.warn('Error registrando jugador inicial:', e)
        }

        this.sendLocationHttpFallback({
          lat: initialLat,
          lon: initialLon,
          precision: Number.isFinite(initialPrecision) ? initialPrecision : null,
          ts: now
        })
      }

      // Registrar jugador por HTTP (necesario si no hay WS)
      if (!hasInitialLocation) {
        this.registerPlayerHttp()
      }

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
      this.lastHttpLiveSentAt = 0
      this.httpLiveSending = false
    },

    startGamePolling() {
      this.stopGamePolling()
      this.gamePollTimer = setInterval(async () => {
        if (this.screen !== 'waiting' && this.screen !== 'webrtc') return
        try {
          const res = await fetch('/api/estado-juego')
          if (!res.ok) return
          const data = await res.json()
          const resetId = Number(data.reset_id ?? 0)
          if (this.shouldResetWithId(resetId)) {
            this.markResetSeen(resetId)
            this.handleReset()
            return
          }
          this.applyGameState(data)
          if (this.screen === 'waiting' && data?.juego_en_curso === true) {
            const startId = Number(data.game_start_id ?? 0)
            if (this.shouldStartWithId(startId)) {
              this.markStartSeen(startId)
              this.screen = 'webrtc'
            }
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

    onGeoSuccess(pos) {
      if (!this.userAlias) return

      const { latitude, longitude, accuracy } = pos.coords
      const now = Date.now()

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

      const payload = {
        lat: latitude,
        lon: longitude,
        precision: accuracy,
        ts: now
      }

      // Enviamos por WS si está disponible, pero el backend HTTP es la fuente fiable del mapa.
      this.live.sendLocation(payload)
      this.sendLocationHttpFallback(payload)
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

    registerPlayerHttp() {
      const alias = this.userAlias
      if (!alias || !('geolocation' in navigator)) return
      const playerId = this.live?.session?.playerId
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lat = Number(pos.coords.latitude)
          const lon = Number(pos.coords.longitude)
          if (Number.isNaN(lat) || Number.isNaN(lon)) return
          try {
            await fetch('/api/jugador', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                alias,
                playerId,
                lat,
                lon,
                resetId: this.getLastResetSeen() || 0,
                ts: Date.now()
              })
            })
          } catch (e) {
            console.warn('Error registrando jugador HTTP:', e)
          }
        },
        (err) => {
          console.warn('Error obteniendo ubicación para registro:', err)
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
      )
    },

    sendLocationHttpFallback({ lat, lon, precision, ts }) {
      if (!this.userAlias) return
      const targetLat = Number(lat)
      const targetLon = Number(lon)
      if (!Number.isFinite(targetLat) || !Number.isFinite(targetLon)) return

      const now = Date.now()
      const MIN_HTTP_INTERVAL_MS = 350
      if (this.lastHttpLiveSentAt && now - this.lastHttpLiveSentAt < MIN_HTTP_INTERVAL_MS) return
      if (this.httpLiveSending && now - this.lastHttpLiveSentAt < 2000) return

      this.lastHttpLiveSentAt = now
      this.httpLiveSending = true

      const playerId = this.live?.session?.playerId
      fetch('/api/ubicacion-live', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          alias: this.userAlias,
          playerId,
          resetId: this.getLastResetSeen() || 0,
          lat: targetLat,
          lon: targetLon,
          precision,
          ts: Number.isFinite(ts) ? ts : now
        })
      })
        .catch((e) => {
          console.warn('Error enviando ubicación live por HTTP:', e)
        })
        .finally(() => {
          this.httpLiveSending = false
        })
    },

    async syncGameStateOnJoin() {
      try {
        const res = await fetch('/api/estado-juego')
        if (!res.ok) return
        const data = await res.json()
        const startId = Number(data.game_start_id ?? 0)
        if (Number.isFinite(startId) && startId >= 0) {
          this.markStartSeen(startId)
        }
        const resetId = Number(data.reset_id ?? 0)
        if (Number.isFinite(resetId) && resetId >= 0) {
          this.markResetSeen(resetId)
        }
        this.applyGameState(data)
      } catch (e) {
        console.warn('Error sincronizando estado juego:', e)
      }
    },

    applyGameState(data) {
      if (!data || typeof data !== 'object') return

      if (typeof data.dron_despegado === 'boolean') {
        this.droneInAir = data.dron_despegado
      }

      if ('jugador_actual_alias' in data) {
        const alias = data.jugador_actual_alias == null
          ? null
          : (String(data.jugador_actual_alias).trim().toUpperCase() || null)
        this.activePlayerAlias = alias
      }

      if ('siguiente_jugador_alias' in data) {
        const alias = data.siguiente_jugador_alias == null
          ? null
          : (String(data.siguiente_jugador_alias).trim().toUpperCase() || null)
        this.selectedNextPlayerAlias = alias
      }

      if ('foto_tomada_alias' in data) {
        const alias = data.foto_tomada_alias == null
          ? null
          : (String(data.foto_tomada_alias).trim().toUpperCase() || null)
        this.photoTakenAlias = alias
      }

      if (this.screen === 'waiting' && this.droneInAir) {
        this.screen = 'webrtc'
      }
    },

    async handleNextPlayerSelected(alias) {
      const nextAlias = alias == null ? null : (String(alias).trim().toUpperCase() || null)
      if (!nextAlias) return

      this.selectedNextPlayerAlias = nextAlias

      try {
        await fetch('/api/estado-juego', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            siguiente_jugador_alias: nextAlias
          })
        })
      } catch (e) {
        console.warn('Error guardando siguiente jugador:', e)
      }
    },

    shouldStartWithId(startId) {
      if (!startId) return false
      const last = this.getLastStartSeen()
      return last == null || startId > last
    },

    getLastStartSeen() {
      if (this.lastStartId != null) return this.lastStartId
      const raw = localStorage.getItem('last_start_id_v1')
      const n = raw != null ? Number(raw) : null
      this.lastStartId = Number.isFinite(n) ? n : null
      return this.lastStartId
    },

    markStartSeen(startId) {
      if (!Number.isFinite(startId) || startId < 0) return
      this.lastStartId = startId
      localStorage.setItem('last_start_id_v1', String(startId))
    },

    shouldResetWithId(resetId) {
      if (!resetId) return false
      const last = this.getLastResetSeen()
      return last == null || resetId > last
    },

    getLastResetSeen() {
      if (this.lastResetId != null) return this.lastResetId
      const raw = localStorage.getItem('last_reset_id_v1')
      const n = raw != null ? Number(raw) : null
      this.lastResetId = Number.isFinite(n) ? n : null
      return this.lastResetId
    },

    markResetSeen(resetId) {
      if (!Number.isFinite(resetId) || resetId < 0) return
      this.lastResetId = resetId
      localStorage.setItem('last_reset_id_v1', String(resetId))
    },

    handleReset() {
      this.stopLiveLocation()
      this.stopGamePolling()
      this.live?.disconnect()
      this.screen = 'login'
      this.userAlias = null
      this.droneInAir = false
      this.activePlayerAlias = null
      this.selectedNextPlayerAlias = null
      this.photoTakenAlias = null
      this.lastSentAt = 0
      this.lastSentCoords = null
      this.lastHttpLiveSentAt = 0
      this.httpLiveSending = false
      try {
        localStorage.removeItem('player_session_v1')
      } catch (e) {
        // ignore
      }
    }
  }
}
</script>

<style>
html,
body {
  margin: 0;
  padding: 0;
  min-height: 100%;
  background-color: black;
  overflow-x: hidden;
}

#app {
  background-color: black;
  min-height: 100vh;
  min-height: 100svh;
  width: 100%;
}
</style>
