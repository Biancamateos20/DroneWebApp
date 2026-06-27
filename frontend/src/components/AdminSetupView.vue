<template>
  <div class="setup-shell">
    <div class="setup-card">
      <div class="setup-header">
        <p class="setup-kicker">Administrador</p>
        <h1>Configura la partida antes de entrar</h1>
        <p class="setup-lead">
          El modo real mantiene el flujo actual con moviles. El modo simulacion prepara jugadores,
          posiciones y conexion del dron antes de abrir el panel.
        </p>
      </div>

      <section class="setup-panel">
        <label class="field">
          <span>Modo de partida</span>
          <select v-model="mode">
            <option value="real">Real</option>
            <option value="simulacion">Simulacion</option>
          </select>
        </label>

        <p v-if="mode === 'real'" class="note">
          Los jugadores entran desde sus moviles y eligen el color en la pantalla de login, igual que ahora.
        </p>
        <p v-else class="note">
          En simulacion eliges los colores aqui, colocas sus posiciones en el mapa y el dron trabajara en modo
          simulacion dentro del panel.
        </p>
      </section>

      <section v-if="mode === 'simulacion'" class="setup-grid">
        <div class="setup-panel">
          <h2>Jugadores simulados</h2>
          <p class="note">Anade hasta 4 colores y luego haz clic en el mapa para colocar a cada jugador.</p>

          <div class="palette">
            <button
              v-for="color in availableColors"
              :key="color"
              type="button"
              class="color-chip"
              :style="{ '--chip': color }"
              @click="addSimulationPlayer(color)"
            >
              <span class="chip-core"></span>
            </button>
          </div>

          <p v-if="!availableColors.length" class="note">
            Todos los colores disponibles ya estan dentro de la simulacion.
          </p>

          <div v-if="simulationPlayers.length" class="player-stack">
            <div
              v-for="player in simulationPlayers"
              :key="player.alias"
              class="player-card"
              :class="{ selected: placementTargetAlias === player.alias }"
            >
              <button type="button" class="player-main" @click="selectPlayerPlacement(player.alias)">
                <span class="player-dot" :style="{ backgroundColor: player.alias }"></span>
                <span class="player-name">{{ player.alias }}</span>
                <span class="player-coords">
                  {{ formatCoords(player.lat, player.lon) }}
                </span>
              </button>

              <button type="button" class="remove-btn" @click="removeSimulationPlayer(player.alias)">
                Quitar
              </button>
            </div>
          </div>
        </div>

        <div class="setup-panel">
          <h2>Mapa de simulacion</h2>

          <p class="note">
            Seleccion actual: {{ currentPlacementLabel }}. Haz clic en el mapa para fijar la ubicacion del jugador.
          </p>

          <div id="admin-setup-map" class="setup-map"></div>
        </div>
      </section>

      <div class="setup-actions">
        <button type="button" class="secondary-btn" @click="cancelAdminSetup">
          Volver
        </button>

        <button type="button" class="primary-btn" @click="startAdminPanel">
          Entrar al panel
        </button>
      </div>

      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script>
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

