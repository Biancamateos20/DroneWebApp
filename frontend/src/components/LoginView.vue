<template>
  <div class="login-shell">
    <div class="bg">
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
      <span class="orb orb-c"></span>
      <div class="grid"></div>
    </div>

    <!-- BOTÓN ADMIN -->
    <button class="admin-button" type="button" @click="showAdmin = true">
      Administrador
    </button>

    <div class="login-container">
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">Drone Mission Control</p>
          <h1>Elige tu alias de color</h1>
          <p class="lead">
            Los colores ocupados desaparecen en tiempo real para el resto de jugadores.
            Elige el tuyo y entra en la sala de espera.
          </p>

          <div class="stats">
            <div class="stat">
              <span class="stat-value">{{ visibleColors.length }}</span>
              <span class="stat-label">colores libres</span>
            </div>
            <div class="stat">
              <span class="stat-value">{{ occupiedCount }}</span>
              <span class="stat-label">ocupados</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2>Paleta activa</h2>
            <p>Haz clic en un color para reservarlo.</p>
          </div>

          <div class="palette" :class="{ locked: picked }">
            <button
              v-for="color in visibleColors"
              :key="color"
              class="color-chip"
              type="button"
              :style="{ '--chip': color }"
              :disabled="picked"
              @pointerdown.prevent="onPickColor(color)"
              @touchstart.prevent="onPickColor(color)"
              @click.prevent="onPickColor(color)"
              :aria-label="`Elegir ${color}`"
            >
              <span class="chip-core"></span>
              <span class="chip-glow"></span>
            </button>

            <div v-if="visibleColors.length === 0" class="palette-empty">
              Sin colores disponibles. Espera a que alguien libere uno.
            </div>
          </div>

          <p v-if="error" class="error">{{ error }}</p>

          <div class="panel-footer">
            <span class="dot"></span>
            <span>Sincronizado en tiempo real</span>
          </div>
        </div>
      </section>
    </div>
  </div>

  <!-- MODAL ADMIN -->
  <div v-if="showAdmin" class="modal-overlay">
    <div class="modal">
      <h2>Acceso Administrador</h2>

      <form class="admin-form" @submit.prevent="adminLogin" @keydown.enter.prevent="triggerAdminEnter">
        <div class="admin-pass-wrap">
          <input
            v-model="adminPassword"
            :type="adminPasswordVisible ? 'text' : 'password'"
            placeholder="Contraseña"
            @keydown.enter.prevent="triggerAdminEnter"
          />
          <button
            type="button"
            class="toggle-pass"
            @click="adminPasswordVisible = !adminPasswordVisible"
          >
            {{ adminPasswordVisible ? 'Ocultar' : 'Ver' }}
          </button>
        </div>

        <div class="modal-actions">
          <button ref="adminEnterBtn" type="submit">Entrar</button>
          <button type="button" class="cancel" @click="showAdmin = false">Cancelar</button>
        </div>
      </form>

      <p v-if="adminError" class="error">{{ adminError }}</p>
    </div>
  </div>
</template>

<script>
import { LiveWS } from '../services/liveWS'

