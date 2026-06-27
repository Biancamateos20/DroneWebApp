<template>
  <div class="sim-room-shell">
    <header class="sim-room-header">
      <div>
        <p class="eyebrow">Modo Simulacion</p>
        <h1>4 pantallas de jugadores</h1>
        <p class="subtitle">
          Cada bloque carga la vista de un jugador simulado con su propio alias.
        </p>
      </div>

      <button
        v-if="maximizedAlias"
        type="button"
        class="sim-room-toolbar-btn"
        @click="showAllPlayers"
      >
        Ver todas
      </button>
    </header>

    <section class="sim-room-grid" :class="{ single: isSingleView }">
      <article
        v-for="player in renderedPlayers"
        :key="player.alias"
        class="sim-room-card"
        :class="{ maximized: maximizedAlias === player.alias }"
      >
        <div class="sim-room-card-head">
          <div class="sim-room-title-wrap">
            <span class="sim-room-dot" :style="{ backgroundColor: player.alias }"></span>
            <div>
              <h2>{{ player.alias }}</h2>
              <p>{{ formatCoords(player.lat, player.lon) }}</p>
            </div>
          </div>

          <button
            type="button"
            class="sim-room-card-btn"
            @click="togglePlayerSize(player.alias)"
          >
            {{ maximizedAlias === player.alias ? 'Ver todas' : 'Maximizar' }}
          </button>
        </div>

        <iframe
          class="sim-room-frame"
          :src="getPlayerFrameUrl(player.alias)"
          :title="`Vista simulada ${player.alias}`"
        ></iframe>
      </article>
    </section>
  </div>
</template>

<script>
export default {
  name: 'SimulationPlayersView',
  props: {
    players: {
      type: Array,
      default: () => []
    }
  },

  data() {
    return {
      maximizedAlias: null
    }
  },

  computed: {
    visiblePlayers() {
      return this.players.slice(0, 4)
    },
    renderedPlayers() {
      if (!this.maximizedAlias) return this.visiblePlayers
      return this.visiblePlayers.filter((player) => player.alias === this.maximizedAlias)
    },
    isSingleView() {
      return !!this.maximizedAlias
    }
  },

  methods: {
    togglePlayerSize(alias) {
      const normalizedAlias = String(alias || '').trim().toUpperCase()
      if (!normalizedAlias) return
      if (this.maximizedAlias === normalizedAlias) {
        this.maximizedAlias = null
        return
      }
      this.maximizedAlias = normalizedAlias
    },

    showAllPlayers() {
      this.maximizedAlias = null
    },

    getPlayerFrameUrl(alias) {
      const url = new URL(window.location.href)
      url.search = ''
      url.searchParams.set('sim-player', '1')
      url.searchParams.set('alias', String(alias || '').trim().toUpperCase())
      return url.toString()
    },

    formatCoords(lat, lon) {
      const latNum = Number(lat)
      const lonNum = Number(lon)
      if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) {
        return 'Sin ubicacion'
      }
      return `${latNum.toFixed(6)}, ${lonNum.toFixed(6)}`
    }
  }
}
</script>

<style scoped>
.sim-room-shell {
  min-height: 100vh;
  min-height: 100svh;
  background:
    radial-gradient(circle at top left, rgba(0, 229, 255, 0.14), transparent 26%),
    radial-gradient(circle at bottom right, rgba(255, 140, 0, 0.14), transparent 26%),
    #03060a;
  padding: 20px;
  box-sizing: border-box;
  color: #eef2f7;
}

.sim-room-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.76rem;
  color: #7dd3fc;
}

.sim-room-header h1 {
  margin: 0;
  font-size: clamp(2rem, 3vw, 3rem);
}

.subtitle {
  margin: 8px 0 0;
  color: rgba(238, 242, 247, 0.72);
}

.sim-room-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.sim-room-grid.single {
  grid-template-columns: 1fr;
}

.sim-room-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  min-height: 46vh;
  padding: 14px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(6, 10, 16, 0.92);
}

.sim-room-card.maximized {
  min-height: calc(100vh - 120px);
}

.sim-room-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.sim-room-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sim-room-title-wrap h2 {
  margin: 0;
  font-size: 1rem;
}

.sim-room-title-wrap p {
  margin: 4px 0 0;
  font-size: 0.86rem;
  color: rgba(238, 242, 247, 0.62);
}

.sim-room-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.92);
}

.sim-room-toolbar-btn,
.sim-room-card-btn {
  border: 0;
  border-radius: 14px;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 700;
  background: rgba(125, 211, 252, 0.14);
  color: #d9f7ff;
}

.sim-room-frame {
  width: 100%;
  min-height: 100%;
  border: 0;
  border-radius: 18px;
  background: #000;
}

@media (max-width: 1024px) {
  .sim-room-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .sim-room-grid {
    grid-template-columns: 1fr;
  }

  .sim-room-card {
    min-height: 70vh;
  }
}
</style>