export default {
  name: 'AdminSetupView',
  emits: ['cancel-admin', 'start-admin'],

  data() {
    return {
      mode: 'real',
      error: null,
      map: null,
      mapReady: false,
      layerEsri: null,
      layerPnoaProvWms: null,
      mapCenter: {
        lat: 41.276425991728814,
        lon: 1.9886158678586885
      },
      playerMarkers: {},
      simulationPlayers: [],
      placementTargetAlias: null,
      colors: [
        '#1E90FF', '#FF0000', '#32CD32', '#FFD700',
        '#800080', '#FF1493', '#00CED1', '#FF8C00'
      ]
    }
  },

  computed: {
    normalizedColors() {
      return this.colors.map((color) => this.normalizeColor(color))
    },
    availableColors() {
      const used = new Set(this.simulationPlayers.map((player) => player.alias))
      return this.normalizedColors.filter((color) => !used.has(color))
    },
    currentPlacementLabel() {
      if (!this.placementTargetAlias) {
        return 'sin objetivo'
      }
      return `jugador ${this.placementTargetAlias}`
    }
  },

  watch: {
    mode(nextValue) {
      this.error = null
      if (nextValue === 'simulacion') {
        this.scheduleMapInit()
        return
      }
      this.destroyMap()
    }
  },

  mounted() {
    if (this.mode === 'simulacion') {
      this.scheduleMapInit()
    }
  },

  beforeUnmount() {
    try {
      this.destroyMap()
    } catch (e) {
      this.logEvent('error', 'Error cerrando el mapa del setup de admin', {
        error: e?.message || String(e)
      })
    }
  },

  methods: {
    logEvent(level, message, extra = null) {
      const entry = {
        ts: new Date().toISOString(),
        scope: 'AdminSetupView',
        level,
        message,
        extra
      }

      try {
        const raw = localStorage.getItem('dronewebapp_logs')
        const logs = raw ? JSON.parse(raw) : []
        logs.push(entry)
        localStorage.setItem('dronewebapp_logs', JSON.stringify(logs.slice(-400)))
      } catch (e) {
        console.warn('[AdminSetupView] No se pudo guardar el log en localStorage:', e)
      }

      if (level === 'error') {
        console.error('[AdminSetupView]', message, extra || '')
        return
      }

      if (level === 'warn') {
        console.warn('[AdminSetupView]', message, extra || '')
        return
      }

      console.log('[AdminSetupView]', message, extra || '')
    },

    destroyMap() {
      try {
        Object.keys(this.playerMarkers).forEach((alias) => {
          this.playerMarkers[alias]?.remove?.()
        })
        this.playerMarkers = {}

        if (this.map) {
          this.map.off('click', this.handleMapClick)
          this.map.remove()
          this.map = null
        }

        this.layerEsri = null
        this.layerPnoaProvWms = null
        this.mapReady = false
      } catch (e) {
        this.logEvent('error', 'Error destruyendo el mapa de simulacion', {
          error: e?.message || String(e)
        })
      }
    },

    scheduleMapInit() {
      this.$nextTick(() => {
        if (this.mode !== 'simulacion') return
        if (this.map) {
          this.map.invalidateSize(true)
          this.refreshMapMarkers()
          return
        }
        this.initMap()
      })
    },

    normalizeColor(value) {
      if (typeof value !== 'string') return ''
      return value.trim().toUpperCase()
    },

    formatCoords(lat, lon) {
      const latNum = Number(lat)
      const lonNum = Number(lon)
      if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) {
        return 'sin colocar'
      }
      return `${latNum.toFixed(6)}, ${lonNum.toFixed(6)}`
    },

    initMap() {
      try {
        if (this.mode !== 'simulacion') return
        this.createMap(this.mapCenter.lat, this.mapCenter.lon)
      } catch (e) {
        this.logEvent('error', 'Error iniciando el mapa de simulacion', {
          error: e?.message || String(e)
        })
        this.createMap(this.mapCenter.lat, this.mapCenter.lon)
      }
    },

    createMap(lat, lon) {
      try {
        if (this.mode !== 'simulacion') return
        const container = L.DomUtil.get('admin-setup-map')
        if (!container) {
          this.error = 'No se pudo crear el mapa de simulacion'
          this.logEvent('warn', 'Intento de crear el mapa sin contenedor visible')
          return
        }

        container._leaflet_id = null

        this.map = L.map('admin-setup-map', { maxZoom: 20 }).setView([lat, lon], 18)

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

        this.map.on('click', this.handleMapClick)
        this.$nextTick(() => this.map?.invalidateSize(true))
        this.mapReady = true
        this.refreshMapMarkers()
        this.logEvent('info', 'Mapa de simulacion preparado', { lat, lon })
      } catch (e) {
        this.error = 'No se pudo crear el mapa de simulacion'
        this.logEvent('error', 'Error creando el mapa de simulacion', {
          error: e?.message || String(e)
        })
      }
    },

    handleMapClick(event) {
      try {
        this.error = null
        const lat = Number(event?.latlng?.lat)
        const lon = Number(event?.latlng?.lng)

        if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
          this.error = 'No se pudo leer la posicion del mapa'
          return
        }

        if (!this.placementTargetAlias) {
          this.error = 'Selecciona un jugador antes de colocarlo'
          return
        }

        this.setPlayerPosition(this.placementTargetAlias, lat, lon)
      } catch (e) {
        this.error = 'Error colocando la posicion en el mapa'
        this.logEvent('error', 'Error procesando el clic del mapa de simulacion', {
          error: e?.message || String(e)
        })
      }
    },

    addSimulationPlayer(color) {
      try {
        if (this.simulationPlayers.length >= 4) {
          this.error = 'La simulacion esta limitada a 4 jugadores'
          return
        }

        const alias = this.normalizeColor(color)
        if (!alias) return
        if (this.simulationPlayers.some((player) => player.alias === alias)) return

        this.simulationPlayers.push({
          alias,
          lat: null,
          lon: null,
          precision: 1
        })
        this.placementTargetAlias = alias
        this.refreshMapMarkers()
        this.logEvent('info', 'Jugador simulado anadido', { alias })
      } catch (e) {
        this.error = 'No se pudo anadir el jugador simulado'
        this.logEvent('error', 'Error anadiendo jugador simulado', {
          error: e?.message || String(e),
          color
        })
      }
    },

    removeSimulationPlayer(alias) {
      try {
        const normalized = this.normalizeColor(alias)
        this.simulationPlayers = this.simulationPlayers.filter((player) => player.alias !== normalized)

        const marker = this.playerMarkers[normalized]
        if (marker) {
          marker.remove()
          delete this.playerMarkers[normalized]
        }

        if (this.placementTargetAlias === normalized) {
          this.placementTargetAlias = null
        }

        this.refreshMapMarkers()
        this.logEvent('info', 'Jugador simulado eliminado', { alias: normalized })
      } catch (e) {
        this.error = 'No se pudo quitar el jugador simulado'
        this.logEvent('error', 'Error quitando jugador simulado', {
          error: e?.message || String(e),
          alias
        })
      }
    },

    selectPlayerPlacement(alias) {
      try {
        this.placementTargetAlias = this.normalizeColor(alias)
        this.logEvent('info', 'Jugador seleccionado para colocar en mapa', {
          alias: this.placementTargetAlias
        })
      } catch (e) {
        this.logEvent('error', 'Error seleccionando jugador para el mapa', {
          error: e?.message || String(e),
          alias
        })
      }
    },

    setPlayerPosition(alias, lat, lon) {
      try {
        const normalized = this.normalizeColor(alias)
        this.simulationPlayers = this.simulationPlayers.map((player) => {
          if (player.alias !== normalized) {
            return player
          }

          return {
            ...player,
            lat: Number(lat.toFixed(7)),
            lon: Number(lon.toFixed(7)),
            precision: 1
          }
        })

        this.refreshMapMarkers()
        this.logEvent('info', 'Posicion simulada de jugador actualizada', {
          alias: normalized,
          lat,
          lon
        })
      } catch (e) {
        this.error = 'No se pudo colocar el jugador seleccionado'
        this.logEvent('error', 'Error asignando posicion a jugador simulado', {
          error: e?.message || String(e),
          alias
        })
      }
    },

    refreshMapMarkers() {
      try {
        if (!this.mapReady || !this.map) return

        this.simulationPlayers.forEach((player) => {
          const lat = Number(player.lat)
          const lon = Number(player.lon)
          const alias = player.alias
          const hasCoords = Number.isFinite(lat) && Number.isFinite(lon)

          if (!hasCoords) {
            if (this.playerMarkers[alias]) {
              this.playerMarkers[alias].remove()
              delete this.playerMarkers[alias]
            }
            return
          }

          if (!this.playerMarkers[alias]) {
            this.playerMarkers[alias] = L.circleMarker([lat, lon], {
              radius: 8,
              weight: 2,
              color: '#ffffff',
              fillColor: alias,
              fillOpacity: 0.95
            }).addTo(this.map)
          }

          this.playerMarkers[alias].setLatLng([lat, lon])
          this.playerMarkers[alias].bindPopup(`Jugador ${alias}`)
        })

        Object.keys(this.playerMarkers).forEach((alias) => {
          const stillExists = this.simulationPlayers.some((player) => player.alias === alias)
          if (stillExists) return
          this.playerMarkers[alias].remove()
          delete this.playerMarkers[alias]
        })
      } catch (e) {
        this.logEvent('error', 'Error refrescando los marcadores del setup', {
          error: e?.message || String(e)
        })
      }
    },

    cancelAdminSetup() {
      try {
        this.logEvent('info', 'Salida del setup de admin sin entrar al panel')
        this.$emit('cancel-admin')
      } catch (e) {
        this.logEvent('error', 'Error cancelando el setup de admin', {
          error: e?.message || String(e)
        })
      }
    },

    startAdminPanel() {
      try {
        this.error = null

        if (this.mode === 'real') {
          this.logEvent('info', 'Entrada al panel de admin en modo real')
          this.$emit('start-admin', {
            mode: 'real',
            simulationConfig: null
          })
          return
        }

        if (!this.simulationPlayers.length) {
          this.error = 'Anade al menos un jugador para la simulacion'
          return
        }

        const playersWithoutPosition = this.simulationPlayers.filter((player) => {
          const lat = Number(player.lat)
          const lon = Number(player.lon)
          return !Number.isFinite(lat) || !Number.isFinite(lon)
        })

        if (playersWithoutPosition.length) {
          this.error = 'Todos los jugadores simulados deben tener una posicion en el mapa'
          return
        }

        const payload = {
          mode: 'simulacion',
          simulationConfig: {
            players: this.simulationPlayers.map((player) => ({
              alias: player.alias,
              lat: Number(player.lat),
              lon: Number(player.lon),
              precision: Number(player.precision) || 1
            }))
          }
        }

        this.logEvent('info', 'Entrada al panel de admin en modo simulacion', payload.simulationConfig)
        this.$emit('start-admin', payload)
      } catch (e) {
        this.error = 'No se pudo abrir el panel de administracion'
        this.logEvent('error', 'Error finalizando el setup del admin', {
          error: e?.message || String(e)
        })
      }
    }
  }
}
</script>