export default {
  name: 'LoginView',
  emits: ['login-success', 'admin-login'],

  data() {
    return {
      error: null,

      showAdmin: false,
      adminPassword: '',
      adminPasswordVisible: false,
      adminError: null,

      colors: [
        '#1E90FF', '#FF0000', '#32CD32', '#FFD700',
        '#800080', '#FF1493', '#00CED1', '#FF8C00'
      ],
      coloresOcupados: [],
      occupancyPollTimer: null,

      picked: false,
      live: null
    }
  },

  computed: {
    normalizedColors() {
      return this.colors.map(c => this.normalizeColor(c))
    },
    occupiedCount() {
      return this.coloresOcupados.length
    },
    visibleColors() {
      return this.normalizedColors.filter(c => !this.coloresOcupados.includes(c))
    }
  },

  mounted() {
    // Conexión ligera para recibir occupancy
    this.live = new LiveWS()
    this.live.onMessage = (msg) => {
      if (msg?.type === 'occupancy' && Array.isArray(msg.aliases)) {
        this.setOccupiedColors(msg.aliases)
      }
      if (msg?.type === 'reset') {
        this.setOccupiedColors([])
        this.picked = false
      }
    }
    this.live.connect({ role: 'player' })
    this.refreshOccupiedFromHttp()
    this.startOccupancyPolling()
  },

  beforeUnmount() {
    this.stopOccupancyPolling()
    this.live?.disconnect()
  },

  methods: {
    normalizeColor(value) {
      if (typeof value !== 'string') return ''
      return value.trim().toUpperCase()
    },

    setOccupiedColors(rawAliases) {
      const allowed = new Set(this.normalizedColors)
      const normalized = (Array.isArray(rawAliases) ? rawAliases : [])
        .map(a => this.normalizeColor(a))
        .filter(a => !!a && allowed.has(a))
      this.coloresOcupados = Array.from(new Set(normalized))
    },

    async refreshOccupiedFromHttp() {
      try {
        const res = await fetch('/api/colores', { cache: 'no-store' })
        if (res.ok) {
          const aliases = await res.json()
          this.setOccupiedColors(aliases)
          return
        }
      } catch (e) {
        // fallback below
      }

      try {
        const res = await fetch('/api/jugadores', { cache: 'no-store' })
        if (!res.ok) return
        const players = await res.json()
        if (!Array.isArray(players)) return
        const aliases = players.map(p => p?.alias)
        this.setOccupiedColors(aliases)
      } catch (e) {
        // si no hay backend accesible, mantenemos último estado conocido
      }
    },

    startOccupancyPolling() {
      this.stopOccupancyPolling()
      this.occupancyPollTimer = setInterval(() => {
        // Si WS no está operativo, polling mantiene la lista y el contador al día.
        if (!(this.live?.enabled && this.live?.isOpen)) {
          this.refreshOccupiedFromHttp()
        }
      }, 1500)
    },

    stopOccupancyPolling() {
      if (this.occupancyPollTimer) clearInterval(this.occupancyPollTimer)
      this.occupancyPollTimer = null
    },

    onPickColor(color) {
      if (this.picked) return
      this.picked = true
      this.error = null
      const normalizedColor = this.normalizeColor(color)

      // si en ese microsegundo se ocupó, evita elegirlo
      if (this.coloresOcupados.includes(normalizedColor)) {
        this.error = 'Color ocupado, elige otro'
        this.picked = false
        return
      }

      this.$emit('login-success', { color: normalizedColor })
    },

    adminLogin() {
      this.adminError = null
      if (this.adminPassword !== 'admin123') {
        this.adminError = 'Contraseña incorrecta'
        return
      }
      this.showAdmin = false
      this.$emit('admin-login')
    },

    triggerAdminEnter() {
      const btn = this.$refs.adminEnterBtn
      if (btn && typeof btn.click === 'function') {
        btn.click()
        return
      }
      this.adminLogin()
    }
  }
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Rajdhani:wght@500;600&display=swap');

.login-shell {
  min-height: 100vh;
  min-height: 100dvh;
  color: #eef1f6;
  font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
  position: relative;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(transparent 94%, rgba(255, 255, 255, 0.04) 100%),
    linear-gradient(90deg, transparent 94%, rgba(255, 255, 255, 0.04) 100%);
  background-size: 36px 36px;
  opacity: 0.4;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(30px);
  opacity: 0.7;
}

.orb-a {
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(0, 224, 255, 0.55), transparent 70%);
  top: -120px;
  left: -120px;
}

.orb-b {
  width: 520px;
  height: 520px;
  background: radial-gradient(circle, rgba(255, 131, 77, 0.45), transparent 70%);
  bottom: -180px;
  right: -160px;
}

.orb-c {
  width: 280px;
  height: 280px;
  background: radial-gradient(circle, rgba(111, 255, 167, 0.35), transparent 70%);
  top: 30%;
  right: 10%;
}

.admin-button {
  position: absolute;
  top: 22px;
  right: 24px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: rgba(7, 11, 18, 0.65);
  color: #f2f4f8;
  padding: 10px 16px;
  border-radius: 999px;
  font-size: 0.85rem;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  cursor: pointer;
  z-index: 5;
  backdrop-filter: blur(6px);
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.login-container {
  position: relative;
  z-index: 2;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px 6vw 50px;
}

.hero {
  width: min(1100px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 36px;
  align-items: center;
}

.hero-copy {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.eyebrow {
  font-family: 'Rajdhani', sans-serif;
  text-transform: uppercase;
  letter-spacing: 2px;
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.7);
  margin: 0;
}

.hero-copy h1 {
  font-size: clamp(2.2rem, 4vw, 3.4rem);
  line-height: 1.05;
  margin: 0;
}

.lead {
  margin: 0;
  color: rgba(240, 244, 250, 0.75);
  font-size: 1.05rem;
}

.stats {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}

.stat {
  background: rgba(10, 14, 22, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 12px 16px;
  min-width: 130px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  backdrop-filter: blur(8px);
}

.stat-value {
  font-size: 1.4rem;
  font-weight: 600;
}

.stat-label {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.6);
}

.panel {
  background: rgba(6, 9, 15, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(10px);
}

.panel-header h2 {
  margin: 0;
  font-size: 1.1rem;
}

.panel-header p {
  margin: 6px 0 0;
  color: rgba(240, 244, 250, 0.65);
  font-size: 0.9rem;
}

.palette {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(68px, 1fr));
  gap: 14px;
  min-height: 140px;
  align-items: center;
}

.palette.locked {
  opacity: 0.55;
  pointer-events: none;
}

.color-chip {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  overflow: hidden;
}

.color-chip:disabled {
  cursor: not-allowed;
}

.chip-core {
  position: absolute;
  inset: 14px;
  border-radius: 14px;
  background: var(--chip);
  box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.4);
}

.chip-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 30% 20%, rgba(255, 255, 255, 0.45), transparent 50%);
  opacity: 0.6;
}

