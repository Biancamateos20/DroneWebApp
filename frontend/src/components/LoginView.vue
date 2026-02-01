<template>
  <!-- BOTÓN ADMIN -->
  <button class="admin-button" type="button" @click="showAdmin = true">
    Administrador
  </button>

  <div class="login-container">
    <h1>Selecciona tu alias</h1>

    <div class="colors">
      <button
        v-for="color in visibleColors"
        :key="color"
        class="color-circle"
        type="button"
        :style="{ backgroundColor: color }"
        @pointerdown.prevent="onPickColor(color)"
        @touchstart.prevent="onPickColor(color)"
        @click.prevent="onPickColor(color)"
      ></button>

      <button
        v-if="!showAll && visibleColors.length > 5"
        class="color-circle plus"
        type="button"
        @pointerdown.prevent="showAll = true"
        @touchstart.prevent="showAll = true"
        @click.prevent="showAll = true"
      >+</button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
  </div>

  <!-- MODAL ADMIN -->
  <div v-if="showAdmin" class="modal-overlay">
    <div class="modal">
      <h2>Acceso Administrador</h2>

      <input v-model="adminPassword" type="password" placeholder="Contraseña" />

      <div class="modal-actions">
        <button type="button" @click="adminLogin">Entrar</button>
        <button type="button" class="cancel" @click="showAdmin = false">Cancelar</button>
      </div>

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
      showAll: false,
      error: null,

      showAdmin: false,
      adminPassword: '',
      adminError: null,

      colors: [
        '#1E90FF', '#FF0000', '#32CD32', '#FFD700',
        '#800080', '#FF1493', '#00CED1', '#FF8C00'
      ],
      coloresOcupados: [],

      picked: false,
      live: null
    }
  },

  computed: {
    visibleColors() {
      const libres = this.colors.filter(c => !this.coloresOcupados.includes(c))
      return this.showAll ? libres : libres.slice(0, 5)
    }
  },

  mounted() {
    // Conexión ligera para recibir occupancy
    this.live = new LiveWS()
    this.live.onMessage = (msg) => {
      if (msg?.type === 'occupancy' && Array.isArray(msg.aliases)) {
        this.coloresOcupados = msg.aliases
      }
      if (msg?.type === 'reset') {
        this.coloresOcupados = []
        this.picked = false
      }
    }
    this.live.connect({ role: 'player' })
  },

  beforeUnmount() {
    this.live?.disconnect()
  },

  methods: {
    onPickColor(color) {
      if (this.picked) return
      this.picked = true
      this.error = null

      // si en ese microsegundo se ocupó, evita elegirlo
      if (this.coloresOcupados.includes(color)) {
        this.error = 'Color ocupado, elige otro'
        this.picked = false
        return
      }

      this.$emit('login-success', { color })
    },

    adminLogin() {
      this.adminError = null
      if (this.adminPassword !== 'admin123') {
        this.adminError = 'Contraseña incorrecta'
        return
      }
      this.showAdmin = false
      this.$emit('admin-login')
    }
  }
}
</script>

<style scoped>
.admin-button {
  position: absolute;
  top: 20px;
  right: 20px;
  background: transparent;
  border: 1px solid #888;
  color: white;
  padding: 8px 14px;
  cursor: pointer;
  z-index: 10;
}

.login-container {
  height: 100vh;
  background: black;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: white;
}

.colors {
  display: grid;
  grid-template-columns: repeat(4, 60px);
  gap: 25px;
  margin-top: 30px;
}

.color-circle {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}

.plus {
  background: #444;
  color: white;
  font-size: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  justify-content: center;
  align-items: center;
}

.modal {
  background: #111;
  padding: 30px;
  border-radius: 8px;
  width: 300px;
  text-align: center;
}

.modal input {
  width: 100%;
  padding: 10px;
  margin-top: 15px;
  background: black;
  color: white;
  border: 1px solid #555;
}

.modal-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
}

.error {
  margin-top: 15px;
  color: red;
}
</style>
