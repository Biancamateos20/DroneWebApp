<template>
  <div class="login-container">
    <h1>Esperando a los demás participantes</h1>

    <div class="spinner"></div>

    <p v-if="registering" class="hint">Registrando ubicación…</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script>
export default {
  name: 'SalaDeEspera',
  emits: ['start-game'],
  props: {
    alias: { type: String, required: true }
  },

  data() {
    return {
      error: null,
      timer: null,
      registering: false,
      registered: false
    }
  },

  async mounted() {
    // 1) Registrar jugador (en móvil es más fiable hacerlo aquí)
    await this.registrarJugador()

    // 2) Polling estado juego
    this.timer = setInterval(this.checkEstadoJuego, 2000)
  },

  beforeUnmount() {
    if (this.timer) clearInterval(this.timer)
  },

  methods: {
    getPosition() {
      return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
          reject(new Error('Tu navegador no soporta geolocalización'))
          return
        }

        navigator.geolocation.getCurrentPosition(
          resolve,
          reject,
          {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
          }
        )
      })
    },

    async registrarJugador() {
      this.error = null
      this.registering = true
      this.registered = false

      try {
        const pos = await this.getPosition()

        const resp = await fetch('/api/jugador', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          keepalive: true,
          body: JSON.stringify({
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            alias: this.alias
          })
        })

        const data = await resp.json().catch(() => ({}))
        if (!resp.ok) throw new Error(data.error || 'Error registrando jugador')

        this.registered = true
      } catch (e) {
        this.error = `No se pudo registrar tu ubicación: ${e.message || e}`
      } finally {
        this.registering = false
      }
    },

    async checkEstadoJuego() {
      // si no se registró, no avances
      if (!this.registered) return

      try {
        // ✅ IMPORTANTE: nada de localhost
        const res = await fetch('/api/estado-juego')
        const data = await res.json()

        if (data.juego_en_curso) {
          clearInterval(this.timer)
          this.$emit('start-game')
        }
      } catch (e) {
        this.error = 'Error comprobando el estado del juego'
      }
    }
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: #000;
  color: white;
}

.spinner {
  margin-top: 30px;
  width: 60px;
  height: 60px;
  border: 6px solid rgba(255, 255, 255, 0.2);
  border-top: 6px solid #00ff88;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.hint {
  margin-top: 18px;
  color: #aaa;
}

.error {
  margin-top: 20px;
  color: #ff4d4d;
  font-weight: bold;
}
</style>