.palette-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: rgba(240, 244, 250, 0.6);
  font-size: 0.9rem;
  padding: 12px;
}

.panel-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(240, 244, 250, 0.55);
  font-size: 0.85rem;
}

.panel-footer .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #49f5a1;
  box-shadow: 0 0 12px rgba(73, 245, 161, 0.8);
}

.error {
  margin: 0;
  color: #ff7a7a;
  font-size: 0.9rem;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(3, 5, 9, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 20;
  backdrop-filter: blur(8px);
}

.modal {
  background: rgba(8, 12, 20, 0.95);
  padding: 28px;
  border-radius: 16px;
  width: min(360px, 90vw);
  text-align: left;
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.45);
}

.modal h2 {
  margin: 0 0 8px;
}

.admin-form {
  margin-top: 10px;
}

.admin-pass-wrap {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin-top: 10px;
}

.admin-pass-wrap input {
  width: 100%;
  padding: 12px 14px;
  background: rgba(4, 6, 10, 0.8);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  font-size: 0.95rem;
}

.toggle-pass {
  height: 100%;
  min-width: 68px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(12, 17, 26, 0.9);
  color: #f6f7fb;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  width: 100%;
}

.modal-actions button {
  flex: 1;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(12, 17, 26, 0.9);
  color: #f6f7fb;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.2s ease;
}

.modal-actions .cancel {
  background: transparent;
}

@media (max-width: 900px) {
  .login-container {
    min-height: auto;
    align-items: flex-start;
    padding: calc(92px + env(safe-area-inset-top)) 5vw
      max(34px, env(safe-area-inset-bottom));
  }

  .hero {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .panel {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .admin-button {
    top: 12px;
    right: 12px;
    padding: 8px 12px;
    font-size: 0.72rem;
    letter-spacing: 0.4px;
  }

  .hero-copy {
    gap: 14px;
  }

  .hero-copy h1 {
    font-size: clamp(1.8rem, 9vw, 2.4rem);
    line-height: 1.1;
  }

  .lead {
    font-size: 0.95rem;
  }

  .stats {
    gap: 10px;
  }

  .stat {
    min-width: 0;
    flex: 1 1 130px;
    padding: 10px 12px;
  }

  .panel {
    padding: 18px;
    border-radius: 18px;
    gap: 14px;
  }

  .palette {
    grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
    gap: 10px;
    min-height: 0;
  }

  .color-chip {
    border-radius: 14px;
  }

  .chip-core {
    inset: 10px;
    border-radius: 10px;
  }

  .panel-footer {
    font-size: 0.8rem;
  }

  .modal {
    padding: 20px;
    width: min(360px, calc(100vw - 24px));
  }

}

@media (max-width: 420px) {
  .login-container {
    padding: calc(78px + env(safe-area-inset-top)) 4vw
      max(24px, env(safe-area-inset-bottom));
  }

  .eyebrow {
    font-size: 0.75rem;
    letter-spacing: 1.6px;
  }

  .panel-header h2 {
    font-size: 1rem;
  }

  .panel-header p {
    font-size: 0.82rem;
  }

  .modal-actions {
    flex-direction: column;
  }
}

@media (hover: hover) and (pointer: fine) {
  .admin-button:hover {
    transform: translateY(-1px);
    border-color: rgba(255, 255, 255, 0.5);
  }

  .color-chip:hover {
    transform: translateY(-4px);
    box-shadow: 0 18px 30px rgba(0, 0, 0, 0.4);
    border-color: rgba(255, 255, 255, 0.4);
  }

  .modal-actions button:hover {
    transform: translateY(-1px);
    border-color: rgba(255, 255, 255, 0.45);
  }
}

</style>