<style scoped>
.setup-shell {
  min-height: 100vh;
  min-height: 100svh;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(0, 229, 255, 0.18), transparent 28%),
    radial-gradient(circle at bottom right, rgba(255, 140, 0, 0.18), transparent 30%),
    #05080d;
  color: #f5f7fb;
  box-sizing: border-box;
}

.setup-card {
  max-width: 1240px;
  margin: 0 auto;
  display: grid;
  gap: 18px;
}

.setup-header,
.setup-panel {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(7, 12, 20, 0.84);
  backdrop-filter: blur(18px);
  border-radius: 22px;
  padding: 22px;
}

.setup-kicker {
  margin: 0 0 10px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.78rem;
  color: #7dd3fc;
}

.setup-header h1,
.setup-panel h2 {
  margin: 0 0 10px;
}

.setup-lead,
.note {
  margin: 0;
  color: rgba(235, 241, 255, 0.75);
  line-height: 1.5;
}

.setup-grid {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 18px;
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  font-size: 0.92rem;
  color: rgba(235, 241, 255, 0.85);
}

.field select {
  border: 1px solid rgba(125, 211, 252, 0.24);
  border-radius: 14px;
  background: rgba(12, 18, 30, 0.9);
  color: #f5f7fb;
  padding: 12px 14px;
  font-size: 1rem;
}

