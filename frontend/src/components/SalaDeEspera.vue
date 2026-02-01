<template>
  <div class="login-container">
    <h1>Esperando a los demás participantes</h1>
    <div class="spinner"></div>
    <p class="hint">El administrador iniciará la partida y entrarás automáticamente.</p>
  </div>
</template>

<script>
export default {
  name: 'SalaDeEspera',
  props: { alias: { type: String, required: true } }
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
</style>
