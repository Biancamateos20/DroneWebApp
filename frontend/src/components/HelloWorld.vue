<script>
export default {
  name: 'HomeView',
  data() {
    return {
      mensaje: ''
    }
  },
  mounted() {
    fetch('http://127.0.0.1:5001/')
      .then(res => res.json())
      .then(data => this.mensaje = data.mensaje)
  }
}
</script>

<template>
  <div>
    <h1>{{ mensaje }}</h1>
  </div>
</template>