.palette {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0 14px;
}

.color-chip {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.03);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.chip-core {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--chip);
  box-shadow: 0 0 18px var(--chip);
}

.player-stack {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.player-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  padding: 10px;
}

.player-card.selected {
  border-color: rgba(125, 211, 252, 0.58);
  box-shadow: 0 0 0 1px rgba(125, 211, 252, 0.18);
}

.player-main {
  border: 0;
  background: transparent;
  color: inherit;
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  text-align: left;
  cursor: pointer;
}

.player-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.86);
}

.player-name {
  font-weight: 700;
}

.player-coords {
  color: rgba(235, 241, 255, 0.7);
  font-size: 0.9rem;
}

.remove-btn,
.ghost-btn,
.secondary-btn,
.primary-btn {
  border: 0;
  border-radius: 14px;
  cursor: pointer;
  font-weight: 700;
  padding: 11px 15px;
}

.remove-btn,
.ghost-btn,
.secondary-btn {
  background: rgba(255, 255, 255, 0.08);
  color: #f5f7fb;
}

.ghost-btn.active {
  background: rgba(0, 229, 255, 0.18);
  color: #a5f3fc;
}

.primary-btn {
  background: linear-gradient(135deg, #00bcd4, #0ea5e9);
  color: #03131a;
}

.map-actions,
.setup-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.setup-map {
  height: 440px;
  margin-top: 14px;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.error {
  margin: 0;
  color: #fca5a5;
  font-weight: 600;
}

@media (max-width: 960px) {
  .setup-shell {
    padding: 16px;
  }

  .setup-grid {
    grid-template-columns: 1fr;
  }

  .setup-map {
    height: 360px;
  }
}
</style>
