<template>
  <div>
    <h2>Ubicación</h2>
    <button @click="obtenerUbicacion">Obtener ubicación</button>
    <p v-if="error" style="color:red">{{ error }}</p>
    <p v-if="success" style="color:green">{{ success }}</p>
  </div>
</template>

<script>
export default {
  name: "UbicationComponent",

  data() {
    return {
      error: null,
      success: null
    };
  },

  methods: {
    obtenerUbicacion() {
      this.error = null;
      this.success = null;

      if (!navigator.geolocation) {
        this.error = "Tu navegador no soporta Geolocalización";
        return;
      }

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          // Asegurarse de que los valores son números válidos
          const lat = Number(pos.coords.latitude);
          const lon = Number(pos.coords.longitude);
          const prec = Number(pos.coords.accuracy);

          if (isNaN(lat) || isNaN(lon) || isNaN(prec)) {
            this.error = "Error: coordenadas inválidas";
            return;
          }

          let bodyData;
          try {
            bodyData = JSON.stringify({ lat, lon, precision: prec });
          } catch (e) {
            this.error = "Error formateando JSON: " + e.message;
            return;
          }


          fetch("http://0.0.0.0:5001/ubicacion", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: bodyData
          })
          .then(() => {
            this.success = `Ubicación enviada correctamente ✔️\nLat: ${lat}, Lon: ${lon}, Precisión: ${prec}m`;
            alert(`Tu ubicación:\nLatitud: ${lat}\nLongitud: ${lon}\nPrecisión: ${prec} m`);
          })
          .catch(err => {
            this.error = "Error enviando al backend: " + err;
          });
        },
        (err) => {
          this.error = "Error obteniendo ubicación: " + err.message;
        }
      );
    }
  }
};
</script>

<style scoped>
button {
  padding: 8px 15px;
  font-size: 16px;
  cursor: pointer;
  margin-top: 10px;
}
h2 {
  color: #333;
}
</style>
